"""Model para respostas de personas técnicas (Phase B)."""
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class PersonaResponse(Base):
    __tablename__ = "persona_responses"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_map_id = Column(PgUUID(as_uuid=True), ForeignKey("document_route_maps.id", ondelete="CASCADE"), nullable=False)

    persona_tag = Column(String(10), nullable=False)  # "gp", "arq", "dba", "dev", "qa", "ux", "ui"
    passada = Column(Integer, nullable=False)  # 1 ou 2

    # Scores por pilar (JSONB): {"escopo": 85, "stack": 72, "dados": 90, ...}
    scores = Column(JSONB, nullable=False, server_default="{}")

    # Aprovação geral (pode prosseguir com implementação?)
    approved = Column(Boolean, nullable=False)

    # Flag: Passada 1 = tentativo; Passada 2 = final
    tentative = Column(Boolean, nullable=False, server_default="true")

    # Issues encontrados (lista estruturada)
    issues = Column(JSONB, nullable=False, server_default="[]")

    # Perguntas geradas pela persona para humanos
    questions = Column(JSONB, nullable=False, server_default="[]")

    # Justificativa textual (para auditoria)
    justification = Column(String, nullable=True)

    # Metadados de execução
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cached_input_tokens = Column(Integer, nullable=False, default=0)
    elapsed_ms = Column(Integer, nullable=False, default=0)
    error_code = Column(String(20), nullable=True)
    error_message = Column(String, nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)

    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relations
    route_map = relationship("DocumentRouteMap", back_populates="persona_responses")

    def __repr__(self):
        return f"<PersonaResponse(persona={self.persona_tag}, passada={self.passada}, approved={self.approved})>"
