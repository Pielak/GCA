"""
Onboarding Service
Orquestra o fluxo de 5 passos para provisioning de novos tenants
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import structlog
import httpx
import secrets

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token, hash_password
from app.models.onboarding import (
    ProjectRequest, OnboardingProgress, TeamInvite, StepStatus,
    ProjectRequestStatus
)
from app.models.base import User

logger = structlog.get_logger(__name__)


class OnboardingService:
    """Service for managing project provisioning and GP onboarding"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ========== ADMIN: CREATE PROJECT ==========

    async def create_project_request(
        self,
        gp_id: UUID,
        project_name: str,
        project_slug: str,
        description: Optional[str] = None
    ) -> ProjectRequest:
        """Admin creates a new project request"""

        # Valida slug
        if not self._validate_slug(project_slug):
            raise ValueError("Invalid slug format")

        # Cria solicitação
        request = ProjectRequest(
            gp_id=gp_id,
            project_name=project_name,
            project_slug=project_slug,
            description=description,
            schema_name=f"proj_{project_slug}",
            status=ProjectRequestStatus.PENDING
        )

        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        logger.info("project.request_created",
                   project_slug=project_slug,
                   gp_id=str(gp_id))

        return request

    async def approve_project_request(
        self,
        request_id: UUID,
        admin_id: UUID
    ) -> ProjectRequest:
        """Admin approves a project request and generates initial credentials"""

        request = await self.db.get(ProjectRequest, request_id)
        if not request:
            raise ValueError("Project request not found")

        if request.status != ProjectRequestStatus.PENDING:
            raise ValueError(f"Cannot approve request in status: {request.status}")

        # Gera senha temporária
        temp_password = secrets.token_urlsafe(12)
        request.initial_password_hash = hash_password(temp_password)

        # Aprova
        request.status = ProjectRequestStatus.APPROVED
        request.approved_by = admin_id
        request.approved_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(request)

        logger.info("project.approved",
                   project_slug=request.project_slug,
                   approved_by=str(admin_id))

        return request

    async def initialize_onboarding(
        self,
        project_id: UUID,
        gp_id: UUID
    ) -> OnboardingProgress:
        """Inicia progress tracking para onboarding"""

        progress = OnboardingProgress(
            project_id=project_id,
            gp_id=gp_id,
            current_step=1
        )

        self.db.add(progress)
        await self.db.commit()
        await self.db.refresh(progress)

        logger.info("onboarding.initialized",
                   project_id=str(project_id),
                   gp_id=str(gp_id))

        return progress

    # ========== STEP 1: REPOSITORY SETUP ==========

    async def complete_step_1_repository(
        self,
        onboarding_id: UUID,
        provider: str,
        repo_url: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        GP configura repositório
        Valida token e acesso
        """

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        try:
            # Valida token baseado em provider
            is_valid = await self._validate_repo_token(provider, access_token)
            if not is_valid:
                raise ValueError("Invalid repository token")

            # Armazena token criptografado
            progress.step_1_provider = provider
            progress.step_1_repo_url = repo_url
            progress.step_1_token_encrypted = encrypt_token(access_token)
            progress.step_1_token_verified = True
            progress.step_1_verified_at = datetime.now(timezone.utc)
            progress.step_1_status = StepStatus.COMPLETED
            progress.current_step = 2

            await self.db.commit()
            await self.db.refresh(progress)

            logger.info("onboarding.step_1_completed",
                       provider=provider,
                       repo_url=repo_url)

            return {
                "status": "completed",
                "verified": True,
                "provider": provider,
                "next_step": 2
            }

        except Exception as e:
            progress.step_1_status = StepStatus.FAILED
            progress.step_1_error_msg = str(e)
            await self.db.commit()

            logger.error("onboarding.step_1_failed", error=str(e))
            raise

    async def _validate_repo_token(self, provider: str, token: str) -> bool:
        """Valida token com o provedor"""

        try:
            async with httpx.AsyncClient() as client:
                if provider == "github":
                    response = await client.get(
                        "https://api.github.com/user",
                        headers={"Authorization": f"token {token}"},
                        timeout=10.0
                    )
                    return response.status_code == 200

                elif provider == "gitlab":
                    response = await client.get(
                        "https://gitlab.com/api/v4/user",
                        headers={"PRIVATE-TOKEN": token},
                        timeout=10.0
                    )
                    return response.status_code == 200

                elif provider == "bitbucket":
                    response = await client.get(
                        "https://api.bitbucket.org/2.0/user",
                        auth=(token.split(":")[0], token.split(":")[1]),
                        timeout=10.0
                    )
                    return response.status_code == 200

                return False

        except Exception as e:
            logger.warning("repo.token_validation_error",
                          provider=provider,
                          error=str(e))
            return False

    # ========== STEP 2: SMTP CONFIGURATION ==========

    async def complete_step_2_smtp(
        self,
        onboarding_id: UUID,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_from_email: str
    ) -> Dict[str, Any]:
        """
        GP configura SMTP para envio de convites
        Testa conexão
        """

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        try:
            # Testa SMTP
            is_valid = await self._test_smtp_connection(
                smtp_host, smtp_port, smtp_user, smtp_password
            )
            if not is_valid:
                raise ValueError("SMTP connection failed")

            # Armazena credenciais criptografadas
            progress.step_2_smtp_host = smtp_host
            progress.step_2_smtp_port = smtp_port
            progress.step_2_smtp_user = smtp_user
            progress.step_2_smtp_password_encrypted = encrypt_token(smtp_password)
            progress.step_2_smtp_from_email = smtp_from_email
            progress.step_2_test_sent = True
            progress.step_2_tested_at = datetime.now(timezone.utc)
            progress.step_2_status = StepStatus.COMPLETED
            progress.current_step = 3

            await self.db.commit()
            await self.db.refresh(progress)

            logger.info("onboarding.step_2_completed",
                       smtp_host=smtp_host,
                       smtp_user=smtp_user)

            return {
                "status": "completed",
                "test_sent": True,
                "next_step": 3
            }

        except Exception as e:
            progress.step_2_status = StepStatus.FAILED
            progress.step_2_error_msg = str(e)
            await self.db.commit()

            logger.error("onboarding.step_2_failed", error=str(e))
            raise

    async def _test_smtp_connection(
        self,
        host: str,
        port: int,
        user: str,
        password: str
    ) -> bool:
        """Testa conexão SMTP"""
        # TODO: Implementar teste com smtplib ou similar
        # Por agora, apenas valida que parâmetros não são vazios
        return all([host, port, user, password])

    # ========== STEP 3: TEAM DEFINITION ==========

    async def complete_step_3_team(
        self,
        onboarding_id: UUID,
        members: list[Dict[str, str]],
        smtp_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        GP define equipe e envia convites
        members = [{"email": "...", "role": "...", "responsibility": "..."}]
        """

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        project_id = progress.project_id

        try:
            invites_sent = 0

            for member in members:
                invite = TeamInvite(
                    project_id=project_id,
                    email=member["email"],
                    role=member["role"],
                    responsibility=member.get("responsibility", ""),
                    invite_token=secrets.token_urlsafe(32),
                    invite_sent_at=datetime.now(timezone.utc),
                    invite_expires_at=datetime.now(timezone.utc) + timedelta(days=7)
                )

                self.db.add(invite)

                # TODO: Enviar email via SMTP
                logger.info("team.invite_created",
                           email=member["email"],
                           role=member["role"])

                invites_sent += 1

            await self.db.commit()

            progress.step_3_team_members_count = invites_sent
            progress.step_3_invites_sent_at = datetime.now(timezone.utc)
            progress.step_3_status = StepStatus.COMPLETED
            progress.current_step = 4

            await self.db.commit()
            await self.db.refresh(progress)

            logger.info("onboarding.step_3_completed",
                       invites_sent=invites_sent)

            return {
                "status": "completed",
                "invites_sent": invites_sent,
                "next_step": 4
            }

        except Exception as e:
            progress.step_3_status = StepStatus.FAILED
            progress.step_3_error_msg = str(e)
            await self.db.commit()

            logger.error("onboarding.step_3_failed", error=str(e))
            raise

    # ========== STEP 4: ARCHITECTURE & LANGUAGE ==========

    async def complete_step_4_architecture(
        self,
        onboarding_id: UUID,
        language: str,
        architecture: str
    ) -> Dict[str, Any]:
        """
        GP seleciona linguagem e arquitetura
        Trigger N8N pipeline para buscar stacks
        """

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        try:
            # Dispara N8N webhook
            n8n_exec_id = await self._trigger_n8n_stack_discovery(
                language=language,
                architecture=architecture,
                onboarding_id=str(onboarding_id)
            )

            progress.step_4_language = language
            progress.step_4_architecture = architecture
            progress.step_4_n8n_execution_id = n8n_exec_id
            progress.step_4_n8n_status = "running"
            progress.step_4_status = StepStatus.IN_PROGRESS
            progress.current_step = 4  # Fica aqui até N8N terminar

            await self.db.commit()
            await self.db.refresh(progress)

            logger.info("onboarding.step_4_started",
                       language=language,
                       architecture=architecture,
                       n8n_exec_id=n8n_exec_id)

            return {
                "status": "in_progress",
                "n8n_execution_id": n8n_exec_id,
                "message": "Analisando stacks... Você será notificado quando estiver pronto",
                "polling_url": f"/api/v1/onboarding/{onboarding_id}/step-4/status"
            }

        except Exception as e:
            progress.step_4_status = StepStatus.FAILED
            progress.step_4_error_msg = str(e)
            await self.db.commit()

            logger.error("onboarding.step_4_failed", error=str(e))
            raise

    async def _trigger_n8n_stack_discovery(
        self,
        language: str,
        architecture: str,
        onboarding_id: str
    ) -> str:
        """Trigger N8N webhook para descobrir stacks"""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.N8N_WEBHOOK_URL}/gca/find-stack",
                    json={
                        "language": language,
                        "architecture": architecture,
                        "onboarding_id": onboarding_id
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                data = response.json()

                return data.get("execution_id") or str(data.get("id"))

        except Exception as e:
            logger.error("n8n.webhook_failed", error=str(e))
            raise

    async def get_step_4_status(
        self,
        onboarding_id: UUID
    ) -> Dict[str, Any]:
        """Poll N8N status e retorna resultado"""

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        if progress.step_4_n8n_status == "success":
            return {
                "status": "success",
                "recommendations": progress.step_4_n8n_result
            }
        elif progress.step_4_n8n_status == "running":
            return {
                "status": "running",
                "progress": 50  # TODO: Implementar polling real
            }
        else:
            return {
                "status": "failed",
                "error": progress.step_4_error_msg
            }

    # ========== STEP 5: STACK SELECTION ==========

    async def complete_step_5_stack_selection(
        self,
        onboarding_id: UUID,
        selected_stack: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        GP finaliza seleção de stack
        Cria OGC inicial
        Marca projeto como pronto
        """

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        try:
            # Armazena stack selecionado
            progress.step_5_selected_stack = selected_stack
            progress.step_5_status = StepStatus.COMPLETED
            progress.step_5_completed_at = datetime.now(timezone.utc)
            progress.current_step = 5
            progress.is_completed = True
            progress.completed_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(progress)

            # TODO: Criar OGC inicial no tenant schema
            # TODO: Criar pillar_configuration padrão no tenant

            logger.info("onboarding.step_5_completed",
                       selected_stack=selected_stack,
                       onboarding_id=str(onboarding_id))

            return {
                "status": "completed",
                "project_ready": True,
                "message": "Projeto pronto! Você pode começar a fazer upload de artefatos",
                "next_steps": [
                    "Configurar OGC customizado",
                    "Definir pesos dos pilares",
                    "Upload artefatos para avaliação"
                ]
            }

        except Exception as e:
            progress.step_5_status = StepStatus.FAILED
            await self.db.commit()

            logger.error("onboarding.step_5_failed", error=str(e))
            raise

    # ========== HELPERS ==========

    def _validate_slug(self, slug: str) -> bool:
        """Valida formato de slug"""
        import re
        return bool(re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', slug))

    async def get_available_steps(
        self,
        onboarding_id: UUID
    ) -> Dict[str, Any]:
        """Retorna quais steps estão disponíveis"""

        progress = await self.db.get(OnboardingProgress, onboarding_id)
        if not progress:
            raise ValueError("Onboarding not found")

        return {
            "step_1": {
                "available": True,
                "status": progress.step_1_status.value if progress.step_1_status else "pending",
                "blocked_by": None
            },
            "step_2": {
                "available": progress.step_1_status == StepStatus.COMPLETED,
                "status": progress.step_2_status.value if progress.step_2_status else "pending",
                "blocked_by": "step_1"
            },
            "step_3": {
                "available": progress.step_2_status == StepStatus.COMPLETED,
                "status": progress.step_3_status.value if progress.step_3_status else "pending",
                "blocked_by": "step_2"
            },
            "step_4": {
                "available": progress.step_3_status == StepStatus.COMPLETED,
                "status": progress.step_4_status.value if progress.step_4_status else "pending",
                "blocked_by": "step_3"
            },
            "step_5": {
                "available": progress.step_4_n8n_status == "success",
                "status": progress.step_5_status.value if progress.step_5_status else "pending",
                "blocked_by": "step_4"
            },
            "current_step": progress.current_step,
            "is_completed": progress.is_completed
        }
