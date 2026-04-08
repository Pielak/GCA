"""
Onboarding Router
Rotas para os 5 passos de onboarding de novos projetos
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
import structlog

from app.db.database import get_db
from app.services.onboarding_service import OnboardingService
from app.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["onboarding"])


# ========== STEP 1: REPOSITORY SETUP ==========

class RepositorySetupRequest(BaseModel):
    """Request model for Step 1"""
    provider: str  # github, gitlab, bitbucket
    repo_url: str
    access_token: str


@router.post("/{onboarding_id}/step-1/repository")
async def setup_repository(
    onboarding_id: UUID,
    req: RepositorySetupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    GP configura repositório
    Valida token e acesso ao repo
    """
    try:
        service = OnboardingService(db)
        result = await service.complete_step_1_repository(
            onboarding_id=onboarding_id,
            provider=req.provider,
            repo_url=req.repo_url,
            access_token=req.access_token
        )
        return result

    except ValueError as e:
        logger.warning("onboarding.step_1_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("onboarding.step_1_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao configurar repositório"
        )


# ========== STEP 2: SMTP CONFIGURATION ==========

class SMTPSetupRequest(BaseModel):
    """Request model for Step 2"""
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str


@router.post("/{onboarding_id}/step-2/smtp")
async def setup_smtp(
    onboarding_id: UUID,
    req: SMTPSetupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    GP configura SMTP para envio de convites
    Testa conexão SMTP
    """
    try:
        service = OnboardingService(db)
        result = await service.complete_step_2_smtp(
            onboarding_id=onboarding_id,
            smtp_host=req.smtp_host,
            smtp_port=req.smtp_port,
            smtp_user=req.smtp_user,
            smtp_password=req.smtp_password,
            smtp_from_email=req.smtp_from_email
        )
        return result

    except ValueError as e:
        logger.warning("onboarding.step_2_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("onboarding.step_2_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao configurar SMTP"
        )


# ========== STEP 3: TEAM DEFINITION ==========

class TeamMemberRequest(BaseModel):
    """Model para membro da equipe"""
    email: str
    role: str  # tech_lead, dev, qa, compliance, viewer
    responsibility: str


class TeamSetupRequest(BaseModel):
    """Request model for Step 3"""
    members: list[TeamMemberRequest]


@router.post("/{onboarding_id}/step-3/team")
async def setup_team(
    onboarding_id: UUID,
    req: TeamSetupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    GP define equipe e envia convites
    """
    try:
        service = OnboardingService(db)

        # Converte request para dict
        members = [m.model_dump() for m in req.members]

        # TODO: Implementar envio de email via SMTP
        smtp_config = {}  # Será carregado do DB na implementação real

        result = await service.complete_step_3_team(
            onboarding_id=onboarding_id,
            members=members,
            smtp_config=smtp_config
        )
        return result

    except ValueError as e:
        logger.warning("onboarding.step_3_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("onboarding.step_3_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao configurar equipe"
        )


# ========== STEP 4: ARCHITECTURE & LANGUAGE ==========

class ArchitectureSetupRequest(BaseModel):
    """Request model for Step 4"""
    language: str  # python, java, nodejs, go, rust, php, csharp
    architecture: str  # monolith, microservices, serverless


@router.post("/{onboarding_id}/step-4/architecture")
async def setup_architecture(
    onboarding_id: UUID,
    req: ArchitectureSetupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    GP seleciona linguagem e arquitetura
    Dispara N8N pipeline para buscar stacks
    """
    try:
        service = OnboardingService(db)
        result = await service.complete_step_4_architecture(
            onboarding_id=onboarding_id,
            language=req.language,
            architecture=req.architecture
        )
        return result

    except ValueError as e:
        logger.warning("onboarding.step_4_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("onboarding.step_4_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao configurar arquitetura"
        )


@router.get("/{onboarding_id}/step-4/status")
async def get_architecture_status(
    onboarding_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Poll N8N status durante execução do Piloter
    """
    try:
        service = OnboardingService(db)
        status_result = await service.get_step_4_status(onboarding_id)
        return status_result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding não encontrado"
        )
    except Exception as e:
        logger.error("onboarding.step_4_status_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao verificar status"
        )


# ========== STEP 5: STACK SELECTION ==========

class StackSelectionRequest(BaseModel):
    """Request model for Step 5"""
    selected_stack: dict  # { "backend": "FastAPI", "database": "PostgreSQL", ... }


@router.post("/{onboarding_id}/step-5/finalize")
async def finalize_stack_selection(
    onboarding_id: UUID,
    req: StackSelectionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    GP finaliza seleção de stack
    Cria OGC inicial e marca como pronto
    """
    try:
        service = OnboardingService(db)
        result = await service.complete_step_5_stack_selection(
            onboarding_id=onboarding_id,
            selected_stack=req.selected_stack
        )
        return result

    except ValueError as e:
        logger.warning("onboarding.step_5_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("onboarding.step_5_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao finalizar seleção de stack"
        )


# ========== STATUS & PROGRESS ==========

@router.get("/{onboarding_id}/status")
async def get_onboarding_status(
    onboarding_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current onboarding progress and available next steps
    """
    try:
        service = OnboardingService(db)
        steps = await service.get_available_steps(onboarding_id)
        return steps

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding não encontrado"
        )
    except Exception as e:
        logger.error("onboarding.status_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter status"
        )
