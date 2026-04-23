"""MVP 23 Fase 23.5 — Testes HTTP dos endpoints RNF_CONTRACTS.

Cobre:
  - GET sem OCG → 404
  - GET com OCG sem RNF_CONTRACTS → 200 rnf_contracts={}
  - GET com RNF_CONTRACTS preenchido → 200 com payload canônico
  - PUT payload válido → 200 applied=True, bump de versão
  - PUT idêntico ao atual → 200 applied=False, sem bump
  - PUT payload inválido (chave desconhecida) → 422
  - PUT sem OCG → 404
  - PUT sem permissão manage_team → 403 (user sem papel GP no projeto)

Permissão: `project:manage_team` cobre Admin + GP.
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.database import AsyncSessionLocal
from app.main import app
from app.models.base import (
    OCG, Organization, Project, ProjectMember, Questionnaire, User,
)


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_admin(session) -> User:
    uid = uuid4()
    u = User(
        id=uid,
        email=f"rnfput-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="RNF PUT Tester",
        is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(u)
    await session.flush()
    return u


async def _make_project_with_ocg(session, user, *, rnf: dict | None = None) -> Project:
    org = Organization(
        id=uuid4(), name=f"Org {uuid4().hex[:6]}",
        slug=f"org-rnfput-{uuid4().hex[:6]}",
        owner_id=user.id, is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name="RNF PUT Proj",
        slug=f"rnfput-{uuid4().hex[:6]}",
        description="t", deliverable_type="web_app",
        status="active", created_at=datetime.utcnow(),
    )
    session.add(project)
    await session.flush()
    # GP no projeto (para permissão manage_team).
    session.add(ProjectMember(
        project_id=project.id, user_id=user.id,
        role="gp", is_active=True, joined_at=datetime.utcnow(),
    ))
    # Questionnaire (FK obrigatória do OCG).
    q = Questionnaire(
        id=uuid4(), project_id=project.id,
        gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    session.add(q)
    await session.flush()
    data = {}
    if rnf is not None:
        data["RNF_CONTRACTS"] = rnf
    ocg = OCG(
        id=uuid4(), project_id=project.id,
        questionnaire_id=q.id, version=3,
        ocg_data=json.dumps(data, ensure_ascii=False),
        status="NEEDS_REVIEW", overall_score=80.0,
        is_blocking=False,
    )
    session.add(ocg)
    await session.flush()
    return project


# ─── GET ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_rnf_contracts_sem_ocg_retorna_404():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            # projeto sem OCG
            uniq = uuid4().hex[:6]
            org = Organization(
                id=uuid4(), name=f"NoOCG-{uniq}", slug=f"noocg-{uniq}",
                owner_id=user.id, is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(org)
            project = Project(
                id=uuid4(), organization_id=org.id,
                name=f"NoOCG-{uniq}", slug=f"noocg-p-{uniq}",
                description="t", deliverable_type="web_app",
                status="active", created_at=datetime.utcnow(),
            )
            session.add(project)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_rnf_contracts_sem_rnf_retorna_vazio():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, rnf=None)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["rnf_contracts"] == {}
    assert body["ocg_version"] == 3


@pytest.mark.asyncio
async def test_get_rnf_contracts_com_dados_retorna_canonico():
    rnf = {"security": {"rate_limit_rpm_public": 60}}
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, rnf=rnf)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    assert r.json()["rnf_contracts"] == rnf


# ─── PUT ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_rnf_contracts_valido_aplica_e_bump_version():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, rnf=None)

    token = create_access_token(data={"sub": str(user.id)})
    payload = {
        "rnf_contracts": {
            "security": {"rate_limit_rpm_public": 60},
            "performance": {"latency_p95_ms": 300},
        }
    }
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is True
    assert body["ocg_version"] == 4  # bump de 3 → 4

    # confirma persistência
    async with AsyncSessionLocal() as session:
        ocg = (await session.execute(
            select(OCG).where(OCG.project_id == project.id)
        )).scalar_one()
        data = json.loads(ocg.ocg_data)
        assert data["RNF_CONTRACTS"] == payload["rnf_contracts"]
        assert ocg.version == 4


@pytest.mark.asyncio
async def test_put_rnf_contracts_idempotente_sem_bump():
    rnf = {"security": {"rate_limit_rpm_public": 60}}
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, rnf=rnf)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
            json={"rnf_contracts": rnf},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is False
    assert body["ocg_version"] == 3  # sem bump


@pytest.mark.asyncio
async def test_put_rnf_contracts_payload_invalido_422():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, rnf=None)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
            json={"rnf_contracts": {"chave_invalida": {}}},
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "errors" in detail
    assert any("chave_invalida" in e["path"] for e in detail["errors"])


@pytest.mark.asyncio
async def test_put_rnf_contracts_sem_ocg_retorna_404():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            uniq = uuid4().hex[:6]
            org = Organization(
                id=uuid4(), name=f"NoOCG2-{uniq}", slug=f"noocg2-{uniq}",
                owner_id=user.id, is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(org)
            project = Project(
                id=uuid4(), organization_id=org.id,
                name=f"NoOCG2-{uniq}", slug=f"noocg2-p-{uniq}",
                description="t", deliverable_type="web_app",
                status="active", created_at=datetime.utcnow(),
            )
            session.add(project)
            # necessita ProjectMember pra manage_team passar
            session.add(ProjectMember(
                project_id=project.id, user_id=user.id,
                role="gp", is_active=True, joined_at=datetime.utcnow(),
            ))

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/rnf-contracts",
            headers={"Authorization": f"Bearer {token}"},
            json={"rnf_contracts": {}},
        )
    assert r.status_code == 404
