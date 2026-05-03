"""
Technical Questionnaire Router — Questionários Dinâmicos com N perguntas

Endpoints para preencher, auto-salvar, validar e submeter questionários técnicos.
Schema das perguntas é flexível (definido em technical_questions_schema.py).
Respostas são armazenadas em JSONB {"Q1": valor, "Q2": [valores], ...}
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import structlog
from datetime import datetime

from app.db.database import get_db
from app.models.base import TechnicalQuestionnaire, Questionnaire, Project, User
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
    """Response: Validation result. MVP 35 expandiu com warnings/info/persisted."""
    is_valid: bool
    progress_percent: int
    visible_questions: List[str]
    conflicts: List[str]  # blocker — schema legacy + RulesEvaluator severity=error
    # MVP 35 — campos canônicos novos (com defaults para retrocompat)
    warnings: List[str] = []  # severity=warning (UI alerta amarelo, não bloqueia)
    info: List[str] = []  # severity=info (UI alerta neutro)
    rules_evaluated: int = 0  # cobertura
    evaluated_at_ms: int = 0  # latência camada 1
    persisted: bool = False  # True se status='validated' foi gravado


# ─── Endpoints ───


@router.get("/technical-questionnaire/rules")
async def get_validation_rules(
    current_user: User = Depends(get_current_user_from_token),
):
    """MVP 35 Fase 35.1 — Catálogo de regras de validação canônicas (single source of truth).

    Frontend carrega 1× no mount + cache local. Elimina necessidade de
    bundle TS espelhado (Arq-S1). Não filtra por projeto — regras são globais.
    """
    from app.services.questionnaire_validation.rules_catalog import RULES_CATALOG
    return {
        "rules": RULES_CATALOG,
        "count": len(RULES_CATALOG),
        "themes": ["nosql_acid", "stack", "fe_be", "compliance", "infra"],
    }


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

    # Get or create technical questionnaire (prefer submitted, fallback to draft)
    stmt = select(TechnicalQuestionnaire).where(
        TechnicalQuestionnaire.project_id == project_id
    ).order_by(TechnicalQuestionnaire.status.desc())  # "submitted" > "draft" alphabetically
    questionnaire = (await db.scalars(stmt)).first()

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

    # Get or create technical questionnaire (prefer submitted, fallback to draft)
    stmt = select(TechnicalQuestionnaire).where(
        TechnicalQuestionnaire.project_id == project_id
    ).order_by(TechnicalQuestionnaire.status.desc())  # "submitted" > "draft" alphabetically
    questionnaire = (await db.scalars(stmt)).first()

    if not questionnaire:
        questionnaire = TechnicalQuestionnaire(
            project_id=project_id,
            status="draft",
            responses={},
            progress_percent=0,
        )
        db.add(questionnaire)

    # MVP 35 fix: limpa respostas órfãs ANTES de persistir.
    # Quando GP muda resposta de pergunta-pai (ex: Q3), perguntas dependentes
    # ficam invisíveis na UI mas seus valores antigos permanecem em responses,
    # gerando "conflito não-corrigível" (campo invisível + validate detecta).
    # Auto-prune mantém responses sempre consistente com visibilidade dinâmica.
    from app.services.technical_questionnaire_service import prune_orphan_responses
    pruned_responses, orphans_removed = prune_orphan_responses(
        req.responses, TECHNICAL_QUESTIONS_SCHEMA
    )
    if orphans_removed:
        logger.info(
            "technical_questionnaire.orphans_pruned",
            project_id=str(project_id),
            removed_fields=orphans_removed,
        )

    # Update responses from request (já com órfãos removidos)
    questionnaire.responses = pruned_responses

    # Recalculate progress
    questionnaire.progress_percent = calculate_progress(pruned_responses, TECHNICAL_QUESTIONS_SCHEMA)

    # Handle submission
    if req.submit:
        # MVP 35 (decisão GP #4): Submeter exige status='validated'.
        # Frontend já bloqueia, backend é defesa em profundidade.
        if questionnaire.status != "validated":
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail=(
                    "Questionário precisa ser validado antes de submeter. "
                    "Clique em 'Validar Escopo' primeiro."
                ),
            )

        # MVP 35 Camada 2: LLM sanity check semântico (DBA-M2 — bloqueia se LLM falha)
        from app.services.questionnaire_validation.llm_sanity_check import llm_sanity_check
        from app.services.questionnaire_validation.rules_evaluator import evaluate_rules

        # Roda RulesEvaluator de novo para passar conflicts ao LLM (não repetir)
        rules_result = evaluate_rules(req.responses)
        conflicts_detected = [c["message"] for c in rules_result["conflicts"]]

        # Esta chamada LEVANTA HTTPException 503 se LLM indisponível — submit aborta.
        await llm_sanity_check(
            db=db,
            project_id=project_id,
            responses=req.responses,
            conflicts_detected=conflicts_detected,
        )

        questionnaire.status = "submitted"
        questionnaire.submitted_by = current_user
        questionnaire.submitted_at = datetime.utcnow()

        # Criar registro na tabela questionnaires (FK do OCG).
        # O OCG (Objeto de Contexto Global) exige questionnaire_id válido,
        # e a FK aponta para questionnaires(id), não technical_questionnaires.
        # Sem isso, a consolidação OCG falha com ForeignKeyViolationError.
        current_q = await db.execute(
            select(Questionnaire).where(
                Questionnaire.project_id == project_id,
            ).order_by(Questionnaire.submitted_at.desc()).limit(1)
        )
        existing_q = current_q.scalar_one_or_none()
        if existing_q is None:
            new_q = Questionnaire(
                project_id=project_id,
                gp_email=current_user if isinstance(current_user, str) else str(current_user),
                responses=json.dumps(req.responses, ensure_ascii=False, default=str),
                status="ok",
                approved=True,
                submitted_at=datetime.utcnow(),
            )
            db.add(new_q)

        # MVP 35 (decisão GP #2): cria IngestedDocument sintético — aparece na aba Ingestão.
        # Idempotente (Arq-M2 + DBA-M1): re-submit com responses iguais reusa row.
        from app.services.questionnaire_validation.synthetic_document import (
            create_or_get_synthetic_document,
        )
        await create_or_get_synthetic_document(
            db=db,
            project_id=project_id,
            project_name=project.name,
            questionnaire_id=questionnaire.id,
            responses=req.responses,
            uploaded_by=current_user,
        )

        logger.info(
            "technical_questionnaire_submitted",
            project_id=str(project_id),
            user_id=str(current_user),
            progress=questionnaire.progress_percent,
        )
    else:
        # MVP 35 DBA-M5: guard contra regressão de status. Auto-save NUNCA
        # sobrescreve estados terminais (submitted/archived). Pode regredir
        # validated→draft (intencional — usuário editou após validar, precisa
        # revalidar para reativar Submeter).
        if questionnaire.status not in ("submitted", "archived"):
            questionnaire.status = "draft"
            # Limpa validated_at quando regride — CHECK constraint chk_tq_validated_at
            # exige IS NOT NULL apenas em status='validated'.
            questionnaire.validated_at = None
            questionnaire.validated_by = None
        logger.info(
            "technical_questionnaire_auto_saved",
            project_id=str(project_id),
            progress=questionnaire.progress_percent,
            preserved_status=questionnaire.status in ("submitted", "archived"),
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

            # NOVO: Disparar regeneração de Pilares Vivos após Questionário Técnico
            # ser submetido (junto com avaliação de personas)
            try:
                from app.tasks.pilares_vivos_task import regenerar_pilares_apos_analise

                regenerar_pilares_apos_analise.delay(
                    project_id=str(project_id),
                    user_id=str(current_user),
                    trigger="questionnaire",
                )
                logger.info(
                    "pilares_vivos.regeneracao_disparada",
                    project_id=str(project_id),
                    trigger="questionnaire",
                    questionnaire_id=str(questionnaire.id),
                )
            except Exception as exc:
                logger.warning(
                    "pilares_vivos.falha_ao_disparar",
                    project_id=str(project_id),
                    error=str(exc),
                )
                # Não bloqueia — Pilares é regenerável manualmente

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
    persist: bool = True,  # MVP 35: True por default — Validar persiste status='validated'
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """
    Validar questionário técnico (MVP 35 — escopo expandido).

    Camada 1 — Validação visibilidade/conflitos lógicos do schema (legacy).
    Camada 2 — Catálogo canônico de 30 regras técnicas (RulesEvaluator):
      conflicts/warnings/info por combo (FE×BE×DB×compliance×infra).

    Args:
      persist: se True (default), persiste status='validated' + validated_at
               quando is_valid=True. Se False, valida sem persistir
               (modo "preview" para validate-on-blur frontend).

    Returns:
      is_valid: True se sem conflicts (warnings não bloqueiam)
      conflicts: lista de blockers
      warnings: lista não-bloqueante (UI alerta amarelo)
      info: lista informativa (UI alerta neutro)
    """
    from datetime import datetime, timezone

    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # MVP 35 fix: prune órfãs ANTES de validar — evita falso conflito por
    # respostas residuais de perguntas que ficaram invisíveis.
    from app.services.technical_questionnaire_service import prune_orphan_responses
    pruned_responses, _ = prune_orphan_responses(req.responses, TECHNICAL_QUESTIONS_SCHEMA)

    # Camada 1 — schema visibility/legacy
    legacy_result = validate_questionnaire(pruned_responses, TECHNICAL_QUESTIONS_SCHEMA)
    visible = calculate_visibility(pruned_responses, TECHNICAL_QUESTIONS_SCHEMA)

    # Camada 2 — RulesEvaluator (MVP 35 Fase 35.1)
    from app.services.questionnaire_validation.rules_evaluator import (
        evaluate_rules,
        is_blocking,
    )
    rules_result = evaluate_rules(pruned_responses)

    # Combina conflicts: legacy schema + rules engine (canônico)
    combined_conflicts = list(legacy_result["conflicts"]) + [
        f"{c['rule_id']}: {c['message']}" for c in rules_result["conflicts"]
    ]
    is_valid_combined = legacy_result["is_valid"] and not is_blocking(rules_result)

    # Persiste status='validated' se passou e flag persist=True (DBA-M3)
    persisted = False
    if persist and is_valid_combined:
        stmt = select(TechnicalQuestionnaire).where(
            TechnicalQuestionnaire.project_id == project_id
        ).order_by(TechnicalQuestionnaire.status.desc())
        questionnaire = (await db.scalars(stmt)).first()

        if questionnaire is None:
            # Cria novo se não existir
            questionnaire = TechnicalQuestionnaire(
                project_id=project_id,
                status="validated",
                responses=pruned_responses,
                progress_percent=legacy_result["progress"],
                validated_at=datetime.now(timezone.utc),
                validated_by=current_user,
            )
            db.add(questionnaire)
        elif questionnaire.status not in ("submitted", "archived"):
            # Só sobe pra validated se não está em estado terminal
            questionnaire.status = "validated"
            questionnaire.responses = pruned_responses
            questionnaire.progress_percent = legacy_result["progress"]
            # CHECK chk_tq_validated_at exige NOT NULL — DBA-M3
            questionnaire.validated_at = datetime.now(timezone.utc)
            questionnaire.validated_by = current_user

        await db.commit()
        persisted = True

    logger.info(
        "technical_questionnaire_validated",
        project_id=str(project_id),
        is_valid=is_valid_combined,
        legacy_conflicts=len(legacy_result["conflicts"]),
        rules_conflicts=len(rules_result["conflicts"]),
        rules_warnings=len(rules_result["warnings"]),
        persisted=persisted,
    )

    return ValidationResponse(
        is_valid=is_valid_combined,
        progress_percent=legacy_result["progress"],
        visible_questions=visible,
        conflicts=combined_conflicts,
        # MVP 35: campos extras canônicos
        warnings=[f"{w['rule_id']}: {w['message']}" for w in rules_result["warnings"]],
        info=[f"{i['rule_id']}: {i['message']}" for i in rules_result["info"]],
        rules_evaluated=rules_result["rules_evaluated"],
        evaluated_at_ms=rules_result["evaluated_at_ms"],
        persisted=persisted,
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

    # Verify questionnaire exists (technical ou bridge na tabela questionnaires)
    from app.models.base import TechnicalQuestionnaire, PersonaResponse, Questionnaire
    stmt = select(TechnicalQuestionnaire).where(
        (TechnicalQuestionnaire.id == questionnaire_id) &
        (TechnicalQuestionnaire.project_id == project_id)
    )
    questionnaire = await db.scalar(stmt)
    if not questionnaire:
        bridge_stmt = select(Questionnaire).where(
            (Questionnaire.id == questionnaire_id) &
            (Questionnaire.project_id == project_id)
        )
        questionnaire = await db.scalar(bridge_stmt)
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
