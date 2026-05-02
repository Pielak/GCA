"""
GCA Global ORM Models
Global schema tables: users, organizations, projects, etc
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index, CheckConstraint, Integer, Float, Text, UniqueConstraint, LargeBinary, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    """User model - global"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)  # NULL for engine personas
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True, index=True)
    is_admin = Column(Boolean, default=False)
    # MVP 6 Emenda 2026-04-19 — Área de Sustentação (cross-instância).
    # Admin HERDA Support: verificação em código é (is_admin OR is_support).
    # Support nunca vira Admin por essa via.
    is_support = Column(Boolean, default=False, nullable=False)
    is_engine = Column(Boolean, default=False, nullable=False)  # System IA_* personas (skip notifications)
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
            "(email IS NULL) OR (email ~ '^[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Z|a-z]{2,}$')",
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
    role = Column(String(50), nullable=False)  # organization-level: admin | member
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
    short_slug = Column(String(15), unique=True, nullable=True, index=True)  # Human-friendly URL slug e.g. /p/financehub-pro
    description = Column(String, nullable=True)

    # Gate bloqueante: tipo de entregável
    deliverable_type = Column(String(50), nullable=False)

    # Project status
    status = Column(String(50), default="initializing", index=True)  # initializing, wizard_step_1-4, active, archived
    wizard_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Provisioning
    provisioning_status = Column(String(50), default="pending")  # pending, in_progress, completed, failed
    provisioning_error = Column(String, nullable=True)

    # DT-038: admin responsável pelo projeto (contrato §2.2). Notificações
    # relacionadas ao projeto (questionário submetido, OCG gerado, etc)
    # vão **apenas** para este admin. Nullable p/ retrocompat; fallback
    # é notificar todos admins ativos com warning log de auditoria.
    responsible_admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Backup-1: cache do timestamp do último backup completo (preenchido
    # pelo project_backup_service ao final). UI lista de projetos lê daqui
    # pra evitar JOIN/aggregate em project_backups.
    last_backup_at = Column(DateTime(timezone=True), nullable=True)

    # MVP governance_mode (2026-04-24): separa core (gerador de código) de
    # módulos opt-in (PM corporativo). solo_owner suprime cobranças de
    # governança no Arguidor/M01/Backlog. team/corporate desbloqueiam módulos.
    governance_mode = Column(String(20), nullable=False, default="solo_owner", server_default="solo_owner")

    # Relationships
    organization = relationship("Organization", back_populates="projects")
    members = relationship("ProjectMember", back_populates="project")
    responsible_admin = relationship("User", foreign_keys=[responsible_admin_id])

    __table_args__ = (
        Index("idx_projects_org_id", organization_id),
        Index("idx_projects_slug", slug),
        Index("idx_projects_status", status),
        CheckConstraint("slug ~ '^[a-z0-9_-]+$'", name="slug_format"),
    )

    def __repr__(self):
        return f"<Project {self.slug}>"


class ProjectBackup(Base):
    """Backup-1 — backups por projeto.

    1 linha por backup gerado. Retenção: 10 últimos por projeto
    (cleanup feito pelo project_backup_service).

    Status:
      - running: backup em curso, ainda não terminou (banner visível ao GP)
      - completed: backup gravado em volume + sha256 OK
      - failed: erro_message preenchido, file_path pode estar incompleto

    trigger_source:
      - scheduled: cron diário 12:00
      - manual_gp: GP do projeto clicou "Backup agora"
      - manual_admin: Admin clicou (a pedido do GP)
      - startup_catchup: servidor estava down 12:00 → roda no startup
    """
    __tablename__ = "project_backups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    trigger_source = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    file_path = Column(String(500), nullable=True)  # relativo ao volume gca-backups
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=True)
    manifest_json = Column(String, nullable=True)  # text — lista tabelas + contagens + hashes
    error_message = Column(String, nullable=True)
    # Quando este backup foi usado para restore:
    restored_at = Column(DateTime(timezone=True), nullable=True)
    restored_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("idx_project_backups_project", project_id, created_at.desc()),
    )

    def __repr__(self):
        return f"<ProjectBackup project={self.project_id} status={self.status}>"


class ProjectMember(Base):
    """Project membership with roles.

    MVP 12 Fase 12.3 — semântica canônica dos timestamps:
    - `invited_at`: sempre preenchido no momento da criação (default now).
    - `accepted_at`: preenchido quando o convidado **aceita** o convite
      (caminho via `POST /accept-invite`). GPs criados por caminho
      direto (aprovação de solicitação-de-projeto; _create_gp_member
      interno) devem preencher AMBOS `accepted_at` e `joined_at` com o
      mesmo timestamp — soberanos não passam por fluxo de aceite.
    - `joined_at`: preenchido quando o membro está efetivamente ativo no
      projeto (ou via aceite, ou via criação direta).
    - `revoked_at`: preenchido quando GP revoga o convite antes do
      aceite, ou quando membro é removido do projeto.

    Regra canônica de query (usar helpers em `project_team_service`):
    - Membro ativo integrado → `is_active AND joined_at IS NOT NULL`.
    - Convite pendente → `is_active AND invite_token IS NOT NULL
      AND joined_at IS NULL AND revoked_at IS NULL`.
    Nunca filtrar só por `accepted_at IS NULL` — retorna GPs ativos
    criados por caminho direto como se fossem convites pendentes.
    """
    __tablename__ = "project_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # papéis canônicos (contrato §4): gp | dev | tester | qa
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invite_token = Column(String(255), unique=True, nullable=True)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)
    full_name = Column(String(255), nullable=True)  # Nome do convidado (preenchido no convite)
    is_active = Column(Boolean, default=True, nullable=False)  # False = revogado
    invited_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

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


class ProjectInvite(Base):
    """Convites de membros por projeto (spec seção 6 e 11)"""
    __tablename__ = "project_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False)  # papéis canônicos do projeto: gp | dev | tester | qa
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invite_token = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING, ACCEPTED, EXPIRED, REVOKED, CANCELLED
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", foreign_keys=[project_id])
    inviter = relationship("User", foreign_keys=[invited_by_user_id])

    __table_args__ = (
        Index("idx_project_invites_project", project_id),
        Index("idx_project_invites_email", email),
        Index("idx_project_invites_token", invite_token),
        Index("idx_project_invites_status", status),
    )

    def __repr__(self):
        return f"<ProjectInvite {self.email} -> {self.project_id} ({self.status})>"


class UserProjectContext(Base):
    """Contexto ativo do usuário — qual projeto está selecionado (spec seção 4.2 e 11)"""
    __tablename__ = "user_project_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    active_project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    last_selected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project", foreign_keys=[active_project_id])

    __table_args__ = (
        Index("idx_user_project_context_user", user_id),
    )

    def __repr__(self):
        return f"<UserProjectContext user={self.user_id} project={self.active_project_id}>"


class ProjectExternalRepo(Base):
    """Repositório externo vinculado ao projeto (read-only)"""
    __tablename__ = "project_external_repos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    repo_url = Column(String(500), nullable=False)
    provider = Column(String(20), nullable=False)  # github, gitlab, bitbucket
    branch = Column(String(100), nullable=False, default="main")
    access_token_encrypted = Column(Text, nullable=True)  # vault pgp_sym_encrypt
    status = Column(String(20), nullable=False, default="pending")  # pending, reading, completed, error, partial
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    files_total = Column(Integer, default=0)
    files_processed = Column(Integer, default=0)
    files_skipped = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # --- Campos de análise (novos) ---
    stack_json = Column(Text, nullable=True)
    compatibility_status = Column(String(50), nullable=True)
    last_compatibility_check = Column(DateTime(timezone=True), nullable=True)
    ai_provider = Column(String(50), default="deepseek")
    is_approved_for_integration = Column(Boolean, default=False)
    approved_by_gp = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # --- Progresso de análise ---
    analysis_phase = Column(Integer, default=0)  # 0-6 (0=idle, 1-6=fases)
    analysis_phase_label = Column(String(100), nullable=True)
    analysis_progress = Column(Integer, default=0)  # 0-100%

    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_ext_repos_project", project_id),
        Index("idx_ext_repos_status", status),
    )

    def __repr__(self):
        return f"<ProjectExternalRepo {self.repo_url} ({self.status})>"


class RepoAnalysisResult(Base):
    """Resultado da análise de repositório externo"""
    __tablename__ = "repo_analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("project_external_repos.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Stack
    stack_json = Column(Text, nullable=True)
    primary_language = Column(String(50), nullable=True)
    framework_name = Column(String(100), nullable=True)
    framework_version = Column(String(30), nullable=True)
    has_docker = Column(Boolean, default=False)
    has_cicd = Column(Boolean, default=False)
    has_tests = Column(Boolean, default=False)

    # Security
    vulnerabilities_json = Column(Text, nullable=True)
    risk_level = Column(String(20), nullable=True)
    vulnerabilities_count = Column(Integer, default=0)
    critical_vulnerabilities = Column(Integer, default=0)

    # Compatibility
    compatibility_matrix = Column(Text, nullable=True)
    gca_overall_status = Column(String(30), nullable=True)
    gca_integration_effort_days = Column(Integer, nullable=True)
    gca_backend_compatible = Column(Boolean, nullable=True)
    gca_frontend_compatible = Column(Boolean, nullable=True)
    gca_database_compatible = Column(Boolean, nullable=True)

    # Analysis
    category = Column(String(50), nullable=True)
    summary = Column(Text, nullable=True)
    metrics = Column(Text, nullable=True)
    files_analyzed = Column(Integer, default=0)
    ai_provider_used = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    repo = relationship("ProjectExternalRepo", foreign_keys=[repo_id])
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_repo_analysis_repo_id", repo_id),
        Index("idx_repo_analysis_gca_status", gca_overall_status),
    )

    def __repr__(self):
        return f"<RepoAnalysisResult repo={self.repo_id} status={self.gca_overall_status}>"


class RepoIntegrationRoadmap(Base):
    """Roadmap de integração de repositório externo"""
    __tablename__ = "repo_integration_roadmaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("project_external_repos.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    effort_hours = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    repo = relationship("ProjectExternalRepo", foreign_keys=[repo_id])

    def __repr__(self):
        return f"<RepoIntegrationRoadmap step={self.step_number} title={self.title}>"


class AIUsageLog(Base):
    """Log de uso de IA por projeto — billing compartimentalizado"""
    __tablename__ = "ai_usage_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(30), nullable=False)
    model = Column(String(50), nullable=False)
    operation = Column(String(50), nullable=False)
    tokens_input = Column(Integer, nullable=False, default=0)
    tokens_output = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ai_usage_project", project_id),
        Index("idx_ai_usage_operation", project_id, operation),
        Index("idx_ai_usage_created", created_at),
    )

    def __repr__(self):
        return f"<AIUsageLog {self.provider}/{self.operation} ${self.cost_usd}>"


class BacklogItem(Base):
    """Item do backlog inteligente do projeto (spec v2.0 secao 5)"""
    __tablename__ = "backlog_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)  # modules, tests, compliance, security, agile, ui_screen, ui_flow, other
    module_type = Column(String(50), nullable=True)  # service, controller, model, middleware, test, migration, ui_screen, ui_flow
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, default="medium")  # critical, high, medium, low
    # Status expandido: pending, ready, generating, tests_running, security_review,
    # compliance_review, awaiting_qa, ready_to_merge, committed, published, blocked
    status = Column(String(30), nullable=False, default="pending")
    source = Column(String(50), nullable=False, default="ocg")  # ocg, ingestion, gatekeeper, arguider, manual
    source_version = Column(Integer, nullable=True)  # OCG version que gerou este item
    dependencies = Column(Text, nullable=True)  # JSON array de backlog_item IDs

    # Campos de artefatos (spec v2.0)
    required_artifacts = Column(Text, nullable=True)  # JSON: ["spec_tela", "erd", "regras_negocio"]
    present_artifacts = Column(Text, nullable=True)  # JSON: ["spec_auth_flow.md", "user_model_erd.sql"]
    compliance_iso27001 = Column(Text, nullable=True)  # JSON: checklist ISO 27001 aplicavel
    warnings = Column(Text, nullable=True)  # JSON: avisos sobre artefatos faltantes ou ferramentas

    # Hierarquia: item pai → sub-items (fixes de security/compliance)
    parent_item_id = Column(UUID(as_uuid=True), ForeignKey("backlog_items.id"), nullable=True)
    fix_severity = Column(String(20), nullable=True)  # CRITICAL, MEDIUM, LOW (para items tipo fix)
    fix_remediation = Column(Text, nullable=True)  # Sugestao de correcao do LLM

    # Cascata canônica Backlog→Roadmap→Scaffold (2026-04-24): FK para o
    # ModuleCandidate de origem quando source=arguider. Roadmap e Scaffold
    # leem readiness e pillar_impact do candidato via este JOIN.
    module_candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("module_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Rastreamento de pipeline
    generated_code_path = Column(String(500), nullable=True)  # Caminho do arquivo gerado
    generated_tests_path = Column(String(500), nullable=True)  # Caminho dos testes gerados
    commit_sha = Column(String(64), nullable=True)  # SHA do commit no repo
    branch_name = Column(String(200), nullable=True)  # Branch temporaria

    # Drag-and-drop order (default 0, updated by user reordering)
    display_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        Index("idx_backlog_project", project_id),
        Index("idx_backlog_category", project_id, category),
        Index("idx_backlog_status", project_id, status),
        Index("idx_backlog_priority", project_id, priority),
    )

    def __repr__(self):
        return f"<BacklogItem {self.title[:30]} ({self.category}/{self.priority}/{self.status})>"


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


class SystemSettings(Base):
    """Configurações globais do sistema (persistente, não por projeto)"""
    __tablename__ = "system_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    setting_key = Column(String(100), unique=True, nullable=False, index=True)  # ex: ai_provider:deepseek
    setting_value = Column(Text, nullable=False, default="{}")  # JSON
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<SystemSettings {self.setting_key}>"


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
    role = Column(String(50), default="admin")  # admin (system-level) para convite de novo Admin
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
    previous_hash = Column(String(64), nullable=True)  # Hash do registro anterior
    current_hash = Column(String(64), nullable=False)   # Hash deste registro (chain integrity)
    correlation_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Vincula eventos relacionados
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_audit_log_event_type", event_type),
        Index("idx_audit_log_created_at", created_at),
        Index("idx_audit_log_correlation", correlation_id),
    )

    def __repr__(self):
        return f"<GlobalAuditLog {self.event_type} {self.resource_type}>"


# Alias para compatibilidade
AuditLogGlobal = GlobalAuditLog


class Questionnaire(Base):
    """Questionnaire model - technical stack analysis submissions"""
    __tablename__ = "questionnaires"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
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

    # DT-020: trace do PDF recebido via aba Questionário (migration 019).
    # Todos nullable para retrocompat com submissions anteriores à migration.
    uploaded_filename = Column(String(500), nullable=True)
    file_hash = Column(String(64), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    answered_questions = Column(Integer, nullable=True)

    # MVP 29 Fase 29.2 — flags de idempotência das tasks Celery canônicas.
    # NOT NULL = "efeito já aplicado, skip silencioso". Cada uma protege
    # uma task que tem efeito externo visível ao usuário (email) ou
    # cria artefato único (OCG).
    admins_notified_at = Column(DateTime(timezone=True), nullable=True)
    analysis_email_sent_at = Column(DateTime(timezone=True), nullable=True)

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

    # Versionamento (spec seção 8.1)
    version = Column(Integer, default=1, nullable=False)  # Versão incremental do OCG
    schema_version = Column(String(20), default="1.0.0", nullable=False)  # Versão do schema JSON
    context_health = Column(Text, nullable=True, default="{}")  # JSON: {depth, confidence, quality}
    change_type = Column(String(20), nullable=True, default="INITIAL")  # INITIAL, EXPAND, CONTRACT

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

# MVP 9 Fase 9.5.2 — vínculo opcional com item do Roadmap.
# Coluna target_module_id adicionada via migration 029.
class IngestedDocument(Base):
    """Documento ingerido por projeto para análise do Arguidor"""
    __tablename__ = "ingested_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)  # nome gerado (uuid + ext)
    original_filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)  # pdf, docx, markdown, image, wireframe, spreadsheet, code, other
    document_category = Column(String(120), nullable=True)  # preenchido pelo Arguidor (texto livre do LLM)
    git_file_path = Column(String(500), nullable=True)
    git_analysis_path = Column(String(500), nullable=True)
    file_hash = Column(String(64), nullable=False)  # SHA256
    file_size_bytes = Column(Integer, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    quarantine_status = Column(String(20), nullable=False, default="none")  # none, quarantined, released, rejected
    pii_detected = Column(Boolean, nullable=False, default=False)
    pii_fields = Column(Text, nullable=True)  # JSON: lista de campos PII detectados
    arguider_status = Column(String(20), nullable=False, default="pending")  # pending, processing, completed, error
    arguider_started_at = Column(DateTime(timezone=True), nullable=True)
    arguider_completed_at = Column(DateTime(timezone=True), nullable=True)
    arguider_error_message = Column(Text, nullable=True)
    # Reforma Arguidor #1 (2026-04-25): flag de decisão canônica do owner.
    # Documentos com essa flag têm precedência sobre conteúdo antigo no OCG —
    # substituem valores em vez de gerar gap punitivo. Auto-detectado por
    # filename/category na ingestão; pode ser flipado manualmente pelo owner.
    is_canonical_decision = Column(Boolean, nullable=False, default=False, server_default="false")
    # MVP 8 Fase 1 — feedback de progresso. Estágio textual canônico +
    # porcentagem bucket por estágio. Frontend renderiza barra real.
    arguider_stage = Column(String(40), nullable=False, default="queued")
    arguider_progress_percent = Column(Integer, nullable=False, default=0)
    arguider_stage_updated_at = Column(DateTime(timezone=True), nullable=True)
    ocg_updated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # --- Rastreabilidade de origem (novos) ---
    source_type = Column(String(20), default="upload")
    source_url = Column(Text, nullable=True)
    source_repo_id = Column(UUID(as_uuid=True), ForeignKey("project_external_repos.id", ondelete="SET NULL"), nullable=True)

    # --- Disponibilidade dos bytes em disco ---
    # 'available': bytes em /app/storage ou recuperáveis via backfill
    # 'lost': perdidos permanentemente (uploads sem persistência prévia, etc.)
    content_status = Column(String(20), nullable=False, default="available")

    # MVP 9 Fase 9.5.2 — vínculo opcional com item do Roadmap.
    # Migration 029 adicionou FK ON DELETE SET NULL.
    target_module_id = Column(
        UUID(as_uuid=True),
        ForeignKey("module_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )

    project = relationship("Project", foreign_keys=[project_id])
    uploader = relationship("User", foreign_keys=[uploaded_by])
    route_maps = relationship("DocumentRouteMap", back_populates="document", cascade="all, delete-orphan")

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
    # MVP 9 Fase 9.1.1 — nullable porque foundation modules (source='ocg_foundation')
    # nascem do OCG sem passar por ArguiderAnalysis. Migration 027 aplicou
    # DROP NOT NULL + adicionou coluna `source` pra distinguir origem.
    arguider_analysis_id = Column(UUID(as_uuid=True), ForeignKey("arguider_analyses.id"), nullable=True)
    source = Column(String(30), nullable=False, default="arguider")  # 'arguider' | 'ocg_foundation'
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    module_type = Column(String(20), nullable=False)  # feature, component
    priority = Column(String(10), nullable=False, default="medium")  # high, medium, low
    status = Column(String(20), nullable=False, default="sugerido")  # MVP 9.1.2: pt-BR canônico
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    dependencies = Column(Text, nullable=False, default="[]")  # JSON array of module_candidate ids
    source_document_ids = Column(Text, nullable=False, default="[]")  # JSON array
    pillar_impact = Column(Text, nullable=False, default="{}")  # JSON {p1:bool,...,p7:bool}
    ready_for_codegen = Column(Boolean, nullable=False, default=False)
    # MVP 9 Fase 9.2 — cache do detalhamento gerado por Ollama (migration 028).
    # JSON: {what_it_is, prerequisites, missing_inputs, input_examples,
    # suggested_template_sections}. NULL = nunca gerado.
    details_json = Column(Text, nullable=True)
    details_generated_at = Column(DateTime(timezone=True), nullable=True)
    details_provider = Column(String(50), nullable=True)
    details_model = Column(String(100), nullable=True)
    # MVP 9 Fase 9.3 — orquestração premium (migration 030).
    # readiness_status: ready_for_codegen | partial | needs_input | unknown
    # readiness_gaps: JSON list de strings curtas
    # dependencies_inferred: JSON list de UUIDs/names de módulos pré-requisito
    readiness_status = Column(String(30), nullable=True)
    readiness_gaps = Column(Text, nullable=True)
    readiness_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    readiness_provider = Column(String(50), nullable=True)
    readiness_model = Column(String(100), nullable=True)
    dependencies_inferred = Column(Text, nullable=True)
    # MVP 9 Fase 9.2.ext — WebFetch curado (migration 031).
    # URL declarada explicitamente pelo GP/Foundation generator.
    # WebFetch só roda quando preenchido (sem navegação autônoma).
    external_reference = Column(String(500), nullable=True)
    external_reference_content = Column(Text, nullable=True)
    external_reference_fetched_at = Column(DateTime(timezone=True), nullable=True)
    external_reference_fetch_error = Column(Text, nullable=True)
    # MVP 19 Fase 19.1 — classificação IEEE 830 do requisito (migration 033).
    # Valores canônicos aplicação-level: functional | non_functional |
    # business_rule | NULL (ainda não classificado pelo GP). Whitelist
    # validada em app; banco aceita qualquer string ≤ 20 chars.
    requirement_category = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", foreign_keys=[project_id])
    analysis = relationship("ArguiderAnalysis", foreign_keys=[arguider_analysis_id])

    __table_args__ = (
        Index("idx_module_candidates_project", project_id),
        Index("idx_module_candidates_status", project_id, status),
        Index("idx_module_candidates_requirement_category", project_id, requirement_category),
    )


class UserNotification(Base):
    """Notificação in-app entregue a um usuário específico."""
    __tablename__ = "user_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    event_type = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    link = Column(String(500), nullable=True)
    severity = Column(String(20), nullable=False, default="info")
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_user_notif_user_unread", user_id, read_at),
        Index("idx_user_notif_user_created", user_id, created_at.desc()),
        Index("idx_user_notif_project", project_id),
    )


class IncidentTicket(Base):
    """MVP 6 — ticket de incidente aberto por usuário do projeto.

    Roteamento por papel do autor (resolvido no service):
      Dev/Tester/QA  → target_scope='gp'    (GPs do projeto recebem)
      GP             → target_scope='admin' (Admins da instância recebem)
      Admin          → target_scope='admin' (demais Admins recebem)

    Compartimentalização: cada ticket pertence a exatamente 1 projeto.
    Ticket de projeto A nunca é visto por membro de projeto B.
    """
    __tablename__ = "incident_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    target_scope = Column(String(10), nullable=False)  # 'gp' | 'admin'
    category = Column(String(40), nullable=False)  # bug | duvida | pedido_feature | incidente_pipeline
    priority = Column(String(10), nullable=False)  # baixa | media | alta | critica
    status = Column(String(20), nullable=False, default="open")  # open | in_progress | resolved | closed
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    # MVP 6 Emenda — contexto obrigatório do incidente.
    # section_reference: autopreenchida pelo frontend com a rota atual.
    # flow_description: textarea obrigatório (modal recusa vazio).
    # Ambos nullable no DB pra retrocompat com tickets anteriores à emenda;
    # service valida presença em criações novas.
    section_reference = Column(String(300), nullable=True)
    flow_description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("idx_incident_tickets_project_created", project_id, created_at.desc()),
        Index("idx_incident_tickets_target_status", target_scope, status, created_at.desc()),
        Index("idx_incident_tickets_author", author_id, created_at.desc()),
    )


class IncidentTicketAttachment(Base):
    """MVP 6 Emenda — anexo em ticket de incidente (imagem / log / texto / pdf).

    Storage: volume gca-uploads em incidents/{ticket_id}/{hash}_{filename}.
    Até 5 anexos por ticket, 10 MB cada (enforcement no service/router).
    """
    __tablename__ = "incident_ticket_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("incident_tickets.id", ondelete="CASCADE"), nullable=False)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    filename = Column(String(255), nullable=False)
    mime = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_path = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_incident_attachments_ticket", ticket_id, created_at.asc()),
    )


class Release(Base):
    """MVP 7 — Release aplicada ou pendente na instância.

    Cada release é declarada em backend/releases/<tag>.yaml shipado com
    o código. Ao startup, `release_service` detecta novas e:
      - não-destrutivas: aplica automaticamente (status='applied').
      - destrutivas: fica status='pending' até Admin confirmar; na
        aplicação, snapshot DT-063 por projeto ativo registrado em
        release_application_log antes das migrations rodarem.

    Rollback: snapshot pré-release pode restaurar o projeto (DT-063).
    Não há rollback do app/container (continua op manual via DT-062).
    """
    __tablename__ = "releases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tag = Column(String(40), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    is_destructive = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending | applied | rolled_back
    declared_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    git_commit_hash = Column(String(64), nullable=True)
    source_yaml = Column(String(255), nullable=True)


class ReleaseItem(Base):
    """Item de changelog dentro de uma release (MVP, ticket, fix, feature)."""
    __tablename__ = "release_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    release_id = Column(UUID(as_uuid=True), ForeignKey("releases.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(40), nullable=False)  # mvp | mvp_emenda | ticket | feature | fix | schema_change
    ref_id = Column(String(60), nullable=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # JSON: ["admin", "gp", "dev", "tester", "qa", "all"]
    affected_roles = Column(Text, default='["all"]', nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_release_items_release", release_id, display_order),
    )


class ReleaseApplicationLog(Base):
    """Log de eventos de release (aplicação, snapshot, rollback)."""
    __tablename__ = "release_application_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    release_id = Column(UUID(as_uuid=True), ForeignKey("releases.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(60), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column("metadata", Text, nullable=True)  # coluna "metadata" no DB, atributo metadata_json em Python (metadata é reservado do SQLAlchemy)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_release_log_release_created", release_id, created_at.asc()),
    )


class ReleaseCompletionTask(Base):
    """MVP 7 Fase 4 — tarefa pós-release por projeto.

    Criada quando uma release adiciona campo novo obrigatório; o GP/Admin
    preenche via UI e marca como 'done'. Estrutura pronta pra uso futuro.
    """
    __tablename__ = "release_completion_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    release_id = Column(UUID(as_uuid=True), ForeignKey("releases.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(60), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending | done | dismissed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("idx_release_tasks_project_status", project_id, status, created_at.desc()),
        Index("idx_release_tasks_release", release_id, status),
    )


class IncidentTicketComment(Base):
    """MVP 6 — comentário em ticket de incidente."""
    __tablename__ = "incident_ticket_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("incident_tickets.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_incident_comments_ticket", ticket_id, created_at.asc()),
    )


class OCGDeltaLog(Base):
    """Histórico de mudanças no OCG — auditoria + rollback"""
    __tablename__ = "ocg_delta_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="SET NULL"), nullable=True)
    ocg_version_from = Column(Integer, nullable=False)
    ocg_version_to = Column(Integer, nullable=False)
    fields_changed = Column(Text, nullable=False, default="{}")  # JSON {field: {old, new, reasoning}}
    change_summary = Column(Text, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    trigger_source = Column(String(50), nullable=False, default="document_ingestion")
    ocg_snapshot = Column(Text, nullable=True)  # JSON completo do OCG na versão_to — fonte do rollback
    source = Column(String(50), default="document_ingestion")  # questionnaire_response, persona_validation, etc
    persona_id = Column(String(20), nullable=True)  # gp, arquiteto, dba, dev_sr, qa
    decision = Column(String(30), nullable=True)  # approved, needs_clarification, rejected
    hash_chain = Column(String(64), nullable=True)  # SHA256 para integridade
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ocg_delta_project", project_id),
        Index("idx_ocg_delta_trigger", project_id, trigger_source),
        Index("idx_ocg_delta_version", project_id, ocg_version_to),
        Index("idx_ocg_delta_source", project_id, source),
        Index("idx_ocg_delta_persona", project_id, persona_id),
    )


class OCGIndividual(Base):
    """Parecer individual de uma persona LLM para um documento ingerido.

    Gerado pelo pipeline n8n (fan-out de 12 personas). Uma linha por
    combinação (document_id, persona_id). persona_id é a tag canônica
    da persona (ex: "AUD", "GP", "ARQ") — não é FK para users.id.

    MVP 31 Fase 31.1 — substituiu UUID FK→users pelo VARCHAR(20) tag.
    """
    __tablename__ = "ocg_individual"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="CASCADE"), nullable=False
    )
    # Tag canônica da persona LLM (ex: "AUD", "GP", "ARQ", "DBA", "DEV", etc.)
    # VARCHAR(20) — NÃO é FK para users.id (Conjunto B, §0.5 do CLAUDE.md)
    persona_id = Column(String(20), nullable=False)
    persona_name = Column(String(100), nullable=False)  # Nome exibível da persona
    parecer = Column(JSONB, nullable=False)  # Estrutura: {titulo, analise, riscos, recomendacoes, criticidade}
    status = Column(String(20), nullable=False)  # pending, processing, completed, error
    error_message = Column(Text, nullable=True)
    ai_provider = Column(String(50), nullable=True)  # Provedor de IA usado (auditoria)
    ai_model = Column(String(100), nullable=True)  # Modelo exato usado (auditoria)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("document_id", "persona_id", name="uq_ocg_individual_per_document_persona"),
        Index("idx_ocg_individual_project", project_id),
        Index("idx_ocg_individual_document", document_id),
        Index("idx_ocg_individual_persona", persona_id),
        Index("idx_ocg_individual_status", status),
    )

    def __repr__(self) -> str:
        return f"<OCGIndividual document={self.document_id} persona={self.persona_id} status={self.status}>"


class OCGGlobal(Base):
    """Parecer consolidado de todas as personas para um documento ingerido.

    Gerado pelo Consolidador n8n após receber todos os pareceres
    individuais via Redis accumulator. Uma linha por document_id.

    MVP 31 Fase 31.1 — modelo ORM espelhando schema pós-migration 062.
    """
    __tablename__ = "ocg_global"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="CASCADE"), nullable=False
    )
    parecer_consolidated = Column(JSONB, nullable=False)  # Parecer unificado após votação
    consensus_fields = Column(JSONB, nullable=False)  # Campos com consenso entre personas
    conflicting_fields = Column(JSONB, nullable=False)  # Campos com divergência (entrada p/ HITL)
    voting_results = Column(JSONB, nullable=False)  # Resultado da votação por campo
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    consolidated_at = Column(DateTime(timezone=True), nullable=True)
    consolidated_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("document_id", name="uq_ocg_global_per_document"),
        Index("idx_ocg_global_project", project_id),
        Index("idx_ocg_global_document", document_id),
    )

    def __repr__(self) -> str:
        return f"<OCGGlobal document={self.document_id} project={self.project_id}>"


class OCGIndividualRefined(Base):
    """Refinamento humano do parecer individual de uma persona (HITL).

    DT-080 — stub: completar quando pipeline HITL ativar na Fase 31.3.
    Por ora apenas espelha o schema da tabela para que o ORM não quebre.
    """
    __tablename__ = "ocg_individual_refined"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    ocg_individual_id = Column(
        UUID(as_uuid=True), ForeignKey("ocg_individual.id", ondelete="CASCADE"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<OCGIndividualRefined ocg_individual={self.ocg_individual_id}>"


class PersonaFollowUpQuestion(Base):
    """Pergunta de follow-up gerada por persona LLM para complementação humana (HITL).

    DT-080 — stub: completar quando pipeline HITL ativar na Fase 31.3.
    Por ora apenas espelha o schema da tabela para que o ORM não quebre.
    """
    __tablename__ = "persona_follow_up_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PersonaFollowUpQuestion project={self.project_id}>"


class AppPreviewSession(Base):
    """G4 (2026-04-25) — Sessão de preview do app gerado pelo owner.

    GCA não tem docker.sock montado, então não roda `docker compose up`
    do app gerado direto. Backend prepara comando shell pronto, persiste
    sessão aqui, e owner cola/roda local. Status reflete o que GCA SABE:
    `prepared` quando comando foi entregue, `running` se owner reportou
    sucesso, `stopped` quando owner declarou que parou, `error` se algo
    falhou na preparação.
    """
    __tablename__ = "app_preview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scaffold_run_id = Column(UUID(as_uuid=True), ForeignKey("scaffold_runs.id", ondelete="SET NULL"), nullable=True)
    port = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="prepared")
    setup_command = Column(Text, nullable=True)
    preview_url = Column(Text, nullable=True)
    repository_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    stopped_at = Column(DateTime(timezone=True), nullable=True)


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


class ProjectGlossaryTerm(Base):
    """MVP 19 Fase 19.3 — Termo do glossário vivo por projeto.

    Alimenta a seção 1.3 do ERS (IEEE 830). Candidatos são extraídos
    automaticamente via heurísticas do corpus do projeto (módulos,
    análises do Arguidor, OCG profile); apenas termos com status
    'approved' entram no ERS.gerado.
    """
    __tablename__ = "project_glossary_terms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    term = Column(String(200), nullable=False)
    definition = Column(Text, nullable=False, default="")
    # Valores canônicos (aplicação-level):
    #   ingested_doc | arguider_response | module_description |
    #   ocg_profile | manual
    source = Column(String(30), nullable=False, default="ingested_doc")
    # Valores canônicos (aplicação-level):
    #   candidate | approved | rejected
    status = Column(String(20), nullable=False, default="candidate")
    # Contexto curto de onde o termo foi extraído — exibido na UI
    # para o GP revisar com contexto.
    source_reference = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # UNIQUE com LOWER(term) é criada via migration 034 (SQLAlchemy não
        # suporta funções em UniqueConstraint sem Index Index func+DDL direto).
        Index("idx_glossary_project_status", project_id, status),
    )


class ExternalIssue(Base):
    """MVP 20 Fase 20.1a — Vínculo com issue em tracker externo (Jira, Trello, …).

    Cada linha = 1 issue criada/espelhada em um tracker configurado no projeto.
    `status_canonical` guarda o estado CANÔNICO do GCA; o status específico do
    provider (raw) fica em `status_raw` pra auditoria. Mapeamento provider→canônico
    é configurável por projeto (via `/settings`).

    Idempotência de webhook garantida por UNIQUE (project_id, provider, external_id)
    — ver migration 035. Mesma issue notificada 2x → mesma row atualizada, sem duplicar.

    Compartimentalização §2.2: project_id é NOT NULL e toda query filtra por ele;
    issue do projeto A nunca aparece em tracker do projeto B.
    """
    __tablename__ = "external_issues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    module_candidate_id = Column(UUID(as_uuid=True), ForeignKey("module_candidates.id", ondelete="SET NULL"), nullable=True)

    # Valores canônicos (aplicação-level whitelist):
    #   jira | trello | linear | asana | github
    # V1 aceita apenas: jira, trello.
    provider = Column(String(20), nullable=False)
    # ID nativo do provider: Jira key (ex: PROJ-123), Trello card id (hash), etc.
    external_id = Column(String(200), nullable=False)
    url = Column(Text, nullable=True)

    title = Column(String(500), nullable=False)
    # Estado CANÔNICO do GCA (whitelist aplicação-level):
    #   todo | in_progress | review | done | cancelled
    status_canonical = Column(String(20), nullable=False, default="todo")
    # Último estado recebido do provider (preserva naming específico).
    status_raw = Column(String(100), nullable=True)
    # Whitelist aplicação-level: low | medium | high | critical
    priority = Column(String(20), nullable=True)

    # Payload JSON com campos específicos do provider que não cabem no schema
    # canônico: epic_key/sprint_id/labels/assignee_id (Jira), list_id/board_id
    # /labels (Trello), etc. Evita UNION schema explodir.
    provider_specific = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # UNIQUE via migration 035 (índice canônico + expressão).
        Index("idx_external_issues_project", project_id),
        Index("idx_external_issues_status", project_id, status_canonical),
    )


class SecurityFinding(Base):
    """MVP 20 Fase 20.2 — Finding de segurança consumido de scanner externo.

    GCA NÃO gera finding próprio em V1 (decisão binária #3 MVP 20). Adapters
    consomem Sonar/Snyk/gitleaks do cliente e normalizam para schema canônico.

    Idempotência de re-sync via UNIQUE (project_id, source_scanner, external_id)
    garantida pela migration 036 — re-processar findings do mesmo scanner
    atualiza last_seen_at sem duplicar.

    P7 do OCG consome `count(status='open')` ponderado por severity.
    """
    __tablename__ = "security_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Whitelist aplicação-level: sonar | snyk | gitleaks
    source_scanner = Column(String(20), nullable=False)
    external_id = Column(String(200), nullable=False)

    file_path = Column(Text, nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)

    # Whitelist aplicação-level: critical | high | medium | low | info
    severity = Column(String(20), nullable=False)
    cwe_id = Column(String(20), nullable=True)
    rule_id = Column(String(200), nullable=True)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(Text, nullable=True)

    # Whitelist aplicação-level: open | fixed | accepted_risk
    status = Column(String(30), nullable=False, default="open")
    accepted_risk_justification = Column(Text, nullable=True)
    accepted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    admin_co_signed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_co_signed_at = Column(DateTime(timezone=True), nullable=True)

    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    fixed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_security_findings_project_status", project_id, status),
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
    # Contexto do projeto (desnormalizado para rastreabilidade)
    project_code = Column(String(50), nullable=True)
    project_name = Column(String(255), nullable=True)
    project_slug = Column(String(100), nullable=True)
    test_type = Column(String(20), nullable=True)
    adherence_percent = Column(Float, nullable=True)

    test_artifact = relationship("TestArtifact", foreign_keys=[test_artifact_id])
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (
        CheckConstraint("status IN ('passed','failed','error','skipped')", name="ck_test_exec_status"),
        Index("idx_test_exec_logs_artifact", test_artifact_id),
        Index("idx_test_exec_logs_project", project_id),
        Index("idx_test_exec_logs_status", status),
    )


class TestSpec(Base):
    """MVP 10 Fase 10.1 — Plano/spec de teste gerado por LLM.

    Camada **separada** de `TestArtifact` (implementação concreta CRUD manual)
    e `TestFile` (blueprint pós-CodeGen). Usa plain text markdown.

    Granularidade:
    - `module_id` preenchido = spec por módulo (unit/integration/e2e).
    - `module_id=NULL` = spec global consolidando OCG inteiro (security/compliance).

    Idempotência: `UniqueConstraint(project_id, module_id, spec_type)`.

    Stale detection (Fase 10.4): `ocg_version_at_generation` comparado com
    OCG atual — status vira 'stale' quando OCG avança.
    """
    # pytest vê classe iniciando por "Test" e tenta coletar como teste;
    # __test__ = False impede isso. É model SQLAlchemy, não test class.
    __test__ = False

    __tablename__ = "test_specs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(UUID(as_uuid=True), ForeignKey("module_candidates.id", ondelete="CASCADE"), nullable=True)
    spec_type = Column(String(20), nullable=False)  # unit|integration|security|compliance|e2e
    content = Column(Text, nullable=False, default="")  # markdown plain text
    provenance_json = Column(Text, nullable=True)  # JSON com OCG version, questionário, ingestões, LLM
    ocg_version_at_generation = Column(Integer, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    generator_provider = Column(String(50), nullable=True)
    generator_model = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft|approved|rejected|stale
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "module_id", "spec_type", name="uq_test_spec_unique"),
        Index("idx_test_specs_project_type", "project_id", "spec_type"),
        Index("idx_test_specs_status", "project_id", "status"),
    )


class LiveDoc(Base):
    """MVP 10 Fase 10.1 — Documentação viva gerada por LLM.

    - `doc_type='module_doc'` exige `module_id` preenchido (Ollama, baixa crit).
    - `doc_type='index'` ou `'architecture'` usa `module_id=NULL` (Premium, alta crit — consolidação).

    Não substitui docs em Git (README, ARCHITECTURE.md já publicados) —
    complementa com doc por módulo reativa ao OCG. Stale detection igual
    ao TestSpec (compara `ocg_version_at_generation`).
    """
    __tablename__ = "live_docs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(UUID(as_uuid=True), ForeignKey("module_candidates.id", ondelete="CASCADE"), nullable=True)
    doc_type = Column(String(30), nullable=False)  # module_doc|index|architecture
    content = Column(Text, nullable=False, default="")
    provenance_json = Column(Text, nullable=True)
    ocg_version_at_generation = Column(Integer, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    generator_provider = Column(String(50), nullable=True)
    generator_model = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "module_id", "doc_type", name="uq_live_doc_unique"),
        Index("idx_live_docs_project_type", "project_id", "doc_type"),
    )


class ProjectRelease(Base):
    """Release Bundle versionado de um projeto.

    Cada row é um zip gerado em /app/storage/releases/<project_id>/v<N>.zip
    com manifest, release notes, snapshot dos deliverables e docs versionados.
    Imutável após status='ready'.
    """
    __tablename__ = "project_releases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)  # incremental por projeto
    status = Column(String(20), nullable=False, default="generating")  # generating|ready|failed

    file_path = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)

    readiness_pct = Column(Float, nullable=True)
    readiness_threshold = Column(Float, nullable=False, default=90.0)

    manifest_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_release_per_project_version"),
        CheckConstraint("status IN ('generating', 'ready', 'failed')", name="ck_release_status"),
        Index("idx_releases_project_status", project_id, status),
        Index("idx_releases_project_created", project_id, created_at.desc()),
    )


class ProjectDeliverable(Base):
    """Item de OCG.DELIVERABLES materializado como linha rastreável.

    Sincronizado pelo DeliverableRegistry após cada update do OCG. Permite
    casar promessa (declared no OCG) com entrega (status=verified + evidência).
    """
    __tablename__ = "project_deliverables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(500), nullable=False)
    normalized_name = Column(String(500), nullable=False)
    category = Column(String(40), nullable=False, default="other")  # doc|code|test|config|process|other
    kind = Column(String(60), nullable=False, default="other_manual")

    # declared|generating|present|verified|waived|missing
    status = Column(String(20), nullable=False, default="declared")

    evidence_type = Column(String(30), nullable=True)
    evidence_ref = Column(String(500), nullable=True)
    verification_method = Column(String(60), nullable=True)

    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "normalized_name", name="uq_deliverable_per_project"),
        Index("idx_deliverables_project_status", project_id, status),
        Index("idx_deliverables_kind", kind),
    )


class CustomQuestionnaireIteration(Base):
    """M01 — iteração de questionário customizado.

    Uma iteração é gerada quando overall_score < 90 E existe algum
    pilar P1..P7 com score < 75. Respostas viram `ingested_documents`
    normais (campo `answer_document_id` aponta). Convergência detectada
    quando |overall_after - overall_before| < convergence_threshold.
    """

    __tablename__ = "custom_questionnaire_iterations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    iteration = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    target_pillars = Column(JSONB, nullable=False, default=list)
    questions = Column(JSONB, nullable=False, default=list)
    pdf_blob = Column(LargeBinary, nullable=True)
    answer_document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="SET NULL"), nullable=True)
    ocg_version_before = Column(Integer, nullable=True)
    ocg_version_after = Column(Integer, nullable=True)
    overall_before = Column(Numeric(5, 2), nullable=True)
    overall_after = Column(Numeric(5, 2), nullable=True)
    converged = Column(Boolean, nullable=False, default=False)
    not_applicable_ratio = Column(Numeric(4, 3), nullable=True)
    convergence_threshold = Column(Numeric(4, 2), nullable=False, default=1.00)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class AppliedDefault(Base):
    """M02 — decisão automática aplicada ao OCG pelo domain_defaults_resolver.

    Cada linha representa um default canônico (domínio público: LGPD, CC,
    CPC, CLT, segurança básica, padrões técnicos) que o resolver aplicou
    ao projeto em vez de perguntar ao user no M01. User contesta via UI —
    `contested_value` substitui `decision_value` pro CodeGen.
    """

    __tablename__ = "applied_defaults"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    gap_id = Column(String(20), nullable=False)
    category = Column(String(40), nullable=False)
    decision_key = Column(String(160), nullable=False)
    decision_value = Column(Text, nullable=False)
    source_citation = Column(String(400), nullable=False)
    rationale = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    contested_at = Column(DateTime(timezone=True), nullable=True)
    contested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    contested_value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ScaffoldRun(Base):
    """Run server-side de scaffold MVP 30. Sobrevive a desconexão do frontend.

    Statuses: pending → planning → generating → completed (ou failed).
    Após o usuário aprovar via apply, status vira applied (commit no Git).
    """
    __tablename__ = "scaffold_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    plan_summary = Column(Text, nullable=True)
    plan_tokens_used = Column(Integer, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)
    completed_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    apply_committed = Column(Integer, nullable=True)
    apply_failed = Column(Integer, nullable=True)
    # Watchdog 2026-04-25: timestamp do último item completed/failed.
    # status in (planning, generating) + last_progress_at > 10min = zombie.
    last_progress_at = Column(DateTime(timezone=True), nullable=True)


class ScaffoldRunItem(Base):
    """Cada arquivo do plano vira uma row. content é preenchido pelo Celery."""
    __tablename__ = "scaffold_run_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("scaffold_runs.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False)
    path = Column(String(500), nullable=False)
    file_type = Column(String(40), nullable=True)
    purpose = Column(String(500), nullable=True)
    est_lines = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    content = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    # Camada B: lista de paths (JSON-serializado) dos peers em que este
    # item depende. Vazio = sem dep. Toposort no execute_run.
    depends_on = Column(Text, nullable=False, default="[]", server_default="[]")
    # MVP-K (2026-04-26): erros de build reportados pelo owner via
    # /scaffold/runs/{id}/fix-build-errors. Vazio quando item está OK.
    # JSON list[str] ou texto bruto. Lido pelo executor pra injetar no
    # prompt de regeração.
    build_errors = Column(Text, nullable=True)


class CodeAuditFinding(Base):
    """Finding do Arguidor #2 (auditor ativo pós-CodeGen, 2026-04-25).

    1 row por divergência detectada num arquivo gerado vs OCG/RNFs/stack/
    PT-BR/security. Owner decide dismiss/accept; accept pode gerar
    BacklogItem fix.
    """
    __tablename__ = "code_audit_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey("scaffold_runs.id", ondelete="CASCADE"), nullable=False)
    run_item_id = Column(UUID(as_uuid=True), ForeignKey("scaffold_run_items.id", ondelete="SET NULL"), nullable=True)
    file_path = Column(String(500), nullable=False)
    severity = Column(String(10), nullable=False)  # info, warn, critical
    category = Column(String(20), nullable=False)  # rnf, stack, security, ptbr, scope, doc
    finding = Column(Text, nullable=False)
    suggested_fix = Column(Text, nullable=True)
    owner_action = Column(String(20), nullable=True)  # null, dismissed, accepted, fix_created
    owner_note = Column(Text, nullable=True)
    owner_acted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    owner_acted_at = Column(DateTime(timezone=True), nullable=True)
    backlog_fix_item_id = Column(UUID(as_uuid=True), ForeignKey("backlog_items.id", ondelete="SET NULL"), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DeferredGap(Base):
    """Aging de gaps recorrentes — reforma Arguidor #1 (2026-04-25).

    Após 5 sightings sem ação, o gap vira owner-deferred e para de
    impactar o score. Owner ressuscita manualmente se quiser.
    """
    __tablename__ = "deferred_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    gap_signature = Column(String(64), nullable=False)
    pillar = Column(String(40), nullable=True)
    sample_text = Column(Text, nullable=True)
    sightings_count = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    deferred_at = Column(DateTime(timezone=True), nullable=True)
    revived_at = Column(DateTime(timezone=True), nullable=True)
    revived_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class InitialQuestionnaire(Base):
    """Questionário Inicial — 20 perguntas essenciais que guiam as 5 Personas.

    User responde direto no browser (form HTML inline). Respostas persistem
    automaticamente enquanto digita. Cada pergunta pode ter:
    - Resposta de texto (textarea)
    - Opções selecionadas (checklist/radio)
    - Imagens anexadas (file upload)

    Fluxo:
    1. User acessa /projects/{id}/settings?tab=questionario
    2. Vê form com 20 perguntas
    3. Digita respostas (auto-save a cada 2s)
    4. Clica "Submeter" quando pronto
    5. Personas leem as respostas e geram seus questionários dinâmicos
    """
    __tablename__ = "initial_questionnaires"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Status: draft (preenchendo), submitted (enviado), validated (personas leram)
    status = Column(String(20), nullable=False, default="draft")

    # Seção A: Contexto do Projeto
    q1_name = Column(Text, nullable=True)  # Nome e objetivo
    q1_objective = Column(Text, nullable=True)
    q2_type = Column(String(50), nullable=True)  # novo_sistema, refactor, feature, manutencao
    q3_users = Column(Text, nullable=True)  # Quem são os usuários
    q3_volume = Column(Integer, nullable=True)  # Quantos simultâneos
    q4_months = Column(Integer, nullable=True)  # Prazo em meses
    q4_target_date = Column(String(10), nullable=True)  # YYYY-MM-DD

    # Seção B: Requisitos Funcionais
    q5_flows = Column(Text, nullable=True)  # 3-5 fluxos (um por linha)
    q6_integrations = Column(JSONB, nullable=True, default={})  # Lista de integrações selecionadas
    q6_integrations_detail = Column(Text, nullable=True)  # Detalhes de cada integração
    q7_frequency = Column(String(50), nullable=True)  # centenas_dia, milhares_dia, etc
    q8_reports = Column(Text, nullable=True)  # Relatórios e analytics
    q9_rules = Column(Text, nullable=True)  # Regras de negócio complexas

    # Seção C: Requisitos Não-Funcionais
    q10_performance = Column(String(50), nullable=True)  # nao_critica, importante, critica, ultra_critica
    q11_uptime = Column(String(50), nullable=True)  # 99, 99.5, 99.9, 99.99, 99.999
    q12_sensitive_data = Column(JSONB, nullable=True, default={})  # Checklist de tipos de dados
    q13_scalability = Column(String(50), nullable=True)  # estavel, modesto, agressivo, exponencial
    q14_compliance = Column(JSONB, nullable=True, default={})  # LGPD, GDPR, HIPAA, etc
    q15_longevity = Column(String(50), nullable=True)  # mvp_curto, medio_prazo, longo_prazo, permanente

    # Seção D: Contexto Técnico
    q16_stack = Column(Text, nullable=True)  # Backend, frontend, DB, infra
    q17_existing_infra = Column(Text, nullable=True)  # Infraestrutura a reutilizar
    q18_constraints = Column(Text, nullable=True)  # Constraints técnicos conhecidos

    # Seção E: Visão do GCA
    q19_gca_expectations = Column(JSONB, nullable=True, default={})  # Checklist de expectativas
    q20_risks = Column(Text, nullable=True)  # Riscos e incertezas

    # Imagens anexadas (por pergunta)
    # Formato: {"q1": [{"url": "...", "uploaded_at": "...", "size_bytes": ...}], ...}
    question_images = Column(JSONB, nullable=True, default={})

    # Metadados
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    validated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_initial_questionnaire_project", project_id),
        Index("idx_initial_questionnaire_status", project_id, status),
        UniqueConstraint("project_id", name="uq_initial_questionnaire_per_project"),
    )


class TechnicalQuestionnaire(Base):
    """Questionário Técnico Dinâmico — N perguntas com visibilidade condicional.

    Diferente do Initial Questionnaire (20 perguntas fixas), os questionários
    técnicos suportam qualquer número de perguntas com:
    - Visibilidade condicional (pergunta aparece se outra responder X)
    - Validação cruzada automática (se Q3=Não, Q7-14 devem estar vazios)
    - Schema flexível definido em código (technical_questions_schema.py)
    - Progresso calculado apenas com perguntas visíveis

    Fluxo:
    1. User acessa /projects/{id}/technical-questionnaire
    2. Vê form com perguntas dinâmicas (algumas ocultas inicialmente)
    3. Digita respostas (auto-save a cada 2s)
    4. Respostas mostram/ocultam mais perguntas
    5. Clica "Validar Escopo" quando progresso >= 80%
    6. Sistema valida conflitos lógicos (Q3=Não + A.2 preenchido = erro)
    7. Personas leem as respostas validadas
    """
    __tablename__ = "technical_questionnaires"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Respostas em JSONB: {"Q1": "valor", "Q3": ["opt1", "opt2"], ...}
    # Schema das perguntas é definido em technical_questions_schema.py
    responses = Column(JSONB, nullable=False, default={})

    # Progresso em percentual (0-100)
    # Calculado como: (perguntas_visíveis_preenchidas / perguntas_visíveis) * 100
    progress_percent = Column(Integer, nullable=False, default=0)

    # Status: draft (preenchendo), submitted (enviado), validated (personas leram)
    status = Column(String(20), nullable=False, default="draft")

    # Metadados: quem preencheu/validou e quando
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    validated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_technical_questionnaire_project", project_id),
        Index("idx_technical_questionnaire_status", project_id, status),
        Index("idx_technical_questionnaire_submitted_by", submitted_by),
    )


class PersonaResponse(Base):
    """Resposta de uma Persona para validação de questionário técnico.

    Rastreia avaliação de cada persona (GP, Arquiteto, DBA, Dev Sr, QA, etc)
    em tempo real, permitindo:
    - Board visual com status de cada persona
    - Consolidação paralela de OCGs
    - Detecção de discrepâncias entre personas
    - Histórico de decisões por persona
    """
    __tablename__ = "persona_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    technical_questionnaire_id = Column(UUID(as_uuid=True), ForeignKey("technical_questionnaires.id", ondelete="CASCADE"), nullable=False, index=True)

    # Qual persona avaliou: "gp" | "arquiteto" | "dba" | "dev_sr" | "qa"
    persona_name = Column(String(50), nullable=False)

    # Status da avaliação
    status = Column(String(20), nullable=False, default="pending")  # pending, evaluating, completed, error

    # Resultado da validação
    decision = Column(String, nullable=True)  # Texto da decisão (1-2 frases)
    ocg_delta = Column(JSONB, nullable=False, default={})  # Seção OCG a agregar
    followup_questions = Column(JSONB, nullable=True, default=None)  # Array de perguntas de clarificação
    severity = Column(String(20), nullable=False, default="info")  # info, warning, critical

    # Rastreabilidade temporal
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Tratamento de erros
    error_message = Column(String, nullable=True)

    # Qual IA provider foi usado
    ai_provider_used = Column(String(50), nullable=True)  # "anthropic", "deepseek", etc
    ai_model_used = Column(String(100), nullable=True)  # "claude-sonnet-4-6", "deepseek-chat", etc

    __table_args__ = (
        Index("idx_persona_response_project", project_id),
        Index("idx_persona_response_questionnaire", technical_questionnaire_id),
        Index("idx_persona_response_status", technical_questionnaire_id, status),
        Index("idx_persona_response_persona", technical_questionnaire_id, persona_name),
        UniqueConstraint("technical_questionnaire_id", "persona_name", name="uq_persona_response_per_questionnaire"),
    )


class Discrepancy(Base):
    """Conflito entre avaliações de personas.

    Quando 2+ personas discordam sobre campo específico do OCG,
    sistema detecta e permite team resolver (votação, override, arbitragem).

    Exemplos:
    - P1 (GP) diz "escopo crítico" vs P5 (QA) diz "escopo médio"
    - P2 (Arquiteto) recomenda "microserviços" vs P4 (Dev Sr) diz "monolito"
    """
    __tablename__ = "discrepancies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    technical_questionnaire_id = Column(UUID(as_uuid=True), ForeignKey("technical_questionnaires.id", ondelete="CASCADE"), nullable=False, index=True)

    # Campo em conflito (ex: "escopo", "arquitetura.stack", "dados.retention_policy")
    field_path = Column(String(200), nullable=False)

    # Personas envolvidas (JSONB array de persona_names, ex: ["gp", "qa", "dev_sr"])
    conflicting_personas = Column(JSONB, nullable=False, default=[])

    # Valores em conflito (JSONB object: {"gp": "crítico", "qa": "baixa", "dev_sr": "média"})
    conflicting_values = Column(JSONB, nullable=False, default={})

    # Categorização do conflito
    severity = Column(String(20), nullable=False, default="medium")  # low, medium, high, critical
    category = Column(String(50), nullable=True)  # "scope", "architecture", "performance", "data", etc

    # Status da resolução
    status = Column(String(20), nullable=False, default="unresolved")  # unresolved, voted, overridden, arbitrated, resolved

    # Rastreamento de resolução
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    detected_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Contexto/anotações
    context = Column(String, nullable=True)  # Descrição da discrepância
    resolution_notes = Column(String, nullable=True)  # Como foi resolvida

    __table_args__ = (
        Index("idx_discrepancy_project", project_id),
        Index("idx_discrepancy_questionnaire", technical_questionnaire_id),
        Index("idx_discrepancy_status", technical_questionnaire_id, status),
    )


class Resolution(Base):
    """Registro de como uma discrepância foi resolvida.

    Permite rastreamento de: votação (team), override (GP), arbitragem (Admin).
    """
    __tablename__ = "resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    discrepancy_id = Column(UUID(as_uuid=True), ForeignKey("discrepancies.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Qual valor foi escolhido (pode ser um dos conflitantes ou novo)
    resolved_value = Column(Text, nullable=False)

    # Como foi resolvido
    resolution_type = Column(String(50), nullable=False)  # "vote", "override", "arbitration", "compromise"

    # Votação: {"gp": "microserviços", "qa": "monolito", "dev_sr": "microserviços"}
    # Resultado: "microserviços" (venceu com 2/3)
    vote_details = Column(JSONB, nullable=True, default={})

    # Quem resolveu
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    resolved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Justificativa
    justification = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_resolution_discrepancy", discrepancy_id),
        Index("idx_resolution_project", project_id),
    )


class PilaresVivos(Base):
    """Documento consolidado vivo com análise de 7 personas sobre projeto.

    Pilares Vivos substitui documentos estáticos por análise dinâmica regenerável.
    Cada vez que ingestão ocorre, o documento é regenerado com novas análises das 7 personas.

    Estrutura do documento: {
      "P4_Arquiteto": {ocg_individual_json},
      "P1_DBA": {ocg_individual_json},
      "P2_Compliance": {ocg_individual_json},
      "P3_Seguranca": {ocg_individual_json},
      "P5_Dev": {ocg_individual_json},
      "P6_Tester": {ocg_individual_json},
      "P7_QA": {ocg_individual_json}
    }
    """
    __tablename__ = "pilares_vivos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Documento consolidado: análise de cada persona
    documento = Column(JSONB, nullable=False, default={})

    # Contexto usado para gerar
    gatekeeper_summary = Column(JSONB, nullable=True, default=None)  # Resumo dos 87 Gatekeeper items
    questionnaire_responses = Column(JSONB, nullable=True, default=None)  # Respostas do Questionário Técnico

    # Rastreamento
    gerado_por = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    gerado_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    regenerado_em = Column(DateTime(timezone=True), nullable=True)  # Data da última regeneração

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_pilares_vivos_project", project_id),
        Index("idx_pilares_vivos_gerado_por", gerado_por),
        Index("idx_pilares_vivos_gerado_em", gerado_em),
    )


class PilaresVivosHistory(Base):
    """Histórico de versões anteriores de Pilares Vivos para rastreabilidade.

    Armazena versões anteriores para que seja possível visualizar evolução
    e comparar mudanças entre regenerações.
    """
    __tablename__ = "pilares_vivos_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    pilares_vivos_id = Column(UUID(as_uuid=True), ForeignKey("pilares_vivos.id", ondelete="CASCADE"), nullable=False, index=True)

    # Documento da versão anterior
    documento = Column(JSONB, nullable=False, default={})

    # Contexto usado
    gatekeeper_summary = Column(JSONB, nullable=True, default=None)
    questionnaire_responses = Column(JSONB, nullable=True, default=None)

    # Rastreamento
    gerado_por = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    gerado_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    archived_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Mudanças detectadas
    personas_modificadas = Column(JSONB, nullable=True, default=[])  # ["P1_DBA", "P3_Seguranca"]
    resumo_mudancas = Column(String(500), nullable=True)

    __table_args__ = (
        Index("idx_pilares_history_project", project_id),
        Index("idx_pilares_history_current", pilares_vivos_id),
        Index("idx_pilares_history_gerado_em", gerado_em),
    )


class PilaresVivosJob(Base):
    """Rastreamento de jobs assíncronos para regeneração de Pilares Vivos.

    Converte endpoint síncrono /pilares/regenerar para padrão async com Celery.
    Frontend faz poll até job completar (status: completed/failed).
    """
    __tablename__ = "pilares_vivos_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued")  # queued, processing, completed, failed

    resultado_json = Column(JSONB, nullable=True)

    iniciado_em = Column(DateTime(timezone=True), nullable=True)
    concluido_em = Column(DateTime(timezone=True), nullable=True)
    tempo_total_segundos = Column(Numeric(8, 2), nullable=True)

    criado_em = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    criado_por = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    celery_task_id = Column(String(255), nullable=True, index=True)
    erro_mensagem = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_pilares_vivos_jobs_project", project_id),
        Index("idx_pilares_vivos_jobs_status", status),
        Index("idx_pilares_vivos_jobs_created", "criado_em"),
    )


class ConflictPendingReview(Base):
    """Conflito entre personas aguardando decisão humana (HITL — Human-In-The-Loop)."""
    __tablename__ = "conflicts_pending_review"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    route_map_id = Column(UUID(as_uuid=True), ForeignKey("document_route_maps.id", ondelete="CASCADE"), nullable=False)

    # O que as personas discordam
    field_name = Column(String(255), nullable=False)  # ex: "p1_business_score", "architecture_recommendation"
    personas_involved = Column(JSONB, nullable=False)  # list[str] ex: ["gp", "arq", "dev"]
    values_by_persona = Column(JSONB, nullable=False)  # {persona_tag: value} ex: {"gp": 80, "arq": 60, "dev": 70}
    conflict_reason = Column(Text, nullable=True)  # Por que discordam?

    # Status da resolução
    status = Column(String(20), nullable=False, default="pending")  # pending, resolved
    resolved_value = Column(JSONB, nullable=True)  # Valor escolhido pelo usuário
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_justification = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("idx_conflict_project", project_id),
        Index("idx_conflict_status", status),
        Index("idx_conflict_document", document_id),
    )


class ChunkErrorPendingReview(Base):
    """Chunk com erro durante auditoria — aguardando revisão humana (HITL)."""
    __tablename__ = "chunk_errors_pending_review"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("ingested_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(64), nullable=False)  # "chunk_001", "chunk_123", etc
    error_type = Column(String(30), nullable=False)  # json_invalid, timeout, llm_refusal, schema_validation, unknown
    error_message = Column(Text, nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    recovery_attempted = Column(Boolean, nullable=False, default=False)
    suggested_fallback = Column(Text, nullable=True)  # Sugestão de fallback (conteúdo padrão / omitir chunk)
    status = Column(String(20), nullable=False, default="pending")  # pending, resolved, escalated
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("idx_chunk_error_project", project_id),
        Index("idx_chunk_error_document", document_id),
        Index("idx_chunk_error_status", status),
    )
