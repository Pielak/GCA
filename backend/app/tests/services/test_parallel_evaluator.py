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
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    from app.db.database import Base

    # In-memory SQLite
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    llm = AnthropicLLMClient()
    evaluator = ParallelEvaluator(llm, db)

    assert evaluator.llm == llm
    assert evaluator.db == db
    assert "gp" in evaluator.PERSONAS
