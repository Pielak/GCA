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
        questionnaire.submitted_by = current_user
        questionnaire.submitted_at = datetime.utcnow()
        logger.info(
            "technical_questionnaire_submitted",
            project_id=str(project_id),
            user_id=str(current_user),
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

    # Após submissão bem-sucedida, dispara avaliação paralela das Personas
    # (MVP B: 7 personas avaliam em paralelo com IA do projeto)
    if req.submit:
        try:
            from app.tasks.questionnaire import evaluate_persona_task
            from celery import group

            # Personas a avaliar
            personas = ["gp", "arquiteto", "dba", "dev_sr", "qa"]

            # Preparar grupo de tasks paralelas
            persona_tasks = group(
                evaluate_persona_task.s(
                    persona_name=persona,
                    technical_questionnaire_id=str(questionnaire.id),
                    project_id=str(project_id),
                    responses=req.responses,
                    extracted_concepts=[],  # TODO: extrair do documento ingerido
                    document_domain="software",
                )
                for persona in personas
            )

            # Disparar em paralelo
            persona_tasks.apply_async()

            logger.info(
                "technical_questionnaire_personas_evaluation_queued",
                project_id=str(project_id),
                questionnaire_id=str(questionnaire.id),
                personas_count=len(personas),
                task_queued=True,
            )
        except Exception as exc:
            logger.warning(
                "technical_questionnaire_personas_evaluation_failed_to_queue",
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


# ============================================================================
# MVP B — Personas Board Endpoints
# ============================================================================

class PersonaResponseModel(BaseModel):
    """Resposta de uma Persona no board"""
    id: str
    persona_name: str
    status: str  # pending, evaluating, completed, error
    decision: Optional[str] = None
    ocg_delta: Dict[str, Any] = {}
    followup_questions: Optional[List[Dict]] = None
    severity: str = "info"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    ai_provider_used: Optional[str] = None
    ai_model_used: Optional[str] = None


class PersonasBoardResponse(BaseModel):
    """Board de respostas das Personas"""
    questionnaire_id: str
    personas: List[PersonaResponseModel]
    all_completed: bool
    consolidated_ocg_delta: Dict[str, Any] = {}


class DiscrepancyModel(BaseModel):
    """Discrepância entre personas"""
    id: str
    field_path: str
    conflicting_personas: List[str]
    conflicting_values: Dict[str, Any]
    severity: str
    category: Optional[str] = None
    status: str
    context: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


class DiscrepanciesResponse(BaseModel):
    """Board de discrepâncias detectadas"""
    questionnaire_id: str
    discrepancies: List[DiscrepancyModel]
    unresolved_count: int
    all_resolved: bool


@router.get("/{project_id}/technical-questionnaire/{questionnaire_id}/personas-board", response_model=PersonasBoardResponse)
async def get_personas_board(
    project_id: UUID,
    questionnaire_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Retrieve real-time board of persona responses for technical questionnaire.

    Shows status of each persona evaluation (pending, evaluating, completed, error)
    and allows team to track progress.
    """
    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Verify questionnaire exists
    from app.models.base import TechnicalQuestionnaire, PersonaResponse
    stmt = select(TechnicalQuestionnaire).where(
        (TechnicalQuestionnaire.id == questionnaire_id) &
        (TechnicalQuestionnaire.project_id == project_id)
    )
    questionnaire = await db.scalar(stmt)
    if not questionnaire:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionário não encontrado")

    # Fetch all persona responses
    stmt = select(PersonaResponse).where(
        PersonaResponse.technical_questionnaire_id == questionnaire_id
    ).order_by(PersonaResponse.persona_name)
    persona_responses = await db.scalars(stmt)

    # Build response
    personas = []
    consolidated_delta = {}
    for resp in persona_responses:
        personas.append(
            PersonaResponseModel(
                id=str(resp.id),
                persona_name=resp.persona_name,
                status=resp.status,
                decision=resp.decision,
                ocg_delta=resp.ocg_delta,
                followup_questions=resp.followup_questions,
                severity=resp.severity,
                started_at=resp.started_at.isoformat() if resp.started_at else None,
                completed_at=resp.completed_at.isoformat() if resp.completed_at else None,
                error_message=resp.error_message,
                ai_provider_used=resp.ai_provider_used,
                ai_model_used=resp.ai_model_used,
            )
        )

        # Merge OCG deltas if persona approved
        if resp.status == "completed" and resp.ocg_delta:
            for key, value in resp.ocg_delta.items():
                if key not in consolidated_delta:
                    consolidated_delta[key] = value

    all_completed = all(p.status == "completed" for p in personas) if personas else False

    logger.info(
        "personas_board_retrieved",
        project_id=str(project_id),
        questionnaire_id=str(questionnaire_id),
        personas_count=len(personas),
        all_completed=all_completed,
    )

    return PersonasBoardResponse(
        questionnaire_id=str(questionnaire_id),
        personas=personas,
        all_completed=all_completed,
        consolidated_ocg_delta=consolidated_delta,
    )


# ============================================================================
# MVP C — Discrepancy Detection & Resolution
# ============================================================================

@router.post("/{project_id}/technical-questionnaire/{questionnaire_id}/detect-discrepancies")
async def detect_discrepancies(
    project_id: UUID,
    questionnaire_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Detect discrepancies between persona evaluations.

    Runs after all personas complete evaluation.
    Finds fields where personas disagree and creates Discrepancy records.
    """
    from app.models.base import PersonaResponse, Discrepancy
    from app.services.discrepancy_detector import detect_persona_discrepancies

    # Verify project and questionnaire
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    stmt = select(TechnicalQuestionnaire).where(
        (TechnicalQuestionnaire.id == questionnaire_id) &
        (TechnicalQuestionnaire.project_id == project_id)
    )
    questionnaire = await db.scalar(stmt)
    if not questionnaire:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionário não encontrado")

    # Fetch all persona responses
    stmt = select(PersonaResponse).where(
        PersonaResponse.technical_questionnaire_id == questionnaire_id
    )
    persona_responses_list = await db.scalars(stmt)

    # Build persona_responses dict for detector
    persona_responses = {}
    for resp in persona_responses_list:
        persona_responses[resp.persona_name] = {
            "ocg_delta": resp.ocg_delta,
            "status": resp.status,
            "decision": resp.decision,
        }

    # Detect discrepancies
    discrepancies_found = detect_persona_discrepancies(persona_responses)

    # Save to database
    for disc in discrepancies_found:
        existing = await db.scalar(
            select(Discrepancy).where(
                (Discrepancy.technical_questionnaire_id == questionnaire_id) &
                (Discrepancy.field_path == disc.field_path)
            )
        )

        if not existing:
            discrepancy = Discrepancy(
                project_id=project_id,
                technical_questionnaire_id=questionnaire_id,
                field_path=disc.field_path,
                conflicting_personas=disc.conflicting_personas,
                conflicting_values=disc.conflicting_values,
                severity=disc.severity,
                category=disc.category,
                status="unresolved",
                context=f"Conflito entre {', '.join(disc.conflicting_personas)}",
                detected_at=datetime.utcnow(),
            )
            db.add(discrepancy)

    await db.commit()

    logger.info(
        "discrepancies_detected_and_saved",
        project_id=str(project_id),
        questionnaire_id=str(questionnaire_id),
        discrepancy_count=len(discrepancies_found),
    )

    return {
        "status": "ok",
        "discrepancies_found": len(discrepancies_found),
        "discrepancies": [
            {
                "field_path": d.field_path,
                "conflicting_personas": d.conflicting_personas,
                "severity": d.severity,
            }
            for d in discrepancies_found
        ],
    }


@router.get("/{project_id}/technical-questionnaire/{questionnaire_id}/discrepancies-board", response_model=DiscrepanciesResponse)
async def get_discrepancies_board(
    project_id: UUID,
    questionnaire_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Retrieve discrepancies board for technical questionnaire.

    Shows all detected discrepancies and their resolution status.
    """
    from app.models.base import Discrepancy

    # Verify project and questionnaire
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    stmt = select(TechnicalQuestionnaire).where(
        (TechnicalQuestionnaire.id == questionnaire_id) &
        (TechnicalQuestionnaire.project_id == project_id)
    )
    questionnaire = await db.scalar(stmt)
    if not questionnaire:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionário não encontrado")

    # Fetch all discrepancies
    stmt = select(Discrepancy).where(
        Discrepancy.technical_questionnaire_id == questionnaire_id
    ).order_by(Discrepancy.severity.desc(), Discrepancy.field_path)
    discrepancies_list = await db.scalars(stmt)

    # Build response
    discrepancies = []
    unresolved_count = 0

    for disc in discrepancies_list:
        discrepancies.append(
            DiscrepancyModel(
                id=str(disc.id),
                field_path=disc.field_path,
                conflicting_personas=disc.conflicting_personas,
                conflicting_values=disc.conflicting_values,
                severity=disc.severity,
                category=disc.category,
                status=disc.status,
                context=disc.context,
                created_at=disc.created_at.isoformat() if disc.created_at else None,
                resolved_at=disc.resolved_at.isoformat() if disc.resolved_at else None,
            )
        )
        if disc.status == "unresolved":
            unresolved_count += 1

    all_resolved = unresolved_count == 0

    logger.info(
        "discrepancies_board_retrieved",
        project_id=str(project_id),
        questionnaire_id=str(questionnaire_id),
        discrepancy_count=len(discrepancies),
        unresolved_count=unresolved_count,
    )

    return DiscrepanciesResponse(
        questionnaire_id=str(questionnaire_id),
        discrepancies=discrepancies,
        unresolved_count=unresolved_count,
        all_resolved=all_resolved,
    )


class ResolveDiscrepancyRequest(BaseModel):
    """Request to resolve a discrepancy"""
    resolved_value: str  # Valor escolhido (pode ser um dos conflitantes ou novo)
    resolution_type: str  # "vote", "override", "arbitration", "compromise"
    vote_details: Optional[Dict[str, Any]] = None  # Se votação
    justification: Optional[str] = None


@router.post("/{project_id}/technical-questionnaire/{questionnaire_id}/discrepancies/{discrepancy_id}/resolve")
async def resolve_discrepancy(
    project_id: UUID,
    questionnaire_id: UUID,
    discrepancy_id: UUID,
    req: ResolveDiscrepancyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Resolve a discrepancy (vote, override, arbitration).
    """
    from app.models.base import Discrepancy, Resolution

    # Verify resources exist
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    stmt = select(Discrepancy).where(
        (Discrepancy.id == discrepancy_id) &
        (Discrepancy.technical_questionnaire_id == questionnaire_id)
    )
    discrepancy = await db.scalar(stmt)
    if not discrepancy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discrepância não encontrada")

    # Create resolution record
    resolution = Resolution(
        discrepancy_id=discrepancy_id,
        project_id=project_id,
        resolved_value=req.resolved_value,
        resolution_type=req.resolution_type,
        vote_details=req.vote_details or {},
        resolved_by=current_user.id,
        justification=req.justification,
    )
    db.add(resolution)

    # Update discrepancy status
    discrepancy.status = "resolved"
    discrepancy.resolved_at = datetime.utcnow()
    discrepancy.resolved_by = current_user.id
    discrepancy.resolution_notes = f"Resolvido por votação" if req.resolution_type == "vote" else f"Resolvido por {req.resolution_type}"

    await db.commit()

    logger.info(
        "discrepancy_resolved",
        project_id=str(project_id),
        discrepancy_id=str(discrepancy_id),
        resolution_type=req.resolution_type,
        resolved_by=str(current_user.id),
    )

    return {
        "status": "ok",
        "discrepancy_id": str(discrepancy_id),
        "resolved_value": req.resolved_value,
        "resolution_type": req.resolution_type,
    }
