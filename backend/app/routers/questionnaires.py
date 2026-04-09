"""Questionnaires Router"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
from typing import Dict, Any, Optional
import structlog

from app.db.database import get_db
from app.services.questionnaire_service import QuestionnaireService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)

router = APIRouter()


# Request/Response Models
class SubmitQuestionnaireRequest(BaseModel):
    """Request: Submit technical questionnaire"""
    project_id: Optional[UUID] = None
    gp_email: str
    responses: Dict[str, Any]


class SubmitQuestionnaireResponse(BaseModel):
    """Response: Questionnaire submitted"""
    questionnaire_id: str
    project_id: Optional[str] = None
    status: str = "pending"
    submission_date: str
    message: str = "Questionário submetido para análise. Você receberá um email com o resultado"


class QuestionnaireStatusResponse(BaseModel):
    """Response: Questionnaire status with n8n analysis"""
    questionnaire_id: str
    status: str  # Pendente, Incompleto, OK
    submission_date: str
    observations: Optional[str] = None
    restrictions: Optional[str] = None
    highlighted_fields: list = []
    internal: Optional[Dict[str, Any]] = None  # Only for admin


@router.post("/", response_model=SubmitQuestionnaireResponse)
async def submit_questionnaire(
    req: SubmitQuestionnaireRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit technical questionnaire for n8n analysis.
    Triggers n8n webhook for intelligent validation.
    """
    success, questionnaire_id, error = await QuestionnaireService.submit_questionnaire(
        db=db,
        project_id=req.project_id,
        gp_email=req.gp_email,
        responses=req.responses,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    from datetime import datetime, timezone
    return SubmitQuestionnaireResponse(
        questionnaire_id=questionnaire_id,
        project_id=str(req.project_id),
        status="pending",
        submission_date=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{questionnaire_id}/status", response_model=QuestionnaireStatusResponse)
async def get_questionnaire_status(
    questionnaire_id: str,
    current_user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Get questionnaire status with n8n analysis results.
    Admin sees: adherence_score + gaps
    GP sees: only status + observations + restrictions
    """
    # Determine if user is admin (for now, simplified)
    is_admin = False  # Would check user.is_admin in real implementation

    status = await QuestionnaireService.get_questionnaire_status(
        db=db,
        questionnaire_id=questionnaire_id,
        is_admin=is_admin,
    )

    return QuestionnaireStatusResponse(**status)


# ============================================================================
# External Project Request (link único com token)
# ============================================================================

class RequestProjectAccessRequest(BaseModel):
    email: str
    full_name: str
    role: str = "gp"


class RequestProjectAccessResponse(BaseModel):
    success: bool
    message: str
    token: str | None = None
    expires_at: str | None = None


@router.post("/request-access", response_model=RequestProjectAccessResponse)
async def request_project_access(
    req: RequestProjectAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Gera um token único para acesso ao questionário e envia por email.
    O token é vinculado ao email e não pode ser reutilizado.
    Se já existir um token ativo (não expirado, não usado) para o email,
    reutiliza o existente em vez de criar um novo.
    """
    import secrets
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select

    from app.models.base import InvitationToken
    from app.core.security import hash_password
    from uuid import uuid4

    now = datetime.now(timezone.utc)

    # Verificar se já existe token ativo para este email (role=gp, não usado, não expirado)
    existing = await db.execute(
        select(InvitationToken).where(
            InvitationToken.email == req.email,
            InvitationToken.role == req.role,
            InvitationToken.is_used == False,
            InvitationToken.expires_at > now,
        ).order_by(InvitationToken.created_at.desc()).limit(1)
    )
    active_token = existing.scalar_one_or_none()

    if active_token:
        # Token ativo já existe — reutilizar sem enviar novo email
        logger.info(
            "questionnaire.existing_token_reused",
            email=req.email,
            token=active_token.token[:10],
            expires_at=active_token.expires_at.isoformat(),
        )
        return RequestProjectAccessResponse(
            success=True,
            message=f"Você já possui um link ativo enviado para {req.email}. Verifique sua caixa de entrada.",
            token=active_token.token,
            expires_at=active_token.expires_at.isoformat(),
        )

    # Gerar token único
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=5)

    invitation = InvitationToken(
        id=uuid4(),
        email=req.email,
        full_name=req.full_name,
        role=req.role,
        token=token,
        temporary_password_hash=hash_password(token[:8]),  # placeholder
        expires_at=expires_at,
    )
    db.add(invitation)
    await db.commit()

    # Enviar email com link único
    link = f"https://gca.code-auditor.com.br/novo-projeto?token={token}&email={req.email}"

    try:
        from app.services.email_service import EmailService
        success, error = EmailService.send_questionnaire_link_email(
            to_email=req.email,
            full_name=req.full_name,
            questionnaire_link=link,
            expires_at=expires_at,
        )
        if not success:
            logger.warning("questionnaire.email_failed", email=req.email, error=error)
    except Exception as e:
        logger.warning("questionnaire.email_method_missing", error=str(e))

    logger.info("questionnaire.access_requested", email=req.email, token=token[:10])

    return RequestProjectAccessResponse(
        success=True,
        message=f"Link do questionário enviado para {req.email}. Válido por 5 dias.",
        token=token,
        expires_at=expires_at.isoformat(),
    )


@router.post("/draft")
async def save_draft(
    req: dict,
    db: AsyncSession = Depends(get_db),
):
    """Salva rascunho do questionário."""
    import json
    from datetime import datetime, timezone

    questionnaire = Questionnaire(
        project_id=None,
        gp_email=req.get("gp_email", ""),
        responses=json.dumps(req.get("responses", {})),
        status="draft",
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(questionnaire)
    await db.commit()

    return {"success": True, "message": "Rascunho salvo"}


@router.post("/archive-expired")
async def archive_expired_questionnaires(
    db: AsyncSession = Depends(get_db),
):
    """
    Arquiva tokens de questionário expirados como 'timeout' para auditoria.
    Chamado pelo admin ou por job automático.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select, update
    from app.models.base import InvitationToken

    now = datetime.now(timezone.utc)

    # Buscar tokens de questionário (role=gp) que expiraram e não foram usados
    expired = await db.execute(
        select(InvitationToken).where(
            InvitationToken.role.in_(["gp", "admin_gp", "tech_lead", "stakeholder"]),
            InvitationToken.is_used == False,
            InvitationToken.expires_at <= now,
        )
    )
    expired_tokens = expired.scalars().all()

    archived_count = 0
    for token in expired_tokens:
        token.is_used = True  # Marcar como usado para não reaparecer
        # Usar o campo validation_attempts para indicar timeout
        token.validation_attempts = -1  # Convenção: -1 = timeout
        archived_count += 1

        logger.info(
            "questionnaire.archived_timeout",
            email=token.email,
            token=token.token[:10],
            expired_at=token.expires_at.isoformat(),
        )

    if archived_count > 0:
        await db.commit()

    return {
        "archived": archived_count,
        "message": f"{archived_count} questionário(s) arquivado(s) por timeout.",
    }
