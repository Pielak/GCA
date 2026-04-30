"""Model para outputs do Auditor (Camada 1 LLM output)."""
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, func, Boolean
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class AuditorOutput(Base):
    __tablename__ = "auditor_outputs"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_map_id = Column(
        PgUUID(as_uuid=True),
        ForeignKey("document_route_maps.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )

    summary = Column(Text, nullable=False)
    summary_token_count = Column(Integer, nullable=False)

    chunk_tags = Column(JSONB, nullable=False)
    highlights = Column(JSONB, nullable=False)
    audit_findings = Column(JSONB, nullable=False)
    backlog_to_specialists = Column(JSONB, nullable=False, server_default="[]")
    questionnaire_to_human = Column(JSONB, nullable=False, server_default="[]")

    llm_provider = Column(String(50), nullable=False)
    llm_model = Column(String(100), nullable=False)

    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cached_input_tokens = Column(Integer, nullable=False, server_default="0")
    elapsed_ms = Column(Integer, nullable=False)

    error_code = Column(String(20), nullable=True)
    error_message = Column(Text, nullable=True)
    fallback_used = Column(Boolean, nullable=False, server_default="false")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relations
    route_map = relationship("DocumentRouteMap", back_populates="auditor_output")

    def __repr__(self):
        return f"<AuditorOutput(route_map_id={self.route_map_id}, chunks={len(self.chunk_tags)})>"
