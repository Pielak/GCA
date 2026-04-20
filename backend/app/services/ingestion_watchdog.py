"""DT-3 dogfood — Watchdog/recovery de tasks de ingestão.

Resolve o cenário onde o backend é reiniciado durante uma análise do
Arguidor: o `asyncio.create_task` morre com o processo, mas a linha em
`ingested_documents` fica com `arguider_status='processing'` para sempre.
Consequência prática: `delete_document` bloqueia (guard 409) e o GP não
consegue subir o doc de novo.

Também atende ao sintoma operacional da DT-5 (sem fila persistente):
mesmo sem migrar para Celery/RQ, garantimos que docs zumbis não fiquem
indefinidamente travados.

Política:
- Threshold padrão: 30 minutos sem atualização de stage. Análises reais
  do Arguidor levam segundos a poucos minutos com Anthropic, até ~5 min
  com Ollama local. 30 min é margem confortável.
- Recovery escreve `arguider_error_message` claro pra UI mostrar (DT-022).
- Stage vai para 'failed' pra frontend parar o polling.
- Idempotente: roda múltiplas vezes sem duplicar efeito.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import update, select

from app.db.database import AsyncSessionLocal
from app.models.base import IngestedDocument

logger = structlog.get_logger(__name__)

ZOMBIE_THRESHOLD_MINUTES = 30
RECOVERY_MESSAGE = (
    "Análise interrompida por reinício do backend. "
    "Documento liberado para nova tentativa ou exclusão."
)


async def recover_zombie_documents(
    threshold_minutes: int = ZOMBIE_THRESHOLD_MINUTES,
    db=None,
) -> dict[str, Any]:
    """Marca como 'error' docs presos em 'processing' por mais que o threshold.

    Idempotente. Executar no startup do backend (lifespan) e/ou em job
    periódico.

    Args:
        threshold_minutes: idade mínima de `arguider_started_at` pra considerar zombie.
        db: opcional — sessão a usar (útil em testes). Se None, abre uma fresh
            via `AsyncSessionLocal()`.

    Returns:
        {
            "checked": int,        # quantos docs estavam em 'processing'
            "recovered": int,      # quantos foram marcados como error
            "threshold_minutes": int,
        }
    """
    if db is not None:
        return await _do_recover(db, threshold_minutes)
    async with AsyncSessionLocal() as _db:
        return await _do_recover(_db, threshold_minutes)


async def _do_recover(db, threshold_minutes: int) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    rows = await db.execute(
        select(IngestedDocument.id, IngestedDocument.project_id, IngestedDocument.original_filename)
        .where(
            IngestedDocument.arguider_status == "processing",
            IngestedDocument.arguider_started_at < cutoff,
        )
    )
    candidates = rows.all()
    checked = len(candidates)

    if checked == 0:
        return {"checked": 0, "recovered": 0, "threshold_minutes": threshold_minutes}

    result = await db.execute(
        update(IngestedDocument)
        .where(
            IngestedDocument.arguider_status == "processing",
            IngestedDocument.arguider_started_at < cutoff,
        )
        .values(
            arguider_status="error",
            arguider_error_message=RECOVERY_MESSAGE,
            arguider_stage="failed",
        )
    )
    await db.commit()
    recovered = result.rowcount or 0

    for cid, pid, fname in candidates:
        logger.warning(
            "ingestion.zombie_recovered",
            document_id=str(cid),
            project_id=str(pid),
            filename=fname,
            threshold_minutes=threshold_minutes,
        )

    logger.info(
        "ingestion.watchdog_summary",
        checked=checked,
        recovered=recovered,
    )

    return {
        "checked": checked,
        "recovered": recovered,
        "threshold_minutes": threshold_minutes,
    }
