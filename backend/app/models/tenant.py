"""
GCA Tenant Models
Modelos isolados por tenant (schema proj_{slug}_*)
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index, CheckConstraint, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class PillarConfiguration(Base):
    """Customização dos 7 pilares por projeto"""
    __tablename__ = "pillar_configuration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    pillar_code = Column(String(10), nullable=False)  # P1, P2, ..., P7
    pillar_name = Column(String(255), nullable=False)

    # Customização
    weight = Column(Float, nullable=False, default=1.0)
    importance = Column(String(50))  # 'critical', 'high', 'medium', 'low'

    # Critérios customizados
    custom_criteria = Column(JSON)  # Sobrescreve critérios padrão

    # Pesos customizados para subcritérios
    subcriteria_weights = Column(JSON, default={})

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_pillar_code", "pillar_code"),
    )

    def __repr__(self):
        return f"<PillarConfiguration {self.pillar_code} weight={self.weight}>"


class OGCVersion(Base):
    """Ontologia de Geração de Código - versionada"""
    __tablename__ = "ogc_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    version = Column(Integer, nullable=False, default=1)

    # Stack definido
    language = Column(String(100))
    architecture = Column(String(100))
    framework = Column(String(100))
    database = Column(String(100))
    frontend_framework = Column(String(100))
    deployment_type = Column(String(100))

    # Contexto dos pilares
    pillar_context = Column(JSON)  # { "P1": {...}, "P2": {...}, ... }

    # OGC completa
    ogc_data = Column(JSON)  # Estrutura completa

    # Metadata
    created_by = Column(UUID(as_uuid=True))  # User ID (será do schema global)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    change_notes = Column(Text)

    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_ogc_version", "version"),
    )

    def __repr__(self):
        return f"<OGCVersion v{self.version}>"


class ArtifactEvaluation(Base):
    """Avaliação de artefatos contra os 7 pilares"""
    __tablename__ = "artifact_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    artifact_id = Column(UUID(as_uuid=True))  # Será FK depois

    # Scores por pilar
    p1_business_score = Column(Float)
    p2_rules_score = Column(Float)
    p3_functional_score = Column(Float)
    p4_nonfunctional_score = Column(Float)
    p5_architecture_score = Column(Float)
    p6_data_score = Column(Float)
    p7_security_score = Column(Float)

    # Pesos utilizados
    p1_weight = Column(Float, default=1.0)
    p2_weight = Column(Float, default=1.0)
    p3_weight = Column(Float, default=1.0)
    p4_weight = Column(Float, default=1.0)
    p5_weight = Column(Float, default=1.0)
    p6_weight = Column(Float, default=1.0)
    p7_weight = Column(Float, default=1.0)

    # Cálculos
    p7_blocked = Column(Boolean, default=False)  # P7 < 70
    final_score = Column(Float)
    final_status = Column(String(50))  # 'approved', 'needs_review', 'blocked'

    # Detalhes
    evaluation_details = Column(JSON)  # Detalhamento de cada pilar
    feedback = Column(Text)

    # Geração de código
    code_generation_allowed = Column(Boolean, default=False)

    evaluation_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    evaluated_by = Column(UUID(as_uuid=True))  # User ID

    __table_args__ = (
        Index("idx_evaluation_artifact", "artifact_id"),
        Index("idx_evaluation_status", "final_status"),
    )

    def __repr__(self):
        return f"<ArtifactEvaluation score={self.final_score} status={self.final_status}>"


class ArtifactStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ArtifactType(str, enum.Enum):
    REQUIREMENTS = "requirements"
    DIAGRAM = "diagram"
    DOCUMENT = "document"
    CODE = "code"
    TEST = "test"
    ARCHITECTURE = "architecture"


class Artifact(Base):
    """Artefatos do projeto tenant"""
    __tablename__ = "artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    type = Column(SQLEnum(ArtifactType), nullable=False)

    # Conteúdo
    content = Column(Text)
    file_path = Column(String(255))
    file_size = Column(Integer)

    # Metadados
    description = Column(Text)
    tags = Column(JSON, default=[])

    # Status
    status = Column(SQLEnum(ArtifactStatus), default=ArtifactStatus.DRAFT)

    # Avaliação
    evaluation_id = Column(UUID(as_uuid=True))
    last_evaluation_date = Column(DateTime(timezone=True))

    # Geração
    code_generated_at = Column(DateTime(timezone=True), nullable=True)
    generated_code = Column(Text)  # Código gerado pelo GCA

    # Auditoria
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_artifact_type", "type"),
        Index("idx_artifact_status", "status"),
        Index("idx_artifact_created", "created_at"),
    )

    def __repr__(self):
        return f"<Artifact {self.name} type={self.type}>"


class AuditLog(Base):
    """Audit log isolado por tenant"""
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(UUID(as_uuid=True))

    # Detalhes
    details = Column(JSON)

    # Auditoria
    actor_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_audit_action", "action"),
        Index("idx_audit_created", "created_at"),
    )

    def __repr__(self):
        return f"<AuditLog {self.action} on {self.resource_type}>"
