"""Schemas para os 6 outputs do Auditor."""
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.chunk import PersonaTag, TECHNICAL_TAGS


# === Output 5: Backlog para especialistas ===

class BacklogItem(BaseModel):
    id: str = Field(..., description="ID estável: 'backlog_001'")
    category: Literal[
        "ambiguity",
        "missing_info",
        "internal_conflict",
        "domain_jargon",
        "uncertain_routing",
    ]
    severity: Literal["high", "medium", "low"]
    chunk_refs: list[str]
    target_personas: list[PersonaTag]
    description: str
    auditor_hypothesis: Optional[str] = None
    suggested_action: str


# === Output 6: Questionário para humano ===

class QuestionForHuman(BaseModel):
    id: str = Field(..., description="ID estável: 'Q-001'")
    asked_by: PersonaTag
    target_human_role: Literal[
        "gerente_projetos", "tech_lead", "dba", "dev_senior",
        "qa_lead", "ux_designer", "ui_designer",
    ]
    category: Literal[
        "missing_data",
        "decision_required",
        "validation_request",
        "context_clarification",
        "constraint_check",
    ]
    severity: Literal["blocker", "important", "informational"]

    question_text: str
    rationale: str

    answer_type: Literal[
        "single_choice", "multi_choice", "numeric",
        "boolean", "free_text", "file_upload",
    ]
    answer_options: Optional[list[str]] = None
    answer_unit: Optional[str] = None

    blocks_personas: list[PersonaTag]
    blocks_pillars: list[str]

    chunk_refs: list[str] = Field(default_factory=list)


# === Output completo do Auditor ===

class AuditorOutput(BaseModel):
    summary: str
    summary_token_count: int
    chunk_tags: dict[str, list[PersonaTag]]
    highlights: dict[PersonaTag, list[str]]
    audit_findings: dict
    backlog_to_specialists: list[BacklogItem]
    questionnaire_to_human: list[QuestionForHuman]

    project_size_mode: Literal["solo", "small", "large"]
    consolidation_applied: bool
    error_code: Optional[str] = None
    fallback_used: bool = False


class AuditorOutputRead(BaseModel):
    id: UUID
    route_map_id: UUID
    summary: str
    chunk_tags: dict
    highlights: dict
    audit_findings: dict
    backlog_to_specialists: list[BacklogItem]
    questionnaire_to_human: list[QuestionForHuman]
    elapsed_ms: int
    created_at: datetime

    class Config:
        from_attributes = True
