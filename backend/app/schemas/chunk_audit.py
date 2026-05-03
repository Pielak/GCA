"""Schemas para auditoria de chunks — ChunkAuditorService."""
import re
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime


class PersonaRelevance(BaseModel):
    relevant: bool
    reason: str = Field(default="", max_length=500)
    briefing: str = Field(default="", max_length=2000)


class RequirementFound(BaseModel):
    id: str = Field(default="", max_length=50)
    type: str = Field(default="functional", max_length=50)
    text: str = Field(default="", max_length=2000)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def coerce_from_string(cls, data):
        if isinstance(data, str):
            m = re.match(r"^([A-Za-z0-9_-]+):\s*(.+)$", data, re.DOTALL)
            if m:
                return {"id": m.group(1)[:50], "text": m.group(2)[:2000]}
            return {"text": data[:2000]}
        return data


class Risk(BaseModel):
    id: str = Field(default="", max_length=50)
    severity: str = Field(default="medium", max_length=50)
    description: str = Field(default="", max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def coerce_from_string(cls, data):
        if isinstance(data, str):
            m = re.match(r"^([A-Za-z0-9_-]+):\s*(.+)$", data, re.DOTALL)
            if m:
                return {"id": m.group(1)[:50], "description": m.group(2)[:2000]}
            return {"description": data[:2000]}
        return data


class Gap(BaseModel):
    id: str = Field(default="", max_length=50)
    question: str = Field(default="", max_length=500)
    targetPersona: str = Field(default="DEV", max_length=50)

    @model_validator(mode="before")
    @classmethod
    def coerce_from_string(cls, data):
        if isinstance(data, str):
            return {"question": data[:500]}
        return data


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
