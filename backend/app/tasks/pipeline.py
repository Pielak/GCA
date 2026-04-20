"""MVP 13 Fase 13.3a — tasks Celery do pipeline de ingestão.

Primeiro ponto de migração asyncio → Celery. Escopo mínimo: envelopa
`IngestionService._analyze_async` numa task Celery chamada
`pipeline_ingest_task`, mantendo a assinatura semântica original.

A task:
- Recebe apenas IDs + metadados leves (bytes vão pelo storage, não
  pelo broker — evita encher Redis com payload pesado).
- Abre nova AsyncSession dedicada (worker roda em processo separado
  do backend).
- Lê bytes do storage path gravado no `IngestedDocument`.
- Invoca `_analyze_async` via `asyncio.run` (Celery task é sync).
- Retry bounded: max_retries=2, exponencial + jitter.

Outros pontos de `asyncio.create_task` no pipeline seguem cobertos
por 13.3b/c ou pelo watchdog DT-073 até lá.
"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine
from uuid import UUID

import structlog

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_coro_isolated(coro: Coroutine[Any, Any, Any]) -> Any:
    """Roda corrotina num event loop isolado.

    Substitui `asyncio.run()` que falha em eager mode (pytest-asyncio)
    quando já há loop rodando. Em worker Celery de verdade (processo
    separado sem loop), funciona igual a `asyncio.run()`.
    """
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except RuntimeError:
        # Fallback extremo: se mesmo new_event_loop falhar, tenta o
        # loop atual (caminho pytest-asyncio com loop em execução).
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)


@celery_app.task(
    name="app.tasks.pipeline.pipeline_ingest_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def pipeline_ingest_task(self, document_id: str, project_id: str, file_type: str) -> dict:
    """Roda `IngestionService._analyze_async` como task Celery.

    Args:
        document_id: UUID str do IngestedDocument.
        project_id: UUID str do projeto dono.
        file_type: MIME type ou sufixo já normalizado pelo upload.

    Returns:
        dict com {status, document_id, duration_ms} para result backend.

    Raises:
        Reraise com `self.retry()` quando falha de infra (I/O, DB).
        Exceptions do domínio (análise inválida, quarentena) são
        registradas no arguider_status do doc e NÃO disparam retry —
        já são tratadas por `_analyze_async` via status='error'.
    """
    import time
    t0 = time.time()

    try:
        _run_coro_isolated(_run_analyze_async(document_id, project_id, file_type))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "pipeline_ingest_task.failed",
            document_id=document_id,
            project_id=project_id,
            retries_remaining=self.max_retries - self.request.retries,
            error=str(exc),
        )
        # Retry apenas infra (task levanta); erros de domínio já foram
        # gravados no doc como arguider_status='error' dentro do
        # _analyze_async e NÃO levantam daqui.
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)

    return {
        "status": "ok",
        "document_id": document_id,
        "duration_ms": int((time.time() - t0) * 1000),
    }


async def _run_analyze_async(document_id: str, project_id: str, file_type: str) -> None:
    """Wrapper assíncrono: abre session, carrega bytes, chama service.

    Isolado pra permitir `asyncio.run()` limpo dentro da task Celery.
    """
    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.models.base import IngestedDocument
    from app.services.ingestion_service import IngestionService

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(IngestedDocument).where(IngestedDocument.id == UUID(document_id))
        )
        doc = res.scalar_one_or_none()
        if not doc:
            logger.warning("pipeline_ingest_task.doc_not_found", document_id=document_id)
            return

        # Lê bytes do storage (upload_document persistiu via write_ingested).
        # Storage helper usa project_id + filename (o UUID-prefixed do upload).
        from app.utils.ingested_storage import read_ingested
        file_bytes = read_ingested(UUID(project_id), doc.filename)
        if file_bytes is None:
            logger.warning(
                "pipeline_ingest_task.storage_missing",
                document_id=document_id,
                filename=doc.filename,
            )
            doc.arguider_status = "error"
            doc.arguider_error_message = f"storage não encontrado: {doc.filename}"
            await db.commit()
            return

        svc = IngestionService(db)
        await svc._analyze_async(
            UUID(document_id),
            UUID(project_id),
            file_bytes,
            file_type or doc.file_type,
        )


# ─── Fase 13.3b: propagate / regenerate_backlog / reevaluate_gatekeeper ──


@celery_app.task(
    name="app.tasks.pipeline.propagate_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def propagate_task(self, project_id: str, changes: list, ocg_version) -> dict:
    """Propaga mudanças do OCG (backlog/codegen/livedocs) via Celery.

    Substitui `asyncio.create_task(_propagate_async(...))` em
    ingestion_service (linhas 247 e 1327 pré-13.3b).
    """
    try:
        _run_coro_isolated(_run_propagate(project_id, changes, ocg_version))
    except Exception as exc:  # noqa: BLE001
        logger.error("propagate_task.failed", project_id=project_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "project_id": project_id}


async def _run_propagate(project_id: str, changes: list, ocg_version) -> None:
    from app.services.ingestion_service import _propagate_async
    await _propagate_async(
        project_id=UUID(project_id),
        changes=changes,
        ocg_version=ocg_version,
    )


@celery_app.task(
    name="app.tasks.pipeline.regenerate_backlog_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def regenerate_backlog_task(self, project_id: str, ocg_version, trigger: str) -> dict:
    """Regenera backlog a partir do OCG atual. Substitui
    `asyncio.create_task(_regenerate_backlog_async(...))` em
    ingestion_service linha 255 pré-13.3b.
    """
    try:
        _run_coro_isolated(_run_regenerate_backlog(project_id, ocg_version, trigger))
    except Exception as exc:  # noqa: BLE001
        logger.error("regenerate_backlog_task.failed", project_id=project_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "project_id": project_id}


async def _run_regenerate_backlog(project_id: str, ocg_version, trigger: str) -> None:
    from app.services.ingestion_service import _regenerate_backlog_async
    await _regenerate_backlog_async(
        project_id=UUID(project_id),
        ocg_version=ocg_version,
        trigger=trigger,
    )


@celery_app.task(
    name="app.tasks.pipeline.reevaluate_gatekeeper_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def reevaluate_gatekeeper_task(self, project_id: str, ocg_version, trigger: str) -> dict:
    """Reavalia Gatekeeper pós-OCG. Substitui
    `asyncio.create_task(_reevaluate_gatekeeper_async(...))` em
    ingestion_service linhas 263 e 1338 pré-13.3b.
    """
    try:
        _run_coro_isolated(_run_reevaluate_gatekeeper(project_id, ocg_version, trigger))
    except Exception as exc:  # noqa: BLE001
        logger.error("reevaluate_gatekeeper_task.failed", project_id=project_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "project_id": project_id}


async def _run_reevaluate_gatekeeper(project_id: str, ocg_version, trigger: str) -> None:
    from app.services.ingestion_service import _reevaluate_gatekeeper_async
    await _reevaluate_gatekeeper_async(
        project_id=UUID(project_id),
        ocg_version=ocg_version,
        trigger=trigger,
    )


# ─── Fase 13.3c: auto_generate (OCG updater) + external_repos fallback ──


@celery_app.task(
    name="app.tasks.pipeline.auto_generate_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def auto_generate_task(self, project_id: str, updated_ocg: dict) -> dict:
    """Dispara generators de deliverables pós-OCG update.

    Substitui `asyncio.create_task(_auto_generate_in_background(...))`
    em ocg_updater_service linha 369 pré-13.3c. O payload `updated_ocg`
    pode ser grande mas é serializável JSON — trafega OK pelo broker.
    Se tamanho virar gargalo, migrar pra fetch no DB via project_id.
    """
    try:
        _run_coro_isolated(_run_auto_generate(project_id, updated_ocg))
    except Exception as exc:  # noqa: BLE001
        logger.error("auto_generate_task.failed", project_id=project_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "project_id": project_id}


async def _run_auto_generate(project_id: str, updated_ocg: dict) -> None:
    from app.services.ocg_updater_service import _auto_generate_in_background
    await _auto_generate_in_background(UUID(project_id), updated_ocg)


@celery_app.task(
    name="app.tasks.pipeline.external_repo_fallback_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def external_repo_fallback_task(self, project_id: str, repo_id: str) -> dict:
    """Análise direta de repo externo quando n8n falha.

    Substitui os 2 `asyncio.create_task(_run_analysis_fallback(...))`
    em external_repos_router (linhas 199 e 205 pré-13.3c). Retry mais
    conservador (60s) — repo clone + análise leva minutos.
    """
    try:
        _run_coro_isolated(_run_external_fallback(project_id, repo_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("external_repo_fallback_task.failed", repo_id=repo_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60 + 60 * self.request.retries)
    return {"status": "ok", "repo_id": repo_id}


async def _run_external_fallback(project_id: str, repo_id: str) -> None:
    from app.routers.external_repos_router import _run_analysis_fallback
    await _run_analysis_fallback(UUID(project_id), UUID(repo_id))
