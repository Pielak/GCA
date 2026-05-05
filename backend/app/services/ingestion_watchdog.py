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

ZOMBIE_THRESHOLD_MINUTES = 15
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
    # F5.1 (DBA CO-1): threshold dedicado para `ocg_updating`. Worst-case:
    # 3 retries Celery exponenciais (30s+120s+480s = 10.5min) + LLM ~60s ≈ 12min.
    # 15min cobre com margem. NÃO usa o threshold global (8min default).
    cutoff_ocg_updating = datetime.now(timezone.utc) - timedelta(minutes=15)

    # F4.2 — threshold dedicado para `chunking_parent`. Pai aguarda todos os
    # filhos terminarem. Worst-case: MAX_PARTS=10 filhos × ~120s cada = 20min.
    # 15min já deteta pais travados antes do worst-case sem ser agressivo.
    cutoff_chunking_parent = datetime.now(timezone.utc) - timedelta(minutes=15)

    # MVP 29 Fase 29.1 + sessão 30: três padrões de zombie cobertos.
    #
    #  1. status='processing' + started_at velho — caso clássico pré-MVP 29.
    #     CO-2 (F4.2): filtro `deleted_at IS NULL` adicionado.
    #  2. status='pending' + started_at NOT NULL e velho — bug novo descoberto
    #     no dogfood: fluxos de fallback (DT-064) e reanalyze resetavam
    #     status→'pending' mas deixavam started_at preenchido.
    #     CO-2 (F4.2): filtro `deleted_at IS NULL` adicionado.
    #  3. stage='failed' + status IN ('pending','processing') — sessão 30:
    #     worker crashou dentro do pipeline ANTES de atualizar o status.
    #     `stage` virou 'failed' mas `status` ficou 'pending'/'processing'
    #     (estado ilegal que esconde o doc da UI, sem botão retry visível).
    #     Pegamos sem cutoff de tempo — stage=failed significa crash real,
    #     não há razão pra esperar.
    #     CO-2 (F4.2): filtro `deleted_at IS NULL` adicionado.
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
            IngestedDocument.deleted_at.is_(None),  # CO-2
        ),
        and_(
            IngestedDocument.arguider_stage == "failed",
            IngestedDocument.arguider_status.in_(("pending", "processing")),
            IngestedDocument.deleted_at.is_(None),  # CO-2
        ),
        # Pipeline n8n não seta `arguider_started_at` — usa `updated_at`
        # como proxy. Cobre Conferente/Specialist/Consolidador caindo
        # silenciosamente sem virar stage='failed' nem started_at preenchido.
        and_(
            IngestedDocument.arguider_status == "processing",
            IngestedDocument.arguider_stage == "n8n_pipeline",
            IngestedDocument.updated_at < cutoff,
            IngestedDocument.deleted_at.is_(None),
        ),
        # F5.1 (DBA CO-1): docs presos em `ocg_updating` — Celery task
        # process_ingestion_complete_ocg morreu/travou após handler retornar
        # 202. Threshold próprio de 15min (cutoff_ocg_updating) — independe
        # do threshold global de 8min do `processing`. Usa updated_at
        # como proxy (task não escreve em arguider_started_at).
        and_(
            IngestedDocument.arguider_status == "ocg_updating",
            IngestedDocument.updated_at < cutoff_ocg_updating,
            IngestedDocument.deleted_at.is_(None),
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

    project_ids_recovered: set = set()
    for cid, pid, fname, prev_status in candidates:
        project_ids_recovered.add(pid)
        logger.warning(
            "ingestion.zombie_recovered",
            document_id=str(cid),
            project_id=str(pid),
            filename=fname,
            previous_status=prev_status,
            threshold_minutes=threshold_minutes,
        )

    # Dispara próximo pendente por projeto afetado — sem isso a fila trava
    # mesmo após marcar zombie (lição da sessão 2026-05-04).
    if project_ids_recovered:
        try:
            from app.services.ingestion_service import (
                dispatch_first_pending_for_project,
            )
            for pid in project_ids_recovered:
                try:
                    await dispatch_first_pending_for_project(db, pid)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ingestion.watchdog_dispatch_next_failed",
                        project_id=str(pid),
                        error=str(exc),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingestion.watchdog_dispatch_import_failed", error=str(exc))

    # ── F4.2.5 — Watchdog para pais presos em 'chunking_parent' > 15 min ──
    # Pai entra em chunking_parent quando seus filhos são criados. Se o pai
    # ainda está em processing/chunking_parent após 15min, verifica filhos:
    #   - Todos concluídos → tenta resolver o pai (chamando _maybe_resolve_parent).
    #   - Algum filho ainda em pending → reenfileira filho individualmente.
    # Usa updated_at como proxy (pai não atualiza arguider_started_at).
    chunking_parent_count = await _recover_chunking_parent_zombies(
        db, cutoff_chunking_parent
    )

    logger.info(
        "ingestion.watchdog_summary",
        checked=checked,
        recovered=recovered,
        projects_dispatched=len(project_ids_recovered),
        chunking_parent_recovered=chunking_parent_count,
    )

    return {
        "checked": checked,
        "recovered": recovered,
        "threshold_minutes": threshold_minutes,
        "chunking_parent_recovered": chunking_parent_count,
    }


async def _recover_chunking_parent_zombies(db, cutoff) -> int:
    """Recupera pais presos em arguider_stage='chunking_parent' > 15 min.

    Verifica estado dos filhos:
      - Todos concluídos/erro → tenta resolver o pai via _maybe_resolve_parent.
      - Filhos ainda em pending/processing → reenfileira filhos individualmente
        marcando-os como zombie (status='error', stage='failed') para que o
        próximo dispatch os pegue via retry do usuário.

    Retorna contagem de pais processados.
    """
    from sqlalchemy import select as _select
    rows = await db.execute(
        _select(
            IngestedDocument.id,
            IngestedDocument.project_id,
        ).where(
            and_(
                IngestedDocument.arguider_stage == "chunking_parent",
                IngestedDocument.arguider_status == "processing",
                IngestedDocument.updated_at < cutoff,
                IngestedDocument.deleted_at.is_(None),
            )
        )
    )
    stale_parents = rows.all()
    processed = 0

    for parent_id, project_id in stale_parents:
        try:
            await _handle_stale_chunking_parent(db, parent_id, project_id)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ingestion.watchdog_chunking_parent_failed",
                parent_id=str(parent_id),
                project_id=str(project_id),
                error=str(exc),
            )

    return processed


async def _handle_stale_chunking_parent(db, parent_id, project_id) -> None:
    """Verifica filhos de um pai zombie e age conforme estado deles."""
    from sqlalchemy import select as _select
    siblings_q = await db.execute(
        _select(IngestedDocument).where(
            and_(
                IngestedDocument.parent_document_id == parent_id,
                IngestedDocument.deleted_at.is_(None),
            )
        )
    )
    siblings = siblings_q.scalars().all()

    if not siblings:
        # Pai sem filhos: estado inválido, marcar erro
        logger.warning(
            "ingestion.watchdog_chunking_parent_no_children",
            parent_id=str(parent_id),
        )
        await db.execute(
            update(IngestedDocument)
            .where(IngestedDocument.id == parent_id)
            .values(
                arguider_status="error",
                arguider_stage="failed",
                arguider_error_message=(
                    "Processamento chunking_parent expirou sem filhos registrados. "
                    "Verifique logs de ingestão."
                ),
            )
        )
        await db.commit()
        return

    all_done = all(
        s.arguider_status in ("completed", "error", "partial", "ocg_updating", "ocg_pending")
        for s in siblings
    )

    if all_done:
        # Todos terminaram — tenta resolver o pai
        logger.info(
            "ingestion.watchdog_chunking_parent_resolving",
            parent_id=str(parent_id),
            project_id=str(project_id),
            filhos=len(siblings),
        )
        try:
            from app.routers.webhooks import _maybe_resolve_parent
            parent_doc = await db.get(IngestedDocument, parent_id)
            if parent_doc:
                await _maybe_resolve_parent(db, parent_doc)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ingestion.watchdog_maybe_resolve_failed",
                parent_id=str(parent_id),
                error=str(exc),
            )
    else:
        # Filhos ainda em pending/processing — marcar filhos zombie
        pending_siblings = [
            s for s in siblings
            if s.arguider_status in ("pending", "processing")
        ]
        logger.warning(
            "ingestion.watchdog_chunking_parent_stale_children",
            parent_id=str(parent_id),
            filhos_pendentes=len(pending_siblings),
        )
        for sib in pending_siblings:
            sib.arguider_status = "error"
            sib.arguider_stage = "failed"
            sib.arguider_error_message = (
                "Filho de sub-ingestão expirou sem conclusão (watchdog 15min). "
                "Pai aguarda. Verifique logs n8n e tente reprocessar o documento original."
            )
        if pending_siblings:
            await db.flush()
            await db.commit()

        # Tenta resolver o pai após marcar filhos como erro
        try:
            from app.routers.webhooks import _maybe_resolve_parent
            parent_doc = await db.get(IngestedDocument, parent_id)
            if parent_doc:
                await _maybe_resolve_parent(db, parent_doc)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ingestion.watchdog_maybe_resolve_after_zombie_failed",
                parent_id=str(parent_id),
                error=str(exc),
            )
