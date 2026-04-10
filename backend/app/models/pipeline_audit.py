"""Modelo de audit log para pipeline de qualidade (spec v2.0 secao 9)."""
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Float, Index
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class PipelineAuditEntry(Base):
    """Registro de auditoria de cada fase do pipeline por item do backlog."""
    __tablename__ = "pipeline_audit_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    backlog_item_id = Column(UUID(as_uuid=True), ForeignKey("backlog_items.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_used = Column(String(30), nullable=False)
    phase = Column(String(50), nullable=False)  # code_generation, test_generation, test_execution, security_review, compliance_check, qa_approval, commit
    status = Column(String(30), nullable=False)  # COMPLETED, FAILED, APPROVED, REJECTED, COMPLETED_WITH_WARNINGS
    duration_seconds = Column(Float, nullable=True)
    context = Column(Text, nullable=True)  # JSON: detalhes especificos da fase
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_pipeline_audit_project", project_id),
        Index("idx_pipeline_audit_item", backlog_item_id),
        Index("idx_pipeline_audit_phase", project_id, phase),
        Index("idx_pipeline_audit_user", user_id),
    )
