"""Testes da extensão 2026-04-19:
- Métricas por projeto (MetricsService.as_dashboard_dict(project_id=...))
- Gestão de admin (admin_management_service.set_admin_flag / invite_admin)

Cobertura:
- as_dashboard_dict global mantém users + projects
- as_dashboard_dict com project_id omite users + projects; filtra
  ai_usage por AIUsageLog.project_id
- set_admin_flag promove/rebaixa; não-admin não pode; último admin
  não pode se auto-rebaixar
- invite_admin cria novo user com is_admin=True + senha retornada
  quando email não é enviado
- invite_admin promove user existente sem mexer na senha
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import AIUsageLog, User
from app.services import admin_management_service as mgmt_svc
from app.services.metrics_service import MetricsService
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ─── Métricas por projeto ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_global_includes_users_and_projects(db_session):
    svc = MetricsService(db_session)
    d = await svc.as_dashboard_dict(hours=24)
    assert d["scope"] == "global"
    assert d["project_id"] is None
    assert "users" in d
    assert "projects" in d


@pytest.mark.asyncio
async def test_dashboard_project_scoped_filters_ai_usage(db_session):
    org = await create_test_organization(db_session)
    p_a = await create_test_project(db_session, organization_id=org.id, slug="met-a")
    p_b = await create_test_project(db_session, organization_id=org.id, slug="met-b")

    # Seed: 2 chamadas em P_A, 3 em P_B
    for _ in range(2):
        db_session.add(AIUsageLog(
            id=uuid4(), project_id=p_a.id, provider="anthropic",
            model="claude", operation="analyze", tokens_input=10,
            tokens_output=20, cost_usd=0.01, created_at=datetime.now(timezone.utc),
        ))
    for _ in range(3):
        db_session.add(AIUsageLog(
            id=uuid4(), project_id=p_b.id, provider="anthropic",
            model="claude", operation="analyze", tokens_input=5,
            tokens_output=10, cost_usd=0.005, created_at=datetime.now(timezone.utc),
        ))
    await db_session.commit()

    svc = MetricsService(db_session)

    # Global soma tudo (ao menos 5 chamadas — o teste pode ter outras)
    d_global = await svc.as_dashboard_dict(hours=1)
    total_global = sum(r["calls"] for r in d_global["ai_usage"]["rows"])
    assert total_global >= 5

    # Escopo P_A → só as 2 dele
    d_a = await svc.as_dashboard_dict(hours=1, project_id=p_a.id)
    assert d_a["scope"] == "project"
    assert d_a["project_id"] == str(p_a.id)
    assert "users" not in d_a
    assert "projects" not in d_a
    total_a = sum(r["calls"] for r in d_a["ai_usage"]["rows"])
    assert total_a == 2

    # Escopo P_B → 3
    d_b = await svc.as_dashboard_dict(hours=1, project_id=p_b.id)
    total_b = sum(r["calls"] for r in d_b["ai_usage"]["rows"])
    assert total_b == 3


# ─── Gestão de admin ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_admin_flag_promote_and_demote(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    other_admin = await create_test_user(db_session, is_admin=True)  # evita órfão
    target = await create_test_user(db_session, is_admin=False)

    u = await mgmt_svc.set_admin_flag(
        db_session, target_user_id=target.id, new_value=True, actor_id=actor.id,
    )
    assert u.is_admin is True

    u2 = await mgmt_svc.set_admin_flag(
        db_session, target_user_id=target.id, new_value=False, actor_id=actor.id,
    )
    assert u2.is_admin is False


@pytest.mark.asyncio
async def test_set_admin_flag_does_not_touch_support(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    other = await create_test_user(db_session, is_admin=True)  # evita órfão
    target = await create_test_user(db_session, is_admin=False)
    target.is_support = True
    await db_session.flush()

    u = await mgmt_svc.set_admin_flag(
        db_session, target_user_id=target.id, new_value=True, actor_id=actor.id,
    )
    assert u.is_admin is True
    assert u.is_support is True


@pytest.mark.asyncio
async def test_non_admin_cannot_toggle(db_session):
    user = await create_test_user(db_session, is_admin=False)
    target = await create_test_user(db_session, is_admin=False)
    with pytest.raises(PermissionError, match="Admin"):
        await mgmt_svc.set_admin_flag(
            db_session, target_user_id=target.id, new_value=True, actor_id=user.id,
        )


@pytest.mark.asyncio
async def test_last_admin_cannot_self_demote(db_session):
    """Se só existe 1 admin ativo e ele tenta se rebaixar → PermissionError."""
    # Desativa quaisquer admins pré-existentes criados por outros testes
    existing_admins = (await db_session.execute(
        select(User).where(User.is_admin.is_(True), User.is_active.is_(True))
    )).scalars().all()
    for a in existing_admins:
        a.is_active = False
    await db_session.flush()

    only_admin = await create_test_user(db_session, is_admin=True)

    with pytest.raises(PermissionError, match="último"):
        await mgmt_svc.set_admin_flag(
            db_session, target_user_id=only_admin.id, new_value=False, actor_id=only_admin.id,
        )


@pytest.mark.asyncio
async def test_invite_admin_creates_new_user(db_session, monkeypatch):
    actor = await create_test_user(db_session, is_admin=True)

    # Mockando o email service pra não tentar SMTP real
    from app.services.email_service import EmailService
    monkeypatch.setattr(
        EmailService, "send_admin_invitation_email",
        lambda **kwargs: (False, "smtp off"),
    )

    email = f"novoadm-{uuid4().hex[:6]}@example.com"
    result = await mgmt_svc.invite_admin(
        db_session, email=email, full_name="Novo Admin", actor_id=actor.id,
    )
    assert result["created"] is True
    assert result["email_sent"] is False
    # Como email falhou, senha é retornada pra admin comunicar manual
    assert result["temp_password"] is not None
    assert len(result["temp_password"]) >= 10

    # User de fato gravado como admin
    found = (await db_session.execute(
        select(User).where(User.email == email)
    )).scalar_one()
    assert found.is_admin is True
    assert found.is_active is True
    assert found.first_access_completed is False


@pytest.mark.asyncio
async def test_invite_admin_promotes_existing_user(db_session, monkeypatch):
    actor = await create_test_user(db_session, is_admin=True)
    from app.services.email_service import EmailService
    monkeypatch.setattr(
        EmailService, "send_admin_invitation_email",
        lambda **kwargs: (True, None),
    )

    existing_email = f"existente-{uuid4().hex[:6]}@example.com"
    existing = await create_test_user(
        db_session, email=existing_email, is_admin=False,
    )
    old_hash = existing.password_hash

    result = await mgmt_svc.invite_admin(
        db_session, email=existing_email, full_name="Já existe",
        actor_id=actor.id,
    )
    assert result["created"] is False

    # Mesmo user, agora admin, com senha inalterada
    refreshed = (await db_session.execute(
        select(User).where(User.id == existing.id)
    )).scalar_one()
    assert refreshed.is_admin is True
    assert refreshed.password_hash == old_hash


@pytest.mark.asyncio
async def test_invite_admin_rejects_bad_email(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    with pytest.raises(ValueError, match="Email"):
        await mgmt_svc.invite_admin(
            db_session, email="not-an-email", full_name="X", actor_id=actor.id,
        )


@pytest.mark.asyncio
async def test_invite_admin_rejects_empty_name(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    with pytest.raises(ValueError, match="Nome"):
        await mgmt_svc.invite_admin(
            db_session, email="x@y.com", full_name="   ", actor_id=actor.id,
        )
