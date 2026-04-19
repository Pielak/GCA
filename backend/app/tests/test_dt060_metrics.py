"""DT-060 — Métricas: dashboard + Prometheus.

Cobertura:
- MetricsService.as_dashboard_dict agrega ai_usage / audit / projects / users
- as_prometheus_text formato HELP/TYPE/labels válido
- Filtragem por janela temporal (`hours`)
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.base import AIUsageLog, GlobalAuditLog
from app.services.metrics_service import MetricsService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_ai_usage(db, project_id, hours_ago=1, **overrides):
    row = AIUsageLog(
        id=uuid4(),
        project_id=project_id,
        provider=overrides.get("provider", "anthropic"),
        model=overrides.get("model", "claude-haiku"),
        operation=overrides.get("operation", "analyzer"),
        tokens_input=overrides.get("tokens_input", 100),
        tokens_output=overrides.get("tokens_output", 50),
        cost_usd=overrides.get("cost_usd", 0.001),
        actor_id=None,
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    db.add(row)
    await db.flush()


async def _seed_audit(db, event_type, hours_ago=1):
    row = GlobalAuditLog(
        id=uuid4(),
        event_type=event_type,
        actor_id=None,
        actor_email=None,
        resource_type="test",
        resource_id=None,
        details=None,
        previous_hash=None,
        current_hash="x" * 64,
        correlation_id=None,
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    db.add(row)
    await db.flush()


# ---------------------------------------------------------------------------
# Dashboard agregação
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_aggregates_ai_usage_by_provider_operation(db_session, test_project):
    """Soma calls/tokens/cost agrupando por (provider, operation)."""
    await _seed_ai_usage(db_session, test_project.id, provider="anthropic", operation="analyzer", tokens_input=100, tokens_output=50, cost_usd=0.001)
    await _seed_ai_usage(db_session, test_project.id, provider="anthropic", operation="analyzer", tokens_input=200, tokens_output=80, cost_usd=0.002)
    await _seed_ai_usage(db_session, test_project.id, provider="deepseek", operation="ocg_update", tokens_input=300, tokens_output=120, cost_usd=0.0005)

    svc = MetricsService(db_session)
    d = await svc.as_dashboard_dict(hours=24)

    rows = {(r["provider"], r["operation"]): r for r in d["ai_usage"]["rows"]}
    assert (("anthropic", "analyzer")) in rows
    anth = rows[("anthropic", "analyzer")]
    assert anth["calls"] == 2
    assert anth["tokens_in"] == 300
    assert anth["tokens_out"] == 130
    assert round(anth["cost_usd"], 5) == 0.003

    ds = rows[("deepseek", "ocg_update")]
    assert ds["calls"] == 1
    assert ds["tokens_in"] == 300


@pytest.mark.asyncio
async def test_dashboard_filters_by_time_window(db_session, test_project):
    """Eventos fora da janela `hours` não aparecem."""
    await _seed_ai_usage(db_session, test_project.id, hours_ago=2)
    await _seed_ai_usage(db_session, test_project.id, hours_ago=48)  # fora janela 24h

    svc = MetricsService(db_session)
    d = await svc.as_dashboard_dict(hours=24)
    total_calls = sum(r["calls"] for r in d["ai_usage"]["rows"])
    assert total_calls == 1


@pytest.mark.asyncio
async def test_dashboard_aggregates_audit_events(db_session):
    """Conta eventos de audit por tipo."""
    for _ in range(3):
        await _seed_audit(db_session, "GATEKEEPER_REEVALUATED")
    await _seed_audit(db_session, "PROJECT_CREATED")

    svc = MetricsService(db_session)
    d = await svc.as_dashboard_dict(hours=24)
    by_type = {e["event_type"]: e["count"] for e in d["audit"]["events"]}
    assert by_type.get("GATEKEEPER_REEVALUATED") == 3
    assert by_type.get("PROJECT_CREATED") == 1


@pytest.mark.asyncio
async def test_dashboard_includes_project_and_user_summary(db_session, test_project, test_user):
    svc = MetricsService(db_session)
    d = await svc.as_dashboard_dict(hours=24)

    # test_project + test_user existem
    assert d["projects"]["by_status"]
    assert any(p["count"] >= 1 for p in d["projects"]["by_status"])
    assert d["users"]["active"] >= 1
    assert d["users"]["admin_active"] >= 1


# ---------------------------------------------------------------------------
# Prometheus text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prometheus_text_has_help_and_type_lines(db_session, test_project):
    """Formato Prometheus exige HELP+TYPE antes de cada métrica."""
    await _seed_ai_usage(db_session, test_project.id)

    svc = MetricsService(db_session)
    txt = await svc.as_prometheus_text(hours=24)

    for metric in ("gca_ai_calls_total", "gca_ai_tokens_total", "gca_ai_cost_usd_total",
                   "gca_audit_events_total", "gca_projects_total", "gca_users_total"):
        assert f"# HELP {metric}" in txt, f"Falta HELP de {metric}"
        assert f"# TYPE {metric}" in txt, f"Falta TYPE de {metric}"


@pytest.mark.asyncio
async def test_prometheus_text_emits_labels(db_session, test_project):
    """Labels formatados {key="value"} ordenados alfabeticamente."""
    await _seed_ai_usage(
        db_session, test_project.id, provider="anthropic", operation="analyzer",
        tokens_input=10, tokens_output=5, cost_usd=0.001,
    )

    svc = MetricsService(db_session)
    txt = await svc.as_prometheus_text(hours=24)

    # operation=analyzer + provider=anthropic — ordem alfabética
    assert 'gca_ai_calls_total{operation="analyzer",provider="anthropic"}' in txt
    assert 'direction="in"' in txt and 'direction="out"' in txt


@pytest.mark.asyncio
async def test_prometheus_text_handles_empty_data(db_session):
    """Sem dados no DB ainda deve retornar texto válido com HELP/TYPE."""
    svc = MetricsService(db_session)
    txt = await svc.as_prometheus_text(hours=1)
    assert "gca_ai_calls_total" in txt  # HELP/TYPE sempre presentes
    assert "gca_users_total" in txt
