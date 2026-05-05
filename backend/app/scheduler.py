"""APScheduler para watchdogs em-processo (Fase 1 migração Celery → Dramatiq).

Substitui celery-beat com jobs periódicos executados no evento loop do backend.
Watchdogs:
- watchdog_ingestion (120s): recupera docs presos em 'processing'
- watchdog_scaffold (300s): re-enfileira ScaffoldRuns zombies

Ativado no lifespan do FastAPI (main.py).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_ingestion_watchdog() -> dict[str, Any]:
    """Watchdog de ingestão: marca docs presos em 'processing' como error."""
    try:
        from app.services.ingestion_watchdog import recover_zombie_documents

        result = await recover_zombie_documents(threshold_minutes=15)
        if result.get("count", 0) > 0:
            logger.warning(
                "watchdog_ingestion.found_zombies",
                count=result.get("count", 0),
                released_docs=result.get("released_docs", []),
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog_ingestion.failed", error=str(exc), exc_info=True)
        return {"status": "error", "error": str(exc)[:500]}


async def _run_scaffold_watchdog() -> dict[str, Any]:
    """Watchdog de scaffold: re-enfileira ScaffoldRuns zombie via Celery (Fase 1)."""
    try:
        from app.tasks.scaffold import watchdog_scaffold_zombies

        # Fase 1: chama task Celery diretamente
        # Fase 3: trocar para orchestração via Dramatiq
        result = watchdog_scaffold_zombies(threshold_minutes=10)
        if result.get("requeued", 0) > 0:
            logger.info(
                "watchdog_scaffold.requeued",
                count=result.get("requeued", 0),
                run_ids=result.get("run_ids", []),
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog_scaffold.failed", error=str(exc), exc_info=True)
        return {"status": "error", "error": str(exc)[:500]}


def start_watchdog_scheduler() -> None:
    """Inicia scheduler de watchdogs. Chamado em main.py lifespan (startup)."""
    global _scheduler

    # Pula em modo teste
    if "PYTEST_CURRENT_TEST" in os.environ:
        logger.info("watchdog_scheduler.skipped_in_pytest")
        return

    try:
        _scheduler = AsyncIOScheduler()

        # Watchdog ingestion — a cada 120s
        _scheduler.add_job(
            _run_ingestion_watchdog,
            IntervalTrigger(seconds=120),
            id="watchdog_ingestion",
            name="Ingestion Zombie Recovery",
            max_instances=1,
            coalesce=True,
        )

        # Watchdog scaffold — a cada 300s
        _scheduler.add_job(
            _run_scaffold_watchdog,
            IntervalTrigger(seconds=300),
            id="watchdog_scaffold",
            name="Scaffold Zombie Recovery",
            max_instances=1,
            coalesce=True,
        )

        _scheduler.start()
        logger.info("watchdog_scheduler.started")
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog_scheduler.start_failed", error=str(exc), exc_info=True)


async def stop_watchdog_scheduler() -> None:
    """Para scheduler. Chamado em main.py lifespan (shutdown)."""
    global _scheduler

    if _scheduler is None:
        return

    try:
        if _scheduler.running:
            _scheduler.shutdown()
        logger.info("watchdog_scheduler.stopped")
    except Exception as exc:  # noqa: BLE001
        logger.error("watchdog_scheduler.stop_failed", error=str(exc), exc_info=True)
