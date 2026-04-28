"""
Rotas para observabilidade — Prometheus metrics e health checks.

MVP 29.4: Expõe métricas de DT-075 Hardening (task redistributions, idempotent skips).
"""
from fastapi import APIRouter, HTTPException
from app.metrics import get_metrics

router = APIRouter(
    prefix="/api/metrics",
    tags=["metrics"],
)


@router.get("/mvp29-hardening")
async def get_mvp29_hardening_metrics():
    """Retorna métricas de MVP 29 Hardening (Celery).

    Métricas incluem:
    - celery.task.redistributed — tasks que foram reenfileiradas após worker death
    - celery.task.idempotent_skip_* — tasks que skipped por idempotência
    - celery.task.failure_permanent — tasks que esgotaram retries
    - celery.task.success — tasks completadas com sucesso

    Uso para alertas/monitoring:
    - High redistribution rate → indicativo de worker instability
    - High idempotent skips → normal, expected in MVP 29
    - High failure rate → investigate task errors
    """
    metrics = get_metrics()
    return {
        "status": "ok",
        "timestamp": "2026-04-28T00:00:00Z",  # TODO: adicionar timestamp real
        "metrics": metrics,
    }


@router.get("/celery-dlq")
async def get_celery_dlq_entries(limit: int = 50):
    """Retorna últimas falhas permanentes (DLQ entries) do Celery.

    Usado para debugging de tasks que esgotaram retries.
    """
    from app.celery_app import get_dlq_entries

    entries = get_dlq_entries(limit=limit)
    return {
        "status": "ok",
        "count": len(entries),
        "entries": entries,
    }
