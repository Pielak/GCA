"""Celery task pra scaffold server-side persistido (2026-04-25).

Substitui a iteração síncrona via HTTP `/scaffold/plan` + N×`/scaffold/item`
do frontend. Aqui a run roda inteira no worker Celery, sobrevivendo a
qualquer desconexão do navegador.

Frontend só chama `POST /scaffold/start` (retorna `run_id`) e depois
`GET /scaffold/runs/{run_id}` em poll. Apply é manual via outro endpoint.
"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine
from uuid import UUID

import structlog

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_coro_isolated(coro: Coroutine[Any, Any, Any]) -> Any:
    """Roda corrotina num event loop isolado (mesmo padrão de pipeline.py)."""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception:
        raise


@celery_app.task(
    name="app.tasks.scaffold.watchdog_scaffold_zombies",
    bind=True,
)
def watchdog_scaffold_zombies(self, threshold_minutes: int = 10) -> dict:
    """Roda periodicamente (Celery beat) e re-enfileira ScaffoldRuns zombie.

    Critério de zombie: status in (planning, generating) + last_progress_at
    > threshold_minutes atrás. Indica worker que morreu/restartou e
    abandonou a run no meio.

    Estratégia: re-enfileira via scaffold_run_executor — execute_run agora
    aceita 'generating' e processa só items pending (resume).
    """
    import asyncio
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, or_, and_
    from app.db.database import AsyncSessionLocal
    from app.models.base import ScaffoldRun

    async def _scan() -> dict:
        async with AsyncSessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
            rows = (await db.execute(
                select(ScaffoldRun).where(
                    ScaffoldRun.status.in_(("planning", "generating")),
                    or_(
                        ScaffoldRun.last_progress_at.is_(None),
                        ScaffoldRun.last_progress_at < cutoff,
                    ),
                )
            )).scalars().all()
            zombies = [str(r.id) for r in rows]
        return {"zombies": zombies, "count": len(zombies)}

    try:
        result = _run_coro_isolated(_scan())
        zombies = result.get("zombies", [])
        for run_id in zombies:
            scaffold_run_executor.delay(run_id)
            logger.info("watchdog_scaffold.requeued", run_id=run_id)
        if zombies:
            logger.warning(
                "watchdog_scaffold.found_zombies",
                count=len(zombies),
                threshold_minutes=threshold_minutes,
            )
        return {"requeued": len(zombies), "run_ids": zombies}
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog_scaffold.failed", error=str(exc), exc_info=True)
        return {"status": "error", "error": str(exc)[:500]}


@celery_app.task(
    name="app.tasks.scaffold.code_audit_executor",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def code_audit_executor(self, run_id: str) -> dict:
    """Roda o auditor pós-CodeGen (Arguidor #2) em uma scaffold_run aplicada.

    Disparado automaticamente após apply_scaffold_run finalizar com committed > 0.
    Pode também ser invocado manualmente via POST /scaffold/runs/{id}/audit/start.
    """
    from app.services.code_audit_service import audit_run

    try:
        result = _run_coro_isolated(audit_run(UUID(run_id)))
        logger.info("code_audit_executor.ok", run_id=run_id, result=result)
        return {"status": "ok", "run_id": run_id, **(result or {})}
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "code_audit_executor.unhandled",
            run_id=run_id,
            error=str(exc),
            exc_info=True,
        )
        return {"status": "error", "run_id": run_id, "error": str(exc)[:500]}


@celery_app.task(
    name="app.tasks.scaffold.scaffold_run_executor",
    bind=True,
    max_retries=0,  # falhas dentro da run são gravadas no DB, não retry
    acks_late=True,
)
def scaffold_run_executor(self, run_id: str) -> dict:
    """Executa uma `ScaffoldRun` ponta-a-ponta: planning → items → completed.

    Cada arquivo gerado vira row em `scaffold_run_items` com `content`
    persistido. O frontend acompanha via GET. Apply ao Git é separado.

    Args:
        run_id: UUID str da ScaffoldRun em status='pending'.

    Returns:
        dict com {status, run_id} pra result backend.
    """
    from app.services.scaffold_run_service import execute_run

    try:
        _run_coro_isolated(execute_run(UUID(run_id)))
        logger.info("scaffold_run_executor.ok", run_id=run_id)
        return {"status": "ok", "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        # Erros não-tratados aqui são raros: o execute_run já grava status=failed
        # nas exceções esperadas (LLM, parse, sem chave). Só vem aqui crash de
        # infra grave; logamos pra investigação manual.
        logger.error(
            "scaffold_run_executor.unhandled",
            run_id=run_id,
            error=str(exc),
            exc_info=True,
        )
        return {"status": "error", "run_id": run_id, "error": str(exc)[:500]}
