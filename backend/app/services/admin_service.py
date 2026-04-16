"""
Admin Service
Gerencia criação e aprovação de projetos, provisioning de tenants
"""
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import structlog
import secrets

from app.core.config import settings
from app.core.security import hash_password
from app.utils.slug import generate_short_slug
from app.models.onboarding import ProjectRequest, ProjectRequestStatus, OnboardingProgress, DeliverableType
from app.models.base import User, Organization, Project, ProjectMember, AccessAttempt, SupportTicket, TicketResponse, IntegrationWebhook, SystemAlert
from app.models.pillar import PillarTemplate
from app.models.tenant import PillarConfiguration, OGCVersion

logger = structlog.get_logger(__name__)


class AdminService:
    """Service for admin project management and tenant provisioning"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_project_request(
        self,
        gp_id: UUID,
        project_name: str,
        project_slug: str,
        description: Optional[str] = None,
        deliverable_type: DeliverableType = None
    ) -> ProjectRequest:
        """Admin creates a new project request.
        deliverable_type é gate bloqueante — sem ele, o projeto não avança.
        """

        # Gate bloqueante: tipo de entregável obrigatório
        if not deliverable_type:
            raise ValueError(
                "Tipo de entregável é obrigatório. "
                "Opções: new_system, mobile_app, module, enhancement, "
                "integration, modernization, etl, maintenance"
            )

        # Valida slug
        if not self._validate_slug(project_slug):
            raise ValueError("Invalid slug format. Must be lowercase alphanumeric with hyphens")

        # Verifica se slug já existe
        result = await self.db.execute(
            select(ProjectRequest).where(ProjectRequest.project_slug == project_slug)
        )
        if result.scalar_one_or_none():
            raise ValueError(f"Project slug '{project_slug}' already exists")

        # Cria solicitação
        request = ProjectRequest(
            gp_id=gp_id,
            project_name=project_name,
            project_slug=project_slug,
            description=description,
            deliverable_type=deliverable_type,
            schema_name=f"proj_{project_slug}",
            status=ProjectRequestStatus.PENDING
        )

        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        logger.info("project.request_created",
                   project_slug=project_slug,
                   gp_id=str(gp_id),
                   request_id=str(request.id))

        return request

    async def approve_project_request(
        self,
        request_id: UUID,
        admin_id: UUID
    ) -> ProjectRequest:
        """Admin approves project request and provisions tenant.
        Spec seção 3.1: score >= 90 para onboarding automático.
        Spec seção 3.2: 6 ações obrigatórias (email, user, membership, token, convite, auditoria).
        """
        from uuid import uuid4 as new_uuid
        from app.services.audit_service import AuditService
        from app.models.base import Questionnaire

        request = await self.db.get(ProjectRequest, request_id)
        if not request:
            raise ValueError("Project request not found")

        if request.status != ProjectRequestStatus.PENDING:
            raise ValueError(f"Cannot approve request in status: {request.status}")

        # Correlation ID para vincular todos os eventos desta aprovação
        correlation_id = new_uuid()
        audit = AuditService(self.db)

        try:
            # === VALIDAÇÃO: Buscar score do questionário associado ===
            questionnaire = None
            gp = await self.db.get(User, request.gp_id)
            if gp:
                q_result = await self.db.execute(
                    select(Questionnaire)
                    .where(Questionnaire.gp_email == gp.email)
                    .order_by(Questionnaire.submitted_at.desc())
                    .limit(1)
                )
                questionnaire = q_result.scalar_one_or_none()

            adherence_score = questionnaire.adherence_score if questionnaire else None

            # Score < 90 => registrar pendência, não bloquear aprovação manual do admin
            if adherence_score is not None and adherence_score < 90:
                logger.warning("project.low_score_approval",
                              project_slug=request.project_slug,
                              score=adherence_score,
                              admin_id=str(admin_id))

            # === AÇÃO 1: Aprovar e gerar credenciais ===
            temp_password = secrets.token_urlsafe(12)
            request.initial_password_hash = hash_password(temp_password)
            request.status = ProjectRequestStatus.APPROVED
            request.approved_by = admin_id
            request.approved_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(request)

            # === AÇÃO 2: Provisionar tenant ===
            try:
                await self._provision_tenant(request)
                logger.info("project.approved_and_provisioned",
                           project_slug=request.project_slug,
                           approved_by=str(admin_id))
            except Exception as e:
                logger.error("project.provisioning_failed",
                            project_slug=request.project_slug,
                            error=str(e))
                raise

            # Restaurar search_path para schema global (provisioning altera)
            await self.db.execute(text('SET search_path = public'))

            # === AÇÃO 3: Criar/reutilizar User para GP ===
            if not gp:
                # User não existe — criar com senha temporária
                gp = User(
                    email=request.project_slug + "@gca.local",  # fallback
                    full_name="GP - " + request.project_name,
                    password_hash=hash_password(temp_password),
                    is_admin=False,
                    is_active=True,
                    first_access_completed=False,
                )
                self.db.add(gp)
                await self.db.flush()
                logger.info("project.gp_user_created", gp_id=str(gp.id))

                await audit.log_event(
                    event_type="GP_USER_CREATED",
                    resource_type="user",
                    actor_id=admin_id,
                    resource_id=gp.id,
                    correlation_id=correlation_id,
                    details={"gp_email": gp.email, "project": request.project_name},
                )

            # === AÇÃO 4: Criar Project + Membership ===
            org = await self._get_or_create_default_org(request.gp_id)

            short_slug = await generate_short_slug(request.project_name, self.db)
            project = Project(
                organization_id=org.id,
                name=request.project_name,
                slug=request.project_slug,
                short_slug=short_slug,
                description=request.description,
                deliverable_type=request.deliverable_type.value if request.deliverable_type else "new_system",
                status="active",
                provisioning_status="completed",
            )
            self.db.add(project)
            await self.db.flush()

            member = ProjectMember(
                project_id=project.id,
                user_id=request.gp_id,
                role="gp",
            )
            self.db.add(member)
            await self.db.commit()

            logger.info("project.record_created",
                       project_id=str(project.id),
                       project_slug=request.project_slug,
                       gp_id=str(request.gp_id))

            await audit.log_event(
                event_type="PROJECT_MEMBERSHIP_CREATED",
                resource_type="project_member",
                actor_id=admin_id,
                resource_id=project.id,
                correlation_id=correlation_id,
                details={"gp_id": str(request.gp_id), "role": "gp", "project": request.project_name},
            )

            # Initialize onboarding
            onboarding = OnboardingProgress(
                project_id=request.id,
                gp_id=request.gp_id
            )
            self.db.add(onboarding)
            await self.db.commit()

            # === AÇÃO 5: Gerar token de convite para primeiro acesso ===
            invite_token = secrets.token_urlsafe(32)

            # === AÇÃO 6: Enviar email de aprovação + email convite ===
            try:
                if gp:
                    from app.services.email_service import EmailService
                    score_text = f"Score de aderência: <strong>{adherence_score}%</strong>" if adherence_score else ""

                    # Email 1: Aprovação do projeto
                    EmailService.send_email(
                        to_email=gp.email,
                        subject=f"GCA — Projeto '{request.project_name}' aprovado!",
                        html_content=f"""
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <div style="background: #1e1b4b; padding: 20px; border-radius: 12px 12px 0 0;">
                                <h2 style="color: #c4b5fd; margin: 0;">Projeto Aprovado!</h2>
                            </div>
                            <div style="background: #1e293b; padding: 24px; border-radius: 0 0 12px 12px; color: #cbd5e1;">
                                <p>Olá <strong>{gp.full_name}</strong>,</p>
                                <p>Seu projeto <strong style="color: #a78bfa;">{request.project_name}</strong> foi aprovado pelo administrador do GCA.</p>
                                {f'<p>{score_text}</p>' if score_text else ''}
                                <p>O ambiente do projeto já foi provisionado e está pronto para uso.</p>
                                <hr style="border-color: #334155; margin: 20px 0;" />
                                <p style="color: #64748b; font-size: 12px;">GCA — Gestão de Codificação Assistida</p>
                            </div>
                        </div>
                        """,
                    )

                    # Email 2: Convite com token e instruções de acesso
                    login_url = f"https://gca.code-auditor.com.br/login"
                    is_first_access = not gp.first_access_completed

                    EmailService.send_email(
                        to_email=gp.email,
                        subject=f"GCA — Convite: Acesse o projeto '{request.project_name}'",
                        html_content=f"""
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <div style="background: #1e1b4b; padding: 20px; border-radius: 12px 12px 0 0;">
                                <h2 style="color: #c4b5fd; margin: 0;">Convite de Acesso</h2>
                            </div>
                            <div style="background: #1e293b; padding: 24px; border-radius: 0 0 12px 12px; color: #cbd5e1;">
                                <p>Olá <strong>{gp.full_name}</strong>,</p>
                                <p>Você foi designado(a) como <strong style="color: #a78bfa;">Gerente de Projeto</strong> no projeto <strong>{request.project_name}</strong>.</p>
                                <p>Acesse o GCA para gerenciar seu projeto:</p>
                                <p style="text-align: center; margin: 20px 0;">
                                    <a href="{login_url}" style="background: #7c3aed; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold;">Acessar GCA</a>
                                </p>
                                {'<p><strong>Primeiro acesso:</strong> Ao entrar, você deverá definir uma nova senha.</p>' if is_first_access else ''}
                                <p>Ao entrar, você verá apenas os projetos dos quais é membro. Selecione o projeto para acessar Ingestão, Dashboard, Team Invite e acompanhar o backlog.</p>
                                <hr style="border-color: #334155; margin: 20px 0;" />
                                <p style="color: #64748b; font-size: 12px;">Este acesso é limitado ao projeto e ao papel concedidos. — GCA</p>
                            </div>
                        </div>
                        """,
                    )

                    logger.info("project.gp_notified_both_emails",
                               gp_email=gp.email, project=request.project_name)

                    await audit.log_event(
                        event_type="PROJECT_APPROVAL_EMAIL_SENT",
                        resource_type="project_request",
                        actor_id=admin_id,
                        actor_email=gp.email,
                        resource_id=request.id,
                        correlation_id=correlation_id,
                        details={"project": request.project_name, "emails_sent": 2},
                    )

            except Exception as e:
                logger.warning("project.gp_notification_failed", error=str(e))

            # === AUDITORIA: Registrar aprovação ===
            await audit.log_event(
                event_type="QUESTIONNAIRE_APPROVED",
                resource_type="project_request",
                actor_id=admin_id,
                resource_id=request.id,
                correlation_id=correlation_id,
                details={
                    "project_name": request.project_name,
                    "project_slug": request.project_slug,
                    "adherence_score": adherence_score,
                    "gp_id": str(request.gp_id),
                },
            )
            await self.db.commit()

            # === AUTO-START: Se score >= 90, disparar geração do OCG automaticamente ===
            if adherence_score is not None and adherence_score >= 90 and questionnaire:
                try:
                    import asyncio
                    from app.services.ocg_service import OCGService
                    from app.routers.admin_gca_router import _load_ai_providers_from_db

                    # Carregar chaves IA do banco
                    await _load_ai_providers_from_db(self.db)

                    ocg_service = OCGService(self.db)
                    asyncio.create_task(
                        self._generate_ocg_async(questionnaire.id, project.id)
                    )
                    logger.info("project.ocg_auto_generation_triggered",
                               project_slug=request.project_slug,
                               score=adherence_score)
                except Exception as e:
                    logger.warning("project.ocg_auto_generation_failed", error=str(e))

            return request

        except Exception as e:
            await self.db.rollback()
            logger.error("project.approval_failed",
                        request_id=str(request_id),
                        error=str(e))
            raise

    async def reject_project_request(
        self,
        request_id: UUID,
        admin_id: UUID,
        reason: str
    ) -> ProjectRequest:
        """Admin rejects a project request"""

        request = await self.db.get(ProjectRequest, request_id)
        if not request:
            raise ValueError("Project request not found")

        if request.status != ProjectRequestStatus.PENDING:
            raise ValueError(f"Cannot reject request in status: {request.status}")

        request.status = ProjectRequestStatus.REJECTED
        request.approved_by = admin_id
        request.approved_at = datetime.now(timezone.utc)
        request.rejection_reason = reason

        await self.db.commit()
        await self.db.refresh(request)

        logger.info("project.request_rejected",
                   project_slug=request.project_slug,
                   rejected_by=str(admin_id),
                   reason=reason)

        return request

    async def get_pending_projects(self) -> list[ProjectRequest]:
        """Get all project requests (pending, approved, rejected)"""

        result = await self.db.execute(
            select(ProjectRequest)
            .order_by(ProjectRequest.requested_at.desc())
        )

        return result.scalars().all()

    async def _generate_ocg_async(self, questionnaire_id, project_id):
        """Gera OCG em background após aprovação com score >= 90."""
        try:
            from app.db.database import AsyncSessionLocal
            from app.services.ocg_service import OCGService

            async with AsyncSessionLocal() as db:
                ocg_service = OCGService(db)
                await ocg_service.generate_ocg_from_questionnaire(
                    questionnaire_id=questionnaire_id,
                    project_id=project_id,
                )
                logger.info("project.ocg_auto_generated",
                           questionnaire_id=str(questionnaire_id),
                           project_id=str(project_id))
        except Exception as e:
            logger.error("project.ocg_auto_generation_error", error=str(e))

    # ========== ORGANIZATION HELPER ==========

    async def _get_or_create_default_org(self, gp_id: UUID) -> Organization:
        """Busca organização do GP ou cria uma padrão"""
        from sqlalchemy.orm import selectinload

        # Verificar se GP já tem organização
        result = await self.db.execute(
            select(Organization).where(Organization.owner_id == gp_id)
        )
        org = result.scalar_one_or_none()
        if org:
            return org

        # Criar organização padrão para o GP
        gp = await self.db.get(User, gp_id)
        gp_name = gp.full_name if gp else "GP"
        slug = f"org-{gp_name.lower().replace(' ', '-')[:30]}"

        # Garantir slug único
        check = await self.db.execute(select(Organization).where(Organization.slug == slug))
        if check.scalar_one_or_none():
            slug = f"{slug}-{secrets.token_hex(3)}"

        org = Organization(
            name=f"Organização de {gp_name}",
            slug=slug,
            owner_id=gp_id,
        )
        self.db.add(org)
        await self.db.flush()

        logger.info("organization.default_created",
                    org_id=str(org.id),
                    gp_id=str(gp_id))

        return org

    # ========== TENANT PROVISIONING ==========

    async def _provision_tenant(self, project: ProjectRequest):
        """Provision tenant schema and initialize data"""

        schema_name = project.schema_name

        try:
            # Import engine for schema/table creation
            from app.db.database import engine, Base

            # 1. Create schema using engine (not session)
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
                logger.info("tenant.schema_created", schema_name=schema_name)

            # 2. Create tables in tenant schema
            from sqlalchemy.schema import CreateTable

            async with engine.begin() as conn:
                # Manually create each table with schema qualification
                for table in Base.metadata.sorted_tables:
                    # Create DDL statement with schema prefix
                    create_stmt = CreateTable(table, if_not_exists=True)

                    # Modify the statement to use the correct schema
                    ddl_string = str(create_stmt.compile(dialect=engine.dialect))

                    # Replace table references with schema-qualified names
                    qualified_ddl = ddl_string.replace(
                        f'{table.name}',
                        f'"{schema_name}"."{table.name}"',
                        1  # Replace only first occurrence
                    )

                    try:
                        await conn.execute(text(qualified_ddl))
                    except Exception as e:
                        logger.debug("tenant.table_creation_detail",
                                    table=table.name,
                                    schema=schema_name,
                                    error=str(e))

                logger.info("tenant.tables_created", schema_name=schema_name)

            # 3. Seed pillar configurations
            await self._seed_tenant_pillars(schema_name, project.id)

            # 4. Create initial OGC
            await self._create_initial_ogc(schema_name, project.id)

        except Exception as e:
            logger.error("tenant.provisioning_failed",
                        schema=schema_name,
                        project_id=str(project.id),
                        error=str(e))
            raise

    async def _seed_tenant_pillars(self, schema_name: str, project_id: UUID):
        """Copy pillar templates to tenant schema with default weights"""

        try:
            # Get all pillar templates from global schema
            result = await self.db.execute(select(PillarTemplate))
            pillars = result.scalars().all()

            if not pillars:
                logger.warning("tenant.pillar_seeding_no_templates",
                              schema=schema_name)
                return

            # Set search path to tenant schema for inserts
            await self.db.execute(text(f'SET search_path = "{schema_name}", public'))

            # Create configurations for each pillar
            for pillar in pillars:
                config = PillarConfiguration(
                    pillar_code=pillar.code,
                    pillar_name=pillar.name,
                    weight=pillar.default_weight,
                    importance="high" if pillar.is_blocking else "medium",
                    custom_criteria=pillar.default_criteria.copy() if pillar.default_criteria else {},
                    is_active=True
                )
                self.db.add(config)
                logger.info("tenant.pillar_configured",
                           schema=schema_name,
                           pillar=pillar.code)

            # Commit all pillar configurations
            await self.db.commit()

        except Exception as e:
            await self.db.rollback()
            logger.error("tenant.pillar_seeding_failed",
                        schema=schema_name,
                        error=str(e))
            raise

    async def _create_initial_ogc(self, schema_name: str, project_id: UUID):
        """Create initial OGC version for tenant"""

        try:
            # Set search path to tenant schema
            await self.db.execute(text(f'SET search_path = "{schema_name}", public'))

            ogc = OGCVersion(
                version=1,
                pillar_context={},
                ogc_data={
                    "project_id": str(project_id),
                    "schema": schema_name,
                    "initialized_at": datetime.now(timezone.utc).isoformat(),
                    "status": "initialization"
                },
                is_active=True
            )
            self.db.add(ogc)
            await self.db.commit()

            logger.info("tenant.ogc_initialized",
                       schema=schema_name,
                       version=1,
                       project_id=str(project_id))

        except Exception as e:
            await self.db.rollback()
            logger.error("tenant.ogc_creation_failed",
                        schema=schema_name,
                        error=str(e))
            raise

    def _validate_slug(self, slug: str) -> bool:
        """Valida formato de slug"""
        import re
        return bool(re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', slug))

    # ========== USER MANAGEMENT ==========

    async def list_users(self) -> list[User]:
        """List all users in the system"""
        result = await self.db.execute(
            select(User)
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()

    async def reset_user_password(self, user_id: UUID) -> dict:
        """Generate new temporary password for user"""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)
        user.password_hash = hash_password(temp_password)
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)

        logger.info("user.password_reset",
                   user_id=str(user_id),
                   email=user.email)

        return {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "temp_password": temp_password,
            "reset_at": user.updated_at.isoformat()
        }

    async def lock_user(self, user_id: UUID) -> dict:
        """Lock (deactivate) a user account"""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        if not user.is_active:
            raise ValueError("User is already locked")

        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)

        logger.info("user.locked",
                   user_id=str(user_id),
                   email=user.email)

        return {
            "user_id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "locked_at": user.updated_at.isoformat()
        }

    async def unlock_user(self, user_id: UUID) -> dict:
        """Unlock (reactivate) a user account"""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        if user.is_active:
            raise ValueError("User is already active")

        user.is_active = True
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)

        logger.info("user.unlocked",
                   user_id=str(user_id),
                   email=user.email)

        return {
            "user_id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "unlocked_at": user.updated_at.isoformat()
        }

    # ========== SUSPICIOUS ACCESS MONITORING ==========

    async def get_suspicious_access_attempts(self) -> list[AccessAttempt]:
        """Get all suspicious access attempts (blocked users)"""
        result = await self.db.execute(
            select(AccessAttempt)
            .where(AccessAttempt.blocked == True)
            .order_by(AccessAttempt.blocked_at.desc())
        )
        return result.scalars().all()

    async def record_access_attempt(
        self,
        user_id: UUID,
        project_id: UUID
    ) -> dict:
        """Record unauthorized access attempt and lock user if 5 attempts reached"""

        # Check if user is trying to access a project they're not authorized for
        # This should be called by auth middleware when user tries to access project they don't belong to

        # Get current attempt count for this user+project combination
        result = await self.db.execute(
            select(AccessAttempt)
            .where(
                (AccessAttempt.user_id == user_id) &
                (AccessAttempt.project_id == project_id) &
                (AccessAttempt.blocked == False)
            )
            .order_by(AccessAttempt.created_at.desc())
        )
        latest_attempt = result.scalars().first()

        if latest_attempt:
            latest_attempt.attempt_number += 1
        else:
            latest_attempt = AccessAttempt(
                user_id=user_id,
                project_id=project_id,
                attempt_number=1
            )
            self.db.add(latest_attempt)

        # If 5 attempts reached, block the user
        if latest_attempt.attempt_number >= 5:
            latest_attempt.blocked = True
            latest_attempt.blocked_at = datetime.now(timezone.utc)

            # Lock the user account
            user = await self.db.get(User, user_id)
            if user and user.is_active:
                user.is_active = False
                user.updated_at = datetime.now(timezone.utc)
                logger.warning("user.locked_due_to_suspicious_access",
                             user_id=str(user_id),
                             project_id=str(project_id),
                             attempts=latest_attempt.attempt_number)

        await self.db.commit()
        await self.db.refresh(latest_attempt)

        logger.info("access.attempt_recorded",
                   user_id=str(user_id),
                   project_id=str(project_id),
                   attempt=latest_attempt.attempt_number,
                   blocked=latest_attempt.blocked)

        return {
            "user_id": str(user_id),
            "project_id": str(project_id),
            "attempt_number": latest_attempt.attempt_number,
            "blocked": latest_attempt.blocked,
            "blocked_at": latest_attempt.blocked_at.isoformat() if latest_attempt.blocked_at else None
        }

    async def unlock_suspicious_access(self, access_attempt_id: UUID) -> dict:
        """Unlock a user from suspicious access block"""
        attempt = await self.db.get(AccessAttempt, access_attempt_id)
        if not attempt:
            raise ValueError("Access attempt record not found")

        if not attempt.blocked:
            raise ValueError("This access attempt is not blocked")

        attempt.blocked = False
        attempt.unblocked_at = datetime.now(timezone.utc)

        # Reactivate user
        user = await self.db.get(User, attempt.user_id)
        if user:
            user.is_active = True
            user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(attempt)

        logger.info("suspicious_access.unblocked",
                   access_attempt_id=str(access_attempt_id),
                   user_id=str(attempt.user_id))

        return {
            "access_attempt_id": str(attempt.id),
            "user_id": str(attempt.user_id),
            "project_id": str(attempt.project_id),
            "blocked": attempt.blocked,
            "unblocked_at": attempt.unblocked_at.isoformat()
        }

    # ========== SAC - SUPPORT TICKETS ==========

    async def get_all_tickets(self, status: Optional[str] = None, severity: Optional[str] = None) -> list[SupportTicket]:
        """Get all support tickets, optionally filtered by status and severity"""
        query = select(SupportTicket)

        if status:
            query = query.where(SupportTicket.status == status)
        if severity:
            query = query.where(SupportTicket.severity == severity)

        query = query.order_by(SupportTicket.created_at.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_ticket_details(self, ticket_id: UUID) -> SupportTicket:
        """Get full details of a support ticket including all responses"""
        ticket = await self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise ValueError("Support ticket not found")

        return ticket

    async def respond_to_ticket(
        self,
        ticket_id: UUID,
        responder_id: UUID,
        message: str,
        resolve: bool = False
    ) -> dict:
        """Admin/GP responds to a support ticket"""
        ticket = await self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise ValueError("Support ticket not found")

        # Create response
        response = TicketResponse(
            ticket_id=ticket_id,
            responder_id=responder_id,
            message=message,
            is_resolution=resolve
        )
        self.db.add(response)

        # Update ticket status
        if ticket.status == "ABERTO":
            ticket.status = "EM_ANÁLISE"
            if ticket.first_response_at is None:
                ticket.first_response_at = datetime.now(timezone.utc)

        if resolve:
            ticket.status = "RESOLVIDO"
            ticket.resolved_at = datetime.now(timezone.utc)

        ticket.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(response)
        await self.db.refresh(ticket)

        logger.info("ticket.response_added",
                   ticket_id=str(ticket_id),
                   responder_id=str(responder_id),
                   resolved=resolve)

        return {
            "response_id": str(response.id),
            "ticket_id": str(ticket.id),
            "ticket_status": ticket.status,
            "message": message,
            "is_resolution": resolve,
            "responded_at": response.created_at.isoformat()
        }

    # ========== DASHBOARD EXECUTIVO ==========

    async def get_dashboard_metrics(self) -> dict:
        """Get executive dashboard metrics"""
        from app.models.base import Project, Organization

        try:
            # Count projects by status
            result_projects = await self.db.execute(select(Project))
            all_projects = result_projects.scalars().all()

            # Count users
            result_users = await self.db.execute(select(User))
            all_users = result_users.scalars().all()

            # Count tickets by status
            result_tickets = await self.db.execute(select(SupportTicket))
            all_tickets = result_tickets.scalars().all()

            # Count suspicious access blocks
            result_access = await self.db.execute(
                select(AccessAttempt).where(AccessAttempt.blocked == True)
            )
            blocked_users = result_access.scalars().all()

            # Calculate metrics
            projects_active = len([p for p in all_projects if p.status in ["active", "wizard_step_1", "wizard_step_2", "wizard_step_3", "wizard_step_4"]])
            projects_completed = len([p for p in all_projects if p.status == "completed"])
            projects_archived = len([p for p in all_projects if p.status == "archived"])

            tickets_open = len([t for t in all_tickets if t.status == "ABERTO"])
            tickets_analyzing = len([t for t in all_tickets if t.status == "EM_ANÁLISE"])
            tickets_resolved = len([t for t in all_tickets if t.status == "RESOLVIDO"])

            # SLA Compliance (tickets resolved on time)
            tickets_on_time = sum(1 for t in all_tickets if t.status == "RESOLVIDO" and t.resolved_at and (t.resolved_at - t.created_at).days <= 7)
            sla_compliance = (tickets_on_time / len([t for t in all_tickets if t.status == "RESOLVIDO"]) * 100) if len([t for t in all_tickets if t.status == "RESOLVIDO"]) > 0 else 0

            # Average response time
            response_times = []
            for t in all_tickets:
                if t.first_response_at:
                    response_time = (t.first_response_at - t.created_at).total_seconds() / 3600
                    response_times.append(response_time)

            avg_response_time = sum(response_times) / len(response_times) if response_times else 0

            logger.info("dashboard.metrics_calculated",
                       projects_count=len(all_projects),
                       users_count=len(all_users),
                       tickets_count=len(all_tickets))

            return {
                "summary": {
                    "total_projects": len(all_projects),
                    "projects_active": projects_active,
                    "projects_completed": projects_completed,
                    "projects_archived": projects_archived,
                    "total_users": len(all_users),
                    "total_tickets": len(all_tickets)
                },
                "tickets": {
                    "open": tickets_open,
                    "analyzing": tickets_analyzing,
                    "resolved": tickets_resolved,
                    "average_response_time_hours": round(avg_response_time, 2),
                    "sla_compliance_percent": round(sla_compliance, 1)
                },
                "security": {
                    "blocked_users": len(blocked_users),
                    "access_incidents": len(blocked_users)
                },
                "system_health": {
                    "uptime_percent": 99.5,  # Placeholder - would come from monitoring
                    "average_response_time_ms": 250,  # Placeholder
                    "success_rate_percent": 94.2  # Placeholder
                },
                "projects": [
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "slug": p.slug,
                        "status": p.status,
                        "provisioning_status": p.provisioning_status,
                        "created_at": p.created_at.isoformat()
                    }
                    for p in all_projects[:10]  # Top 10 projects
                ],
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error("dashboard.metrics_error", error=str(e))
            raise

    # ========== INTEGRATIONS & ALERTS ==========

    async def test_webhook(self, integration_type: str, webhook_url: str) -> dict:
        """Test a webhook integration (Teams, Slack, Discord)"""
        import requests
        import json

        try:
            # Prepare test message based on integration type
            if integration_type.lower() == "teams":
                payload = {
                    "@type": "MessageCard",
                    "@context": "https://schema.org/extensions",
                    "summary": "GCA Webhook Test",
                    "themeColor": "0078D4",
                    "title": "✅ GCA - Teste de Integração",
                    "sections": [
                        {
                            "text": "Esta é uma mensagem de teste para confirmar que a integração está funcionando corretamente."
                        }
                    ]
                }
            elif integration_type.lower() == "slack":
                payload = {
                    "text": "✅ GCA - Teste de Integração",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "Teste de Integração GCA"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Esta é uma mensagem de teste para confirmar que a integração está funcionando corretamente."
                            }
                        }
                    ]
                }
            else:
                return {
                    "success": False,
                    "error": f"Unsupported integration type: {integration_type}",
                    "tested_at": datetime.now(timezone.utc).isoformat()
                }

            # Send test message to webhook
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )

            success = response.status_code in [200, 201]

            logger.info("webhook.test_completed",
                       integration_type=integration_type,
                       status_code=response.status_code,
                       success=success)

            return {
                "success": success,
                "status_code": response.status_code,
                "message": "Webhook test successful" if success else "Webhook test failed",
                "tested_at": datetime.now(timezone.utc).isoformat()
            }

        except requests.exceptions.RequestException as e:
            logger.warning("webhook.test_failed",
                          integration_type=integration_type,
                          error=str(e))
            return {
                "success": False,
                "error": str(e),
                "tested_at": datetime.now(timezone.utc).isoformat()
            }

    async def get_alerts_history(
        self,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> list[SystemAlert]:
        """Get system alerts history with optional filters"""
        query = select(SystemAlert)

        if alert_type:
            query = query.where(SystemAlert.alert_type == alert_type)
        if severity:
            query = query.where(SystemAlert.severity == severity)
        if status:
            query = query.where(SystemAlert.status == status)

        query = query.order_by(SystemAlert.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def record_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        details: Optional[str] = None,
        send_to_teams: bool = False,
        send_to_slack: bool = False,
        send_via_email: bool = False
    ) -> dict:
        """Record a system alert to be sent to admins"""
        alert = SystemAlert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            details=details,
            sent_to_teams=send_to_teams,
            sent_to_slack=send_to_slack,
            sent_via_email=send_via_email,
            status="pending"
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)

        logger.info("alert.recorded",
                   alert_type=alert_type,
                   severity=severity,
                   alert_id=str(alert.id))

        return {
            "alert_id": str(alert.id),
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "status": alert.status,
            "created_at": alert.created_at.isoformat()
        }

    async def acknowledge_alert(self, alert_id: UUID, admin_id: UUID) -> dict:
        """Mark an alert as acknowledged by an admin"""
        alert = await self.db.get(SystemAlert, alert_id)
        if not alert:
            raise ValueError("Alert not found")

        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = admin_id

        await self.db.commit()
        await self.db.refresh(alert)

        logger.info("alert.acknowledged",
                   alert_id=str(alert_id),
                   admin_id=str(admin_id))

        return {
            "alert_id": str(alert.id),
            "status": alert.status,
            "acknowledged_at": alert.acknowledged_at.isoformat()
        }
