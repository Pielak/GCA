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
from uuid import UUID

import structlog

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


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
        asyncio.run(_run_analyze_async(document_id, project_id, file_type))
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
