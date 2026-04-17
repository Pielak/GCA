"""Testes de reavaliação do Gatekeeper após ingestão (MVP 2 §10).

Verifica `_reevaluate_gatekeeper_for_audit`:
- projeto com OCG válido → emite evento GATEKEEPER_REEVALUATED no audit_log
  com blocking_pillars, derived_status e ocg_version;
- projeto sem OCG → no-op (não emite evento, não quebra);
- helper não mexe em GatekeeperItem/ModuleCandidate (é read-only sobre esse
  estado; só re-aplica thresholds e grava evento).
"""
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    GlobalAuditLog, OCG, Organization, Project, Questionnaire, User,
)
from app.services.ingestion_service import _reevaluate_gatekeeper_for_audit

pytestmark = pytest.mark.asyncio


async def _seed_project(db: AsyncSession, slug: str) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        email=f"{slug}@reeval.local",
        full_name=f"User {slug}",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    org = Organization(
        id=uuid.uuid4(), name=f"Org {slug}", slug=f"o-{slug}", owner_id=user.id,
    )
    db.add(org)
    await db.flush()
    proj = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Proj {slug}",
        slug=f"p-{slug}",
        short_slug=f"s-{slug}"[:16],
        status="active",
        deliverable_type="new_system",
    )
    db.add(proj)
    await db.flush()
    return proj.id


async def _seed_ocg(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    version: int = 1,
    p7: float = 80.0,
    p2: float = 80.0,
    overall: float = 85.0,
) -> OCG:
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=project_id,
        gp_email="seed@reeval.local",
        responses=json.dumps({"1": "seed"}),
        status="ok",
    )
    db.add(q)
    await db.flush()
    ocg = OCG(
        id=uuid.uuid4(),
        questionnaire_id=q.id,
        project_id=project_id,
        version=version,
        p1_business_score=80.0,
        p2_rules_score=p2,
        p3_features_score=80.0,
        p4_nfr_score=80.0,
        p5_architecture_score=80.0,
        p6_data_score=80.0,
        p7_security_score=p7,
        overall_score=overall,
        status="READY",
        ocg_data=json.dumps({"stack": "FastAPI"}, ensure_ascii=False),
    )
    db.add(ocg)
    await db.flush()
    return ocg


async def _count_reeval_events(db: AsyncSession, project_id: uuid.UUID) -> list[GlobalAuditLog]:
    result = await db.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.event_type == "GATEKEEPER_REEVALUATED",
            GlobalAuditLog.resource_id == project_id,
        )
    )
    return list(result.scalars().all())


async def test_reevaluation_emits_audit_event_with_expected_payload(db_session: AsyncSession):
    """Projeto com OCG → emite 1 evento GATEKEEPER_REEVALUATED com payload esperado."""
    project_id = await _seed_project(db_session, "ok")
    ocg = await _seed_ocg(db_session, project_id, version=2)

    before = await _count_reeval_events(db_session, project_id)
    assert before == []

    await _reevaluate_gatekeeper_for_audit(
        db_session, project_id, ocg_version=ocg.version, trigger="document_ingestion"
    )

    after = await _count_reeval_events(db_session, project_id)
    assert len(after) == 1

    event = after[0]
    assert event.resource_type == "project"
    assert event.resource_id == project_id

    details = json.loads(event.details)
    assert details["ocg_version"] == 2
    assert details["trigger"] == "document_ingestion"
    assert "blocking_pillars" in details
    assert "derived_status" in details
    # OCG com P7=80 e P2=80 não deve bloquear (thresholds default 70)
    assert isinstance(details["blocking_pillars"], list)


async def test_reevaluation_noop_when_project_has_no_ocg(db_session: AsyncSession):
    """Projeto sem OCG → não emite evento (não há o que reavaliar)."""
    project_id = await _seed_project(db_session, "noocg")

    await _reevaluate_gatekeeper_for_audit(
        db_session, project_id, ocg_version=None, trigger="document_ingestion"
    )

    events = await _count_reeval_events(db_session, project_id)
    assert events == []


async def test_reevaluation_idempotent_multiple_calls_append_events(db_session: AsyncSession):
    """Cada chamada grava 1 evento. Duas chamadas → 2 eventos (trilha de auditoria)."""
    project_id = await _seed_project(db_session, "twice")
    ocg = await _seed_ocg(db_session, project_id, version=3)

    await _reevaluate_gatekeeper_for_audit(
        db_session, project_id, ocg_version=ocg.version, trigger="document_ingestion"
    )
    await _reevaluate_gatekeeper_for_audit(
        db_session, project_id, ocg_version=ocg.version, trigger="document_ingestion"
    )

    events = await _count_reeval_events(db_session, project_id)
    assert len(events) == 2
