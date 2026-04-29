"""
Technical Questionnaire Router — Questionários Dinâmicos com N perguntas

Endpoints para preencher, auto-salvar, validar e submeter questionários técnicos.
Schema das perguntas é flexível (definido em technical_questions_schema.py).
Respostas são armazenadas em JSONB {"Q1": valor, "Q2": [valores], ...}
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import structlog
from datetime import datetime

from app.db.database import get_db
from app.models.base import TechnicalQuestionnaire, Project, User
from app.middleware.auth import get_current_user_from_token
from app.data.technical_questions_schema import TECHNICAL_QUESTIONS_SCHEMA
from app.services.technical_questionnaire_service import (
    calculate_visibility,
    validate_questionnaire,
    calculate_progress,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["technical_questionnaire"])


# ─── Request/Response Models ───


class TechnicalQuestionnaireRequest(BaseModel):
    """Request: Save (draft) or submit technical questionnaire"""
    responses: Dict[str, Any]  # {"Q1": "valor", "Q3": ["opt1", "opt2"], ...}
    submit: bool = False  # Se True, muda status para "submitted"


class TechnicalQuestionnaireResponse(BaseModel):
    """Response: Technical questionnaire status"""
    id: str
    project_id: str
    status: str  # draft | submitted | validated
    progress_percent: int
    created_at: str
    updated_at: str
    submitted_at: Optional[str] = None
    submitted_by: Optional[str] = None


class TechnicalQuestionnaireDetailResponse(BaseModel):
    """Response: Full questionnaire with all answers"""
    id: str
    project_id: str
    status: str
    responses: Dict[str, Any]
    progress_percent: int
    visible_questions: List[str]  # Perguntas visíveis conforme respostas atuais
    created_at: str
    updated_at: str
    submitted_at: Optional[str] = None
    submitted_by: Optional[str] = None


class ValidationResponse(BaseModel):
    """Response: Validation result"""
    is_valid: bool
    progress_percent: int
    visible_questions: List[str]
    conflicts: List[str]  # Mensagens de erro de validação cruzada


# ─── Endpoints ───


@router.get("/{project_id}/technical-questionnaire", response_model=TechnicalQuestionnaireDetailResponse)
async def get_technical_questionnaire(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Retrieve technical questionnaire for a project.
    Returns full questionnaire with all answers and visibility state.
    If no questionnaire exists, creates empty draft.
    """
    # Verify project exists and user has access
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Get or create technical questionnaire (get first draft, or create new)
    stmt = select(TechnicalQuestionnaire).where(
        (TechnicalQuestionnaire.project_id == project_id) &
        (TechnicalQuestionnaire.status == "draft")
    )
    questionnaire = await db.scalar(stmt)

    if not questionnaire:
        # Create empty draft
        questionnaire = TechnicalQuestionnaire(
            project_id=project_id,
            status="draft",
            responses={},
            progress_percent=0,
        )
        db.add(questionnaire)
        await db.commit()
        await db.refresh(questionnaire)

    visible = calculate_visibility(questionnaire.responses, TECHNICAL_QUESTIONS_SCHEMA)
    progress = calculate_progress(questionnaire.responses, TECHNICAL_QUESTIONS_SCHEMA)

    logger.info(
        "technical_questionnaire_retrieved",
        project_id=str(project_id),
        status=questionnaire.status,
        progress=progress,
    )

    return TechnicalQuestionnaireDetailResponse(
        id=str(questionnaire.id),
        project_id=str(questionnaire.project_id),
        status=questionnaire.status,
        responses=questionnaire.responses,
        progress_percent=progress,
        visible_questions=visible,
        created_at=questionnaire.created_at.isoformat() if questionnaire.created_at else None,
        updated_at=questionnaire.updated_at.isoformat() if questionnaire.updated_at else None,
        submitted_at=questionnaire.submitted_at.isoformat() if questionnaire.submitted_at else None,
        submitted_by=str(questionnaire.submitted_by) if questionnaire.submitted_by else None,
    )


@router.patch("/{project_id}/technical-questionnaire", response_model=TechnicalQuestionnaireResponse)
async def save_technical_questionnaire(
    project_id: UUID,
    req: TechnicalQuestionnaireRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Auto-save (draft) or submit technical questionnaire.

    - If submit=False: save as draft (auto-save)
    - If submit=True: mark as submitted and set submitted_at/submitted_by
    - Progresso é calculado automaticamente baseado em perguntas visíveis

    Returns only summary (id, project_id, status, progress, timestamps).
    """
    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Get or create technical questionnaire
    stmt = select(TechnicalQuestionnaire).where(
        (TechnicalQuestionnaire.project_id == project_id) &
        (TechnicalQuestionnaire.status == "draft")
    )
    questionnaire = await db.scalar(stmt)

    if not questionnaire:
        questionnaire = TechnicalQuestionnaire(
            project_id=project_id,
            status="draft",
            responses={},
            progress_percent=0,
        )
        db.add(questionnaire)

    # Update responses from request
    questionnaire.responses = req.responses

    # Recalculate progress
    questionnaire.progress_percent = calculate_progress(req.responses, TECHNICAL_QUESTIONS_SCHEMA)

    # Handle submission
    if req.submit:
        questionnaire.status = "submitted"
        questionnaire.submitted_by = current_user.id
        questionnaire.submitted_at = datetime.utcnow()
        logger.info(
            "technical_questionnaire_submitted",
            project_id=str(project_id),
            user_id=str(current_user.id),
            progress=questionnaire.progress_percent,
        )
    else:
        questionnaire.status = "draft"
        logger.info(
            "technical_questionnaire_auto_saved",
            project_id=str(project_id),
            progress=questionnaire.progress_percent,
        )

    await db.commit()
    await db.refresh(questionnaire)

    # Após submissão bem-sucedida, dispara geração automática de OCG
    # (MVP Fase 1: user responde 15 perguntas → OCG gerado na mesma sessão)
    if req.submit:
        try:
            from app.tasks.pipeline import auto_generate_task
            # Prepara OCG inicial com dados do TechnicalQuestionnaire
            ocg_data = {
                "project_id": str(project_id),
                "source": "technical_questionnaire",
                "responses": req.responses,
                "created_by": str(current_user.id),
                "created_at": datetime.utcnow().isoformat(),
            }
            auto_generate_task.delay(str(project_id), ocg_data)
            logger.info(
                "technical_questionnaire_ocg_generation_queued",
                project_id=str(project_id),
                task_queued=True,
            )
        except Exception as exc:
            logger.warning(
                "technical_questionnaire_ocg_generation_failed_to_queue",
                project_id=str(project_id),
                error=str(exc),
                exc_info=True,
            )
            # Não bloqueia o retorno se o Celery falhar — questionário já foi salvo

    return TechnicalQuestionnaireResponse(
        id=str(questionnaire.id),
        project_id=str(questionnaire.project_id),
        status=questionnaire.status,
        progress_percent=questionnaire.progress_percent,
        created_at=questionnaire.created_at.isoformat() if questionnaire.created_at else None,
        updated_at=questionnaire.updated_at.isoformat() if questionnaire.updated_at else None,
        submitted_at=questionnaire.submitted_at.isoformat() if questionnaire.submitted_at else None,
        submitted_by=str(questionnaire.submitted_by) if questionnaire.submitted_by else None,
    )


@router.post("/{project_id}/technical-questionnaire/validate", response_model=ValidationResponse)
async def validate_technical_questionnaire(
    project_id: UUID,
    req: TechnicalQuestionnaireRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Validate technical questionnaire for logical conflicts.

    Checks:
    - Se Q3="Não" mas Q7-14 estão preenchidos → erro
    - Todas as perguntas visíveis obrigatórias preenchidas → progresso >= 80%

    Returns validation status, conflicts, progress, and visible questions.
    """
    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Validate
    validation_result = validate_questionnaire(req.responses, TECHNICAL_QUESTIONS_SCHEMA)
    visible = calculate_visibility(req.responses, TECHNICAL_QUESTIONS_SCHEMA)

    logger.info(
        "technical_questionnaire_validated",
        project_id=str(project_id),
        is_valid=validation_result["is_valid"],
        conflicts_count=len(validation_result["conflicts"]),
    )

    return ValidationResponse(
        is_valid=validation_result["is_valid"],
        progress_percent=validation_result["progress"],
        visible_questions=visible,
        conflicts=validation_result["conflicts"],
    )
