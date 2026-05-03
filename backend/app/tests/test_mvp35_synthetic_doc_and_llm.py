"""MVP 35 Fase 35.5 — Testes do IngestedDocument sintético + LLM sanity check.

Cobre:
  - Hash canônico idempotente (Arq-M2): listas com ordens diferentes = mesmo hash
  - Dup-check com filtro deleted_at IS NULL (DBA-M1)
  - IngestedDocument sintético com file_type='questionnaire' + arguider_status='completed'
  - Guard A-M1: file_type='questionnaire' não dispara n8n
  - LLM sanity check bloqueia submit em falha (DBA-M2)
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.base import IngestedDocument
from app.services.questionnaire_validation.llm_sanity_check import llm_sanity_check
from app.services.questionnaire_validation.synthetic_document import (
    QUESTIONNAIRE_FILE_TYPE,
    QUESTIONNAIRE_STAGE,
    canonical_responses,
    compute_questionnaire_hash,
    create_or_get_synthetic_document,
)
from app.tests.factories import (
    create_test_organization,
    create_test_project,
    create_test_user,
)


async def _seed_project(db):
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    project = await create_test_project(
        db, organization_id=org.id, slug=f"mvp35-syn-{uuid4().hex[:6]}"
    )
    return user, project


# =============================================================================
# Hash canônico — idempotência (Arq-M2)
# =============================================================================


def test_canonical_responses_ordena_listas():
    """Listas com ordens diferentes viram canonicas iguais."""
    r1 = {"Q5": ["Python/FastAPI", "Go"]}
    r2 = {"Q5": ["Go", "Python/FastAPI"]}
    assert canonical_responses(r1) == canonical_responses(r2)


def test_canonical_responses_preserva_scalars():
    """Scalars (string/int/bool) não são tocados."""
    r = {"Q1": "Novo sistema", "Q3": "Não", "Q7": "1000"}
    assert canonical_responses(r) == r


def test_hash_idempotente_listas_ordens_diferentes():
    """Hash de mesma resposta canônica = mesmo hash (independente de ordem)."""
    r1 = {"Q5": ["Python/FastAPI", "Go"], "Q1": "Novo sistema"}
    r2 = {"Q1": "Novo sistema", "Q5": ["Go", "Python/FastAPI"]}
    assert compute_questionnaire_hash(r1) == compute_questionnaire_hash(r2)


def test_hash_diferente_para_responses_diferentes():
    r1 = {"Q1": "Novo sistema"}
    r2 = {"Q1": "Refactor de existente"}
    assert compute_questionnaire_hash(r1) != compute_questionnaire_hash(r2)


def test_hash_64_caracteres_hex():
    """SHA256 = 64 chars hex."""
    h = compute_questionnaire_hash({"Q1": "x"})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# =============================================================================
# create_or_get_synthetic_document — idempotência + dup-check
# =============================================================================


@pytest.mark.asyncio
async def test_create_synthetic_document_primeira_vez(db_session):
    """Primeira chamada cria novo IngestedDocument com tipo questionnaire."""
    user, project = await _seed_project(db_session)
    questionnaire_id = uuid4()
    responses = {"Q1": "Novo sistema", "Q5": ["Python/FastAPI"]}

    doc, created = await create_or_get_synthetic_document(
        db=db_session,
        project_id=project.id,
        project_name=project.name,
        questionnaire_id=questionnaire_id,
        responses=responses,
        uploaded_by=user.id,
    )
    assert created is True
    assert doc.file_type == "questionnaire"
    assert doc.arguider_status == "completed"
    assert doc.arguider_stage == QUESTIONNAIRE_STAGE
    assert doc.ocg_updated is True
    assert doc.original_filename.startswith("Questionário Técnico")
    assert str(questionnaire_id) in doc.filename


@pytest.mark.asyncio
async def test_create_synthetic_document_idempotente(db_session):
    """Segunda chamada com mesmas responses retorna doc existente (created=False)."""
    user, project = await _seed_project(db_session)
    questionnaire_id = uuid4()
    responses = {"Q1": "Novo sistema", "Q5": ["Python/FastAPI"]}

    doc1, created1 = await create_or_get_synthetic_document(
        db=db_session,
        project_id=project.id,
        project_name=project.name,
        questionnaire_id=questionnaire_id,
        responses=responses,
        uploaded_by=user.id,
    )
    doc2, created2 = await create_or_get_synthetic_document(
        db=db_session,
        project_id=project.id,
        project_name=project.name,
        questionnaire_id=questionnaire_id,
        responses=responses,
        uploaded_by=user.id,
    )
    assert created1 is True
    assert created2 is False
    assert doc1.id == doc2.id


@pytest.mark.asyncio
async def test_create_synthetic_document_idempotente_ordens_diferentes(db_session):
    """Re-submit com listas em ordem diferente reusa row (hash canônico Arq-M2)."""
    user, project = await _seed_project(db_session)
    questionnaire_id = uuid4()

    doc1, _ = await create_or_get_synthetic_document(
        db=db_session, project_id=project.id, project_name=project.name,
        questionnaire_id=questionnaire_id,
        responses={"Q5": ["Python/FastAPI", "Go"]},
        uploaded_by=user.id,
    )
    doc2, created2 = await create_or_get_synthetic_document(
        db=db_session, project_id=project.id, project_name=project.name,
        questionnaire_id=questionnaire_id,
        responses={"Q5": ["Go", "Python/FastAPI"]},  # ordem invertida
        uploaded_by=user.id,
    )
    assert doc1.id == doc2.id
    assert created2 is False


@pytest.mark.asyncio
async def test_dup_check_filtra_deleted_at_null(db_session):
    """Soft-delete + re-submit com mesmo hash = nova row criada (DBA-M1)."""
    user, project = await _seed_project(db_session)
    questionnaire_id = uuid4()
    responses = {"Q1": "Novo sistema"}

    doc1, _ = await create_or_get_synthetic_document(
        db=db_session, project_id=project.id, project_name=project.name,
        questionnaire_id=questionnaire_id, responses=responses, uploaded_by=user.id,
    )

    # Soft-delete (MVP 34)
    doc1.deleted_at = datetime.now(timezone.utc)
    doc1.deleted_reason = "manual"
    await db_session.flush()

    # Re-submit com responses idênticas — DEVE criar novo (não reusar deletado)
    doc2, created2 = await create_or_get_synthetic_document(
        db=db_session, project_id=project.id, project_name=project.name,
        questionnaire_id=uuid4(),  # novo questionnaire_id
        responses=responses, uploaded_by=user.id,
    )
    assert created2 is True
    assert doc2.id != doc1.id
    assert doc2.file_hash == doc1.file_hash  # mesmo hash, mas dup-check filtrou deleted


# =============================================================================
# Guard A-M1: file_type='questionnaire' NÃO entra no pipeline n8n
# =============================================================================


def test_dispatch_to_n8n_skip_questionnaire():
    """ingestion_service._dispatch_to_n8n tem guard explícito para 'questionnaire'."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "services" / "ingestion_service.py").read_text()
    assert "if file_type == \"questionnaire\":" in src
    assert "ingestion.dispatch_skipped_questionnaire_synthetic" in src


def test_pipeline_celery_skip_questionnaire():
    """ingestion_service também tem guard no caminho Celery."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "services" / "ingestion_service.py").read_text()
    assert "file_type != \"questionnaire\"" in src


# =============================================================================
# LLM sanity check — DBA-M2 (bloqueia em falha)
# =============================================================================


@pytest.mark.asyncio
async def test_llm_sanity_check_bloqueia_quando_provider_indisponivel(db_session):
    """LLM call levanta HTTPException 503 → llm_sanity_check propaga 503 (DBA-M2)."""
    user, project = await _seed_project(db_session)

    with patch(
        "app.services.codegen_llm.call_codegen_llm",
        new=AsyncMock(side_effect=HTTPException(503, "no provider")),
    ):
        with pytest.raises(HTTPException) as exc:
            await llm_sanity_check(
                db=db_session,
                project_id=project.id,
                responses={"Q1": "Novo sistema"},
                conflicts_detected=[],
            )
    assert exc.value.status_code == 503
    assert "indispon" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_llm_sanity_check_sucesso_parsea_json(db_session):
    """LLM retorna JSON válido → parse + retorna incoherences."""
    user, project = await _seed_project(db_session)
    fake_response = json.dumps({
        "incoherences": [
            {"description": "K8s + 2 devs", "severity": "warning", "suggestion": "VPS simples"}
        ]
    })

    with patch(
        "app.services.codegen_llm.call_codegen_llm",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await llm_sanity_check(
            db=db_session,
            project_id=project.id,
            responses={"Q1": "Novo sistema"},
            conflicts_detected=[],
        )
    assert result["llm_used"] is True
    assert len(result["incoherences"]) == 1
    assert result["incoherences"][0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_llm_sanity_check_parse_falha_retorna_vazio(db_session):
    """LLM cuspe não-JSON → degrada para sem incoerências (não bloqueia)."""
    user, project = await _seed_project(db_session)

    with patch(
        "app.services.codegen_llm.call_codegen_llm",
        new=AsyncMock(return_value="texto sem json"),
    ):
        result = await llm_sanity_check(
            db=db_session,
            project_id=project.id,
            responses={},
            conflicts_detected=[],
        )
    assert result["incoherences"] == []
    assert result["llm_used"] is True


# =============================================================================
# IngestedDocument sintético — campos canônicos
# =============================================================================


@pytest.mark.asyncio
async def test_synthetic_document_arguider_completed(db_session):
    """Doc sintético tem arguider_status='completed' — NÃO entra no pipeline."""
    user, project = await _seed_project(db_session)
    doc, _ = await create_or_get_synthetic_document(
        db=db_session, project_id=project.id, project_name=project.name,
        questionnaire_id=uuid4(), responses={"Q1": "x"}, uploaded_by=user.id,
    )
    assert doc.arguider_status == "completed"
    assert doc.arguider_progress_percent == 100


@pytest.mark.asyncio
async def test_synthetic_document_filename_canonico(db_session):
    """filename = questionnaire-{id}.json"""
    user, project = await _seed_project(db_session)
    qid = uuid4()
    doc, _ = await create_or_get_synthetic_document(
        db=db_session, project_id=project.id, project_name=project.name,
        questionnaire_id=qid, responses={"Q1": "x"}, uploaded_by=user.id,
    )
    assert doc.filename == f"questionnaire-{qid}.json"
    assert "Questionário Técnico" in doc.original_filename
    assert project.name in doc.original_filename
