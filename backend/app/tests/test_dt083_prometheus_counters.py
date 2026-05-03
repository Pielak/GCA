"""DT-083 — 3 contadores Prometheus para OCG + CodeGen Gate.

Implementação: queries derivadas de tabelas existentes (sem prometheus_client).

Cobre:
  - `gca_ocg_delta_applied_total{project,trigger_source}` ← ocg_delta_log
  - `gca_ocg_negative_delta_blocked_total{project}` ← audit_log_global (novo evento)
  - `gca_codegen_blocked_total{block_level}` ← scaffold_runs WHERE status='blocked'
  - Não-regressão: contadores antigos (ai_calls, audit_events, projects, users) continuam.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_dt083_prometheus_counters.py -v"
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.base import (
    GlobalAuditLog,
    OCGDeltaLog,
    Questionnaire,
    ScaffoldRun,
)
from app.services.audit_service import AuditEvents, AuditService
from app.services.metrics_service import MetricsService
from app.tests.factories import create_test_organization, create_test_project, create_test_user


# =============================================================================
# Helpers
# =============================================================================


async def _seed_project(db):
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"dt083-{uuid4().hex[:6]}"
    )
    return project


async def _seed_questionnaire(db, project_id):
    q = Questionnaire(
        id=uuid4(),
        project_id=project_id,
        gp_email=f"dt083-{uuid4().hex[:6]}@test.com",
        responses="{}",
        status="pending",
    )
    db.add(q)
    await db.flush()
    return q


async def _seed_ocg_delta(db, project_id, trigger_source, version_to=2):
    log = OCGDeltaLog(
        id=uuid4(),
        project_id=project_id,
        document_id=None,
        ocg_version_from=version_to - 1,
        ocg_version_to=version_to,
        fields_changed="{}",
        change_summary=None,
        trigger_source=trigger_source,
        source=trigger_source,
    )
    db.add(log)
    await db.flush()
    return log


async def _seed_scaffold_run_blocked(db, project_id, block_level):
    """Cria run com status='failed' + prefixo canônico no error.

    Schema não permite status='blocked' (CHECK constraint). DT-082 originalmente
    propunha esse status; DT-083 corrigiu para `failed` + `error LIKE '[ocg_gate:%'`
    para que a métrica seja derivada sem migration.
    """
    user = await create_test_user(db, is_admin=True)
    run = ScaffoldRun(
        id=uuid4(),
        project_id=project_id,
        triggered_by=user.id,
        status="failed",
        error=f"[ocg_gate:{block_level}] OCG bloqueado pelo gate.",
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    return run


# =============================================================================
# Aggregations — `_ocg_delta_aggregations`
# =============================================================================


@pytest.mark.asyncio
async def test_ocg_delta_aggregations_groups_by_project_and_trigger(db_session):
    """Conta deltas agrupados por (project_id, trigger_source)."""
    p1 = await _seed_project(db_session)
    p2 = await _seed_project(db_session)

    await _seed_ocg_delta(db_session, p1.id, "document_ingestion_n8n", version_to=2)
    await _seed_ocg_delta(db_session, p1.id, "document_ingestion_n8n", version_to=3)
    await _seed_ocg_delta(db_session, p1.id, "manual_recalc", version_to=4)
    await _seed_ocg_delta(db_session, p2.id, "document_ingestion_n8n", version_to=2)

    svc = MetricsService(db_session)
    rows = await svc._ocg_delta_aggregations()

    by_key = {(r["project_id"], r["trigger_source"]): r["count"] for r in rows}
    assert by_key.get((str(p1.id), "document_ingestion_n8n")) == 2
    assert by_key.get((str(p1.id), "manual_recalc")) == 1
    assert by_key.get((str(p2.id), "document_ingestion_n8n")) == 1


# =============================================================================
# Aggregations — `_ocg_negative_delta_block_aggregations`
# =============================================================================


@pytest.mark.asyncio
async def test_ocg_negative_delta_block_aggregations_counts_audit_events(db_session):
    """Conta eventos OCG_NEGATIVE_DELTA_BLOCKED em audit_log_global por project."""
    p1 = await _seed_project(db_session)
    p2 = await _seed_project(db_session)

    audit = AuditService(db_session)
    await audit.log_event(
        event_type=AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED,
        resource_type="ocg",
        resource_id=p1.id,
        details={"project_id": str(p1.id), "count": 2, "samples": []},
    )
    await audit.log_event(
        event_type=AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED,
        resource_type="ocg",
        resource_id=p1.id,
        details={"project_id": str(p1.id), "count": 1, "samples": []},
    )
    await audit.log_event(
        event_type=AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED,
        resource_type="ocg",
        resource_id=p2.id,
        details={"project_id": str(p2.id), "count": 1, "samples": []},
    )

    svc = MetricsService(db_session)
    rows = await svc._ocg_negative_delta_block_aggregations()

    by_proj = {r["project_id"]: r["count"] for r in rows}
    assert by_proj.get(str(p1.id)) == 2
    assert by_proj.get(str(p2.id)) == 1


@pytest.mark.asyncio
async def test_ocg_negative_delta_block_ignores_other_event_types(db_session):
    """Não conta outros tipos de evento."""
    p1 = await _seed_project(db_session)
    audit = AuditService(db_session)
    await audit.log_event(
        event_type=AuditEvents.OCG_UPDATED,
        resource_type="ocg",
        resource_id=p1.id,
    )

    svc = MetricsService(db_session)
    rows = await svc._ocg_negative_delta_block_aggregations()

    by_proj = {r["project_id"]: r["count"] for r in rows}
    assert by_proj.get(str(p1.id), 0) == 0


# =============================================================================
# Aggregations — `_codegen_block_aggregations`
# =============================================================================


@pytest.mark.asyncio
async def test_codegen_block_aggregations_parses_canonical_level(db_session):
    """Parseia block_level do prefixo `[ocg_gate:<level>]` em scaffold_runs.error."""
    p1 = await _seed_project(db_session)
    await _seed_scaffold_run_blocked(db_session, p1.id, "hard_block")
    await _seed_scaffold_run_blocked(db_session, p1.id, "hard_block")
    await _seed_scaffold_run_blocked(db_session, p1.id, "immature")
    await _seed_scaffold_run_blocked(db_session, p1.id, "no_ocg")

    svc = MetricsService(db_session)
    rows = await svc._codegen_block_aggregations()

    by_level = {r["block_level"]: r["count"] for r in rows}
    assert by_level.get("hard_block") == 2
    assert by_level.get("immature") == 1
    assert by_level.get("no_ocg") == 1


@pytest.mark.asyncio
async def test_codegen_block_aggregations_handles_non_canonical_error(db_session):
    """Run com status=blocked sem prefixo canônico → block_level='other'."""
    # NOTA: este teste cobre o caso "outro tipo de falha que não envolve gate".
    # Como o filtro WHERE LIKE '[ocg_gate:%' já exclui errors sem prefixo
    # canônico, o resultado esperado é COUNT=0 (não 'other') — ou seja, runs
    # com falhas comuns não contaminam a métrica do gate.
    p1 = await _seed_project(db_session)
    user = await create_test_user(db_session, is_admin=True)
    run = ScaffoldRun(
        id=uuid4(),
        project_id=p1.id,
        triggered_by=user.id,
        status="failed",
        error="Erro genérico sem prefixo canônico",
        finished_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()

    svc = MetricsService(db_session)
    rows = await svc._codegen_block_aggregations()

    # Filtro WHERE LIKE exclui errors sem prefixo canônico — métrica não conta
    # falhas que não vieram do gate. Resultado esperado: dict vazio ou sem
    # esse error genérico.
    by_level = {r["block_level"]: r["count"] for r in rows}
    assert by_level.get("other", 0) == 0
    # E não vaza para nenhum block_level válido
    assert sum(by_level.values()) == 0


# =============================================================================
# Render Prometheus — guarda os 3 contadores no texto
# =============================================================================


@pytest.mark.asyncio
async def test_prometheus_text_includes_3_new_counters(db_session):
    """O texto Prometheus inclui as 3 novas métricas com HELP+TYPE+linhas."""
    p1 = await _seed_project(db_session)
    await _seed_ocg_delta(db_session, p1.id, "document_ingestion_n8n", version_to=2)
    await AuditService(db_session).log_event(
        event_type=AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED,
        resource_type="ocg",
        resource_id=p1.id,
        details={"count": 1},
    )
    await _seed_scaffold_run_blocked(db_session, p1.id, "immature")

    svc = MetricsService(db_session)
    text = await svc.as_prometheus_text(hours=24)

    # HELP+TYPE
    assert "# HELP gca_ocg_delta_applied_total" in text
    assert "# TYPE gca_ocg_delta_applied_total counter" in text
    assert "# HELP gca_ocg_negative_delta_blocked_total" in text
    assert "# TYPE gca_ocg_negative_delta_blocked_total counter" in text
    assert "# HELP gca_codegen_blocked_total" in text
    assert "# TYPE gca_codegen_blocked_total counter" in text

    # Linhas com valores
    assert f'gca_ocg_delta_applied_total{{project="{p1.id}",trigger_source="document_ingestion_n8n"}} 1' in text
    assert f'gca_ocg_negative_delta_blocked_total{{project="{p1.id}"}} 1' in text
    assert 'gca_codegen_blocked_total{block_level="immature"} 1' in text


@pytest.mark.asyncio
async def test_prometheus_text_preserves_legacy_counters(db_session):
    """Não-regressão: contadores legados continuam no texto."""
    svc = MetricsService(db_session)
    text = await svc.as_prometheus_text(hours=24)

    # Contadores pré-DT-083
    for legacy in [
        "gca_ai_calls_total",
        "gca_ai_tokens_total",
        "gca_ai_cost_usd_total",
        "gca_audit_events_total",
        "gca_projects_total",
        "gca_users_total",
        "gca_celery_broker_reachable",
    ]:
        assert legacy in text, f"Métrica legada '{legacy}' sumiu do texto"


# =============================================================================
# Guards estáticos
# =============================================================================


def test_ocg_negative_delta_blocked_event_registered():
    """Guard: AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED é canônico (string fixa)."""
    assert AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED == "ocg_negative_delta_blocked"


def test_ocg_updater_emits_negative_delta_audit():
    """Guard: ocg_updater_service.py emite OCG_NEGATIVE_DELTA_BLOCKED."""
    from pathlib import Path

    src = (
        Path(__file__).parent.parent
        / "services"
        / "ocg_updater_service.py"
    ).read_text(encoding="utf-8")

    assert "AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED" in src, (
        "ocg_updater não emite o evento canônico — métrica DT-083 não popula"
    )
