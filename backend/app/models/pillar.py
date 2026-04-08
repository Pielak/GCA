"""
GCA Pillar Models
Os 7 Pilares de Avaliação de Código
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class PillarTemplate(Base):
    """Template dos 7 pilares padrão da empresa"""
    __tablename__ = "pillar_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code = Column(String(10), unique=True, nullable=False)  # P1, P2, ..., P7
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Padrões
    default_weight = Column(Float, default=1.0)
    is_blocking = Column(Boolean, default=False)
    blocking_threshold = Column(Float, nullable=True)  # P7: 70

    # Subcritérios padrão
    default_criteria = Column(JSON, default={})  # { "security": {...}, "lgpd": {...} }

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<PillarTemplate {self.code}>"


class CompanyPolicy(Base):
    """Políticas que a empresa pode impor aos tenants"""
    __tablename__ = "company_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_name = Column(String(255), nullable=False)
    pillar_id = Column(UUID(as_uuid=True), ForeignKey("pillar_templates.id", ondelete="CASCADE"))
    description = Column(Text)

    # Regras de validação
    validation_rules = Column(JSON)  # { "only_github": true, "min_rbac_score": 80 }
    severity = Column(String(50), nullable=False)  # 'warning', 'error'

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<CompanyPolicy {self.policy_name}>"
