"""Schemas para auditoria de chunks — ChunkAuditorService."""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime


class PersonaRelevance(BaseModel):
    """Relevância de um chunk para uma persona específica."""
    relevant: bool
    reason: str = Field(..., min_length=1, max_length=500)
    briefing: str = Field(default="", max_length=2000)


class RequirementFound(BaseModel):
    """Requisito detectado no chunk."""
    id: str = Field(..., min_length=1, max_length=50)
    type: Literal["business", "functional", "non_functional", "data", "integration", "security", "ux", "ui", "qa"]
    text: str = Field(..., min_length=1, max_length=1000)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class Risk(BaseModel):
    """Risco identificado no chunk."""
    id: str = Field(..., min_length=1, max_length=50)
    severity: Literal["low", "medium", "high", "critical"]
    description: str = Field(..., min_length=1, max_length=1000)


class Gap(BaseModel):
    """Gap de informação — questão para humano."""
    id: str = Field(..., min_length=1, max_length=50)
    question: str = Field(..., min_length=1, max_length=500)
    targetPersona: Literal["AUD", "GP", "ARQ", "DBA", "DEV", "QA", "UX", "UI"]


class ChunkAuditOutput(BaseModel):
    """Saída estruturada de auditoria para um chunk."""
    documentId: str = Field(..., min_length=1)
    chunkId: str = Field(..., min_length=1, max_length=64)
    chunkPosition: int = Field(..., ge=0)
    status: Literal["ok", "partial", "quarantine"]
    summary: str = Field(..., min_length=1, max_length=500)
    detectedTopics: list[str] = Field(default=[], max_items=20)
    personas: dict[str, PersonaRelevance] = Field(
        default_factory=lambda: {
            "AUD": PersonaRelevance(relevant=True, reason="Auditor sempre relevante", briefing=""),
            "GP": PersonaRelevance(relevant=False, reason="", briefing=""),
            "ARQ": PersonaRelevance(relevant=False, reason="", briefing=""),
            "DBA": PersonaRelevance(relevant=False, reason="", briefing=""),
            "DEV": PersonaRelevance(relevant=False, reason="", briefing=""),
            "QA": PersonaRelevance(relevant=False, reason="", briefing=""),
            "UX": PersonaRelevance(relevant=False, reason="", briefing=""),
            "UI": PersonaRelevance(relevant=False, reason="", briefing=""),
        }
    )
    requirementsFound: list[RequirementFound] = Field(default=[], max_items=50)
    risks: list[Risk] = Field(default=[], max_items=20)
    gaps: list[Gap] = Field(default=[], max_items=10)


class ChunkAuditResult(BaseModel):
    """Resultado de auditoria de um chunk — sucesso."""
    chunk_id: str
    output: ChunkAuditOutput
    extraction_time_ms: int
    retry_count: int = 0
    repair_applied: bool = False
    error_code: Optional[str] = None


class ChunkErrorForReview(BaseModel):
    """Chunk com erro — aguardando revisão humana."""
    chunk_id: str
    document_id: UUID
    error_type: Literal["json_invalid", "timeout", "llm_refusal", "schema_validation", "unknown"]
    retry_count: int
    last_error_message: str = Field(..., max_length=2000)
    recovery_attempted: bool
    suggested_fallback: Optional[str] = Field(default=None, max_length=1000)
    status: Literal["pending", "resolved", "escalated"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
