"""Model para respostas de validadores humanos às perguntas das personas."""
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class HumanAnswer(Base):
    """Resposta de um validador humano a uma pergunta gerada por uma persona."""
    __tablename__ = "human_answers"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_map_id = Column(
        PgUUID(as_uuid=True),
        ForeignKey("document_route_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Qual persona fez a pergunta
    persona_tag = Column(String(20), nullable=False)

    # ID da pergunta (ex: "GP-001", "ARQ-FALLBACK-1")
    question_id = Column(String(50), nullable=False)

    # Resposta textual do usuário
    answer_text = Column(Text, nullable=False)

    # ID do usuário que respondeu (opcional, pode ser anônimo em contexto de validação)
    answered_by = Column(PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Rastreamento temporal
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    # Relations
    route_map = relationship("DocumentRouteMap", backref="human_answers")

    def __repr__(self):
        return f"<HumanAnswer(persona_tag={self.persona_tag}, question_id={self.question_id})>"
