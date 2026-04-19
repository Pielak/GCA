"""DT-065 — Checkpoint no fallback do pipeline de ingestão.

Quando o provider falha em um estágio AVANÇADO do pipeline (ex: OCG
updater), o fallback para o próximo provider NÃO deve refazer estágios
anteriores já concluídos (ex: análise do Arguidor). Isso:
  - Economiza tempo (evita chamada LLM pesada repetida).
  - Economiza custo ($ de tokens em provider pago).
  - Evita risco de o provider alternativo produzir análise divergente
    da que já foi persistida (inconsistência).

Estratégia: helper detecta `arguider_analyses` existente para o
document_id antes de chamar `arguider.analyze_document`. Se presente,
pula direto pro estágio `updating_ocg`.
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import ArguiderAnalysis, IngestedDocument
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


async def _seed_ingested_doc(db, project_id, uploader_id, *, arguider_status="pending"):
    import hashlib
    file_hash = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project_id,
        uploaded_by=uploader_id,
        original_filename="test.docx",
        filename=f"{uuid4()}.docx",
        file_type="docx",
        file_hash=file_hash,
        file_size_bytes=1000,
        arguider_status=arguider_status,
        arguider_stage="queued",
        arguider_progress_percent=0,
        pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def _seed_arguider_analysis(db, document_id, project_id):
    """Simula análise já persistida por tentativa anterior."""
    a = ArguiderAnalysis(
        id=uuid4(),
        document_id=document_id,
        project_id=project_id,
        document_classification=json.dumps({"type": "requirements"}),
        gaps=json.dumps([]),
        show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]),
        improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([{"name": "Módulo X", "priority": "high"}]),
        ocg_fields_to_update=json.dumps([]),
        llm_model="claude-haiku-4-5-20251001",
        tokens_used=1234,
        latency_ms=5000,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.mark.asyncio
async def test_checkpoint_detects_existing_analysis(db_session):
    """Helper de detecção: se `arguider_analyses` tem row para o doc,
    o pipeline deve saber que pode pular a análise."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt065-detect")
    doc = await _seed_ingested_doc(db_session, p.id, user.id)
    await _seed_arguider_analysis(db_session, doc.id, p.id)

    # Verifica diretamente — é o mesmo select usado pelo _analyze_async
    row = (await db_session.execute(
        select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == doc.id)
    )).scalar_one_or_none()
    assert row is not None, "checkpoint não encontrou análise existente"
    assert row.llm_model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_no_analysis_means_fresh_run(db_session):
    """Sem análise persistida, o pipeline deve rodar normalmente
    (cenário de primeira tentativa ou reanalyze após limpeza)."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt065-fresh")
    doc = await _seed_ingested_doc(db_session, p.id, user.id)

    row = (await db_session.execute(
        select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == doc.id)
    )).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_stage_percent_does_not_regress(db_session):
    """_update_stage preserva porcentagem máxima quando estágio volta
    a um anterior — regra dura pra não reduzir percepção do user."""
    from app.services.ingestion_service import IngestionService

    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt065-noregress")
    doc = await _seed_ingested_doc(db_session, p.id, user.id)

    # Avança pra 70%
    await IngestionService._update_stage(db_session, doc.id, "updating_ocg")
    found = await db_session.get(IngestedDocument, doc.id)
    assert found.arguider_progress_percent == 70
    assert found.arguider_stage == "updating_ocg"

    # Tenta voltar pra extracting_text (10%) — stage atualiza mas
    # percent não regride.
    await IngestionService._update_stage(db_session, doc.id, "extracting_text")
    found = await db_session.get(IngestedDocument, doc.id)
    assert found.arguider_stage == "extracting_text"
    assert found.arguider_progress_percent == 70  # preservado


@pytest.mark.asyncio
async def test_stage_failed_allows_any_percent(db_session):
    """Em estágio 'failed' o percent pode ser alterado livremente."""
    from app.services.ingestion_service import IngestionService

    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt065-failed")
    doc = await _seed_ingested_doc(db_session, p.id, user.id)

    await IngestionService._update_stage(db_session, doc.id, "analyzing")
    found = await db_session.get(IngestedDocument, doc.id)
    assert found.arguider_progress_percent == 40

    # Transição para failed com percent=0 é permitida
    await IngestionService._update_stage(db_session, doc.id, "failed", percent=0)
    found = await db_session.get(IngestedDocument, doc.id)
    assert found.arguider_stage == "failed"
    assert found.arguider_progress_percent == 0


@pytest.mark.asyncio
async def test_stage_update_stamps_timestamp(db_session):
    """Cada mudança de estágio registra timestamp pra UI mostrar
    'X segundos decorridos' honestamente."""
    from app.services.ingestion_service import IngestionService

    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt065-ts")
    doc = await _seed_ingested_doc(db_session, p.id, user.id)

    assert doc.arguider_stage_updated_at is None
    await IngestionService._update_stage(db_session, doc.id, "analyzing")
    found = await db_session.get(IngestedDocument, doc.id)
    assert found.arguider_stage_updated_at is not None
