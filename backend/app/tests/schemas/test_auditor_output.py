"""Tests for Auditor output schemas."""
import pytest
from app.schemas.chunk import Chunk, PersonaTag
from app.schemas.auditor_output import (
    BacklogItem, QuestionForHuman, AuditorOutput
)


def test_chunk_schema():
    """Test Chunk schema validation."""
    chunk = Chunk(
        id="chunk_001",
        heading_path="Main / Section",
        chunk_type="section",
        text="Some text content",
        first_sentence="Some text.",
        token_count=10,
        position=0,
        tags=["GP", "ARQ"],
    )
    assert chunk.id == "chunk_001"
    assert len(chunk.tags) == 2


def test_chunk_unique_tags():
    """Test that chunk tags must be unique."""
    with pytest.raises(ValueError, match="duplicadas"):
        Chunk(
            id="chunk_001",
            heading_path="Main",
            chunk_type="section",
            text="Text",
            first_sentence="Text.",
            token_count=5,
            position=0,
            tags=["GP", "GP"],  # Duplicate
        )


def test_backlog_item_schema():
    """Test BacklogItem schema."""
    item = BacklogItem(
        id="backlog_001",
        category="ambiguity",
        severity="high",
        chunk_refs=["chunk_001", "chunk_002"],
        target_personas=["GP", "ARQ"],
        description="Some ambiguity found",
        auditor_hypothesis="Could mean X or Y",
        suggested_action="Clarify with stakeholder",
    )
    assert item.id == "backlog_001"
    assert item.severity == "high"


def test_question_for_human_schema():
    """Test QuestionForHuman schema."""
    question = QuestionForHuman(
        id="Q-001",
        asked_by="AUD",
        target_human_role="gerente_projetos",
        category="missing_data",
        severity="blocker",
        question_text="What is X?",
        rationale="Need this to proceed",
        answer_type="single_choice",
        answer_options=["Option A", "Option B", "Option C"],
        blocks_personas=["GP", "ARQ"],
        blocks_pillars=["escopo"],
    )
    assert question.id == "Q-001"
    assert len(question.answer_options) == 3


def test_auditor_output_schema():
    """Test complete AuditorOutput schema."""
    output = AuditorOutput(
        summary="Project summary",
        summary_token_count=100,
        chunk_tags={"chunk_001": ["GP", "ARQ"]},
        highlights={"GP": ["Point 1"], "ARQ": ["Point 2"]},
        audit_findings={"completeness": "Good"},
        backlog_to_specialists=[],
        questionnaire_to_human=[],
        project_size_mode="small",
        consolidation_applied=False,
        fallback_used=False,
    )
    assert output.summary == "Project summary"
    assert output.project_size_mode == "small"
