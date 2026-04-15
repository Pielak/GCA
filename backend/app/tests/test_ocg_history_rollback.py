"""Testes do histórico do OCG + rollback."""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.base import (
    OCG,
    OCGDeltaLog,
    Organization,
    Project,
    ProjectMember,
    Questionnaire,
    User,
)
from app.core.security import create_access_token, hash_password
from app.db.database import AsyncSessionLocal


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Helpers — usam db_session (transação fake) para testes de serviço
# ou AsyncSessionLocal (commit real) para testes de endpoint HTTP.
# ---------------------------------------------------------------------------

async def _make_user(session: AsyncSession) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        email=f"ocg-test-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="OCG Tester",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    await session.flush()
    return user


async def _make_org(session: AsyncSession, owner_id) -> Organization:
    uid = uuid4()
    org = Organization(
        id=uid,
        name=f"OCG Org {uid.hex[:6]}",
        slug=f"ocg-org-{uid.hex[:6]}",
        owner_id=owner_id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(org)
    await session.flush()
    return org


async def _make_project(session: AsyncSession, org_id) -> Project:
    uid = uuid4()
    project = Project(
        id=uid,
        organization_id=org_id,
        name="OCG Test Project",
        slug=f"ocg-proj-{uid.hex[:6]}",
        description="Projeto para testes de OCG history/rollback",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    session.add(project)
    await session.flush()
    return project


# ---------------------------------------------------------------------------
# Testes de serviço — usam db_session (transação fake, sem commit real)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_delta_without_document_id_is_persisted(db_session):
    """Delta sem document_id ainda assim é gravado (regressão do early-return antigo)."""
    from app.services.ocg_updater_service import OCGUpdaterService

    user = await _make_user(db_session)
    org = await _make_org(db_session, user.id)
    project = await _make_project(db_session, org.id)

    updater = OCGUpdaterService(db_session)
    await updater._log_delta(
        project_id=project.id,
        document_id=None,
        ocg_version_from=1,
        ocg_version_to=2,
        changes=[{"field": "STACK", "old_value": "a", "new_value": "b", "reasoning": "update"}],
        changed_by=user.id,
        trigger_source="manual_edit",
        ocg_snapshot={"STACK": "b"},
    )
    await db_session.flush()

    result = await db_session.execute(
        select(OCGDeltaLog).where(OCGDeltaLog.project_id == project.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].document_id is None
    assert rows[0].trigger_source == "manual_edit"
    assert rows[0].changed_by == user.id
    assert rows[0].ocg_snapshot is not None


@pytest.mark.asyncio
async def test_log_delta_preserves_snapshot_json(db_session):
    """Snapshot é persistido como JSON válido para permitir rollback."""
    from app.services.ocg_updater_service import OCGUpdaterService

    user = await _make_user(db_session)
    org = await _make_org(db_session, user.id)
    project = await _make_project(db_session, org.id)

    updater = OCGUpdaterService(db_session)
    snap = {"PILLAR_SCORES": {"P1": 85}, "COMPOSITE_SCORE": 82}
    await updater._log_delta(
        project_id=project.id,
        document_id=None,
        ocg_version_from=1,
        ocg_version_to=2,
        changes=[],
        trigger_source="pillar_agent",
        ocg_snapshot=snap,
    )
    await db_session.flush()

    result = await db_session.execute(
        select(OCGDeltaLog).where(OCGDeltaLog.project_id == project.id)
    )
    row = result.scalar_one()
    assert json.loads(row.ocg_snapshot) == snap


# ---------------------------------------------------------------------------
# Testes de endpoint — precisam de AsyncSessionLocal (commit real) pois o
# endpoint HTTP usa uma sessão diferente do conftest db_session.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_endpoint_creates_new_version():
    """Rollback não destrói histórico — cria nova versão com trigger_source='rollback'."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_user(session)
            org = await _make_org(session, user.id)
            project = await _make_project(session, org.id)

            # Adicionar test_user como GP para ter project:manage_team
            member = ProjectMember(
                project_id=project.id,
                user_id=user.id,
                role="gp",
                is_active=True,
            )
            session.add(member)

            # Questionnaire (FK obrigatória do OCG)
            questionnaire = Questionnaire(
                id=uuid4(),
                project_id=project.id,
                gp_email=user.email,
                responses="{}",
                status="ok",
                approved=True,
            )
            session.add(questionnaire)
            await session.flush()

            # OCG em v2
            ocg = OCG(
                project_id=project.id,
                questionnaire_id=questionnaire.id,
                version=2,
                ocg_data=json.dumps({"STACK": "v2"}),
            )
            session.add(ocg)
            await session.flush()

            # Snapshot v1 disponível
            session.add(OCGDeltaLog(
                project_id=project.id,
                ocg_version_from=0,
                ocg_version_to=1,
                fields_changed="{}",
                trigger_source="document_ingestion",
                ocg_snapshot=json.dumps({"STACK": "v1"}),
            ))
        # commit implícito pelo context manager

    token = create_access_token(data={"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    async with _client() as client:
        resp = await client.post(
            f"/api/v1/projects/{project.id}/ocg/rollback/1",
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_version"] == 3
    assert body["restored_from"] == 1

    # Verificar no DB que OCG foi atualizado
    async with AsyncSessionLocal() as session:
        ocg_updated = (await session.execute(
            select(OCG).where(OCG.project_id == project.id)
        )).scalar_one()
        assert json.loads(ocg_updated.ocg_data) == {"STACK": "v1"}
        assert ocg_updated.version == 3

        r = await session.execute(
            select(OCGDeltaLog).where(
                OCGDeltaLog.project_id == project.id,
                OCGDeltaLog.trigger_source == "rollback",
            )
        )
        rollback_entry = r.scalar_one()
        assert rollback_entry.ocg_version_to == 3

    # Cleanup via DELETE direto (evita problema de cascade ORM com NOT NULL FK)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))


@pytest.mark.asyncio
async def test_rollback_404_when_no_snapshot():
    """Rollback para versão sem snapshot retorna 404."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_user(session)
            org = await _make_org(session, user.id)
            project = await _make_project(session, org.id)
            member = ProjectMember(
                project_id=project.id,
                user_id=user.id,
                role="gp",
                is_active=True,
            )
            session.add(member)

    token = create_access_token(data={"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    async with _client() as client:
        resp = await client.post(
            f"/api/v1/projects/{project.id}/ocg/rollback/999",
            headers=headers,
        )
    assert resp.status_code == 404

    # Cleanup via DELETE direto (cascade do FK limpa ProjectMember)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))
