"""MVP 25 Fase 25.5 — Testes HTTP dos endpoints `design-tokens`.

Cobre:
  - GET sem OCG → 404
  - GET com OCG sem design_tokens → {} + ocg_version
  - GET com tokens populados → shape canônico
  - PUT payload válido → 200 applied=True + bump + source="manual" por default
  - PUT idempotente ignorando generated_at → applied=False
  - PUT substitui "css_ingested" prévio → source="mixed"
  - PUT payload inválido → 422 com errors[]
  - PUT sem OCG → 404
"""
from __future__ import annotations

import json
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
        id=uid, email=f"dt255-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="DT255 Tester", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(u)
    await session.flush()
    return u


async def _make_project_with_ocg(
    session, user, *, design_tokens: dict | None = None,
) -> Project:
    org = Organization(
        id=uuid4(), name=f"Org {uuid4().hex[:6]}",
        slug=f"org-dt255-{uuid4().hex[:6]}",
        owner_id=user.id, is_active=True,
        created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name="DT255 Proj",
        slug=f"dt255-{uuid4().hex[:6]}",
        description="t", deliverable_type="web_app",
        status="active", created_at=datetime.utcnow(),
    )
    session.add(project)
    await session.flush()
    session.add(ProjectMember(
        project_id=project.id, user_id=user.id,
        role="gp", is_active=True, joined_at=datetime.utcnow(),
    ))
    q = Questionnaire(
        id=uuid4(), project_id=project.id,
        gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    session.add(q)
    await session.flush()

    ocg_data: dict = {}
    if design_tokens is not None:
        ocg_data["STACK_RECOMMENDATION"] = {
            "frontend": {"design_tokens": design_tokens}
        }
    ocg = OCG(
        id=uuid4(), project_id=project.id,
        questionnaire_id=q.id, version=3,
        ocg_data=json.dumps(ocg_data, ensure_ascii=False),
        status="NEEDS_REVIEW", overall_score=80.0,
        is_blocking=False,
    )
    session.add(ocg)
    await session.flush()
    return project


# ─── GET ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_sem_ocg_retorna_404():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            uniq = uuid4().hex[:6]
            org = Organization(
                id=uuid4(), name=f"NoOCG-DT-{uniq}", slug=f"noocg-dt-{uniq}",
                owner_id=user.id, is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(org)
            project = Project(
                id=uuid4(), organization_id=org.id,
                name=f"NoOCG-DT-{uniq}", slug=f"noocg-dt-p-{uniq}",
                description="t", deliverable_type="web_app",
                status="active", created_at=datetime.utcnow(),
            )
            session.add(project)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_sem_design_tokens_retorna_vazio():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=None)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["design_tokens"] == {}
    assert body["ocg_version"] == 3


@pytest.mark.asyncio
async def test_get_com_tokens_populados():
    tokens = {
        "palette": {"top": ["#7c3aed"], "by_role": {"primary": "#7c3aed"}},
        "source": "css_ingested",
    }
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=tokens)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    assert r.json()["design_tokens"]["palette"]["by_role"]["primary"] == "#7c3aed"


# ─── PUT ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_valido_aplica_e_marca_manual_por_default():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=None)

    token = create_access_token(data={"sub": str(user.id)})
    payload = {
        "design_tokens": {
            "palette": {"by_role": {"primary": "#7c3aed"}},
            "typography": {"sizes_px": [16, 24]},
        }
    }
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is True
    assert body["ocg_version"] == 4
    assert body["design_tokens"]["source"] == "manual"
    assert body["design_tokens"]["generated_at"]  # carimbado

    # Persistência verificada
    async with AsyncSessionLocal() as session:
        ocg = (await session.execute(
            select(OCG).where(OCG.project_id == project.id)
        )).scalar_one()
        data = json.loads(ocg.ocg_data)
        dt = data["STACK_RECOMMENDATION"]["frontend"]["design_tokens"]
        assert dt["source"] == "manual"
        assert ocg.version == 4


@pytest.mark.asyncio
async def test_put_idempotente_so_timestamp_muda():
    """Payload idêntico (mesmo ignorando generated_at) → applied=False sem bump."""
    tokens = {
        "palette": {"top": ["#abcdef"]},
        "source": "manual",
        "generated_at": "2026-04-22T10:00:00+00:00",
    }
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=tokens)

    token = create_access_token(data={"sub": str(user.id)})
    payload = {
        "design_tokens": {
            "palette": {"top": ["#abcdef"]},
            "source": "manual",
            "generated_at": "2026-04-22T99:99:99+00:00",  # timestamp ignorado
        }
    }
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is False
    assert body["ocg_version"] == 3


@pytest.mark.asyncio
async def test_put_apos_css_ingested_vira_mixed():
    """Edição manual de tokens originados do extractor → source="mixed"."""
    prev = {
        "palette": {"by_role": {"primary": "#111111"}},
        "source": "css_ingested",
        "generated_at": "2026-04-22T10:00:00+00:00",
    }
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=prev)

    token = create_access_token(data={"sub": str(user.id)})
    payload = {
        "design_tokens": {
            "palette": {"by_role": {"primary": "#7c3aed", "accent": "#ff00ff"}},
        }
    }
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True
    assert body["design_tokens"]["source"] == "mixed"


@pytest.mark.asyncio
async def test_put_payload_invalido_422():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=None)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json={"design_tokens": {
                "palette": {"by_role": {"random_role": "#abcdef"}},
            }},
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "errors" in detail
    assert any("random_role" in e["path"] for e in detail["errors"])


@pytest.mark.asyncio
async def test_put_hex_invalido_422():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project_with_ocg(session, user, design_tokens=None)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json={"design_tokens": {
                "palette": {"top": ["not-a-hex"]},
            }},
        )
    assert r.status_code == 422
    assert any("top[0]" in e["path"] for e in r.json()["detail"]["errors"])


@pytest.mark.asyncio
async def test_put_sem_ocg_retorna_404():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            uniq = uuid4().hex[:6]
            org = Organization(
                id=uuid4(), name=f"NoOCG2-DT-{uniq}", slug=f"noocg2-dt-{uniq}",
                owner_id=user.id, is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(org)
            project = Project(
                id=uuid4(), organization_id=org.id,
                name=f"NoOCG2-DT-{uniq}", slug=f"noocg2-dt-p-{uniq}",
                description="t", deliverable_type="web_app",
                status="active", created_at=datetime.utcnow(),
            )
            session.add(project)
            session.add(ProjectMember(
                project_id=project.id, user_id=user.id,
                role="gp", is_active=True, joined_at=datetime.utcnow(),
            ))

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.put(
            f"/api/v1/projects/{project.id}/ocg/design-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json={"design_tokens": {}},
        )
    assert r.status_code == 404
