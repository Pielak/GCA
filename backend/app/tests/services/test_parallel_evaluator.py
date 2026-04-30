"""Tests for Phase B — ParallelEvaluator and personas."""
import pytest
from app.services.personas.base import PersonaScore, PersonaIssue, PersonaQuestion, PersonaOutput
from app.services.personas.gp import GPPersona
from app.services.parallel_evaluator import ParallelEvaluator


def test_persona_score_creation():
    """Test PersonaScore dataclass."""
    score = PersonaScore(escopo=85, stack=72, dados=90)
    assert score.escopo == 85
    assert score.stack == 72
    assert score.dados == 90


def test_persona_issue_creation():
    """Test PersonaIssue dataclass."""
    issue = PersonaIssue(
        chunk_id="chunk_001",
        category="ambiguity",
        severity="critical",
        description="Escopo não claro",
        suggested_action="Clarificar com stakeholder"
    )
    assert issue.chunk_id == "chunk_001"
    assert issue.category == "ambiguity"
    assert issue.severity == "critical"


def test_persona_question_creation():
    """Test PersonaQuestion dataclass."""
    question = PersonaQuestion(
        id="Q-001",
        question_text="Qual o volume esperado?",
        rationale="Para dimensionar a infraestrutura",
        answer_type="numeric",
        severity="blocker",
        chunk_refs=["chunk_001", "chunk_002"]
    )
    assert question.id == "Q-001"
    assert len(question.chunk_refs) == 2


def test_persona_output_creation():
    """Test PersonaOutput dataclass."""
    scores = PersonaScore(escopo=85)
    output = PersonaOutput(
        persona_tag="gp",
        passada=1,
        scores=scores,
        approved=True,
        tentative=True,
        input_tokens=1200,
        output_tokens=340,
    )
    assert output.persona_tag == "gp"
    assert output.passada == 1
    assert output.tentative == True
    assert output.approved == True


def test_gp_persona_instantiation():
    """Test GP persona can be instantiated."""
    from app.services.llm_client import AnthropicLLMClient

    llm = AnthropicLLMClient()
    gp = GPPersona(llm)

    assert gp.tag == "gp"
    assert gp.name == "Gerente de Projetos"
    assert gp.llm == llm


def test_parallel_evaluator_instantiation():
    """Test ParallelEvaluator can be instantiated."""
    from app.services.llm_client import AnthropicLLMClient
    from unittest.mock import MagicMock

    llm = AnthropicLLMClient()
    db = MagicMock()  # Mock database session

    evaluator = ParallelEvaluator(llm, db)

    assert evaluator.llm == llm
    assert evaluator.db == db
    assert "gp" in evaluator.PERSONAS


@pytest.mark.asyncio
async def test_parallel_evaluator_passada_1_with_mock_llm():
    """Test Passada 1 execution with mocked LLM."""
    from app.services.llm_client import AnthropicLLMClient, LLMResponse, LLMUsage
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.schemas.chunk import Chunk
    from uuid import uuid4

    # Create mock LLM
    llm = AnthropicLLMClient()

    # Mock the complete method to return a valid GP response
    mock_response = LLMResponse(
        content='{"scores": {"escopo": 85, "stack": 72, "dados": 90, "implementacao": 80, "testes": 75}, "approved": true, "issues": [], "questions": [], "justification": "Escopo claro e time preparado"}',
        usage=LLMUsage(
            input_tokens=1000,
            output_tokens=300,
            cached_input_tokens=0
        ),
        finish_reason="end_turn"
    )

    llm.complete = AsyncMock(return_value=mock_response)

    # Create mock database and evaluator
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()

    evaluator = ParallelEvaluator(llm, db)

    # Create mock inputs
    route_map_id = uuid4()
    chunks = [
        Chunk(
            id="chunk_001",
            heading_path="/Requisitos/Escopo",
            chunk_type="section",
            text="O sistema deve ser um e-commerce com carrinho de compras",
            first_sentence="O sistema deve ser um e-commerce com carrinho de compras",
            position=0,
            tags=["GP", "ARQ"],
            token_count=20,
        )
    ]

    # Create mock route_map and auditor_output
    route_map = MagicMock()
    route_map.id = route_map_id
    route_map.chunks = [c.__dict__ for c in chunks]

    auditor_output = MagicMock()
    auditor_output.summary = "E-commerce com autenticação"
    auditor_output.highlights = {"GP": ["Escopo claro", "Timeline definida"]}
    auditor_output.backlog_to_specialists = []

    # Run Passada 1
    responses = await evaluator.run_passada_1(route_map, auditor_output)

    # Verify results
    assert "gp" in responses
    assert db.add.called
    assert db.commit.called

    # Verify the response has correct structure
    gp_response = responses["gp"]
    assert gp_response.persona_tag == "gp"
    assert gp_response.passada == 1
    assert gp_response.tentative is True
    assert gp_response.approved is True
