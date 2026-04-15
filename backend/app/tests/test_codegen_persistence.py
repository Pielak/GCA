"""Testes de persistência do CodeGen — guard de ProjectGitConfig.

Nota: o happy-path (commit por arquivo) é validado via E2E manual na UI
porque a chamada LLM é inline com AsyncAnthropic, tornando o mock frágil.
Este arquivo cobre apenas o guard estrutural — suficiente para prevenir
regressão da regra "sem Git config → 400".
"""
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.main import app
from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_scaffold_400_when_no_git_config():
    """Projeto sem ProjectGitConfig → 400 com mensagem clara."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project

    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"codegen-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Codegen Tester",
                is_active=True,
                is_admin=True,
                created_at=datetime.utcnow(),
            )
            org = Organization(
                id=uuid4(),
                name=f"Org {uid.hex[:6]}",
                slug=f"org-{uid.hex[:6]}",
                owner_id=uid,
                is_active=True,
                created_at=datetime.utcnow(),
            )
            session.add(user)
            session.add(org)
            await session.flush()
            project = Project(
                id=uuid4(),
                organization_id=org.id,
                name="P sem Git",
                slug=f"p-nogit-{uid.hex[:6]}",
                status="active",
                deliverable_type="web_app",
                created_at=datetime.utcnow(),
            )
            session.add(project)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as client:
        resp = await client.post(
            "/api/v1/code-generation/scaffold",
            headers={"Authorization": f"Bearer {token}"},
            json={"project_id": str(project.id)},
        )

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "Git" in body["detail"]

    # Cleanup
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(Project.__table__.delete().where(Project.id == project.id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org.id))
            await session.execute(User.__table__.delete().where(User.id == user.id))
