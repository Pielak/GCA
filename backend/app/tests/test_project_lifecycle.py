"""Testes do lifecycle de projeto (2026-04-19):
- set_project_status transita entre active/paused/inactive
- Rejeita status inválido
- Projeto inexistente → ValueError
- Só Admin pode
"""
import pytest
from sqlalchemy import select

from app.models.base import Project
from app.services import admin_management_service as svc
from app.tests.factories import create_test_organization, create_test_project, create_test_user


@pytest.mark.asyncio
async def test_set_project_status_active_to_paused(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="lc-paused")

    updated = await svc.set_project_status(
        db_session, project_id=p.id, new_status="paused", actor_id=actor.id,
    )
    assert updated.status == "paused"

    # DB reflete a mudança
    found = (await db_session.execute(
        select(Project).where(Project.id == p.id)
    )).scalar_one()
    assert found.status == "paused"


@pytest.mark.asyncio
async def test_set_project_status_to_inactive_preserves_slug(db_session):
    """inactive não apaga nada — slug/name/id preservados."""
    actor = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="lc-inactive")

    updated = await svc.set_project_status(
        db_session, project_id=p.id, new_status="inactive", actor_id=actor.id,
    )
    assert updated.status == "inactive"
    assert updated.slug == "lc-inactive"
    assert updated.id == p.id


@pytest.mark.asyncio
async def test_set_project_status_noop_when_same(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="lc-noop")

    # p criado já vem active — chamar active novamente não quebra
    updated = await svc.set_project_status(
        db_session, project_id=p.id, new_status="active", actor_id=actor.id,
    )
    assert updated.status == "active"


@pytest.mark.asyncio
async def test_set_project_status_rejects_invalid(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="lc-bad")

    with pytest.raises(ValueError, match="Status inválido"):
        await svc.set_project_status(
            db_session, project_id=p.id, new_status="explodido", actor_id=actor.id,
        )


@pytest.mark.asyncio
async def test_set_project_status_rejects_unknown_project(db_session):
    from uuid import uuid4
    actor = await create_test_user(db_session, is_admin=True)
    with pytest.raises(ValueError, match="não encontrado"):
        await svc.set_project_status(
            db_session, project_id=uuid4(), new_status="paused", actor_id=actor.id,
        )


@pytest.mark.asyncio
async def test_set_project_status_requires_admin(db_session):
    actor = await create_test_user(db_session, is_admin=False)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="lc-noperm")

    with pytest.raises(PermissionError, match="Admin"):
        await svc.set_project_status(
            db_session, project_id=p.id, new_status="paused", actor_id=actor.id,
        )
