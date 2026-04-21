"""MVP 14 Fase 14.8 — OCG consolidate_ocg explícito."""
import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    GlobalAuditLog,
    OCG,
    OCGDeltaLog,
    Organization,
    Project,
    Questionnaire,
    User,
)
from app.core.security import hash_password
from app.services.ocg_service import OCGService
from app.services.audit_service import AuditEvents


async def _seed(session, pillar_scores: dict, overall: float = 0.0, status: str = "NEEDS_REVIEW"):
    uid = uuid4()
    user = User(
        id=uid,
        email=f"ocg-148-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="OCG 14.8",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    org = Organization(
        id=uuid4(),
        name=f"Org {uid.hex[:6]}",
        slug=f"org-148-{uid.hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="Proj 148",
        slug=f"proj-148-{uid.hex[:6]}",
        description="fase 14.8",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    session.add(project)
    quest = Questionnaire(
        id=uuid4(),
        project_id=project.id,
        gp_email=user.email,
        responses="{}",
        status="ok",
        approved=True,
    )
    session.add(quest)
    await session.flush()

    ocg = OCG(
        project_id=project.id,
        questionnaire_id=quest.id,
        version=5,
        overall_score=overall,
        status=status,
        is_blocking=False,
        ocg_data=json.dumps({
            "PILLAR_SCORES": pillar_scores,
            "COMPOSITE_SCORE": {"overall": overall, "is_blocking": False, "status": status},
        }),
    )
    session.add(ocg)
    await session.flush()
    return user, project, ocg


@pytest.mark.asyncio
async def test_consolidate_recomputes_score_ready(db_session):
    """P≥90 em todos os pilares → READY + nova versão + delta + audit."""
    pillars = {f"P{i}": {"score": 95} for i in range(1, 8)}
    user, project, ocg = await _seed(db_session, pillars, overall=0, status="AT_RISK")

    result = await OCGService(db_session).consolidate_ocg(
        project_id=project.id, actor_id=user.id
    )

    assert result["changed"] is True
    assert result["previous_version"] == 5
    assert result["new_version"] == 6
    assert result["overall_score"] == 95.0
    assert result["status"] == "READY"
    assert result["is_blocking"] is False

    ocg_fresh = (await db_session.execute(
        select(OCG).where(OCG.project_id == project.id)
    )).scalar_one()
    assert ocg_fresh.version == 6
    assert ocg_fresh.status == "READY"

    delta = (await db_session.execute(
        select(OCGDeltaLog).where(
            OCGDeltaLog.project_id == project.id,
            OCGDeltaLog.trigger_source == "consolidation",
        )
    )).scalar_one()
    assert delta.ocg_version_to == 6

    audit = (await db_session.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.event_type == AuditEvents.OCG_CONSOLIDATED,
            GlobalAuditLog.resource_id == project.id,
        )
    )).scalar_one()
    details = json.loads(audit.details)
    assert details["version_to"] == 6
    assert details["extra"]["status_after"] == "READY"


@pytest.mark.asyncio
async def test_consolidate_p7_below_70_blocks(db_session):
    """P7<70 → BLOCKED mesmo com score alto."""
    pillars = {f"P{i}": {"score": 95} for i in range(1, 7)}
    pillars["P7"] = {"score": 50}
    user, project, _ = await _seed(db_session, pillars, overall=0, status="AT_RISK")

    result = await OCGService(db_session).consolidate_ocg(
        project_id=project.id, actor_id=user.id
    )

    assert result["status"] == "BLOCKED"
    assert result["is_blocking"] is True


@pytest.mark.asyncio
async def test_consolidate_idempotent_no_change(db_session):
    """Rodar consolidação duas vezes — segunda é no-op."""
    pillars = {f"P{i}": {"score": 80} for i in range(1, 8)}
    user, project, _ = await _seed(db_session, pillars, overall=0, status="AT_RISK")

    svc = OCGService(db_session)
    first = await svc.consolidate_ocg(project_id=project.id, actor_id=user.id)
    assert first["changed"] is True

    second = await svc.consolidate_ocg(project_id=project.id, actor_id=user.id)
    assert second["changed"] is False
    assert second["version"] == first["new_version"]


@pytest.mark.asyncio
async def test_consolidate_missing_ocg_raises(db_session):
    with pytest.raises(ValueError, match="OCG do projeto não encontrado"):
        await OCGService(db_session).consolidate_ocg(
            project_id=uuid4(), actor_id=None
        )
