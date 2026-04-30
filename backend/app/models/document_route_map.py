"""Model para routing de documentos (Camada 0 parser output)."""
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class DocumentRouteMap(Base):
    __tablename__ = "document_route_maps"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(PgUUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False, server_default="1")

    llm_provider = Column(String(50), nullable=False)
    llm_model = Column(String(100), nullable=False)

    chunks = Column(JSONB, nullable=False)
    total_chunks = Column(Integer, nullable=False)
    chunking_time_ms = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relations
    document = relationship("IngestedDocument", back_populates="route_maps")
    auditor_output = relationship("AuditorOutput", back_populates="route_map", uselist=False)
    gatekeeper_persona_responses = relationship("GatekeeperPersonaResponse", back_populates="route_map", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DocumentRouteMap(document_id={self.document_id}, version={self.version}, chunks={self.total_chunks})>"
