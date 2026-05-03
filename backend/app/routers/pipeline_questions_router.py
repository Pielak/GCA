"""Router: Perguntas de follow-up das personas LLM (HITL — Human In The Loop).

Lê de `persona_follow_up_questions` (tabela canônica MVP 34, populada pelo
webhook /ingestion-complete a partir do PersonaOutput-v2.questions[]).

Substituiu (2026-05-03) o caminho legado via DocumentRouteMap + AuditorOutput +
GatekeeperPersonaResponse, que não é mais populado pelo pipeline n8n.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import IngestedDocument, PersonaFollowUpQuestion, User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline_questions"])


class QuestionItem(BaseModel):
    id: str
    source: str
    document_id: str
    document_name: str
    route_map_id: str  # mantido para compat de schema com frontend; usa document_id
    question_text: str
    rationale: str
    answer_type: str
    answer_options: list[str] | None = None
    category: str | None = None
    severity: str | None = None
    status: str = "pending"
    answer_text: str | None = None


class PipelineQuestionsResponse(BaseModel):
    pending_questions: list[QuestionItem]
    answered_questions: list[QuestionItem]


class AnswersRequest(BaseModel):
    answers: dict[str, str]  # {persona_follow_up_question.id: answer_text}


class AnswersResponse(BaseModel):
    stored: int
    documents_reprocessed: list[str]


def _to_item(pfq: PersonaFollowUpQuestion, filename: str) -> QuestionItem:
    return QuestionItem(
        id=str(pfq.id),
        source=(pfq.persona_id or "").lower(),
        document_id=str(pfq.document_id),
        document_name=filename,
        route_map_id=str(pfq.document_id),
        question_text=pfq.question_text,
        rationale=pfq.context or "",
        answer_type="free_text",
        answer_options=None,
        category=None,
        severity=None,
        status=pfq.status or "pending",
        answer_text=pfq.answer_text,
    )


@router.get(
    "/projects/{project_id}/pipeline-questions",
    response_model=PipelineQuestionsResponse,
)
async def get_pipeline_questions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    stmt = (
        select(PersonaFollowUpQuestion, IngestedDocument.original_filename)
        .join(
            IngestedDocument,
            PersonaFollowUpQuestion.document_id == IngestedDocument.id,
        )
        .where(
            PersonaFollowUpQuestion.project_id == project_id,
            IngestedDocument.deleted_at.is_(None),
        )
        .order_by(
            PersonaFollowUpQuestion.persona_id.asc(),
            PersonaFollowUpQuestion.question_order.asc().nulls_last(),
            PersonaFollowUpQuestion.created_at.asc(),
        )
    )
    rows = (await db.execute(stmt)).all()

    pending: list[QuestionItem] = []
    answered: list[QuestionItem] = []
    for pfq, filename in rows:
        item = _to_item(pfq, filename or "(sem nome)")
        if (pfq.status or "pending") == "answered":
            answered.append(item)
        elif pfq.status in (None, "pending"):
            pending.append(item)
        # 'skipped' e 'expired' são omitidos da UI

    return PipelineQuestionsResponse(
        pending_questions=pending,
        answered_questions=answered,
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
    if not req.answers:
        raise ValidationError(
            "Nenhuma resposta fornecida",
            context={"project_id": str(project_id)},
        )

    user_id = getattr(current_user, "id", None)
    now = datetime.now(timezone.utc)
    stored = 0
    docs_touched: set[str] = set()

    for qid_str, answer_text in req.answers.items():
        try:
            qid = UUID(qid_str)
        except (ValueError, TypeError):
            logger.warning("pipeline_questions.invalid_uuid", question_id=qid_str)
            continue

        pfq = (
            await db.execute(
                select(PersonaFollowUpQuestion).where(
                    PersonaFollowUpQuestion.id == qid,
                    PersonaFollowUpQuestion.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if pfq is None:
            logger.warning("pipeline_questions.unknown_question", question_id=qid_str)
            continue

        await db.execute(
            update(PersonaFollowUpQuestion)
            .where(PersonaFollowUpQuestion.id == qid)
            .values(
                answer_text=answer_text,
                answer_provided_at=now,
                answered_by=user_id,
                status="answered",
                updated_at=now,
            )
        )
        stored += 1
        docs_touched.add(str(pfq.document_id))

    await db.commit()

    logger.info(
        "pipeline_questions.answers_submitted",
        project_id=str(project_id),
        stored=stored,
        documents=len(docs_touched),
    )

    # Re-trigger de pipeline ainda não conectado ao novo fluxo n8n —
    # respostas ficam persistidas para próxima rodada manual.
    return AnswersResponse(
        stored=stored,
        documents_reprocessed=list(docs_touched),
    )
