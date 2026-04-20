"""MVP 12 Fase 12.3 — Consolidar semântica de `accepted_at` / `joined_at`.

Contrato §7 MVP 12 Fase 12.3:
- `admin_service.approve_project_request` cria GP com `accepted_at` e
  `joined_at` preenchidos (soberano direto, não passa por aceite).
- Helper canônico `is_pending_invite(member)` retorna True apenas para
  `invite_token IS NOT NULL AND joined_at IS NULL AND revoked_at IS
  NULL AND is_active`.
- Helper canônico `is_active_integrated_member(member)` retorna True
  para `is_active AND joined_at IS NOT NULL` — cobre convidados que
  aceitaram E GPs criados por caminho direto.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.project_team_service import (
    is_pending_invite,
    is_active_integrated_member,
)


# ─── Helper is_pending_invite ─────────────────────────────────────────


def _member(**kwargs) -> SimpleNamespace:
    """Builder de ProjectMember-like para teste de semântica (sem DB)."""
    return SimpleNamespace(
        is_active=kwargs.get("is_active", True),
        invite_token=kwargs.get("invite_token"),
        joined_at=kwargs.get("joined_at"),
        accepted_at=kwargs.get("accepted_at"),
        revoked_at=kwargs.get("revoked_at"),
        role=kwargs.get("role", "dev"),
    )


def test_is_pending_invite_true_when_canonical_pending():
    m = _member(invite_token="tok", joined_at=None, is_active=True)
    assert is_pending_invite(m) is True


def test_is_pending_invite_false_when_joined():
    m = _member(invite_token="tok", joined_at=datetime.now(timezone.utc), is_active=True)
    assert is_pending_invite(m) is False


def test_is_pending_invite_false_when_revoked():
    m = _member(invite_token="tok", joined_at=None, revoked_at=datetime.now(timezone.utc))
    assert is_pending_invite(m) is False


def test_is_pending_invite_false_when_inactive():
    m = _member(invite_token="tok", joined_at=None, is_active=False)
    assert is_pending_invite(m) is False


def test_is_pending_invite_false_when_no_token():
    """GP criado por aprovação-de-projeto não tem invite_token — não é convite pendente."""
    m = _member(invite_token=None, joined_at=None, is_active=True)
    assert is_pending_invite(m) is False


def test_is_pending_invite_gracefully_handles_none():
    assert is_pending_invite(None) is False


# ─── Helper is_active_integrated_member ───────────────────────────────


def test_active_integrated_true_when_joined_with_or_without_accepted():
    """Aceitou via convite: tem accepted_at + joined_at."""
    m1 = _member(
        joined_at=datetime.now(timezone.utc),
        accepted_at=datetime.now(timezone.utc),
        is_active=True,
    )
    assert is_active_integrated_member(m1) is True

    """Admin approve (direto): tem joined_at + accepted_at ambos (após Fase 12.3)."""
    m2 = _member(
        joined_at=datetime.now(timezone.utc),
        accepted_at=datetime.now(timezone.utc),
        is_active=True,
    )
    assert is_active_integrated_member(m2) is True


def test_active_integrated_false_when_not_joined():
    m = _member(joined_at=None, accepted_at=None, is_active=True, invite_token="tok")
    assert is_active_integrated_member(m) is False


def test_active_integrated_false_when_inactive():
    m = _member(joined_at=datetime.now(timezone.utc), is_active=False)
    assert is_active_integrated_member(m) is False


def test_active_integrated_gracefully_handles_none():
    assert is_active_integrated_member(None) is False


# ─── admin_service.approve_project_request preenche timestamps ────────


@pytest.mark.asyncio
async def test_approve_project_request_creates_gp_with_both_timestamps():
    """Fluxo de aprovação: GP membro criado com accepted_at e joined_at preenchidos."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, ProjectMember
    from app.models.onboarding import ProjectRequest, ProjectRequestStatus, DeliverableType
    from app.services.admin_service import AdminService
    from app.core.security import hash_password

    admin_id = uuid4()
    gp_id = uuid4()
    request_id = uuid4()

    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(
                    id=admin_id,
                    email=f"mvp12-f123-admin-{admin_id.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F123 Admin",
                    is_active=True, is_admin=True,
                    created_at=datetime.utcnow(),
                ))
                session.add(User(
                    id=gp_id,
                    email=f"mvp12-f123-gp-{gp_id.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name=f"F123 GP {gp_id.hex[:6]}",
                    is_active=False, is_admin=False,
                    created_at=datetime.utcnow(),
                ))
                await session.flush()
                # approve_project_request cria org internamente; não pré-crio aqui.
                session.add(ProjectRequest(
                    id=request_id,
                    gp_id=gp_id,
                    project_name=f"F123 Proj {request_id.hex[:6]}",
                    project_slug=f"f123-proj-{request_id.hex[:6]}",
                    description="descricao",
                    deliverable_type="new_system",
                    status=ProjectRequestStatus.PENDING,
                    requested_at=datetime.utcnow(),
                ))

        async with AsyncSessionLocal() as session:
            svc = AdminService(session)
            result = await svc.approve_project_request(
                request_id=request_id, admin_id=admin_id,
            )
        # result é o ProjectRequest atualizado; o project criado tem mesmo slug
        assert result is not None

        # Valida: ProjectMember criado tem ambos os timestamps
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            from app.models.base import Project
            proj_res = await session.execute(
                select(Project).where(Project.slug == result.project_slug)
            )
            proj = proj_res.scalar_one()
            res = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == proj.id)
                    & (ProjectMember.user_id == gp_id)
                )
            )
            member = res.scalar_one()
            assert member.accepted_at is not None, "accepted_at deveria estar preenchido"
            assert member.joined_at is not None, "joined_at deveria estar preenchido"
            assert member.is_active is True
            assert member.role == "gp"
            assert is_active_integrated_member(member) is True
            assert is_pending_invite(member) is False
    finally:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select, text
        from app.models.base import Project, Organization
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Cleanup em ordem: onboarding_progress, membership, project,
                # org, project_request, users. FKs estritas exigem ordem.
                req_res = await session.execute(
                    select(ProjectRequest).where(ProjectRequest.id == request_id)
                )
                pr = req_res.scalar_one_or_none()
                if pr and pr.project_slug:
                    proj_res = await session.execute(
                        select(Project).where(Project.slug == pr.project_slug)
                    )
                    proj = proj_res.scalar_one_or_none()
                    if proj:
                        org_to_del = proj.organization_id
                        await session.execute(
                            ProjectMember.__table__.delete().where(ProjectMember.project_id == proj.id)
                        )
                        await session.execute(Project.__table__.delete().where(Project.id == proj.id))
                        if org_to_del:
                            await session.execute(Organization.__table__.delete().where(Organization.id == org_to_del))
                # Onboarding progress refere project_requests por FK
                await session.execute(text("DELETE FROM onboarding_progress WHERE project_id = :rid"), {"rid": str(request_id)})
                await session.execute(ProjectRequest.__table__.delete().where(ProjectRequest.id == request_id))
                await session.execute(User.__table__.delete().where(User.id.in_([admin_id, gp_id])))
