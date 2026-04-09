"""
GCA Global ORM Models
Global schema tables: users, organizations, projects, etc
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index, CheckConstraint, Integer, Float, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    """User model - global"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True, index=True)
    is_admin = Column(Boolean, default=False)
    first_access_completed = Column(Boolean, default=False, index=True)  # Tracks if first password change done
    password_changed_at = Column(DateTime(timezone=True), nullable=True)  # Last password change timestamp
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    organizations_owned = relationship("Organization", back_populates="owner", foreign_keys="Organization.owner_id")
    organization_memberships = relationship("OrganizationMember", back_populates="user")
    project_memberships = relationship("ProjectMember", back_populates="user", foreign_keys="ProjectMember.user_id")
    projects_invited_by = relationship("ProjectMember", foreign_keys="ProjectMember.invited_by", viewonly=True)

    __table_args__ = (
        CheckConstraint(
            "email ~ '^[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Z|a-z]{2,}$'",
            name="email_format"
        ),
    )

    def __repr__(self):
        return f"<User {self.email}>"


class Organization(Base):
    """Organization model - global"""
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = relationship("User", back_populates="organizations_owned", foreign_keys=[owner_id])
    members = relationship("OrganizationMember", back_populates="organization")
    projects = relationship("Project", back_populates="organization")

    __table_args__ = (
        Index("idx_organizations_owner_id", owner_id),
    )

    def __repr__(self):
        return f"<Organization {self.slug}>"


class OrganizationMember(Base):
    """Organization membership"""
    __tablename__ = "organization_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # admin, member, viewer
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="organization_memberships")

    __table_args__ = (
        Index("idx_org_members_org_id", organization_id),
        Index("idx_org_members_user_id", user_id),
    )

    def __repr__(self):
        return f"<OrganizationMember {self.user_id} -> {self.organization_id}>"


class Project(Base):
    """Project model - global metadata"""
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False)  # Used to create proj_{slug}_* schemas
    description = Column(String, nullable=True)

    # Project status
    status = Column(String(50), default="initializing", index=True)  # initializing, wizard_step_1-4, active, archived
    wizard_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Provisioning
    provisioning_status = Column(String(50), default="pending")  # pending, in_progress, completed, failed
    provisioning_error = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    organization = relationship("Organization", back_populates="projects")
    members = relationship("ProjectMember", back_populates="project")

    __table_args__ = (
        Index("idx_projects_org_id", organization_id),
        Index("idx_projects_slug", slug),
        Index("idx_projects_status", status),
        CheckConstraint("slug ~ '^[a-z0-9_-]+$'", name="slug_format"),
    )

    def __repr__(self):
        return f"<Project {self.slug}>"


class ProjectMember(Base):
    """Project membership with roles"""
    __tablename__ = "project_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # gp, tech_lead, dev, qa, compliance, viewer
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invite_token = Column(String(255), unique=True, nullable=True)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="project_memberships", foreign_keys=[user_id])
    invited_by_user = relationship("User", foreign_keys=[invited_by], viewonly=True)

    __table_args__ = (
        Index("idx_project_members_project_id", project_id),
        Index("idx_project_members_user_id", user_id),
    )

    def __repr__(self):
        return f"<ProjectMember {self.user_id} -> {self.project_id}>"


class AccessAttempt(Base):
    """Track unauthorized access attempts to projects"""
    __tablename__ = "access_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, default=1)  # 1st, 2nd, 3rd, 4th, 5th
    blocked = Column(Boolean, default=False, index=True)  # True if account locked after 5 attempts
    blocked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    unblocked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_access_attempts_user_project", user_id, project_id),
        Index("idx_access_attempts_blocked", blocked),
        Index("idx_access_attempts_created_at", created_at),
    )

    def __repr__(self):
        return f"<AccessAttempt user={self.user_id} project={self.project_id} attempt={self.attempt_number}>"


class SupportTicket(Base):
    """Support/Help tickets (SAC) opened by users"""
    __tablename__ = "support_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Ticket content
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=False)  # 20-5000 characters
    error_message = Column(String, nullable=True)  # Error stack if applicable
    erratic_behavior = Column(String, nullable=True)  # Describe weird behavior

    # Severity levels: BAIXO, MÉDIO, ALTO, CRÍTICO
    severity = Column(String(20), nullable=False, index=True)  # Default: MÉDIO

    # Status: ABERTO, EM_ANÁLISE, AGUARDANDO_FEEDBACK, RESOLVIDO
    status = Column(String(20), default="ABERTO", nullable=False, index=True)

    # SLA tracking
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    first_response_at = Column(DateTime(timezone=True), nullable=True)  # When admin first responded
    resolved_at = Column(DateTime(timezone=True), nullable=True)  # When marked as resolved
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project", foreign_keys=[project_id])
    responses = relationship("TicketResponse", back_populates="ticket", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tickets_user_id", user_id),
        Index("idx_tickets_project_id", project_id),
        Index("idx_tickets_status", status),
        Index("idx_tickets_severity", severity),
        Index("idx_tickets_created_at", created_at),
    )

    def __repr__(self):
        return f"<SupportTicket {self.id} severity={self.severity} status={self.status}>"


class TicketResponse(Base):
    """Responses/replies to support tickets from admin or GP"""
    __tablename__ = "ticket_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    responder_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Response content
    message = Column(String, nullable=False)  # Admin's response/diagnosis

    # Track if this resolved the issue
    is_resolution = Column(Boolean, default=False)  # True if this message resolved the ticket

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    ticket = relationship("SupportTicket", back_populates="responses", foreign_keys=[ticket_id])
    responder = relationship("User", foreign_keys=[responder_id])

    __table_args__ = (
        Index("idx_responses_ticket_id", ticket_id),
        Index("idx_responses_responder_id", responder_id),
        Index("idx_responses_created_at", created_at),
    )

    def __repr__(self):
        return f"<TicketResponse ticket={self.ticket_id} responder={self.responder_id}>"


class IntegrationWebhook(Base):
    """Webhook configurations for Teams, Slack, Discord integrations"""
    __tablename__ = "integration_webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Integration type: teams, slack, discord
    integration_type = Column(String(50), nullable=False, index=True)

    # Webhook URL (encrypted in real DB)
    webhook_url = Column(String(500), nullable=False)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(20), nullable=True)  # success, failed
    last_error = Column(String, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_webhooks_type", integration_type),
        Index("idx_webhooks_active", is_active),
    )

    def __repr__(self):
        return f"<IntegrationWebhook {self.integration_type}>"


class SystemAlert(Base):
    """System alerts and notifications sent to admins"""
    __tablename__ = "system_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Alert type: token_expiring, low_credits, service_down, degradation, suspicious_access
    alert_type = Column(String(50), nullable=False, index=True)

    # Severity: info, warning, critical
    severity = Column(String(20), nullable=False, index=True)

    # Alert content
    title = Column(String(255), nullable=False)
    message = Column(String, nullable=False)
    details = Column(String, nullable=True)  # JSON details

    # Delivery tracking
    sent_to_teams = Column(Boolean, default=False)
    sent_to_slack = Column(Boolean, default=False)
    sent_via_email = Column(Boolean, default=False)

    # Status: pending, sent, failed, acknowledged
    status = Column(String(20), default="pending", nullable=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    acknowledged_by_user = relationship("User", foreign_keys=[acknowledged_by])

    __table_args__ = (
        Index("idx_alerts_type", alert_type),
        Index("idx_alerts_severity", severity),
        Index("idx_alerts_status", status),
        Index("idx_alerts_created_at", created_at),
    )

    def __repr__(self):
        return f"<SystemAlert {self.alert_type} severity={self.severity}>"


class ResetToken(Base):
    """Password reset tokens with TTL and single-use enforcement"""
    __tablename__ = "reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, default=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_reset_tokens_user_id", user_id),
        Index("idx_reset_tokens_expires", expires_at),
    )

    def __repr__(self):
        return f"<ResetToken user={self.user_id} used={self.used}>"


class InvitationToken(Base):
    """Invitation tokens for admin invites. Expires in 2 hours. Max 3 validation attempts."""
    __tablename__ = "invitation_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="admin")
    token = Column(String(255), unique=True, nullable=False, index=True)
    temporary_password_hash = Column(String(255), nullable=False)
    validation_attempts = Column(Integer, default=0)
    is_used = Column(Boolean, default=False)
    invited_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invited_by = relationship("User", foreign_keys=[invited_by_id])

    def __repr__(self):
        return f"<InvitationToken email={self.email} used={self.is_used}>"


class GlobalAuditLog(Base):
    """Global audit log with chain integrity"""
    __tablename__ = "audit_log_global"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type = Column(String(100), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_email = Column(String(255), nullable=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(String, nullable=True)  # JSON field in real DB
    previous_hash = Column(String(64), nullable=True)  # For chain integrity
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_audit_log_event_type", event_type),
        Index("idx_audit_log_created_at", created_at),
    )

    def __repr__(self):
        return f"<GlobalAuditLog {self.event_type} {self.resource_type}>"


class Questionnaire(Base):
    """Questionnaire model - technical stack analysis submissions"""
    __tablename__ = "questionnaires"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    gp_email = Column(String(255), nullable=False, index=True)

    # Submitted responses
    responses = Column(String, nullable=False)  # JSON field in PostgreSQL

    # Analysis results
    adherence_score = Column(Integer, nullable=True, index=True)
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending, incomplete, ok
    approved = Column(Boolean, default=False, nullable=False, index=True)

    # Validation results (JSON)
    validations = Column(String, nullable=True)  # JSON: logicConflicts, gaps, incompatibilities
    observations = Column(String, nullable=True)
    restrictions = Column(String, nullable=True)
    highlighted_fields = Column(String, nullable=True)  # JSON array

    # Metadata
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_questionnaires_project_id", project_id),
        Index("idx_questionnaires_gp_email", gp_email),
        Index("idx_questionnaires_status", status),
        Index("idx_questionnaires_approved", approved),
        Index("idx_questionnaires_submitted_at", submitted_at),
    )

    def __repr__(self):
        return f"<Questionnaire project={self.project_id} status={self.status} score={self.adherence_score}>"


class OCG(Base):
    """Objeto Contexto Global (OCG) - Output from 8-agent pipeline"""
    __tablename__ = "ocg"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    questionnaire_id = Column(UUID(as_uuid=True), ForeignKey("questionnaires.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)

    # Pillar scores (0-100)
    p1_business_score = Column(Float, nullable=True)
    p2_rules_score = Column(Float, nullable=True)
    p3_features_score = Column(Float, nullable=True)
    p4_nfr_score = Column(Float, nullable=True)
    p5_architecture_score = Column(Float, nullable=True)
    p6_data_score = Column(Float, nullable=True)
    p7_security_score = Column(Float, nullable=True)

    # Composite score
    overall_score = Column(Float, nullable=True, index=True)
    status = Column(String(50), default="READY", nullable=False, index=True)  # READY, NEEDS_REVIEW, AT_RISK, BLOCKED
    is_blocking = Column(Boolean, default=False, nullable=False, index=True)

    # Full OCG as JSON
    ocg_data = Column(String, nullable=False)  # JSON string - complete OCG object

    # Audit trail
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    questionnaire = relationship("Questionnaire", foreign_keys=[questionnaire_id])
    project = relationship("Project", foreign_keys=[project_id])
    generator_user = relationship("User", foreign_keys=[generated_by], primaryjoin="OCG.generated_by == User.id")
    reviewer_user = relationship("User", foreign_keys=[reviewed_by], primaryjoin="OCG.reviewed_by == User.id")

    __table_args__ = (
        Index("idx_ocg_questionnaire_id", questionnaire_id),
        Index("idx_ocg_project_id", project_id),
        Index("idx_ocg_overall_score", overall_score),
        Index("idx_ocg_status", status),
        Index("idx_ocg_is_blocking", is_blocking),
        Index("idx_ocg_generated_at", generated_at),
    )

    def __repr__(self):
        return f"<OCG questionnaire={self.questionnaire_id} score={self.overall_score} status={self.status}>"


class OCGAnalysisLog(Base):
    """Audit log for agent analysis - tracks every decision"""
    __tablename__ = "ocg_analysis_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ocg_id = Column(UUID(as_uuid=True), ForeignKey("ocg.id", ondelete="CASCADE"), nullable=False, index=True)

    # Agent metadata
    agent_name = Column(String(50), nullable=False, index=True)  # analyzer, pillar_1..7, consolidator
    agent_input_hash = Column(String(64), nullable=True)  # SHA256 of input
    agent_output_hash = Column(String(64), nullable=True)  # SHA256 of output

    # Performance metrics
    tokens_used = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), default="success", nullable=False)  # success, error, timeout
    error_message = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    ocg = relationship("OCG", foreign_keys=[ocg_id])

    __table_args__ = (
        Index("idx_analysis_log_ocg_id", ocg_id),
        Index("idx_analysis_log_agent_name", agent_name),
        Index("idx_analysis_log_created_at", created_at),
    )

    def __repr__(self):
        return f"<OCGAnalysisLog ocg={self.ocg_id} agent={self.agent_name} status={self.status}>"


class ProjectGitConfig(Base):
    """Git repository configuration per project"""
    __tablename__ = "project_git_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    provider = Column(String(20), nullable=False)  # github, gitlab, bitbucket, azure_devops, other
    repository_url = Column(String(500), nullable=False)
    default_branch = Column(String(100), nullable=False, default="main")
    pat_encrypted = Column(Text, nullable=False)
    connection_verified = Column(Boolean, nullable=False, default=False)
    connection_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_commit_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_project_git_configs_project", project_id),
    )

    def __repr__(self):
        return f"<ProjectGitConfig project={self.project_id} provider={self.provider} verified={self.connection_verified}>"


class ProjectSecret(Base):
    """Encrypted secrets per project (vault)"""
    __tablename__ = "project_secrets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    secret_type = Column(String(50), nullable=False)  # llm_api_key, smtp_password, webhook_secret, git_pat, n8n_token, custom
    secret_key = Column(String(100), nullable=False)  # identifier within type (e.g. 'anthropic', 'openai')
    secret_value_encrypted = Column(Text, nullable=False)  # pgp_sym_encrypt(value, master_key)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint("project_id", "secret_type", "secret_key", name="uq_project_secret"),
        Index("idx_project_secrets_project", project_id),
        Index("idx_project_secrets_type", project_id, secret_type),
    )


class ProjectSettings(Base):
    """Non-secret settings per project (SMTP config, LLM provider, n8n)"""
    __tablename__ = "project_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    setting_type = Column(String(50), nullable=False)  # smtp, llm, n8n, general
    settings_json = Column(Text, nullable=False, default="{}")  # JSON with non-secret config
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("project_id", "setting_type", name="uq_project_setting"),
    )


# ============================================================================
# FASE 1 — Ingestão de Documentos + Arguidor
# ============================================================================

class IngestedDocument(Base):
    """Documento ingerido por projeto para análise do Arguidor"""
    __tablename__ = "ingested_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)  # nome gerado (uuid + ext)
    original_filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)  # pdf, docx, markdown, image, wireframe, spreadsheet, code, other
    document_category = Column(String(30), nullable=True)  # preenchido pelo Arguidor
    git_file_path = Column(String(500), nullable=True)
    git_analysis_path = Column(String(500), nullable=True)
    file_hash = Column(String(64), nullable=False)  # SHA256
    file_size_bytes = Column(Integer, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    arguider_status = Column(String(20), nullable=False, default="pending")  # pending, processing, completed, error
    arguider_started_at = Column(DateTime(timezone=True), nullable=True)
    arguider_completed_at = Column(DateTime(timezone=True), nullable=True)
    arguider_error_message = Column(Text, nullable=True)
    ocg_updated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", foreign_keys=[project_id])
    uploader = relationship("User", foreign_keys=[uploaded_by])

    __table_args__ = (
        Index("idx_ingested_docs_project", project_id),
        Index("idx_ingested_docs_status", project_id, arguider_status),
        UniqueConstraint("project_id", "file_hash", name="uq_ingested_doc_hash"),
    )


class ArguiderAnalysis(Base):
    """Resultado da análise do Arguidor (Agent 9) para um documento"""
    __tablename__ = "arguider_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    document_classification = Column(Text, nullable=False, default="{}")  # JSON
    gaps = Column(Text, nullable=False, default="[]")  # JSON array
    show_stoppers = Column(Text, nullable=False, default="[]")  # JSON array
    poor_definitions = Column(Text, nullable=False, default="[]")  # JSON array
    improvement_suggestions = Column(Text, nullable=False, default="[]")  # JSON array
    module_candidates = Column(Text, nullable=False, default="[]")  # JSON array
    ocg_fields_to_update = Column(Text, nullable=False, default="[]")  # JSON array
    llm_model = Column(String(50), nullable=False, default="claude-opus-4-6")
    tokens_used = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document = relationship("IngestedDocument", foreign_keys=[document_id])

    __table_args__ = (
        Index("idx_arguider_analyses_project", project_id),
    )


class ModuleCandidate(Base):
    """Candidato a módulo identificado pelo Arguidor"""
    __tablename__ = "module_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    arguider_analysis_id = Column(UUID(as_uuid=True), ForeignKey("arguider_analyses.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    module_type = Column(String(20), nullable=False)  # feature, component
    priority = Column(String(10), nullable=False, default="medium")  # high, medium, low
    status = Column(String(20), nullable=False, default="suggested")  # suggested, approved, rejected, in_progress, completed
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    dependencies = Column(Text, nullable=False, default="[]")  # JSON array of module_candidate ids
    source_document_ids = Column(Text, nullable=False, default="[]")  # JSON array
    pillar_impact = Column(Text, nullable=False, default="{}")  # JSON {p1:bool,...,p7:bool}
    ready_for_codegen = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", foreign_keys=[project_id])
    analysis = relationship("ArguiderAnalysis", foreign_keys=[arguider_analysis_id])

    __table_args__ = (
        Index("idx_module_candidates_project", project_id),
        Index("idx_module_candidates_status", project_id, status),
    )


class OCGDeltaLog(Base):
    """Histórico de mudanças no OCG causadas por ingestão de documentos"""
    __tablename__ = "ocg_delta_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id"), nullable=False)
    ocg_version_from = Column(Integer, nullable=False)
    ocg_version_to = Column(Integer, nullable=False)
    fields_changed = Column(Text, nullable=False, default="{}")  # JSON {field: {old, new, reasoning}}
    change_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ocg_delta_project", project_id),
    )


class GatekeeperItem(Base):
    """Item de rastreamento do Gatekeeper (gap, show_stopper, poor_definition, improvement)"""
    __tablename__ = "gatekeeper_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    arguider_analysis_id = Column(UUID(as_uuid=True), ForeignKey("arguider_analyses.id"), nullable=False)
    item_type = Column(String(20), nullable=False)  # gap, show_stopper, poor_definition, improvement
    item_id_in_analysis = Column(String(10), nullable=False)  # G001, SS002, PD001, IS001
    item_data = Column(Text, nullable=False, default="{}")  # JSON completo do item
    status = Column(String(20), nullable=False, default="pending")  # pending, resolved, ignored
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution_note = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_gatekeeper_project", project_id),
        Index("idx_gatekeeper_status", project_id, status),
        Index("idx_gatekeeper_type", project_id, item_type),
    )


class GeneratedModule(Base):
    """Módulo gerado pelo CodeGen a partir de um candidato aprovado"""
    __tablename__ = "generated_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    module_candidate_id = Column(UUID(as_uuid=True), ForeignKey("module_candidates.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False)
    module_type = Column(String(50), nullable=False)  # feature, component, service, controller, etc.
    status = Column(String(30), nullable=False, default="generating")  # generating, completed, failed, cancelled
    git_source_path = Column(Text, nullable=True)  # Caminho do código-fonte no repositório
    git_unit_test_path = Column(Text, nullable=True)  # Caminho dos testes unitários
    git_integration_test_path = Column(Text, nullable=True)  # Caminho dos testes de integração
    git_uat_test_path = Column(Text, nullable=True)  # Caminho dos testes UAT
    git_docs_path = Column(Text, nullable=True)  # Caminho da documentação do módulo
    llm_provider = Column(String(50), nullable=True)  # anthropic, openai, etc.
    llm_model = Column(String(100), nullable=True)  # claude-opus-4-0-20250514, gpt-4, etc.
    tokens_used = Column(Integer, nullable=True)
    generation_latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    project = relationship("Project", foreign_keys=[project_id])
    module_candidate = relationship("ModuleCandidate", foreign_keys=[module_candidate_id])

    __table_args__ = (
        Index("idx_generated_modules_project", project_id),
        Index("idx_generated_modules_candidate", module_candidate_id),
    )

    def __repr__(self):
        return f"<GeneratedModule {self.name} status={self.status}>"


class TestFile(Base):
    """Arquivo de teste gerado para um módulo"""
    __tablename__ = "test_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    generated_module_id = Column(UUID(as_uuid=True), ForeignKey("generated_modules.id", ondelete="CASCADE"), nullable=False)
    test_type = Column(String(20), nullable=False)  # unit, integration, uat
    git_path = Column(Text, nullable=True)  # Caminho no repositório Git
    framework = Column(String(50), nullable=True)  # pytest, jest, junit5, etc.
    coverage_scope = Column(Text, nullable=True)  # Descrição do escopo de cobertura
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    project = relationship("Project", foreign_keys=[project_id])
    generated_module = relationship("GeneratedModule", foreign_keys=[generated_module_id])

    __table_args__ = (
        Index("idx_test_files_project", project_id),
        Index("idx_test_files_module", generated_module_id),
    )

    def __repr__(self):
        return f"<TestFile type={self.test_type} module={self.generated_module_id}>"


# ============================================================================
# SESSION 14 — QA Readiness + Tester Review
# ============================================================================

class TestArtifact(Base):
    """Artefato de teste com revisão RBAC e versionamento."""
    __tablename__ = "test_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(UUID(as_uuid=True), ForeignKey("module_candidates.id"), nullable=True)
    test_type = Column(String(20), nullable=False)  # unit, integration, e2e, regression, load, security
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending_review")  # pending_review, approved, rejected, edited
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_edited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_edited_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)

    project = relationship("Project", foreign_keys=[project_id])
    module = relationship("ModuleCandidate", foreign_keys=[module_id])

    __table_args__ = (
        CheckConstraint("test_type IN ('unit','integration','e2e','regression','load','security')", name="ck_test_artifact_type"),
        CheckConstraint("status IN ('pending_review','approved','rejected','edited')", name="ck_test_artifact_status"),
        Index("idx_test_artifacts_project", project_id),
        Index("idx_test_artifacts_module", module_id),
        Index("idx_test_artifacts_type", test_type),
        Index("idx_test_artifacts_status", status),
    )

    def __repr__(self):
        return f"<TestArtifact title={self.title} type={self.test_type} status={self.status}>"


class TestExecutionLog(Base):
    """Log de execução de teste com rastreabilidade de autoria."""
    __tablename__ = "test_execution_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    test_artifact_id = Column(UUID(as_uuid=True), ForeignKey("test_artifacts.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    executed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    executed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False)  # passed, failed, error, skipped
    duration_ms = Column(Integer, nullable=True)
    output = Column(Text, nullable=True)
    module_name = Column(String(255), nullable=True)
    function_name = Column(String(255), nullable=True)
    test_created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    test_edited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    test_version_at_run = Column(Integer, nullable=False, default=1)

    test_artifact = relationship("TestArtifact", foreign_keys=[test_artifact_id])
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        CheckConstraint("status IN ('passed','failed','error','skipped')", name="ck_test_exec_status"),
        Index("idx_test_exec_logs_artifact", test_artifact_id),
        Index("idx_test_exec_logs_project", project_id),
        Index("idx_test_exec_logs_status", status),
    )
