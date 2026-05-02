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


# MVP 29 Fase 29.3 — Lease helper canônico para idempotência de tasks
# de propagação. `SET NX EX` no Redis: a primeira task que chega claima
# a chave por `ttl_seconds` e corre; outra task com mesma chave dentro
# do TTL encontra a chave existente e skipa silenciosamente.
#
# Uso: assinatura canônica = f"gca:task:{task_name}:{project_id}:{version}".
# Quando OCG ainda não tem versão, usa "none" como sentinel — lease curto
# garante que a task rode pelo menos uma vez por reboot.


_LEASE_TTL_SECONDS = 600  # 10 min — janela conservadora pra tasks de propagação


# MVP 29.1 — Idempotência guards para tasks críticas
def _check_document_already_analyzed(document_id: str, project_id: str) -> bool:
    """Retorna True se documento já foi analisado (status != 'processing').

    Garante que task redistribuída não roda 2x. Check simples: se
    arguider_status não é 'processing', assume que processamento já
    completou (sucesso ou erro de domínio — ambos são finais).

    MVP 29.1: Guard de idempotência crítica pra pipeline_ingest_task.
    Falha silenciosa (retorna False) se DB inacessível — fail-open.
    """
    try:
        import asyncio
        from sqlalchemy import select
        from app.db.database import AsyncSessionLocal
        from app.models.base import IngestedDocument

        async def _check():
            async with AsyncSessionLocal() as session:
                stmt = select(IngestedDocument).where(
                    (IngestedDocument.id == UUID(document_id))
                    & (IngestedDocument.project_id == UUID(project_id))
                )
                return await session.scalar(stmt)

        doc = asyncio.get_event_loop().run_until_complete(_check())
        if not doc:
            logger.warning(
                "pipeline_ingest.document_not_found",
                document_id=document_id,
                project_id=project_id,
            )
            return False
        is_analyzed = doc.arguider_status in ("completed", "error", "failed")
        if is_analyzed:
            logger.info(
                "pipeline_ingest.document_status",
                document_id=document_id,
                status=doc.arguider_status,
            )
        return is_analyzed
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pipeline_ingest.idempotency_check_failed",
            document_id=document_id,
            error=str(exc)[:100],
        )
        return False  # fail-open: melhor rodar 2x que não rodar


def _try_claim_task_lease(key: str, ttl_seconds: int = _LEASE_TTL_SECONDS) -> bool:
    """Retorna True se esta execução claimou o slot; False se outra já
    claimou nos últimos `ttl_seconds`. Nunca levanta — se o Redis estiver
    inacessível, devolve True (fail-open: melhor rodar duas vezes que
    travar o pipeline).
    """
    try:
        import redis  # importado lazy pra manter a task leve em startup
        from app.celery_app import _resolve_broker_url
        client = redis.Redis.from_url(_resolve_broker_url(), decode_responses=True)
        acquired = client.set(key, "1", nx=True, ex=ttl_seconds)
        if not acquired:
            logger.info("task.lease_already_claimed", key=key)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        # Fail-open: não travamos o pipeline por falha de lease.
        logger.warning("task.lease_check_failed", key=key, error=str(exc)[:200])
        return True


def _lease_key(task_name: str, project_id: str, version: Any) -> str:
    """Chave canônica. `version` pode ser int ou None."""
    v = str(version) if version is not None else "none"
    return f"gca:task:{task_name}:{project_id}:{v}"


@celery_app.task(
    name="app.tasks.pipeline.watchdog_ingestion_zombies",
    bind=True,
)
def watchdog_ingestion_zombies(self, threshold_minutes: int = 8) -> dict:
    """Task periódica do Celery beat: marca docs zombie como 'error'.

    Sem essa task o watchdog só rodava no startup do backend (lifespan),
    e docs presos em status='processing' ficavam zombie até o próximo
    restart. Agora é checado a cada 5 min independentemente.

    Returns: {checked, recovered, threshold_minutes}
    """
    from app.services.ingestion_watchdog import recover_zombie_documents
    try:
        result = _run_coro_isolated(recover_zombie_documents(threshold_minutes=threshold_minutes))
        if result.get("recovered"):
            logger.warning(
                "watchdog.recovered",
                recovered=result["recovered"],
                checked=result["checked"],
                threshold_minutes=threshold_minutes,
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog.failed", error=str(exc), exc_info=True)
        return {"status": "error", "error": str(exc)[:500]}


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

    MVP 29.1 Hardening: Idempotência por document_id. Se task é redistribuída
    após worker death, check inicial garante que não processa 2x.
    MVP 29.4: Observabilidade — metrics de idempotent skips.
    """
    import time
    t0 = time.time()

    # MVP 29.1 — Idempotência guard: check se doc já foi processado
    if _check_document_already_analyzed(document_id, project_id):
        from app.metrics import on_idempotent_skip
        on_idempotent_skip("pipeline_ingest_task", project_id, "document_already_analyzed")

        logger.info(
            "pipeline_ingest_task.idempotent_skip",
            document_id=document_id,
            project_id=project_id,
            reason="document_already_analyzed",
        )
        return {
            "status": "ok_idempotent",
            "document_id": document_id,
            "duration_ms": 0,
        }

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


async def _enqueue_next_pending_document(project_id: UUID, db) -> None:
    """Enfileira o próximo documento pending do projeto (processamento sequencial).

    MVP X — Estratégia: processa 1 doc por vez para reduzir tokens + alucinação.
    Quando um doc termina, esse callback enfileira o próximo automaticamente.
    """
    from sqlalchemy import select, and_
    from app.models.base import IngestedDocument

    # Buscar próximo doc pending (não processing) do mesmo projeto
    res = await db.execute(
        select(IngestedDocument).where(
            and_(
                IngestedDocument.project_id == project_id,
                IngestedDocument.arguider_status == "pending",
            )
        ).order_by(IngestedDocument.created_at.asc()).limit(1)
    )
    next_doc = res.scalar_one_or_none()

    if next_doc:
        try:
            pipeline_ingest_task.delay(
                str(next_doc.id), str(project_id), next_doc.file_type or ""
            )
            logger.info(
                "ingestion.next_document_enqueued",
                document_id=str(next_doc.id),
                project_id=str(project_id),
                position="next_sequential",
            )
        except Exception as exc:
            logger.error(
                "ingestion.next_enqueue_failed",
                document_id=str(next_doc.id),
                project_id=str(project_id),
                error=str(exc),
            )


async def _run_analyze_async(document_id: str, project_id: str, file_type: str) -> None:
    """Wrapper assíncrono: abre session, carrega bytes, chama service.

    Isolado pra permitir `asyncio.run()` limpo dentro da task Celery.

    MVP 29 Fase 29.2 — guard de idempotência: se o doc já está
    `arguider_status='completed'`, skip silencioso. Essencial quando
    `acks_late=True` faz o broker redistribuir a task após worker morto
    que havia concluído a análise mas não conseguiu ACKar.
    """
    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.models.base import IngestedDocument
    from app.services.ingestion_service import IngestionService

    async with AsyncSessionLocal() as db:
        try:
            res = await db.execute(
                select(IngestedDocument).where(IngestedDocument.id == UUID(document_id))
            )
            doc = res.scalar_one_or_none()
            if not doc:
                logger.warning("pipeline_ingest_task.doc_not_found", document_id=document_id)
                return

            if doc.arguider_status == "completed":
                logger.info(
                    "pipeline_ingest_task.skip_already_completed",
                    document_id=document_id,
                )
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

            # MVP X — Enfileira próximo documento do mesmo projeto (processamento sequencial)
            # Reduz tokens + alucinação ao processar 1 doc por vez
            await _enqueue_next_pending_document(UUID(project_id), db)

        except Exception as exc:
            logger.error(
                "pipeline_ingest_task.analyze_failed",
                document_id=document_id,
                project_id=project_id,
                error=str(exc),
                exc_info=True,
            )
            # Marcar documento como erro para não ficar travado
            res = await db.execute(
                select(IngestedDocument).where(IngestedDocument.id == UUID(document_id))
            )
            doc = res.scalar_one_or_none()
            if doc:
                doc.arguider_status = "error"
                doc.arguider_error_message = f"Análise falhou: {str(exc)[:500]}"
                doc.arguider_stage = "failed"
                await db.commit()
            raise


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

    MVP 29.2: Lease-based dedup pra evitar rodadas duplas após worker death.
    """
    # MVP 29.2 — Idempotência lease-based
    # MVP 29.4 — Observabilidade de skips
    lease_key = _lease_key("propagate", project_id, ocg_version)
    if not _try_claim_task_lease(lease_key, ttl_seconds=600):
        from app.metrics import on_idempotent_skip
        on_idempotent_skip("propagate_task", project_id, "lease_already_claimed")

        logger.info(
            "propagate_task.idempotent_skip",
            project_id=project_id,
            ocg_version=ocg_version,
            reason="lease_already_claimed",
        )
        return {
            "status": "ok_idempotent",
            "project_id": project_id,
            "reason": "another_execution_in_progress",
        }

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

    MVP 29.2: Lease-based dedup pra evitar rodadas duplas após worker death.
    """
    # MVP 29.2 — Idempotência lease-based
    # MVP 29.4 — Observabilidade de skips
    lease_key = _lease_key("regenerate_backlog", project_id, ocg_version)
    if not _try_claim_task_lease(lease_key, ttl_seconds=600):
        from app.metrics import on_idempotent_skip
        on_idempotent_skip("regenerate_backlog_task", project_id, "lease_already_claimed")

        logger.info(
            "regenerate_backlog_task.idempotent_skip",
            project_id=project_id,
            ocg_version=ocg_version,
            trigger=trigger,
            reason="lease_already_claimed",
        )
        return {
            "status": "ok_idempotent",
            "project_id": project_id,
            "reason": "another_execution_in_progress",
        }

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

    MVP 29.2: Lease-based dedup pra evitar rodadas duplas após worker death.
    """
    # MVP 29.2 — Idempotência lease-based
    # MVP 29.4 — Observabilidade de skips
    # Usa ocg_version do payload ou timestamp/hash como fallback
    ocg_version = updated_ocg.get("version") or updated_ocg.get("updated_at")
    lease_key = _lease_key("auto_generate", project_id, ocg_version)
    if not _try_claim_task_lease(lease_key, ttl_seconds=600):
        from app.metrics import on_idempotent_skip
        on_idempotent_skip("auto_generate_task", project_id, "lease_already_claimed")

        logger.info(
            "auto_generate_task.idempotent_skip",
            project_id=project_id,
            ocg_version=ocg_version,
            reason="lease_already_claimed",
        )
        return {
            "status": "ok_idempotent",
            "project_id": project_id,
            "reason": "another_execution_in_progress",
        }

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


# ─── MVP 24 Fase 24.4 — Cascateamento pós-questionário técnico ────────


@celery_app.task(
    name="app.tasks.pipeline.propagate_questionnaire_impact_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def propagate_questionnaire_impact_task(
    self, project_id: str, report: dict,
) -> dict:
    """Cascateamento ativo pós-aplicação de questionário técnico.

    Gatilho: `apply_parsed_responses` ao fim. Uma vez disparado, encadeia
    propagação → backlog → Gatekeeper de forma incondicional (ativo/passivo
    canônico: passivo no gatilho, ativo na execução).

    `report` é o dict retornado pelo aplicador:
      {applied, skipped_blank, skipped_not_found, resolved_codes[],
       info_debt_promoted[], complements_document_id?}
    """
    try:
        _run_coro_isolated(_run_propagate_questionnaire(project_id, report))
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "propagate_questionnaire_impact.failed",
            project_id=project_id, error=str(exc),
        )
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "project_id": project_id, "report": report}


async def _run_propagate_questionnaire(project_id: str, report: dict) -> None:
    """Encadeia propagação + backlog + gatekeeper.

    Ordem canônica:
      1. PropagationService.propagate — regenera backlog e emite BACKLOG_REGENERATED
      2. _reevaluate_gatekeeper_async — recalcula aprovação/bloqueios

    Não dispara LLM, não toca OCG diretamente — a mudança já foi feita
    no GatekeeperItem.status=resolved pelo aplicador. Aqui só materializa
    as consequências no backlog e na leitura do Gatekeeper.
    """
    from app.db.database import AsyncSessionLocal
    from app.services.propagation_service import PropagationService
    from app.services.ingestion_service import _reevaluate_gatekeeper_async

    pid = UUID(project_id)

    async with AsyncSessionLocal() as session:
        propagator = PropagationService(session)
        # `changes` sinalizador canônico — campo `RNF_QUESTIONNAIRE` não
        # existe no OCG; o PROPAGATION_MAP trata unknowns com fallback
        # em `modules`, que é o que queremos.
        await propagator.propagate(
            pid,
            changes=[{
                "field": "RNF_QUESTIONNAIRE",
                "source": "arguider_questionnaire_applied",
                "resolved_codes": report.get("resolved_codes") or [],
                "info_debt_promoted": report.get("info_debt_promoted") or [],
            }],
            ocg_version=None,
        )

    await _reevaluate_gatekeeper_async(
        project_id=pid, ocg_version=None,
        trigger="questionnaire_applied",
    )
