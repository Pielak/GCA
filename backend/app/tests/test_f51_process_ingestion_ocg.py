"""Testes F5.1 — Celery task process_ingestion_complete_ocg.

Cobre:
  - Task registrada no Celery com max_retries=3, acks_late=True.
  - Idempotência: skip quando arguider_status != 'ocg_updating'.
  - Handler retorna 202 com celery_task_id persistido.
  - Handler retorna 503 quando broker offline (não fallback síncrono).
  - Handler grava arguider_status='ocg_updating' antes do enqueue.

Banco alvo: gca_test (conftest.py força — DT-034).

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_f51_process_ingestion_ocg.py -v"
"""
from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.db.database import get_db
from app.main import app
from app.models.base import IngestedDocument, OCG, Questionnaire
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


_ENDPOINT = "/api/v1/webhooks/ingestion-complete"
_TAGS = ["AUD", "GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI", "SEG"]


def _build_payload(doc_id: str, project_id: str) -> dict:
    return {
        "ingestion_id": doc_id,
        "project_id": project_id,
        "status": "completed",
        "overall_score": 78,
        "blocked": False,
        "blocking_reason": None,
        "personas_executed": _TAGS,
        "personas_failed": [],
        "ocg_individual": {
            tag: {"persona_name": f"P {tag}", "score": 75, "analise": "ok"}
            for tag in _TAGS
        },
        "ocg_global_delta": {"k": "v"},
        "conflicts_resolved": [],
        "consolidated_findings": [],
        "consolidated_recommendations": [],
        "execution_summary": {"duracao_total_ms": 100},
    }


async def _seed(db):
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(db, organization_id=org.id, slug=f"f51-{uuid4().hex[:6]}")

    q = Questionnaire(
        id=uuid4(), project_id=project.id,
        gp_email=f"gp-{uuid4().hex[:6]}@t.com",
        responses="{}", status="approved", approved=True,
    )
    db.add(q)
    await db.flush()
    ocg = OCG(
        id=uuid4(), questionnaire_id=q.id, project_id=project.id,
        status="READY", is_blocking=False,
        ocg_data=json.dumps({"PILLAR_SCORES": {f"P{i}_x": {"score": 75.0} for i in range(1, 8)}}),
        version=1,
    )
    db.add(ocg)
    await db.flush()

    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=project.id, uploaded_by=user.id,
        original_filename="f51.pdf", filename=f"{uuid4()}.pdf", file_type="pdf",
        file_hash=h, file_size_bytes=1024,
        arguider_status="processing", pii_detected=False,
    )
    db.add(doc)
    await db.flush()
    return project, doc


@asynccontextmanager
async def _client(db):
    async def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


# =============================================================================
# Caso 1 — Task registrada
# =============================================================================

def test_task_registrada_no_celery():
    # Importa o módulo de tasks pra forçar registro
    import app.tasks.pipeline  # noqa: F401
    from app.celery_app import celery_app
    assert "app.tasks.pipeline.process_ingestion_complete_ocg" in celery_app.tasks


def test_task_retry_policy_canonica():
    from app.tasks.pipeline import process_ingestion_complete_ocg
    assert process_ingestion_complete_ocg.max_retries == 3
    assert process_ingestion_complete_ocg.acks_late is True
    assert process_ingestion_complete_ocg.name == (
        "app.tasks.pipeline.process_ingestion_complete_ocg"
    )


# =============================================================================
# Caso 2 — Handler grava ocg_updating + enfileira + retorna 202
# =============================================================================

@pytest.mark.asyncio
async def test_handler_grava_ocg_updating_e_enfileira(db_session):
    project, doc = await _seed(db_session)
    payload = _build_payload(str(doc.id), str(project.id))

    with patch("app.tasks.pipeline.process_ingestion_complete_ocg.delay") as mock_delay:
        mock_delay.return_value = type("R", (), {"id": "task-id-abc"})()
        async with _client(db_session) as c:
            resp = await c.post(_ENDPOINT, json=payload)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["ingestion_id"] == str(doc.id)

    mock_delay.assert_called_once()
    args = mock_delay.call_args.args
    assert args == (str(doc.id), str(project.id))

    row = (await db_session.execute(
        text("SELECT arguider_status, celery_task_id FROM ingested_documents WHERE id=:id"),
        {"id": str(doc.id)},
    )).first()
    assert row[0] == "ocg_updating"
    assert row[1] == "task-id-abc"


# =============================================================================
# Caso 3 — Broker offline → 503 + revert para 'processing'
# =============================================================================

@pytest.mark.asyncio
async def test_handler_503_quando_broker_offline(db_session):
    """CR-4 do Arquiteto: NÃO fallback silencioso pra síncrono — 503 explícito.
    N8n retry vai retentar o callback."""
    project, doc = await _seed(db_session)
    payload = _build_payload(str(doc.id), str(project.id))

    def _broker_dead(*_a, **_kw):
        raise ConnectionError("Connection refused: redis://broker")

    with patch(
        "app.tasks.pipeline.process_ingestion_complete_ocg.delay",
        side_effect=_broker_dead,
    ):
        async with _client(db_session) as c:
            resp = await c.post(_ENDPOINT, json=payload)

    assert resp.status_code == 503
    assert "broker" in resp.text.lower() or "celery" in resp.text.lower()

    # Status revertido pra 'processing' — n8n retry retoma do zero.
    row = (await db_session.execute(
        text("SELECT arguider_status, arguider_error_message FROM ingested_documents WHERE id=:id"),
        {"id": str(doc.id)},
    )).first()
    assert row[0] == "processing"
    assert row[1] and "enfileirar" in row[1]


# =============================================================================
# Caso 4 — Idempotência da task: skip quando status != 'ocg_updating'
# =============================================================================

@pytest.mark.asyncio
async def test_task_idempotencia_skip_se_nao_ocg_updating(db_session):
    """GP MUST 1: task com doc em status != 'ocg_updating' → skip
    silencioso sem chamar OCGUpdater. Patch AsyncSessionLocal pra
    a função reutilizar a fixture session (db_session de teste tem
    auto-rollback — commits da função real não persistem no banco)."""
    project, doc = await _seed(db_session)
    doc.arguider_status = "completed"
    await db_session.flush()

    # Patch AsyncSessionLocal pra usar a fixture session em todas as
    # 3 fases internas da task. Cada `async with AsyncSessionLocal()`
    # vira um no-op context que retorna a mesma db_session.
    @asynccontextmanager
    async def _fake_local():
        yield db_session

    from app.tasks.pipeline import _run_process_ingestion_complete_ocg

    with patch("app.db.database.AsyncSessionLocal", _fake_local), \
         patch("app.services.ocg_updater_service.OCGUpdaterService.update_ocg_from_arguider") as mock_upd:
        result = await _run_process_ingestion_complete_ocg(str(doc.id), str(project.id))

    assert result["status"] == "skipped"
    assert result["reason"] == "completed"
    mock_upd.assert_not_called()


@pytest.mark.asyncio
async def test_task_idempotencia_skip_se_ocg_pending(db_session):
    """Task chamada de novo após esgotar retries (status='ocg_pending'):
    skip silencioso, NÃO retentar."""
    project, doc = await _seed(db_session)
    doc.arguider_status = "ocg_pending"
    await db_session.flush()

    @asynccontextmanager
    async def _fake_local():
        yield db_session

    from app.tasks.pipeline import _run_process_ingestion_complete_ocg
    with patch("app.db.database.AsyncSessionLocal", _fake_local), \
         patch("app.services.ocg_updater_service.OCGUpdaterService.update_ocg_from_arguider") as mock_upd:
        result = await _run_process_ingestion_complete_ocg(str(doc.id), str(project.id))

    assert result["status"] == "skipped"
    assert result["reason"] == "ocg_pending"
    mock_upd.assert_not_called()


@pytest.mark.asyncio
async def test_task_doc_inexistente(db_session):
    """Task chamada com ingestion_id que não existe → not_found graceful."""
    project, _ = await _seed(db_session)
    fake_id = str(uuid4())

    @asynccontextmanager
    async def _fake_local():
        yield db_session

    from app.tasks.pipeline import _run_process_ingestion_complete_ocg
    with patch("app.db.database.AsyncSessionLocal", _fake_local):
        result = await _run_process_ingestion_complete_ocg(fake_id, str(project.id))

    assert result["status"] == "not_found"
    assert result["ingestion_id"] == fake_id


# =============================================================================
# Caso 5 — Schema F5.1: colunas existem em gca_test
# =============================================================================

@pytest.mark.asyncio
async def test_schema_f51_colunas_existem(db_session):
    """Migration 071: celery_task_id em ingested_documents,
    ocg_update_duration_ms em ocg_delta_log."""
    row1 = (await db_session.execute(text("""
        SELECT character_maximum_length FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='ingested_documents' AND column_name='celery_task_id'
    """))).first()
    assert row1 is not None, "celery_task_id ausente em ingested_documents"
    assert row1[0] == 64

    row2 = (await db_session.execute(text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='ocg_delta_log' AND column_name='ocg_update_duration_ms'
    """))).first()
    assert row2 is not None, "ocg_update_duration_ms ausente em ocg_delta_log"
    assert row2[0] == "integer"
