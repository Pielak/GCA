"""Router: Perguntas do Pipeline para validação humana.

Expõe as perguntas geradas pelo Auditor e pelas personas técnicas em um formato
unificado para o frontend exibir no Questionário Técnico. As respostas do usuário
são armazenadas e disparam re-análise (Passada 2).
"""
from __future__ import annotations
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ExternalServiceError, ValidationError
from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import IngestedDocument, User
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
from app.models.human_answer import HumanAnswer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline_questions"])


# ─── Request/Response Models ───


class QuestionItem(BaseModel):
    """Uma pergunta pendente do pipeline."""
    id: str
    source: str  # "auditor", "gp", "arq", "dba", "dev", "qa", "ux", "ui"
    document_id: str
    document_name: str
    route_map_id: str
    question_text: str
    rationale: str
    answer_type: str
    answer_options: list[str] | None = None
    category: str | None = None
    severity: str | None = None
    status: str = "pending"  # "pending" | "answered"
    answer_text: str | None = None


class PipelineQuestionsResponse(BaseModel):
    pending_questions: list[QuestionItem]
    answered_questions: list[QuestionItem]


class AnswersRequest(BaseModel):
    answers: dict[str, str]  # {question_id: answer_text}


class AnswersResponse(BaseModel):
    stored: int
    documents_reprocessed: list[str]


# ─── Helpers ───


async def _get_route_maps(
    db: AsyncSession, project_id: UUID,
) -> list[tuple[DocumentRouteMap, str]]:
    """Retorna (route_map, filename) para todos os roteamentos do projeto."""
    stmt = (
        select(DocumentRouteMap, IngestedDocument.original_filename)
        .join(IngestedDocument, DocumentRouteMap.document_id == IngestedDocument.id)
        .where(IngestedDocument.project_id == project_id)
        .order_by(DocumentRouteMap.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.all())


async def _get_answered_ids(db: AsyncSession, route_map_ids: list[UUID]) -> set[str]:
    """Retorna set de 'question_id' já respondidas para estes route_maps."""
    if not route_map_ids:
        return set()
    stmt = select(HumanAnswer).where(
        HumanAnswer.route_map_id.in_(route_map_ids)
    )
    result = await db.execute(stmt)
    return {(h.route_map_id, h.question_id) for h in result.scalars().all()}


def _extract_questions_from_auditor(
    ao: AuditorOutput, rm: DocumentRouteMap, filename: str,
    answered: set,
) -> tuple[list[QuestionItem], list[QuestionItem]]:
    """Extrai QuestionItem do questionnaire_to_human do Auditor."""
    pending: list[QuestionItem] = []
    answered_list: list[QuestionItem] = []
    try:
        questions = (
            json.loads(ao.questionnaire_to_human)
            if isinstance(ao.questionnaire_to_human, str)
            else (ao.questionnaire_to_human or [])
        )
    except (json.JSONDecodeError, TypeError):
        return [], []

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        qid = q.get("id") or f"AUD-{i:03d}"
        key = (rm.id, qid)
        is_answered = key in answered

        item = QuestionItem(
            id=qid,
            source="auditor",
            document_id=str(rm.document_id),
            document_name=filename,
            route_map_id=str(rm.id),
            question_text=q.get("question_text", ""),
            rationale=q.get("rationale", ""),
            answer_type=q.get("answer_type", "free_text"),
            answer_options=q.get("answer_options"),
            category=q.get("category"),
            severity=q.get("severity"),
            status="answered" if is_answered else "pending",
            answer_text=None,
        )
        if is_answered:
            answered_list.append(item)
        else:
            pending.append(item)

    return pending, answered_list


def _extract_questions_from_personas(
    gpr, rm: DocumentRouteMap, filename: str,
    answered: set,
) -> tuple[list[QuestionItem], list[QuestionItem]]:
    """Extrai QuestionItem das perguntas de uma persona."""
    pending: list[QuestionItem] = []
    answered_list: list[QuestionItem] = []

    # Só passada 1 gera perguntas (passada 2 responde)
    if gpr.passada != 1:
        return [], []

    try:
        questions = (
            json.loads(gpr.questions)
            if isinstance(gpr.questions, str)
            else (gpr.questions or [])
        )
    except (json.JSONDecodeError, TypeError):
        return [], []

    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = q.get("id", "")
        if not qid:
            continue
        key = (rm.id, qid)
        is_answered = key in answered

        item = QuestionItem(
            id=qid,
            source=gpr.persona_tag,
            document_id=str(rm.document_id),
            document_name=filename,
            route_map_id=str(rm.id),
            question_text=q.get("question_text", ""),
            rationale=q.get("rationale", ""),
            answer_type=q.get("answer_type", "free_text"),
            answer_options=None,
            category=None,
            severity=q.get("severity"),
            status="answered" if is_answered else "pending",
            answer_text=None,
        )
        if is_answered:
            answered_list.append(item)
        else:
            pending.append(item)

    return pending, answered_list


# ─── Endpoints ───


@router.get(
    "/projects/{project_id}/pipeline-questions",
    response_model=PipelineQuestionsResponse,
)
async def get_pipeline_questions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """Retorna perguntas pendentes e respondidas do pipeline."""
    try:
        route_maps = await _get_route_maps(db, project_id)
    except Exception as e:
        logger.exception("pipeline_questions.fetch_route_maps_failed")
        raise ExternalServiceError(
            "falha ao consultar roteamentos do projeto",
            context={"project_id": str(project_id)},
        ) from e

    if not route_maps:
        return PipelineQuestionsResponse(pending_questions=[], answered_questions=[])

    rm_ids = [rm.id for rm, _ in route_maps]
    answered_keys = await _get_answered_ids(db, rm_ids)

    all_pending: list[QuestionItem] = []
    all_answered: list[QuestionItem] = []

    for rm, filename in route_maps:
        # Buscar AuditorOutput
        ao_stmt = select(AuditorOutput).where(
            AuditorOutput.route_map_id == rm.id
        ).order_by(AuditorOutput.created_at.desc()).limit(1)
        ao_result = await db.execute(ao_stmt)
        ao = ao_result.scalar_one_or_none()

        if ao and ao.questionnaire_to_human:
            p, a = _extract_questions_from_auditor(ao, rm, filename, answered_keys)
            all_pending.extend(p)
            all_answered.extend(a)

        # Buscar respostas das personas
        gpr_stmt = select(GatekeeperPersonaResponse).where(
            GatekeeperPersonaResponse.route_map_id == rm.id
        ).order_by(GatekeeperPersonaResponse.passada.desc())
        gpr_result = await db.execute(gpr_stmt)
        for gpr in gpr_result.scalars().all():
            if gpr.questions:
                p, a = _extract_questions_from_personas(
                    gpr, rm, filename, answered_keys,
                )
                all_pending.extend(p)
                all_answered.extend(a)

    return PipelineQuestionsResponse(
        pending_questions=all_pending,
        answered_questions=all_answered,
    )


@router.post(
    "/projects/{project_id}/pipeline-questions/answers",
    response_model=AnswersResponse,
)
async def submit_pipeline_answers(
    project_id: UUID,
    req: AnswersRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """Armazena respostas às perguntas do pipeline e re-triggers análise."""
    if not req.answers:
        raise ValidationError(
            "Nenhuma resposta fornecida",
            context={"project_id": str(project_id)},
        )

    # Mapear perguntas para route_map + question_id
    # answers vem como {question_id: answer_text}.
    # Precisamos encontrar route_map_id para cada questão.
    # Buscar todos os route_maps ativos do projeto
    route_maps = await _get_route_maps(db, project_id)
    rm_by_qid: dict[str, UUID] = {}
    qid_by_rm: dict[UUID, list[str]] = {}
    seen_qids: set[str] = set()

    for rm, _ in route_maps:
        # Auditor
        ao_stmt = select(AuditorOutput).where(
            AuditorOutput.route_map_id == rm.id
        )
        ao_result = await db.execute(ao_stmt)
        for ao in ao_result.scalars().all():
            if ao.questionnaire_to_human:
                try:
                    qs = (
                        json.loads(ao.questionnaire_to_human)
                        if isinstance(ao.questionnaire_to_human, str)
                        else ao.questionnaire_to_human
                    )
                    for q in (qs or []):
                        qid = q.get("id") if isinstance(q, dict) else None
                        if qid and qid not in seen_qids:
                            seen_qids.add(qid)
                            rm_by_qid[qid] = rm.id
                            qid_by_rm.setdefault(rm.id, []).append(qid)
                except (json.JSONDecodeError, TypeError):
                    continue

        # Personas
        gpr_stmt = select(GatekeeperPersonaResponse).where(
            GatekeeperPersonaResponse.route_map_id == rm.id,
            GatekeeperPersonaResponse.passada == 1,
        )
        gpr_result = await db.execute(gpr_stmt)
        for gpr in gpr_result.scalars().all():
            if gpr.questions:
                try:
                    qs = (
                        json.loads(gpr.questions)
                        if isinstance(gpr.questions, str)
                        else gpr.questions
                    )
                    for q in (qs or []):
                        qid = q.get("id") if isinstance(q, dict) else None
                        if qid and qid not in seen_qids:
                            seen_qids.add(qid)
                            rm_by_qid[qid] = rm.id
                            qid_by_rm.setdefault(rm.id, []).append(qid)
                except (json.JSONDecodeError, TypeError):
                    continue

    # Salvar respostas
    stored = 0
    documents_to_reprocess: set[str] = set()

    try:
        for question_id, answer_text in req.answers.items():
            rm_id = rm_by_qid.get(question_id)
            if rm_id is None:
                logger.warning(
                    "pipeline_questions.unknown_question",
                    question_id=question_id,
                )
                continue

            ha = HumanAnswer(
                route_map_id=rm_id,
                persona_tag="user",
                question_id=question_id,
                answer_text=answer_text,
                answered_by=getattr(current_user, "id", None),
            )
            db.add(ha)
            stored += 1
            documents_to_reprocess.add(str(rm_id))

        await db.commit()
    except Exception as e:
        logger.exception("pipeline_questions.save_answers_failed")
        raise ExternalServiceError(
            "falha ao salvar respostas",
            context={"project_id": str(project_id)},
        ) from e

    # Re-trigger pipeline para docs com todas as perguntas respondidas
    reprocessed_docs: list[str] = []
    for rm_id_str in documents_to_reprocess:
        try:
            from app.tasks.pipeline import pipeline_ingest_task

            pipeline_ingest_task.delay(document_id=rm_id_str)
            reprocessed_docs.append(rm_id_str)
        except Exception:
            logger.exception(
                "pipeline_questions.reprocess_failed",
                route_map_id=rm_id_str,
            )

    logger.info(
        "pipeline_questions.answers_submitted",
        project_id=str(project_id),
        stored=stored,
        reprocessed=len(reprocessed_docs),
    )

    return AnswersResponse(
        stored=stored,
        documents_reprocessed=reprocessed_docs,
    )
