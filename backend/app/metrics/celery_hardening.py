"""
MVP 29 Hardening — Prometheus Metrics

Métricas para task redistributions, idempotent skips, e falhas de broker.
Observabilidade canônica para DT-075 mitigation.
"""
import structlog

logger = structlog.get_logger(__name__)

# Inicializa métricas simples (in-memory counters)
# Futuro: integrar com Prometheus client para exportar via /metrics endpoint

_METRICS = {
    # Task redistributions
    "celery.task.redistributed": 0,  # Tasks que foram reenfileiradas (worker death recovery)

    # Idempotent skips
    "celery.task.idempotent_skip_ingest": 0,  # pipeline_ingest_task skips
    "celery.task.idempotent_skip_propagate": 0,  # propagate_task skips
    "celery.task.idempotent_skip_regenerate_backlog": 0,  # regenerate_backlog_task skips
    "celery.task.idempotent_skip_autogen": 0,  # auto_generate_task skips

    # Failures
    "celery.task.failure_permanent": 0,  # Tasks que esgotaram retries

    # Success
    "celery.task.success": 0,  # Tasks completadas com sucesso
}


def increment_metric(metric_name: str, value: int = 1) -> None:
    """Incrementa um counter de métrica."""
    if metric_name in _METRICS:
        _METRICS[metric_name] += value
        logger.info(
            "metric.incremented",
            metric=metric_name,
            value=_METRICS[metric_name],
        )
    else:
        logger.warning("metric.unknown", metric=metric_name)


def get_metrics() -> dict:
    """Retorna snapshot de todas as métricas (para /metrics endpoint)."""
    return dict(_METRICS)


def get_metric(metric_name: str) -> int:
    """Retorna valor específico de uma métrica."""
    return _METRICS.get(metric_name, 0)


# Inicialização dos handlers de métricas
# Chamados quando eventos Celery ocorrem


def on_task_redistribution(task_name: str, project_id: str = None) -> None:
    """Chamado quando uma task é redistribuída (worker death recovery)."""
    increment_metric("celery.task.redistributed")
    logger.info(
        "celery.task_redistributed",
        task=task_name,
        project_id=project_id,
    )


def on_idempotent_skip(task_name: str, project_id: str = None, reason: str = None) -> None:
    """Chamado quando uma task é skipped por idempotência."""
    metric_name = None
    if task_name == "pipeline_ingest_task":
        metric_name = "celery.task.idempotent_skip_ingest"
    elif task_name == "propagate_task":
        metric_name = "celery.task.idempotent_skip_propagate"
    elif task_name == "regenerate_backlog_task":
        metric_name = "celery.task.idempotent_skip_regenerate_backlog"
    elif task_name == "auto_generate_task":
        metric_name = "celery.task.idempotent_skip_autogen"

    if metric_name:
        increment_metric(metric_name)

    logger.info(
        "celery.task_idempotent_skip",
        task=task_name,
        project_id=project_id,
        reason=reason,
    )


def on_task_failure(task_name: str, exception: Exception = None) -> None:
    """Chamado quando uma task falha permanentemente (esgotou retries)."""
    increment_metric("celery.task.failure_permanent")
    logger.error(
        "celery.task_failure_permanent_metric",
        task=task_name,
        exception=str(exception)[:200] if exception else None,
    )


def on_task_success(task_name: str) -> None:
    """Chamado quando uma task completa com sucesso."""
    increment_metric("celery.task.success")
    logger.debug(
        "celery.task_success_metric",
        task=task_name,
    )
