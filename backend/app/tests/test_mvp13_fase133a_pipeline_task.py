"""MVP 13 Fase 13.3a — `pipeline_ingest_task` substitui o primeiro ponto
de `asyncio.create_task` no pipeline (router reanalyze).

Contrato §7 MVP 13 Fase 13.3:
- Task Celery `pipeline_ingest_task` registra e é invocável via
  `.delay()` / `.apply_async()`.
- Envelopa `IngestionService._analyze_async` mantendo semântica:
  lê bytes do storage (não passa bytes pelo broker), roda
  assincronamente via `asyncio.run`.
- Config canônica: max_retries=2, default_retry_delay=30, acks_late.
- Doc inexistente: log de warning, retorna sem raise.
- Storage path ausente: marca doc como 'error' + retorna (watchdog
  não tenta reviver).
"""
from unittest.mock import AsyncMock, patch

import pytest

# Garante que a task é registrada no test (celery include é eager no worker,
# lazy no pytest puro).
import app.tasks.pipeline  # noqa: F401


def test_task_registrada_no_celery_app():
    from app.celery_app import celery_app
    assert "app.tasks.pipeline.pipeline_ingest_task" in celery_app.tasks


def test_task_tem_retry_policy_bounded():
    from app.celery_app import celery_app
    task = celery_app.tasks["app.tasks.pipeline.pipeline_ingest_task"]
    assert task.max_retries == 2
    assert task.default_retry_delay == 30
    # acks_late herdado do celery_app.conf (não no decorador), mas task
    # respeita. Cheio OK — retry é o que importa.


def test_task_doc_not_found_nao_raise(monkeypatch):
    """document_id inválido: task retorna cleanly sem levantar."""
    import asyncio
    from app.tasks.pipeline import _run_analyze_async

    async def run():
        # UUID válido mas inexistente no DB de teste.
        await _run_analyze_async(
            "00000000-0000-0000-0000-000000000000",
            "00000000-0000-0000-0000-000000000001",
            "application/pdf",
        )

    # Não deve levantar.
    asyncio.run(run())


@pytest.mark.asyncio
async def test_task_storage_missing_marca_error(monkeypatch):
    """Storage inexistente: doc fica arguider_status='error'."""
    from datetime import datetime
    from uuid import uuid4

    from sqlalchemy import select

    from app.db.database import AsyncSessionLocal
    from app.models.base import IngestedDocument, Organization, Project, User
    from app.core.security import hash_password
    from app.tasks.pipeline import _run_analyze_async

    admin_id = uuid4()
    org_id = uuid4()
    project_id = uuid4()
    doc_id = uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(
                id=admin_id,
                email=f"mvp13-f133a-{admin_id.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="F133a Admin",
                is_active=True, is_admin=True,
                created_at=datetime.utcnow(),
            ))
            session.add(Organization(
                id=org_id, name=f"Org {org_id.hex[:6]}", slug=f"org-f133a-{org_id.hex[:6]}",
                owner_id=admin_id, is_active=True, created_at=datetime.utcnow(),
            ))
            await session.flush()
            session.add(Project(
                id=project_id, organization_id=org_id,
                name=f"P f133a {project_id.hex[:6]}",
                slug=f"p-f133a-{project_id.hex[:6]}",
                status="active", deliverable_type="new_system",
                created_at=datetime.utcnow(),
            ))
            await session.flush()
            session.add(IngestedDocument(
                id=doc_id,
                project_id=project_id,
                filename="nonexistent-file-deadbeef.pdf",  # read_ingested vai falhar
                original_filename="missing.pdf",
                file_type="application/pdf",
                file_size_bytes=0,
                file_hash="deadbeef",
                uploaded_by=admin_id,
                arguider_status="pending",
            ))

    # Roda a corrotina interna direto — evita Celery boilerplate.
    await _run_analyze_async(str(doc_id), str(project_id), "application/pdf")

    # Valida: doc ficou como error com mensagem.
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(IngestedDocument).where(IngestedDocument.id == doc_id))
        doc = res.scalar_one()
        assert doc.arguider_status == "error"
        assert "storage não encontrado" in (doc.arguider_error_message or "")

    # Cleanup
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(IngestedDocument.__table__.delete().where(IngestedDocument.id == doc_id))
            await session.execute(Project.__table__.delete().where(Project.id == project_id))
            await session.execute(Organization.__table__.delete().where(Organization.id == org_id))
            await session.execute(User.__table__.delete().where(User.id == admin_id))


def test_router_reanalyze_usa_task_celery(monkeypatch):
    """Fase 13.3a migrou o router reanalyze para pipeline_ingest_task.delay()."""
    import inspect
    from app.routers import ingestion_router

    src = inspect.getsource(ingestion_router)
    # Substituição da Fase 13.3a
    assert "pipeline_ingest_task" in src
    assert "pipeline_ingest_task.delay(" in src
    # O asyncio.create_task pra _analyze_async foi removido daquele trecho.
    # (Pode haver outros pontos em outros arquivos — cobertos em 13.3b/c.)
    lines = [line for line in src.splitlines() if "asyncio.create_task(svc._analyze_async" in line]
    assert lines == [], f"ponto de create_task no router não foi migrado: {lines}"
