"""MVP 11 Fase 11.4 — Auditoria canônica de eventos de papel.

Contrato §7 MVP 11 Fase 11.4:
- Eventos canônicos em `audit_log_global`: role_granted, role_revoked,
  role_transferred.
- Payload mínimo: actor_id, target_user_id, project_id (nullable na
  instância), old_role, new_role, phase, timestamp.
- Cobertura obrigatória: convite emitido, convite aceito, convite
  revogado, promoção/rebaixamento de Admin, desativação de user com
  papel ativo.
- Transferência de soberania (phase='transferred') é emitida pela
  Fase 11.2 — aqui só valida que o evento canônico foi reservado.
"""
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, desc

from app.main import app
from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_gp_project():
    """Cria User (GP) + Org + Project + ProjectMember (role=gp). Retorna (uid, org_id, project_id)."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember

    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(
                id=uid,
                email=f"mvp11-f114-gp-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="MVP11 F114 GP",
                is_active=True,
                is_admin=False,
                created_at=datetime.utcnow(),
            ))
            session.add(Organization(
                id=org_id,
                name=f"Org {uid.hex[:6]}",
                slug=f"org-f114-{uid.hex[:6]}",
                owner_id=uid,
                is_active=True,
                created_at=datetime.utcnow(),
            ))
            await session.flush()
            session.add(Project(
                id=project_id,
                organization_id=org_id,
                name=f"P f114 {uid.hex[:6]}",
                slug=f"p-f114-{uid.hex[:6]}",
                status="active",
                deliverable_type="new_system",
                created_at=datetime.utcnow(),
            ))
            await session.flush()
            session.add(ProjectMember(
                id=uuid4(),
                project_id=project_id,
                user_id=uid,
                role="gp",
                is_active=True,
                invited_at=datetime.utcnow(),
                joined_at=datetime.utcnow(),
            ))
    return uid, org_id, project_id


async def _cleanup(uid, org_id, project_id):
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember, GlobalAuditLog

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Audit log entries geradas pelos testes deste projeto
            await session.execute(
                GlobalAuditLog.__table__.delete().where(
                    GlobalAuditLog.actor_id.in_(
                        select(User.id).where(User.email.like("mvp11-f114-%@test.com"))
                    )
                )
            )
            await session.execute(
                ProjectMember.__table__.delete().where(ProjectMember.project_id == project_id)
            )
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            await session.execute(User.__table__.delete().where(User.email.like("mvp11-f114-%@test.com")))
            await session.execute(User.__table__.delete().where(User.id == uid))


async def _latest_role_audit_for_actor(actor_id):
    """Retorna o evento de role mais recente cujo actor é `actor_id`."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import GlobalAuditLog

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GlobalAuditLog)
            .where(
                (GlobalAuditLog.actor_id == actor_id)
                & GlobalAuditLog.event_type.in_(["role_granted", "role_revoked", "role_transferred"])
            )
            .order_by(desc(GlobalAuditLog.created_at))
            .limit(1)
        )
        return res.scalar_one_or_none()


# ─── Evento role_granted no convite emitido ──────────────────────────


@pytest.mark.asyncio
async def test_invite_emits_role_granted_invited_phase():
    uid, org_id, project_id = await _make_gp_project()
    invitee_email = f"mvp11-f114-invitee-{uuid4().hex[:6]}@test.com"
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": invitee_email, "role": "gp"},
            )
        assert resp.status_code == 200, resp.text

        audit = await _latest_role_audit_for_actor(uid)
        assert audit is not None, "invite não registrou evento role_granted"
        assert audit.event_type == "role_granted"
        assert audit.resource_type == "project_member"

        details = json.loads(audit.details)
        assert details["project_id"] == str(project_id)
        assert details["new_role"] == "gp"
        assert details["old_role"] is None
        assert details["phase"] == "invited"
        assert details["target_user_id"] is not None
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Evento role_granted no aceite ────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_emits_role_granted_accepted_phase():
    from app.db.database import AsyncSessionLocal
    from app.models.base import ProjectMember

    uid, org_id, project_id = await _make_gp_project()
    invitee_email = f"mvp11-f114-invitee-{uuid4().hex[:6]}@test.com"
    try:
        token_gp = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token_gp}"},
                json={"email": invitee_email, "role": "dev"},
            )
        assert resp.status_code == 200, resp.text
        invite_token = resp.json()["invite_id"]

        # Localiza o user criado e o ProjectMember pendente
        async with AsyncSessionLocal() as session:
            from app.models.base import User
            user_res = await session.execute(
                select(User).where(User.email == invitee_email)
            )
            invitee = user_res.scalar_one()
            member_res = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id)
                    & (ProjectMember.user_id == invitee.id)
                )
            )
            member = member_res.scalar_one()

        # Aceita o convite (endpoint não exige auth; usa token do invite)
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/accept-invite",
                json={"token": invite_token},
            )
        assert resp.status_code in (200, 201), resp.text

        # O evento de aceite tem actor_id = o próprio convidado
        audit = await _latest_role_audit_for_actor(invitee.id)
        assert audit is not None, "accept não registrou evento role_granted"
        assert audit.event_type == "role_granted"

        details = json.loads(audit.details)
        assert details["project_id"] == str(project_id)
        assert details["new_role"] == "dev"
        assert details["phase"] == "accepted"
        assert details["target_user_id"] == str(invitee.id)
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Evento role_revoked na revogação de convite ──────────────────────


@pytest.mark.asyncio
async def test_revoke_invite_emits_role_revoked():
    from app.db.database import AsyncSessionLocal
    from app.models.base import ProjectMember, User

    uid, org_id, project_id = await _make_gp_project()
    invitee_email = f"mvp11-f114-invitee-{uuid4().hex[:6]}@test.com"
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": invitee_email, "role": "tester"},
            )
        assert resp.status_code == 200, resp.text

        # Busca o invite_id do ProjectMember criado
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id)
                    & (ProjectMember.user_id.in_(
                        select(User.id).where(User.email == invitee_email)
                    ))
                )
            )
            member = res.scalar_one()
            member_id = member.id

        # Revoga (endpoint canônico: POST .../invites/{id}/revoke)
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invites/{member_id}/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code in (200, 204), resp.text

        audit = await _latest_role_audit_for_actor(uid)
        assert audit is not None
        assert audit.event_type == "role_revoked"
        details = json.loads(audit.details)
        assert details["project_id"] == str(project_id)
        assert details["old_role"] == "tester"
        assert details["new_role"] is None
        assert details["phase"] == "revoked"
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Evento role_granted na promoção de Admin ─────────────────────────


@pytest.mark.asyncio
async def test_admin_promotion_emits_role_granted_admin_promoted():
    """set_admin_flag(True) emite role_granted com project_id=None e phase='admin_promoted'."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, GlobalAuditLog
    from app.services.admin_management_service import set_admin_flag

    admin_uid = uuid4()
    target_uid = uuid4()
    # Precisa de outro admin ativo para que rebaixamentos subsequentes não sejam bloqueados
    spare_admin_uid = uuid4()
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(
                    id=admin_uid,
                    email=f"mvp11-f114-admin-{admin_uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F114 Admin",
                    is_active=True,
                    is_admin=True,
                    created_at=datetime.utcnow(),
                ))
                session.add(User(
                    id=spare_admin_uid,
                    email=f"mvp11-f114-admin-{spare_admin_uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F114 SpareAdmin",
                    is_active=True,
                    is_admin=True,
                    created_at=datetime.utcnow(),
                ))
                session.add(User(
                    id=target_uid,
                    email=f"mvp11-f114-target-{target_uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F114 Target",
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.utcnow(),
                ))

        async with AsyncSessionLocal() as session:
            await set_admin_flag(session, target_user_id=target_uid, new_value=True, actor_id=admin_uid)

        # Verifica evento
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GlobalAuditLog)
                .where(
                    (GlobalAuditLog.actor_id == admin_uid)
                    & (GlobalAuditLog.event_type == "role_granted")
                )
                .order_by(desc(GlobalAuditLog.created_at))
                .limit(1)
            )
            audit = res.scalar_one_or_none()

        assert audit is not None
        details = json.loads(audit.details)
        assert details["project_id"] is None, "Admin é papel de instância — project_id deve ser null"
        assert details["new_role"] == "admin"
        assert details["phase"] == "admin_promoted"
        assert details["target_user_id"] == str(target_uid)
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    GlobalAuditLog.__table__.delete().where(
                        GlobalAuditLog.actor_id.in_([admin_uid, spare_admin_uid, target_uid])
                    )
                )
                await session.execute(User.__table__.delete().where(User.id.in_([admin_uid, spare_admin_uid, target_uid])))


# ─── Evento role_revoked no rebaixamento de Admin ─────────────────────


@pytest.mark.asyncio
async def test_admin_demotion_emits_role_revoked():
    """set_admin_flag(False) emite role_revoked com phase='admin_demoted'."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, GlobalAuditLog
    from app.services.admin_management_service import set_admin_flag

    admin_uid = uuid4()
    target_uid = uuid4()
    spare_admin_uid = uuid4()
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(id=admin_uid, email=f"mvp11-f114-admin-{admin_uid.hex[:6]}@test.com",
                                 password_hash=hash_password("Test@1234"), full_name="A",
                                 is_active=True, is_admin=True, created_at=datetime.utcnow()))
                session.add(User(id=spare_admin_uid, email=f"mvp11-f114-admin-{spare_admin_uid.hex[:6]}@test.com",
                                 password_hash=hash_password("Test@1234"), full_name="B",
                                 is_active=True, is_admin=True, created_at=datetime.utcnow()))
                session.add(User(id=target_uid, email=f"mvp11-f114-target-{target_uid.hex[:6]}@test.com",
                                 password_hash=hash_password("Test@1234"), full_name="T",
                                 is_active=True, is_admin=True, created_at=datetime.utcnow()))

        async with AsyncSessionLocal() as session:
            await set_admin_flag(session, target_user_id=target_uid, new_value=False, actor_id=admin_uid)

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GlobalAuditLog)
                .where(
                    (GlobalAuditLog.actor_id == admin_uid)
                    & (GlobalAuditLog.event_type == "role_revoked")
                )
                .order_by(desc(GlobalAuditLog.created_at))
                .limit(1)
            )
            audit = res.scalar_one_or_none()

        assert audit is not None
        details = json.loads(audit.details)
        assert details["project_id"] is None
        assert details["old_role"] == "admin"
        assert details["new_role"] is None
        assert details["phase"] == "admin_demoted"
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    GlobalAuditLog.__table__.delete().where(
                        GlobalAuditLog.actor_id.in_([admin_uid, spare_admin_uid, target_uid])
                    )
                )
                await session.execute(User.__table__.delete().where(User.id.in_([admin_uid, spare_admin_uid, target_uid])))


# ─── Evento role_revoked na desativação de user ───────────────────────


@pytest.mark.asyncio
async def test_lock_user_emits_role_revoked_user_deactivated():
    """admin_service.lock_user com actor_id emite role_revoked + phase='user_deactivated'."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, GlobalAuditLog
    from app.services.admin_service import AdminService

    admin_uid = uuid4()
    target_uid = uuid4()
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(id=admin_uid, email=f"mvp11-f114-admin-{admin_uid.hex[:6]}@test.com",
                                 password_hash=hash_password("Test@1234"), full_name="A",
                                 is_active=True, is_admin=True, created_at=datetime.utcnow()))
                session.add(User(id=target_uid, email=f"mvp11-f114-target-{target_uid.hex[:6]}@test.com",
                                 password_hash=hash_password("Test@1234"), full_name="T",
                                 is_active=True, is_admin=False, created_at=datetime.utcnow()))

        async with AsyncSessionLocal() as session:
            svc = AdminService(session)
            await svc.lock_user(target_uid, actor_id=admin_uid)

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GlobalAuditLog)
                .where(
                    (GlobalAuditLog.actor_id == admin_uid)
                    & (GlobalAuditLog.event_type == "role_revoked")
                )
                .order_by(desc(GlobalAuditLog.created_at))
                .limit(1)
            )
            audit = res.scalar_one_or_none()

        assert audit is not None
        details = json.loads(audit.details)
        assert details["phase"] == "user_deactivated"
        assert details["target_user_id"] == str(target_uid)
        assert details["new_role"] is None
        assert "extra" in details
        assert details["extra"]["was_admin"] is False
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    GlobalAuditLog.__table__.delete().where(
                        GlobalAuditLog.actor_id.in_([admin_uid, target_uid])
                    )
                )
                await session.execute(User.__table__.delete().where(User.id.in_([admin_uid, target_uid])))


# ─── Evento canônico role_transferred reservado (Fase 11.2 emitirá) ──


def test_audit_events_catalog_declares_role_transferred():
    """Fase 11.4 reserva o event_type canônico que a Fase 11.2 emite."""
    from app.services.audit_service import AuditEvents

    assert AuditEvents.ROLE_GRANTED == "role_granted"
    assert AuditEvents.ROLE_REVOKED == "role_revoked"
    assert AuditEvents.ROLE_TRANSFERRED == "role_transferred"


# ─── Helper rejeita event_type inválido (defesa canônica) ─────────────


@pytest.mark.asyncio
async def test_log_role_event_rejects_invalid_event_type():
    from app.db.database import AsyncSessionLocal
    from app.services.audit_service import AuditService

    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError):
            await AuditService(session).log_role_event(
                event_type="role_foobar",
                actor_id=uuid4(),
                target_user_id=uuid4(),
                project_id=None,
                old_role="admin",
                new_role=None,
                phase="fake",
            )
