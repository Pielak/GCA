"""Testes de RBAC em endpoints do MVP 4 (DT-044).

Matriz binária esperada (contrato §4.1 + §7):

                             approve   exec   view   docs:edit  audit:export
 GP (gp)                      SIM      NÃO   SIM    SIM        SIM
 Dev (dev)                    NÃO      SIM   SIM    SIM        NÃO
 Tester (tester)              NÃO      SIM   SIM    NÃO        SIM
 QA (qa)                      SIM      NÃO   SIM    NÃO        NÃO
 admin_viewer (admin s/ mem)  NÃO      NÃO   SIM    NÃO        NÃO

Testa:
- qa_router: approve/reject (qa:approve), update_test/execute (pipeline:execute),
  logs_export (audit:export).
- livedocs_router: refresh (docs:edit).
- deliverables_router: verify-all/attest/releases-POST (qa:approve),
  releases/download (audit:export).
"""
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.main import app
from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_project_with_member(role: str):
    """Cria User + Org + Project + Membership com o papel dado.

    Retorna (uid, org_id, project_id).
    """
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
                    email=f"rbac-{role}-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name=f"RBAC {role}",
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.utcnow(),
                )
            )
            session.add(
                Organization(
                    id=org_id,
                    name=f"Org {uid.hex[:6]}",
                    slug=f"org-rbac-{uid.hex[:6]}",
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
                    name=f"P rbac {role}",
                    slug=f"p-rbac-{uid.hex[:6]}",
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
            await session.execute(User.__table__.delete().where(User.id == uid))


# ─── QA Router: approve/reject exigem qa:approve (GP, QA) ───────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [
    ("gp", 404),      # passa RBAC, falha em test_id inexistente
    ("qa", 404),      # passa RBAC, falha em test_id inexistente
    ("dev", 403),     # RBAC bloqueia
    ("tester", 403),  # RBAC bloqueia
])
async def test_qa_approve_rbac(role, expected):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/tests/{uuid4()}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == expected, f"{role}: {resp.text}"
        if expected == 403:
            assert "qa:approve" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [
    ("dev", 404),       # passa RBAC, falha em test_id inexistente
    ("tester", 404),    # passa RBAC, falha em test_id inexistente
    ("gp", 403),        # RBAC bloqueia
    ("qa", 403),        # RBAC bloqueia
])
async def test_qa_update_test_rbac(role, expected):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.put(
                f"/api/v1/projects/{project_id}/tests/{uuid4()}",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "new"},
            )
        assert resp.status_code == expected, f"{role}: {resp.text}"
        if expected == 403:
            assert "pipeline:execute" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [
    ("gp", True),
    ("tester", True),
    ("dev", False),
    ("qa", False),
])
async def test_qa_logs_export_rbac(role, allowed):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/projects/{project_id}/qa/logs/export",
                headers={"Authorization": f"Bearer {token}"},
            )
        if allowed:
            assert resp.status_code == 200, f"{role}: {resp.text}"
        else:
            assert resp.status_code == 403, f"{role}: {resp.text}"
            assert "audit:export" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── LiveDocs Router: refresh exige docs:edit (GP, Dev) ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [
    ("gp", True),
    ("dev", True),
    ("tester", False),
    ("qa", False),
])
async def test_livedocs_refresh_rbac(role, allowed):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/docs/refresh",
                headers={"Authorization": f"Bearer {token}"},
            )
        if allowed:
            # RBAC passa — pode falhar depois por setup/OCG. 200, 400 ou 404 aceitos.
            assert resp.status_code != 403, f"{role}: {resp.text}"
        else:
            assert resp.status_code == 403, f"{role}: {resp.text}"
            assert "docs:edit" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Deliverables: verify-all e releases POST exigem qa:approve ─────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [
    ("gp", True),
    ("qa", True),
    ("dev", False),
    ("tester", False),
])
async def test_deliverables_verify_all_rbac(role, allowed):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/deliverables/verify-all",
                headers={"Authorization": f"Bearer {token}"},
            )
        if allowed:
            assert resp.status_code != 403, f"{role}: {resp.text}"
        else:
            assert resp.status_code == 403, f"{role}: {resp.text}"
            assert "qa:approve" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [
    ("gp", True),
    ("qa", True),
    ("dev", False),
    ("tester", False),
])
async def test_release_bundle_create_rbac(role, allowed):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.post(
                f"/api/v1/projects/{project_id}/releases",
                headers={"Authorization": f"Bearer {token}"},
            )
        if allowed:
            # Esperado 412 (readiness abaixo do threshold) ou 500; NÃO 403.
            assert resp.status_code != 403, f"{role}: {resp.text}"
        else:
            assert resp.status_code == 403, f"{role}: {resp.text}"
            assert "qa:approve" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Release download exige audit:export (GP, Tester) ──────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed", [
    ("gp", True),
    ("tester", True),
    ("dev", False),
    ("qa", False),
])
async def test_release_download_rbac(role, allowed):
    uid, org_id, project_id = await _make_project_with_member(role)
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.get(
                f"/api/v1/projects/{project_id}/releases/1/download",
                headers={"Authorization": f"Bearer {token}"},
            )
        if allowed:
            # Esperado 404 (release não existe); NÃO 403.
            assert resp.status_code != 403, f"{role}: {resp.text}"
        else:
            assert resp.status_code == 403, f"{role}: {resp.text}"
            assert "audit:export" in resp.json()["detail"]
    finally:
        await _cleanup(uid, org_id, project_id)


# ─── Non-member is blocked end-to-end ──────────────────────────────────


@pytest.mark.asyncio
async def test_non_member_blocked_on_mvp4_endpoints():
    """User autenticado sem membership e sem is_admin → 403."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    # Stranger
    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            session.add(
                User(
                    id=uid,
                    email=f"stranger-mvp4-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="Stranger MVP4",
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.utcnow(),
                )
            )

    # Projeto de outra pessoa
    owner_uid, org_id, project_id = await _make_project_with_member("gp")

    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            # Tenta vários endpoints
            for path, method in [
                (f"/api/v1/projects/{project_id}/tests", "GET"),
                (f"/api/v1/projects/{project_id}/deliverables", "GET"),
                (f"/api/v1/projects/{project_id}/docs", "GET"),
                (f"/api/v1/projects/{project_id}/roadmap", "GET"),
            ]:
                if method == "GET":
                    resp = await client.get(path, headers={"Authorization": f"Bearer {token}"})
                assert resp.status_code == 403, f"{path}: {resp.status_code} {resp.text}"
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(User.__table__.delete().where(User.id == uid))
        await _cleanup(owner_uid, org_id, project_id)
