"""MVP 14 Fase 14.10 — métricas Celery no endpoint Prometheus."""
import pytest

from app.services.metrics_service import MetricsService


@pytest.mark.asyncio
async def test_prometheus_text_includes_celery_metrics(db_session):
    """O texto Prometheus declara 3 métricas Celery obrigatórias.

    Não depende de broker real estar up — helpers absorvem erro e reportam 0.
    """
    svc = MetricsService(db_session)
    text = await svc.as_prometheus_text(hours=1)

    assert "gca_celery_broker_reachable" in text
    assert "gca_celery_workers_online" in text
    assert "gca_celery_dlq_entries" in text

    assert "# HELP gca_celery_broker_reachable" in text
    assert "# TYPE gca_celery_broker_reachable gauge" in text
    assert "# HELP gca_celery_workers_online" in text
    assert "# TYPE gca_celery_workers_online gauge" in text
    assert "# HELP gca_celery_dlq_entries" in text
    assert "# TYPE gca_celery_dlq_entries gauge" in text


@pytest.mark.asyncio
async def test_prometheus_text_broker_metric_is_binary(db_session):
    """broker_reachable é gauge binário (0 ou 1)."""
    svc = MetricsService(db_session)
    text = await svc.as_prometheus_text(hours=1)

    for line in text.splitlines():
        if line.startswith("gca_celery_broker_reachable "):
            value = line.split()[-1]
            assert value in {"0", "1"}, f"valor inválido: {value!r}"
            return
    pytest.fail("linha gca_celery_broker_reachable não encontrada")
