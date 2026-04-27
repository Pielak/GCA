"""
Initial Questionnaire Router — 20 essential questions

Endpoints for filling, auto-saving, and submitting the initial questionnaire.
Each project has exactly 1 initial questionnaire (unique constraint on project_id).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Dict, Any
import structlog
from datetime import datetime

from app.db.database import get_db
from app.models.base import InitialQuestionnaire, Project, User
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["initial_questionnaire"])


# ─── Request/Response Models ───

class InitialQuestionnaireRequest(BaseModel):
    """Request: Save (draft) or submit initial questionnaire"""
    # Seção A: Contexto
    q1_name: Optional[str] = None
    q1_objective: Optional[str] = None
    q2_type: Optional[str] = None  # novo_sistema | refactor | feature_nova | manutencao
    q3_users: Optional[str] = None
    q3_volume: Optional[int] = None
    q4_months: Optional[int] = None
    q4_target_date: Optional[str] = None  # YYYY-MM-DD

    # Seção B: Requisitos Funcionais
    q5_flows: Optional[str] = None
    q6_integrations: Optional[list] = None  # ["sms", "google_calendar", ...]
    q6_integrations_detail: Optional[str] = None
    q7_frequency: Optional[str] = None
    q8_reports: Optional[str] = None
    q9_rules: Optional[str] = None

    # Seção C: RNFs
    q10_performance: Optional[str] = None
    q11_uptime: Optional[str] = None
    q12_sensitive_data: Optional[list] = None  # ["dados_pessoais", "dados_saude", ...]
    q13_scalability: Optional[str] = None
    q14_compliance: Optional[list] = None  # ["lgpd", "gdpr", ...]
    q15_longevity: Optional[str] = None

    # Seção D: Técnico
    q16_stack: Optional[str] = None
    q17_existing_infra: Optional[str] = None
    q18_constraints: Optional[str] = None

    # Seção E: GCA Vision
    q19_gca_expectations: Optional[list] = None  # ["codigo_completo", "documentacao", ...]
    q20_risks: Optional[str] = None

    # Attachments: {"q1": ["url1", "url2"], ...}
    question_images: Optional[Dict[str, list]] = None

    # Flag: se True, muda status para "submitted"; senão fica "draft"
    submit: bool = False


class InitialQuestionnaireResponse(BaseModel):
    """Response: Initial questionnaire status"""
    id: str
    project_id: str
    status: str  # draft | submitted | validated
    created_at: str
    updated_at: str
    submitted_at: Optional[str] = None
    submitted_by: Optional[str] = None


class InitialQuestionnaireDetailResponse(BaseModel):
    """Response: Full questionnaire with all answers"""
    id: str
    project_id: str
    status: str

    # Seção A
    q1_name: Optional[str] = None
    q1_objective: Optional[str] = None
    q2_type: Optional[str] = None
    q3_users: Optional[str] = None
    q3_volume: Optional[int] = None
    q4_months: Optional[int] = None
    q4_target_date: Optional[str] = None

    # Seção B
    q5_flows: Optional[str] = None
    q6_integrations: Optional[list] = None
    q6_integrations_detail: Optional[str] = None
    q7_frequency: Optional[str] = None
    q8_reports: Optional[str] = None
    q9_rules: Optional[str] = None

    # Seção C
    q10_performance: Optional[str] = None
    q11_uptime: Optional[str] = None
    q12_sensitive_data: Optional[list] = None
    q13_scalability: Optional[str] = None
    q14_compliance: Optional[list] = None
    q15_longevity: Optional[str] = None

    # Seção D
    q16_stack: Optional[str] = None
    q17_existing_infra: Optional[str] = None
    q18_constraints: Optional[str] = None

    # Seção E
    q19_gca_expectations: Optional[list] = None
    q20_risks: Optional[str] = None

    question_images: Optional[Dict[str, list]] = None
    created_at: str
    updated_at: str
    submitted_at: Optional[str] = None
    submitted_by: Optional[str] = None


# ─── Endpoints ───

@router.get("/{project_id}/initial-questionnaire", response_model=InitialQuestionnaireDetailResponse)
async def get_initial_questionnaire(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Retrieve initial questionnaire for a project.
    Returns full questionnaire with all answers and status.
    If no questionnaire exists, creates empty draft.
    """
    # Verify project exists and user has access
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Get or create initial questionnaire
    stmt = select(InitialQuestionnaire).where(InitialQuestionnaire.project_id == project_id)
    questionnaire = await db.scalar(stmt)

    if not questionnaire:
        # Create empty draft
        questionnaire = InitialQuestionnaire(
            project_id=project_id,
            status="draft"
        )
        db.add(questionnaire)
        await db.commit()
        await db.refresh(questionnaire)

    logger.info("initial_questionnaire_retrieved", project_id=str(project_id), status=questionnaire.status)

    return InitialQuestionnaireDetailResponse(
        id=str(questionnaire.id),
        project_id=str(questionnaire.project_id),
        status=questionnaire.status,
        q1_name=questionnaire.q1_name,
        q1_objective=questionnaire.q1_objective,
        q2_type=questionnaire.q2_type,
        q3_users=questionnaire.q3_users,
        q3_volume=questionnaire.q3_volume,
        q4_months=questionnaire.q4_months,
        q4_target_date=questionnaire.q4_target_date,
        q5_flows=questionnaire.q5_flows,
        q6_integrations=questionnaire.q6_integrations,
        q6_integrations_detail=questionnaire.q6_integrations_detail,
        q7_frequency=questionnaire.q7_frequency,
        q8_reports=questionnaire.q8_reports,
        q9_rules=questionnaire.q9_rules,
        q10_performance=questionnaire.q10_performance,
        q11_uptime=questionnaire.q11_uptime,
        q12_sensitive_data=questionnaire.q12_sensitive_data,
        q13_scalability=questionnaire.q13_scalability,
        q14_compliance=questionnaire.q14_compliance,
        q15_longevity=questionnaire.q15_longevity,
        q16_stack=questionnaire.q16_stack,
        q17_existing_infra=questionnaire.q17_existing_infra,
        q18_constraints=questionnaire.q18_constraints,
        q19_gca_expectations=questionnaire.q19_gca_expectations,
        q20_risks=questionnaire.q20_risks,
        question_images=questionnaire.question_images,
        created_at=questionnaire.created_at.isoformat() if questionnaire.created_at else None,
        updated_at=questionnaire.updated_at.isoformat() if questionnaire.updated_at else None,
        submitted_at=questionnaire.submitted_at.isoformat() if questionnaire.submitted_at else None,
        submitted_by=str(questionnaire.submitted_by) if questionnaire.submitted_by else None,
    )


@router.patch("/{project_id}/initial-questionnaire", response_model=InitialQuestionnaireResponse)
async def save_initial_questionnaire(
    project_id: UUID,
    req: InitialQuestionnaireRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Auto-save (draft) or submit initial questionnaire.

    - If submit=False: save as draft (auto-save)
    - If submit=True: mark as submitted and set submitted_at/submitted_by

    Returns only summary (id, project_id, status, timestamps).
    """
    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Get or create initial questionnaire
    stmt = select(InitialQuestionnaire).where(InitialQuestionnaire.project_id == project_id)
    questionnaire = await db.scalar(stmt)

    if not questionnaire:
        questionnaire = InitialQuestionnaire(project_id=project_id, status="draft")
        db.add(questionnaire)

    # Update all fields from request (only non-None values)
    if req.q1_name is not None:
        questionnaire.q1_name = req.q1_name
    if req.q1_objective is not None:
        questionnaire.q1_objective = req.q1_objective
    if req.q2_type is not None:
        questionnaire.q2_type = req.q2_type
    if req.q3_users is not None:
        questionnaire.q3_users = req.q3_users
    if req.q3_volume is not None:
        questionnaire.q3_volume = req.q3_volume
    if req.q4_months is not None:
        questionnaire.q4_months = req.q4_months
    if req.q4_target_date is not None:
        questionnaire.q4_target_date = req.q4_target_date

    if req.q5_flows is not None:
        questionnaire.q5_flows = req.q5_flows
    if req.q6_integrations is not None:
        questionnaire.q6_integrations = req.q6_integrations
    if req.q6_integrations_detail is not None:
        questionnaire.q6_integrations_detail = req.q6_integrations_detail
    if req.q7_frequency is not None:
        questionnaire.q7_frequency = req.q7_frequency
    if req.q8_reports is not None:
        questionnaire.q8_reports = req.q8_reports
    if req.q9_rules is not None:
        questionnaire.q9_rules = req.q9_rules

    if req.q10_performance is not None:
        questionnaire.q10_performance = req.q10_performance
    if req.q11_uptime is not None:
        questionnaire.q11_uptime = req.q11_uptime
    if req.q12_sensitive_data is not None:
        questionnaire.q12_sensitive_data = req.q12_sensitive_data
    if req.q13_scalability is not None:
        questionnaire.q13_scalability = req.q13_scalability
    if req.q14_compliance is not None:
        questionnaire.q14_compliance = req.q14_compliance
    if req.q15_longevity is not None:
        questionnaire.q15_longevity = req.q15_longevity

    if req.q16_stack is not None:
        questionnaire.q16_stack = req.q16_stack
    if req.q17_existing_infra is not None:
        questionnaire.q17_existing_infra = req.q17_existing_infra
    if req.q18_constraints is not None:
        questionnaire.q18_constraints = req.q18_constraints

    if req.q19_gca_expectations is not None:
        questionnaire.q19_gca_expectations = req.q19_gca_expectations
    if req.q20_risks is not None:
        questionnaire.q20_risks = req.q20_risks

    if req.question_images is not None:
        questionnaire.question_images = req.question_images

    # Handle submission
    if req.submit:
        questionnaire.status = "submitted"
        questionnaire.submitted_by = current_user.id
        questionnaire.submitted_at = datetime.utcnow()
        logger.info("initial_questionnaire_submitted", project_id=str(project_id), user_id=str(current_user.id))
    else:
        questionnaire.status = "draft"
        logger.info("initial_questionnaire_auto_saved", project_id=str(project_id))

    await db.commit()
    await db.refresh(questionnaire)

    return InitialQuestionnaireResponse(
        id=str(questionnaire.id),
        project_id=str(questionnaire.project_id),
        status=questionnaire.status,
        created_at=questionnaire.created_at.isoformat() if questionnaire.created_at else None,
        updated_at=questionnaire.updated_at.isoformat() if questionnaire.updated_at else None,
        submitted_at=questionnaire.submitted_at.isoformat() if questionnaire.submitted_at else None,
        submitted_by=str(questionnaire.submitted_by) if questionnaire.submitted_by else None,
    )
