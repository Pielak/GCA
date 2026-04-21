"""MVP 14 Fase 14.7 — OCG rollback_to_version formal.

Valida:
- `OCGService.rollback_to_version` lê snapshot, cria nova versão e grava delta rollback.
- Evento canônico `OCG_ROLLED_BACK` emitido em `audit_log_global`.
"""
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


async def _seed(session):
    uid = uuid4()
    user = User(
        id=uid,
        email=f"ocg-147-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="OCG 14.7",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    org = Organization(
        id=uuid4(),
        name=f"Org {uid.hex[:6]}",
        slug=f"org-147-{uid.hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="Proj 147",
        slug=f"proj-147-{uid.hex[:6]}",
        description="fase 14.7",
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
        version=2,
        ocg_data=json.dumps({"STACK": "v2"}),
    )
    session.add(ocg)
    session.add(OCGDeltaLog(
        project_id=project.id,
        ocg_version_from=0,
        ocg_version_to=1,
        fields_changed="{}",
        trigger_source="document_ingestion",
        ocg_snapshot=json.dumps({"STACK": "v1"}),
    ))
    await session.flush()
    return user, project


@pytest.mark.asyncio
async def test_rollback_to_version_creates_new_version(db_session):
    user, project = await _seed(db_session)

    result = await OCGService(db_session).rollback_to_version(
        project_id=project.id,
        version_to=1,
        actor_id=user.id,
    )

    assert result["previous_version"] == 2
    assert result["new_version"] == 3
    assert result["restored_from"] == 1

    ocg = (await db_session.execute(
        select(OCG).where(OCG.project_id == project.id)
    )).scalar_one()
    assert ocg.version == 3
    assert json.loads(ocg.ocg_data) == {"STACK": "v1"}

    rollback_delta = (await db_session.execute(
        select(OCGDeltaLog).where(
            OCGDeltaLog.project_id == project.id,
            OCGDeltaLog.trigger_source == "rollback",
        )
    )).scalar_one()
    assert rollback_delta.ocg_version_to == 3
    assert rollback_delta.changed_by == user.id


@pytest.mark.asyncio
async def test_rollback_emits_canonical_audit_event(db_session):
    user, project = await _seed(db_session)

    await OCGService(db_session).rollback_to_version(
        project_id=project.id,
        version_to=1,
        actor_id=user.id,
    )

    audit_rows = (await db_session.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.event_type == AuditEvents.OCG_ROLLED_BACK,
            GlobalAuditLog.resource_id == project.id,
        )
    )).scalars().all()
    assert len(audit_rows) == 1
    entry = audit_rows[0]
    assert entry.resource_type == "ocg"
    assert entry.actor_id == user.id
    details = json.loads(entry.details)
    assert details["version_from"] == 2
    assert details["version_to"] == 3
    assert details["restored_from"] == 1


@pytest.mark.asyncio
async def test_rollback_missing_snapshot_raises(db_session):
    user, project = await _seed(db_session)

    with pytest.raises(ValueError, match="Snapshot não disponível"):
        await OCGService(db_session).rollback_to_version(
            project_id=project.id,
            version_to=999,
            actor_id=user.id,
        )
