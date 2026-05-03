"""Model para respostas de Personas no Gatekeeper (Camada 2 LLM output)."""
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, func, Boolean
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class GatekeeperPersonaResponse(Base):
    """Resposta de uma persona técnica na fase Gatekeeper (Passada 1 ou 2)."""
    __tablename__ = "gatekeeper_persona_responses"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_map_id = Column(
        PgUUID(as_uuid=True),
        ForeignKey("document_route_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Persona tag: "gp", "arq", "dba", "dev", "qa", "ux", "ui"
    persona_tag = Column(String(20), nullable=False)

    # Passada: 1 (tentative com questões) ou 2 (final após respostas)
    passada = Column(Integer, nullable=False)

    # Scores por aspecto (0-100)
    scores = Column(JSONB, nullable=False)

    # Veredito
    approved = Column(Boolean, nullable=False)
    tentative = Column(Boolean, nullable=False)

    # Achados (issues)
    issues = Column(JSONB, nullable=False, server_default="[]")

    # Perguntas para validação humana
    questions = Column(JSONB, nullable=False, server_default="[]")

    # Justificativa textual
    justification = Column(Text, nullable=True)

    # Rastreamento de tokens e performance
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cached_input_tokens = Column(Integer, nullable=False, default=0)
    elapsed_ms = Column(Integer, nullable=False, default=0)

    # Tratamento de erros
    error_code = Column(String(20), nullable=True)
    error_message = Column(Text, nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)

    # Rastreamento de LLM
    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relations
    route_map = relationship("DocumentRouteMap", back_populates="gatekeeper_persona_responses")

    def __repr__(self):
        return f"<GatekeeperPersonaResponse(persona_tag={self.persona_tag}, passada={self.passada}, approved={self.approved})>"
