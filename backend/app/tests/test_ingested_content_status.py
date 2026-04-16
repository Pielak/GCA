"""Testes do endpoint /ingestion/<doc>/content + soft-delete via content_status.

Cobertura:
- 410 Gone quando content_status='lost' (script de inventário marcou).
- 200 normal quando content_status='available' e bytes em disco.

Não testamos o caminho 404 ('available' mas sem bytes em disco) porque
ele já é coberto implicitamente pelo backfill — e mockar o filesystem
adicionaria complexidade sem ganho.
"""
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.main import app
from app.core.security import create_access_token, hash_password
from app.utils.ingested_storage import write_ingested, ingested_path


@pytest.mark.asyncio
async def test_content_returns_410_when_lost():
    """Doc marcado como content_status='lost' devolve 410 Gone com mensagem clara."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, IngestedDocument

    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()
    doc_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                User(
                    id=uid,
                    email=f"lost-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="Lost Tester",
                    is_active=True,
                    is_admin=True,
                    created_at=datetime.utcnow(),
                )
            )
            session.add(
                Organization(
                    id=org_id,
                    name=f"Org {uid.hex[:6]}",
                    slug=f"org-{uid.hex[:6]}",
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
                    name="P lost",
                    slug=f"p-{uid.hex[:6]}",
                    status="active",
                    deliverable_type="web_app",
                    created_at=datetime.utcnow(),
                )
            )
            await session.flush()
            session.add(
                IngestedDocument(
                    id=doc_id,
                    project_id=project_id,
                    filename=f"{doc_id}.pdf",
                    original_filename="lost_doc.pdf",
                    file_type="pdf",
                    file_hash="x" * 64,
                    file_size_bytes=0,
                    uploaded_by=uid,
                    arguider_status="completed",
                    content_status="lost",
                )
            )

    token = create_access_token(data={"sub": str(uid)})
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/projects/{project_id}/ingestion/{doc_id}/content",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 410, resp.text
        body = resp.json()
        assert "perdido" in body["detail"].lower()
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    IngestedDocument.__table__.delete().where(IngestedDocument.id == doc_id)
                )
                await session.execute(Project.__table__.delete().where(Project.id == project_id))
                await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
                await session.execute(User.__table__.delete().where(User.id == uid))


@pytest.mark.asyncio
async def test_content_returns_200_when_available_and_on_disk():
    """Doc available + bytes em disco devolve 200 com Content-Type correto."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, Organization, Project, IngestedDocument

    uid = uuid4()
    org_id = uuid4()
    project_id = uuid4()
    doc_id = uuid4()
    filename = f"{doc_id}.md"
    payload = b"# Hello\n\nConteudo de teste."

    write_ingested(project_id, filename, payload)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                User(
                    id=uid,
                    email=f"avail-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="Avail Tester",
                    is_active=True,
                    is_admin=True,
                    created_at=datetime.utcnow(),
                )
            )
            session.add(
                Organization(
                    id=org_id,
                    name=f"Org {uid.hex[:6]}",
                    slug=f"org-{uid.hex[:6]}",
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
                    name="P avail",
                    slug=f"p-{uid.hex[:6]}",
                    status="active",
                    deliverable_type="web_app",
                    created_at=datetime.utcnow(),
                )
            )
            await session.flush()
            session.add(
                IngestedDocument(
                    id=doc_id,
                    project_id=project_id,
                    filename=filename,
                    original_filename="hello.md",
                    file_type="markdown",
                    file_hash="y" * 64,
                    file_size_bytes=len(payload),
                    uploaded_by=uid,
                    arguider_status="completed",
                    content_status="available",
                )
            )

    token = create_access_token(data={"sub": str(uid)})
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/projects/{project_id}/ingestion/{doc_id}/content",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        assert resp.content == payload
        assert "text/markdown" in resp.headers["content-type"]
    finally:
        # Limpar arquivo + DB
        path = ingested_path(project_id, filename)
        if path.exists():
            path.unlink()
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    IngestedDocument.__table__.delete().where(IngestedDocument.id == doc_id)
                )
                await session.execute(Project.__table__.delete().where(Project.id == project_id))
                await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
                await session.execute(User.__table__.delete().where(User.id == uid))
