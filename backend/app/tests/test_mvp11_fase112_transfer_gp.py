"""MVP 11 Fase 11.2 — GP transferir soberania do projeto.

Contrato §7 MVP 11 Fase 11.2:
- Endpoint POST /projects/{id}/transfer-gp/{user_id}.
- Atomicidade: promove alvo a GP e rebaixa chamador a Dev numa
  única transação.
- Pré-condições: chamador é GP ativo; alvo é membro ativo já integrado
  (joined_at != null); alvo não é GP; alvo != chamador.
- Auditoria: 2 eventos role_transferred com mesmo correlation_id
  (phase='transferred', direção outgoing/incoming).
"""
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_project_gp_plus_member(member_role: str = "dev", member_joined: bool = True):
    """Cria projeto com (a) GP ativo (b) outro usuário com `member_role`.

    Retorna (gp_uid, target_uid, org_id, project_id).
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember

    gp_uid = uuid4()
    target_uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(id=gp_uid, email=f"mvp11-f112-gp-{gp_uid.hex[:6]}@test.com",
                             password_hash=hash_password("Test@1234"), full_name="GP",
                             is_active=True, is_admin=False, created_at=datetime.utcnow()))
            session.add(User(id=target_uid, email=f"mvp11-f112-target-{target_uid.hex[:6]}@test.com",
                             password_hash=hash_password("Test@1234"), full_name="Target",
                             is_active=True, is_admin=False, created_at=datetime.utcnow()))
            session.add(Organization(id=org_id, name=f"Org {gp_uid.hex[:6]}",
                                     slug=f"org-f112-{gp_uid.hex[:6]}", owner_id=gp_uid,
                                     is_active=True, created_at=datetime.utcnow()))
            await session.flush()
            session.add(Project(id=project_id, organization_id=org_id, name=f"P f112 {gp_uid.hex[:6]}",
                                slug=f"p-f112-{gp_uid.hex[:6]}", status="active",
                                deliverable_type="new_system", created_at=datetime.utcnow()))
            await session.flush()
            session.add(ProjectMember(id=uuid4(), project_id=project_id, user_id=gp_uid,
                                      role="gp", is_active=True,
                                      invited_at=datetime.utcnow(), joined_at=datetime.utcnow()))
            session.add(ProjectMember(
                id=uuid4(), project_id=project_id, user_id=target_uid,
                role=member_role, is_active=True,
                invited_at=datetime.utcnow(),
                joined_at=datetime.utcnow() if member_joined else None,
            ))
    return gp_uid, target_uid, org_id, project_id


async def _cleanup(gp_uid, target_uid, org_id, project_id):
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember, GlobalAuditLog

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                GlobalAuditLog.__table__.delete().where(
                    GlobalAuditLog.actor_id.in_([gp_uid, target_uid])
                )
            )
            await session.execute(
                ProjectMember.__table__.delete().where(ProjectMember.project_id == project_id)
            )
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            await session.execute(User.__table__.delete().where(User.id.in_([gp_uid, target_uid])))


# ─── Caminho feliz: transfere e inverte papéis ────────────────────────


@pytest.mark.asyncio
async def test_transfer_gp_swaps_roles_atomically():
    from app.db.database import AsyncSessionLocal
    from app.models.base import ProjectMember

    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member("dev", True)
    try:
        token = create_access_token(data={"sub": str(gp_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{target_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "gp_transferred"
        assert body["from_user_id"] == str(gp_uid)
        assert body["to_user_id"] == str(target_uid)

        # Verifica inversão de papéis no DB
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id)
                    & (ProjectMember.user_id == gp_uid)
                )
            )
            old_gp = res.scalar_one()
            assert old_gp.role == "dev", "chamador deveria ter sido rebaixado a dev"

            res = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id)
                    & (ProjectMember.user_id == target_uid)
                )
            )
            new_gp = res.scalar_one()
            assert new_gp.role == "gp", "alvo deveria ter sido promovido a gp"
    finally:
        await _cleanup(gp_uid, target_uid, org_id, project_id)


# ─── Audit: 2 eventos role_transferred com mesmo correlation_id ──────


@pytest.mark.asyncio
async def test_transfer_gp_emits_two_role_transferred_with_same_correlation():
    from app.db.database import AsyncSessionLocal
    from app.models.base import GlobalAuditLog

    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member("dev", True)
    try:
        token = create_access_token(data={"sub": str(gp_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{target_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GlobalAuditLog).where(
                    (GlobalAuditLog.actor_id == gp_uid)
                    & (GlobalAuditLog.event_type == "role_transferred")
                )
            )
            events = list(res.scalars().all())

        assert len(events) == 2, f"esperava 2 eventos role_transferred e veio {len(events)}"
        corr_ids = {e.correlation_id for e in events}
        assert len(corr_ids) == 1 and None not in corr_ids, \
            "os 2 eventos devem compartilhar correlation_id para serem linkados"

        # Um outgoing (chamador), um incoming (alvo)
        phases = {json.loads(e.details)["extra"]["direction"] for e in events}
        assert phases == {"outgoing", "incoming"}

        for e in events:
            d = json.loads(e.details)
            assert d["project_id"] == str(project_id)
            assert d["phase"] == "transferred"
            if d["extra"]["direction"] == "outgoing":
                assert d["target_user_id"] == str(gp_uid)
                assert d["old_role"] == "gp"
                assert d["new_role"] == "dev"
            else:
                assert d["target_user_id"] == str(target_uid)
                assert d["old_role"] == "dev"
                assert d["new_role"] == "gp"
    finally:
        await _cleanup(gp_uid, target_uid, org_id, project_id)


# ─── Pré-condições negadas ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transfer_gp_to_self_is_rejected():
    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member("dev", True)
    try:
        token = create_access_token(data={"sub": str(gp_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{gp_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 400
        assert "si mesmo" in resp.json()["detail"]
    finally:
        await _cleanup(gp_uid, target_uid, org_id, project_id)


@pytest.mark.asyncio
async def test_transfer_gp_to_unaccepted_member_is_rejected():
    """Alvo que ainda não aceitou convite (joined_at=None) não pode receber."""
    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member("dev", member_joined=False)
    try:
        token = create_access_token(data={"sub": str(gp_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{target_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 400
        assert "ainda não aceitou" in resp.json()["detail"]
    finally:
        await _cleanup(gp_uid, target_uid, org_id, project_id)


@pytest.mark.asyncio
async def test_transfer_gp_to_existing_gp_is_rejected():
    """Alvo que já é GP não pode ser alvo (não faz sentido)."""
    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member("gp", True)
    try:
        token = create_access_token(data={"sub": str(gp_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{target_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 400
        assert "já é GP" in resp.json()["detail"]
    finally:
        await _cleanup(gp_uid, target_uid, org_id, project_id)


@pytest.mark.asyncio
async def test_transfer_gp_to_non_member_is_rejected():
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member("dev", True)
    outsider_uid = uuid4()
    try:
        # Cria um user de fora do projeto
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(id=outsider_uid, email=f"mvp11-f112-outsider-{outsider_uid.hex[:6]}@test.com",
                                 password_hash=hash_password("Test@1234"), full_name="Outsider",
                                 is_active=True, is_admin=False, created_at=datetime.utcnow()))

        token = create_access_token(data={"sub": str(gp_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{outsider_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 400
        assert "não é membro ativo" in resp.json()["detail"]
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(User.__table__.delete().where(User.id == outsider_uid))
        await _cleanup(gp_uid, target_uid, org_id, project_id)


# ─── RBAC: apenas GP invoca ───────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [
    ("dev", 403),
    ("tester", 403),
    ("qa", 403),
])
async def test_non_gp_cannot_transfer(role, expected):
    """Dev/Tester/QA do projeto não têm project:manage_team → 403."""
    gp_uid, target_uid, org_id, project_id = await _make_project_gp_plus_member(role, True)
    try:
        # Chama do user não-GP (target, que tem o role parametrizado)
        token = create_access_token(data={"sub": str(target_uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/transfer-gp/{gp_uid}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == expected, f"{role}: {resp.text}"
    finally:
        await _cleanup(gp_uid, target_uid, org_id, project_id)
