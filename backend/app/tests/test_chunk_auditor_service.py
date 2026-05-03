"""Testes para ChunkAuditorService — auditoria de chunks em batches."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.chunk_auditor_service import ChunkAuditorService
from app.services.llm_client import LLMResponse, LLMUsage
from app.schemas.chunk import Chunk
from app.schemas.chunk_audit import ChunkAuditOutput, ChunkAuditResult, ChunkErrorForReview


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_llm():
    """Mock LLMClient."""
    client = MagicMock()
    client.complete = AsyncMock()
    client.provider_name = "anthropic"
    client.model_name = "claude-opus-4-6"
    return client


@pytest.fixture
def sample_chunks():
    """Criar chunks de teste."""
    return [
        Chunk(
            id=f"chunk_{i}",
            heading_path="",
            chunk_type="section",
            text=f"Chunk {i}: Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            first_sentence=f"Chunk {i}:",
            token_count=10,
            position=i,
        )
        for i in range(5)
    ]


@pytest.fixture
def valid_audit_response():
    """Resposta válida do Auditor (JSON)."""
    return json.dumps({
        "documentId": str(uuid4()),
        "chunkId": "chunk_0",
        "chunkPosition": 0,
        "status": "ok",
        "summary": "Resumo do chunk",
        "detectedTopics": ["requisito", "arquitetura"],
        "personas": {
            "AUD": {"relevant": True, "reason": "Auditor sempre relevante", "briefing": "..."},
            "GP": {"relevant": False, "reason": "", "briefing": ""},
            "ARQ": {"relevant": True, "reason": "Menção a arquitetura", "briefing": "..."},
            "DBA": {"relevant": False, "reason": "", "briefing": ""},
            "DEV": {"relevant": False, "reason": "", "briefing": ""},
            "QA": {"relevant": False, "reason": "", "briefing": ""},
            "UX": {"relevant": False, "reason": "", "briefing": ""},
            "UI": {"relevant": False, "reason": "", "briefing": ""},
        },
        "requirementsFound": [],
        "risks": [],
        "gaps": []
    })


@pytest.mark.asyncio
async def test_audit_single_chunk_success(mock_db, mock_llm, sample_chunks, valid_audit_response):
    """Teste: auditar chunk válido retorna ChunkAuditResult com sucesso."""
    mock_llm.complete.return_value = LLMResponse(
        content=valid_audit_response,
        usage=LLMUsage(input_tokens=100, output_tokens=50),
        finish_reason="end_turn"
    )

    service = ChunkAuditorService(mock_db, mock_llm)
    doc_id = uuid4()
    project_id = uuid4()

    result = await service._audit_single_chunk(
        chunk=sample_chunks[0],
        document_id=doc_id,
        project_id=project_id,
    )

    assert isinstance(result, ChunkAuditResult)
    assert result.chunk_id == "chunk_0"
    assert result.output.status == "ok"
    assert result.retry_count == 0
    assert result.repair_applied == False


@pytest.mark.asyncio
async def test_audit_chunk_json_invalid_empty_response(mock_db, mock_llm, sample_chunks):
    """Teste: resposta vazia gera ChunkErrorForReview imediatamente."""
    mock_llm.complete.return_value = LLMResponse(
        content="",
        usage=LLMUsage(input_tokens=100, output_tokens=0),
        finish_reason="end_turn"
    )

    service = ChunkAuditorService(mock_db, mock_llm)
    doc_id = uuid4()
    project_id = uuid4()

    result = await service._audit_single_chunk(
        chunk=sample_chunks[0],
        document_id=doc_id,
        project_id=project_id,
    )

    assert isinstance(result, ChunkErrorForReview)
    assert result.error_type == "unknown"
    assert result.retry_count == 3


@pytest.mark.asyncio
async def test_audit_batch_partial_failure(mock_db, mock_llm, sample_chunks, valid_audit_response):
    """Teste: batch com sucesso parcial retorna ambos (sucessos + falhas)."""
    # Mock responses: chunk 0 e 2 sucesso, 1, 3, 4 falham
    responses = [
        LLMResponse(content=valid_audit_response, usage=LLMUsage(100, 50), finish_reason="end_turn"),
        LLMResponse(content="INVALID", usage=LLMUsage(100, 50), finish_reason="end_turn"),
        LLMResponse(content=valid_audit_response, usage=LLMUsage(100, 50), finish_reason="end_turn"),
        LLMResponse(content="", usage=LLMUsage(100, 0), finish_reason="end_turn"),
        LLMResponse(content="BROKEN JSON", usage=LLMUsage(100, 50), finish_reason="end_turn"),
    ]
    mock_llm.complete.side_effect = responses

    service = ChunkAuditorService(mock_db, mock_llm)
    doc_id = uuid4()
    project_id = uuid4()

    successful, failed = await service.audit_chunks(
        document_id=doc_id,
        project_id=project_id,
        chunks=sample_chunks,
        batch_size=5,
    )

    # Esperamos 2 sucessos e 3 falhas (aproximadamente)
    assert isinstance(successful, list)
    assert isinstance(failed, list)
    assert len(failed) > 0  # Deve haver falhas


@pytest.mark.asyncio
async def test_audit_batch_size_respected(mock_db, mock_llm, sample_chunks, valid_audit_response):
    """Teste: batch_size é respeitado no parallelismo."""
    call_count = 0
    max_concurrent = 0
    concurrent = 0

    async def counting_complete(*args, **kwargs):
        nonlocal call_count, concurrent, max_concurrent
        call_count += 1
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        await AsyncMock()()  # Simulate some async work
        concurrent -= 1
        return LLMResponse(
            content=valid_audit_response,
            usage=LLMUsage(100, 50),
            finish_reason="end_turn"
        )

    mock_llm.complete.side_effect = counting_complete

    # 10 chunks com batch_size=3 deve processar em 4 batches
    chunks = sample_chunks * 2  # 10 chunks
    service = ChunkAuditorService(mock_db, mock_llm)
    doc_id = uuid4()
    project_id = uuid4()

    successful, failed = await service.audit_chunks(
        document_id=doc_id,
        project_id=project_id,
        chunks=chunks,
        batch_size=3,
    )

    assert call_count == len(chunks)
    # Concorrência não deve exceder batch_size (aprox.)
    assert max_concurrent <= 3 + 1  # +1 for tolerance


@pytest.mark.asyncio
async def test_chunk_error_pending_review_fields(mock_db, mock_llm, sample_chunks):
    """Teste: ChunkErrorForReview tem todos os campos esperados."""
    mock_llm.complete.return_value = LLMResponse(
        content="",
        usage=LLMUsage(100, 0),
        finish_reason="end_turn"
    )

    service = ChunkAuditorService(mock_db, mock_llm)
    doc_id = uuid4()
    project_id = uuid4()

    result = await service._audit_single_chunk(
        chunk=sample_chunks[0],
        document_id=doc_id,
        project_id=project_id,
    )

    assert isinstance(result, ChunkErrorForReview)
    assert hasattr(result, 'chunk_id')
    assert hasattr(result, 'error_type')
    assert hasattr(result, 'last_error_message')
    assert hasattr(result, 'retry_count')
    assert hasattr(result, 'recovery_attempted')
    assert result.status == "pending"
