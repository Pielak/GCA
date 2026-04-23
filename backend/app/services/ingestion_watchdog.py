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
- Threshold padrão: 8 minutos sem atualização de stage. Análises típicas
  do Arguidor com Anthropic ficam em 60–180s; Ollama local excepcional
  chega a ~4min. 8 min dá margem ~2x sem deixar zombies por muito tempo.
  (Ajustado de 30→8 em 2026-04-22 após dogfood do MVP 25: restarts
  encadeados do backend durante desenvolvimento deixavam docs travados
  por 30min inteiros, incomodando o fluxo.)
- Recovery escreve `arguider_error_message` claro pra UI mostrar (DT-022).
- Stage vai para 'failed' pra frontend parar o polling.
- Idempotente: roda múltiplas vezes sem duplicar efeito.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, or_, select, update

from app.db.database import AsyncSessionLocal
from app.models.base import IngestedDocument

logger = structlog.get_logger(__name__)

ZOMBIE_THRESHOLD_MINUTES = 8
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

    # MVP 29 Fase 29.1 + sessão 30: três padrões de zombie cobertos.
    #
    #  1. status='processing' + started_at velho — caso clássico pré-MVP 29.
    #  2. status='pending' + started_at NOT NULL e velho — bug novo descoberto
    #     no dogfood: fluxos de fallback (DT-064) e reanalyze resetavam
    #     status→'pending' mas deixavam started_at preenchido.
    #  3. stage='failed' + status IN ('pending','processing') — sessão 30:
    #     worker crashou dentro do pipeline ANTES de atualizar o status.
    #     `stage` virou 'failed' mas `status` ficou 'pending'/'processing'
    #     (estado ilegal que esconde o doc da UI, sem botão retry visível).
    #     Pegamos sem cutoff de tempo — stage=failed significa crash real,
    #     não há razão pra esperar.
    zombie_predicate = or_(
        and_(
            or_(
                IngestedDocument.arguider_status == "processing",
                and_(
                    IngestedDocument.arguider_status == "pending",
                    IngestedDocument.arguider_started_at.isnot(None),
                ),
            ),
            IngestedDocument.arguider_started_at < cutoff,
        ),
        and_(
            IngestedDocument.arguider_stage == "failed",
            IngestedDocument.arguider_status.in_(("pending", "processing")),
        ),
    )

    rows = await db.execute(
        select(
            IngestedDocument.id,
            IngestedDocument.project_id,
            IngestedDocument.original_filename,
            IngestedDocument.arguider_status,
        ).where(zombie_predicate)
    )
    candidates = rows.all()
    checked = len(candidates)

    if checked == 0:
        return {"checked": 0, "recovered": 0, "threshold_minutes": threshold_minutes}

    result = await db.execute(
        update(IngestedDocument)
        .where(zombie_predicate)
        .values(
            arguider_status="error",
            arguider_error_message=RECOVERY_MESSAGE,
            arguider_stage="failed",
        )
    )
    await db.commit()
    recovered = result.rowcount or 0

    for cid, pid, fname, prev_status in candidates:
        logger.warning(
            "ingestion.zombie_recovered",
            document_id=str(cid),
            project_id=str(pid),
            filename=fname,
            previous_status=prev_status,
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
