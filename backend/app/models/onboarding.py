"""
GCA Onboarding Models
Modelos para provisioning e setup de tenants (schema global)
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.database import Base


class ProjectRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"


class OnboardingStep(str, enum.Enum):
    STEP_1 = "step_1"  # Repository
    STEP_2 = "step_2"  # SMTP
    STEP_3 = "step_3"  # Team
    STEP_4 = "step_4"  # Architecture
    STEP_5 = "step_5"  # Stack Selection


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProjectRequest(Base):
    """Solicitação de criação de projeto"""
    __tablename__ = "project_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # GP que solicitou
    gp_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Informações do projeto
    project_name = Column(String(255), nullable=False)
    project_slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text)

    # Schema PostgreSQL
    schema_name = Column(String(100), unique=True)

    # Status
    status = Column(SQLEnum(ProjectRequestStatus), default=ProjectRequestStatus.PENDING)

    # Aprovação
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))  # Admin ID
    approved_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)

    # Credenciais iniciais
    initial_password_hash = Column(String(255))
    password_changed = Column(Boolean, default=False)

    # Datas
    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_project_gp", "gp_id"),
        Index("idx_project_status", "status"),
    )

    def __repr__(self):
        return f"<ProjectRequest {self.project_slug} status={self.status}>"


class OnboardingProgress(Base):
    """Progresso do onboarding de um projeto"""
    __tablename__ = "onboarding_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_requests.id"), nullable=False)
    gp_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # ========== STEP 1: Repository ==========
    step_1_status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING)
    step_1_provider = Column(String(50))  # 'github', 'gitlab', 'bitbucket'
    step_1_repo_url = Column(String(255))
    step_1_token_encrypted = Column(String(500))
    step_1_token_verified = Column(Boolean, default=False)
    step_1_verified_at = Column(DateTime(timezone=True))
    step_1_error_msg = Column(Text)

    # ========== STEP 2: SMTP ==========
    step_2_status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING)
    step_2_smtp_host = Column(String(255))
    step_2_smtp_port = Column(Integer)
    step_2_smtp_user = Column(String(255))
    step_2_smtp_password_encrypted = Column(String(500))
    step_2_smtp_from_email = Column(String(255))
    step_2_test_sent = Column(Boolean, default=False)
    step_2_tested_at = Column(DateTime(timezone=True))
    step_2_error_msg = Column(Text)

    # ========== STEP 3: Team ==========
    step_3_status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING)
    step_3_team_members_count = Column(Integer, default=0)
    step_3_invites_sent_at = Column(DateTime(timezone=True))
    step_3_error_msg = Column(Text)

    # ========== STEP 4: Architecture ==========
    step_4_status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING)
    step_4_language = Column(String(50))  # python, java, nodejs, go, rust
    step_4_architecture = Column(String(100))  # monolith, microservices, serverless
    step_4_n8n_execution_id = Column(String(255))
    step_4_n8n_status = Column(String(50))  # pending, running, success, failed
    step_4_n8n_result = Column(JSON)  # Resultado do Piloter
    step_4_error_msg = Column(Text)

    # ========== STEP 5: Stack Selection ==========
    step_5_status = Column(SQLEnum(StepStatus), default=StepStatus.PENDING)
    step_5_selected_stack = Column(JSON)  # { "backend": "FastAPI", "database": "PostgreSQL", ... }
    step_5_completed_at = Column(DateTime(timezone=True))

    # ========== OVERALL ==========
    current_step = Column(Integer, default=1)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True))

    # Datas
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_onboarding_project", "project_id"),
        Index("idx_onboarding_gp", "gp_id"),
        Index("idx_onboarding_current_step", "current_step"),
    )

    def __repr__(self):
        return f"<OnboardingProgress step={self.current_step} status={self.step_1_status}>"


class TeamInvite(Base):
    """Convite para integrar equipe do projeto"""
    __tablename__ = "team_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("project_requests.id"), nullable=False)

    # Convidado
    email = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # tech_lead, dev, qa, compliance, viewer
    responsibility = Column(Text)

    # Token de convite
    invite_token = Column(String(255), unique=True, nullable=False)
    invite_sent_at = Column(DateTime(timezone=True))
    invite_expires_at = Column(DateTime(timezone=True))

    # Aceitação
    accepted_at = Column(DateTime(timezone=True))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))  # Preenchido quando aceita

    # Status
    is_accepted = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_invite_project", "project_id"),
        Index("idx_invite_email", "email"),
        Index("idx_invite_token", "invite_token"),
    )

    def __repr__(self):
        return f"<TeamInvite {self.email} -> {self.role}>"


class StackCache(Base):
    """Cache de recomendações de stack (reutiliza queries Piloter)"""
    __tablename__ = "stack_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    language = Column(String(50), nullable=False)
    architecture = Column(String(100), nullable=False)
    cache_key = Column(String(255), unique=True, nullable=False)

    recommendations = Column(JSON)  # Resultado do Piloter processado

    piloter_query_used = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_stack_language", "language"),
        Index("idx_stack_architecture", "architecture"),
        Index("idx_stack_expires", "expires_at"),
    )

    def __repr__(self):
        return f"<StackCache {self.language}/{self.architecture}>"


class PiloterQuery(Base):
    """Histórico de queries ao Piloter API"""
    __tablename__ = "piloter_queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    language = Column(String(50), nullable=False)
    architecture = Column(String(100), nullable=False)

    piloter_request = Column(JSON)
    piloter_response = Column(JSON)

    subscription_calls_used = Column(Integer)
    credits_used = Column(Integer)

    status = Column(String(50))  # success, failed, rate_limited, quota_exceeded
    error_msg = Column(Text)

    recommendations_count = Column(Integer)
    execution_time_ms = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_piloter_status", "status"),
        Index("idx_piloter_created", "created_at"),
    )

    def __repr__(self):
        return f"<PiloterQuery {self.language}/{self.architecture} status={self.status}>"


class PiloterQuotaHistory(Base):
    """Histórico de quotas do Piloter para monitoramento"""
    __tablename__ = "piloter_quota_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    check_date = Column(DateTime(timezone=True))

    # Subscription
    subscription_used = Column(Integer)
    subscription_total = Column(Integer)
    subscription_remaining = Column(Integer)
    subscription_percent_used = Column(Float)

    # Credits
    credits_given = Column(Integer)
    credits_consumed = Column(Integer)
    credits_remaining = Column(Integer)

    # Period
    period_start = Column(String(50))
    period_end = Column(String(50))
    renewal_date = Column(String(50))

    # Rate limits
    rate_limit_per_minute = Column(Integer)
    rate_limit_per_second = Column(Integer)

    # Account
    account_name = Column(String(255))
    account_slug = Column(String(255))

    # Alert
    alert_level = Column(String(50))  # healthy, warning, critical
    alert_message = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_quota_created", "created_at"),
        Index("idx_quota_alert", "alert_level"),
    )

    def __repr__(self):
        return f"<PiloterQuotaHistory {self.alert_level} {self.subscription_percent_used}%>"
