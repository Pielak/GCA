"""MVP 11 Fase 11.1 — GP convida outro GP do mesmo projeto.

Contrato §7 MVP 11 Fase 11.1:
- GP ativo do projeto X pode convidar outro usuário para role='gp' em X.
- Whitelist canônica de role no invite: dev, tester, qa, gp. Qualquer outro
  valor (admin, lixo) retorna 422.
- Compartimentalização: GP de um projeto nunca promove GP em outro projeto
  — garantido por `require_action('project:manage_team')` resolvido dentro
  do `project_id` do path. Não é re-testado aqui porque já é coberto pela
  matriz do MVP 4 RBAC.
- Serviço: o role persistido em `ProjectMember.role` reflete o que o schema
  aceitou — nenhum bypass.
"""
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


async def _make_project_with_gp(role: str = "gp"):
    """Cria User + Org + Project + ProjectMember com o papel dado. Retorna (uid, org_id, project_id)."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember

    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                User(
                    id=uid,
                    email=f"mvp11-{role}-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name=f"MVP11 {role}",
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.utcnow(),
                )
            )
            session.add(
                Organization(
                    id=org_id,
                    name=f"Org {uid.hex[:6]}",
                    slug=f"org-mvp11-{uid.hex[:6]}",
                    owner_id=uid,
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
            )
            await session.flush()
            session.add(
                Project(
                    id=project_id,
                    organization_id=org_id,
                    name=f"P mvp11 {role}",
                    slug=f"p-mvp11-{uid.hex[:6]}",
                    status="active",
                    deliverable_type="new_system",
                    created_at=datetime.utcnow(),
                )
            )
            await session.flush()
            session.add(
                ProjectMember(
                    id=uuid4(),
                    project_id=project_id,
                    user_id=uid,
                    role=role,
                    is_active=True,
                    invited_at=datetime.utcnow(),
                    joined_at=datetime.utcnow(),
                )
            )

    return uid, org_id, project_id


async def _cleanup(uid, org_id, project_id):
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, ProjectMember

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                ProjectMember.__table__.delete().where(ProjectMember.project_id == project_id)
            )
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            # Apaga também qualquer user criado como convidado (email mvp11-invitee-*)
            await session.execute(
                User.__table__.delete().where(User.email.like("mvp11-invitee-%@test.com"))
            )
            await session.execute(User.__table__.delete().where(User.id == uid))


# ─── Caminho feliz: GP convida outro GP no mesmo projeto ──────────────


@pytest.mark.asyncio
async def test_gp_can_invite_another_gp_same_project():
    """GP do projeto X convida usuário novo com role='gp' → 200 e ProjectMember criado com role='gp'."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import ProjectMember

    uid, org_id, project_id = await _make_project_with_gp("gp")
    invitee_email = f"mvp11-invitee-{uuid4().hex[:6]}@test.com"
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": invitee_email, "role": "gp"},
            )
        assert resp.status_code == 200, f"esperava 200 e veio {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["role"] == "gp"
        assert body["email"] == invitee_email
        assert body["status"] == "pending"

        # Verifica no DB que o ProjectMember foi criado com role='gp' e project_id correto
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id)
                    & (ProjectMember.role == "gp")
                    & (ProjectMember.invite_token.is_not(None))
                )
            )
            new_member = result.scalar_one_or_none()
            assert new_member is not None, "ProjectMember GP convidado não foi criado"
            assert new_member.project_id == project_id, "projeto do convite deve ser compartimentalizado"
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Schema whitelist — role inválido é rejeitado ─────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_role", ["admin", "tech_lead", "hacker", "", "GP"])
async def test_schema_rejects_non_canonical_role(invalid_role):
    """Role fora da whitelist {dev,tester,qa,gp} retorna 422."""
    uid, org_id, project_id = await _make_project_with_gp("gp")
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": "outsider@test.com", "role": invalid_role},
            )
        assert resp.status_code == 422, (
            f"role={invalid_role!r} deveria ser 422 e veio {resp.status_code}: {resp.text}"
        )
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Schema whitelist — role canônico é aceito (sanidade) ─────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical_role", ["dev", "tester", "qa", "gp"])
async def test_schema_accepts_canonical_role(canonical_role):
    """Os 4 papéis canônicos de projeto são aceitos pelo schema (retornam 200 ou erro de negócio, nunca 422)."""
    uid, org_id, project_id = await _make_project_with_gp("gp")
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": f"mvp11-invitee-{canonical_role}-{uuid4().hex[:6]}@test.com", "role": canonical_role},
            )
        assert resp.status_code != 422, (
            f"role canônico {canonical_role!r} não deve disparar 422: {resp.text}"
        )
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── RBAC — não-GP não consegue convidar ninguém, inclusive GP ────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["dev", "tester", "qa"])
async def test_non_gp_cannot_invite_gp(role):
    """Dev/Tester/QA tentam convidar GP → 403 (project:manage_team é exclusivo do GP)."""
    uid, org_id, project_id = await _make_project_with_gp(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": "intruder@test.com", "role": "gp"},
            )
        assert resp.status_code == 403, (
            f"{role} deveria receber 403 e veio {resp.status_code}: {resp.text}"
        )
    finally:
        await _cleanup(uid, org_id, project_id)
