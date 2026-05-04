"""Router: Perguntas de follow-up das personas LLM (HITL — Human In The Loop).

Lê de `persona_follow_up_questions` (tabela canônica MVP 34, populada pelo
webhook /ingestion-complete a partir do PersonaOutput-v2.questions[]).

Substituiu (2026-05-03) o caminho legado via DocumentRouteMap + AuditorOutput +
GatekeeperPersonaResponse, que não é mais populado pelo pipeline n8n.
"""
from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import IngestedDocument, PersonaFollowUpQuestion, Project, User

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


# ─── Submit por persona (Save / Validate / Submit) ───


class PersonaSubmitRequest(BaseModel):
    answers: dict[str, str] = {}
    mode: Literal["save", "validate", "submit"]


class PersonaSubmitResponse(BaseModel):
    ok: bool
    saved: int
    pending_count: int
    answered_count: int
    missing_question_ids: list[str]
    document_id: str | None = None
    message: str


@router.post(
    "/projects/{project_id}/pipeline-questions/personas/{persona_id}/submit",
    response_model=PersonaSubmitResponse,
)
async def submit_persona_followup(
    project_id: UUID,
    persona_id: str,
    req: PersonaSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """Salva, valida ou submete respostas HITL de UMA persona específica.

    - mode='save'     → grava respostas, mantém perguntas; status=answered se
                        texto não-vazio, pending caso contrário.
    - mode='validate' → grava + retorna se está pronto pra submeter.
    - mode='submit'   → grava + (se completo) cria IngestedDocument sintético
                        com Q&A serializadas e DELETA as PFQs daquela persona.
    """
    persona_id_norm = persona_id.upper()
    user_id = getattr(current_user, "id", None)
    now = datetime.now(timezone.utc)

    # 1. Salvar respostas (sempre)
    saved = 0
    for qid_str, answer_text in (req.answers or {}).items():
        try:
            qid = UUID(qid_str)
        except (ValueError, TypeError):
            continue
        pfq = (
            await db.execute(
                select(PersonaFollowUpQuestion).where(
                    PersonaFollowUpQuestion.id == qid,
                    PersonaFollowUpQuestion.project_id == project_id,
                    func.upper(PersonaFollowUpQuestion.persona_id) == persona_id_norm,
                )
            )
        ).scalar_one_or_none()
        if pfq is None:
            continue
        text_norm = (answer_text or "").strip()
        await db.execute(
            update(PersonaFollowUpQuestion)
            .where(PersonaFollowUpQuestion.id == qid)
            .values(
                answer_text=text_norm or None,
                answer_provided_at=now if text_norm else None,
                answered_by=user_id if text_norm else None,
                status="answered" if text_norm else "pending",
                updated_at=now,
            )
        )
        saved += 1

    # 2. Recontar pendentes/respondidas
    rows = (
        await db.execute(
            select(PersonaFollowUpQuestion).where(
                PersonaFollowUpQuestion.project_id == project_id,
                func.upper(PersonaFollowUpQuestion.persona_id) == persona_id_norm,
            )
        )
    ).scalars().all()
    missing = [str(p.id) for p in rows if (p.status or "pending") != "answered"]
    answered_count = len(rows) - len(missing)

    if req.mode == "save":
        await db.commit()
        return PersonaSubmitResponse(
            ok=True,
            saved=saved,
            pending_count=len(missing),
            answered_count=answered_count,
            missing_question_ids=missing,
            message=f"{saved} resposta(s) salva(s).",
        )

    if req.mode == "validate":
        await db.commit()
        if missing:
            return PersonaSubmitResponse(
                ok=False,
                saved=saved,
                pending_count=len(missing),
                answered_count=answered_count,
                missing_question_ids=missing,
                message=f"{len(missing)} pergunta(s) sem resposta.",
            )
        return PersonaSubmitResponse(
            ok=True,
            saved=saved,
            pending_count=0,
            answered_count=answered_count,
            missing_question_ids=[],
            message="Todas respondidas — pronto pra submeter.",
        )

    # mode='submit' — comportamento canônico: submete APENAS as respondidas;
    # as em branco permanecem na fila para próxima rodada. Aba só some quando
    # todas forem respondidas/submetidas.
    answered_rows = [r for r in rows if (r.status or "pending") == "answered"]
    if not answered_rows:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Nada a submeter: nenhuma resposta preenchida.",
        )

    persona_name = answered_rows[0].persona_name or persona_id_norm
    qa_payload = [
        {
            "question": p.question_text,
            "context": p.context,
            "answer": p.answer_text,
            "document_origin_id": str(p.document_id),
        }
        for p in sorted(answered_rows, key=lambda r: (r.question_order or 0, r.created_at))
    ]
    payload = {
        "persona_id": persona_id_norm,
        "persona_name": persona_name,
        "submitted_by": str(user_id) if user_id else None,
        "submitted_at": now.isoformat(),
        "qa": qa_payload,
        "qa_count": len(qa_payload),
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    file_hash = hashlib.sha256(payload_bytes).hexdigest()

    project = await db.get(Project, project_id)
    project_name = (project.name if project else "") or "Projeto"
    timestamp_compact = now.strftime("%Y%m%d-%H%M%S")
    filename = f"followup-{persona_id_norm.lower()}-{timestamp_compact}.json"
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project_id,
        uploaded_by=user_id,
        original_filename=f"Respostas HITL — {persona_name} — {project_name}",
        filename=filename,
        file_type="persona_followup",
        file_hash=file_hash,
        file_size_bytes=len(payload_bytes),
        arguider_status="completed",
        arguider_stage="followup_synthetic",
        arguider_progress_percent=100,
        ocg_updated=False,
        pii_detected=False,
    )
    db.add(doc)
    await db.flush()
    new_doc_id = doc.id

    # Persistir payload no storage para extraction-report e auditoria.
    from app.utils.ingested_storage import write_ingested
    write_ingested(project_id, filename, payload_bytes)

    # DELETE somente das respondidas — pendentes em branco continuam na fila.
    await db.execute(
        text(
            "DELETE FROM persona_follow_up_questions "
            "WHERE project_id = :pid AND upper(persona_id) = :persona "
            "AND status = 'answered'"
        ),
        {"pid": str(project_id), "persona": persona_id_norm},
    )

    remaining_pending = (
        await db.scalar(
            select(func.count(PersonaFollowUpQuestion.id)).where(
                PersonaFollowUpQuestion.project_id == project_id,
                func.upper(PersonaFollowUpQuestion.persona_id) == persona_id_norm,
            )
        )
    ) or 0

    await db.commit()

    logger.info(
        "pipeline_questions.persona_submitted",
        project_id=str(project_id),
        persona_id=persona_id_norm,
        questions_count=len(qa_payload),
        document_id=str(new_doc_id),
    )

    msg = f"{len(qa_payload)} resposta(s) submetida(s) como evidência."
    if remaining_pending > 0:
        msg += f" Restam {remaining_pending} pergunta(s) em branco na aba."
    return PersonaSubmitResponse(
        ok=True,
        saved=saved,
        pending_count=remaining_pending,
        answered_count=len(qa_payload),
        missing_question_ids=[],
        document_id=str(new_doc_id),
        message=msg,
    )


# ─── Download .md das perguntas em aberto por persona (HITL offline) ───


@router.get(
    "/projects/{project_id}/pipeline-questions/personas/{persona_id}/download",
    response_class=PlainTextResponse,
)
async def download_persona_questions_md(
    project_id: UUID,
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """Markdown com todas as PFQs pendentes de UMA persona, com IDs marcados.

    Formato canônico: marcador YAML no topo (parseado pelo pipeline de ingestão
    para detectar respostas) + 1 bloco por pergunta com `<!-- pfq-id: UUID -->`.
    GP responde offline e faz upload normal pela aba Ingestão. O backend
    detecta o marcador, marca as PFQs como answered e cria IngestedDocument
    sintético — sem rodar pipeline n8n.
    """
    persona_id_norm = persona_id.upper()
    project = await db.get(Project, project_id)
    project_name = (project.name if project else "Projeto") if project else "Projeto"

    rows = (
        await db.execute(
            select(PersonaFollowUpQuestion).where(
                PersonaFollowUpQuestion.project_id == project_id,
                func.upper(PersonaFollowUpQuestion.persona_id) == persona_id_norm,
                PersonaFollowUpQuestion.status == "pending",
            ).order_by(
                PersonaFollowUpQuestion.question_order.asc().nulls_last(),
                PersonaFollowUpQuestion.created_at.asc(),
            )
        )
    ).scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Sem perguntas pendentes para persona {persona_id_norm}.",
        )

    persona_name = rows[0].persona_name or persona_id_norm
    now_iso = datetime.now(timezone.utc).isoformat()

    lines: list[str] = []
    lines.append("---")
    lines.append("gca-followup-marker: v1")
    lines.append(f"project_id: {project_id}")
    lines.append(f"persona_id: {persona_id_norm}")
    lines.append(f"persona_name: {persona_name}")
    lines.append(f"generated_at: {now_iso}")
    lines.append(f"question_count: {len(rows)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Perguntas em aberto — {persona_name} — {project_name}")
    lines.append("")
    lines.append(
        "Preencha as respostas abaixo de cada pergunta (substitua "
        "`<sua resposta aqui>`). Faça upload deste arquivo pela aba "
        "**Ingestão de Documentos**. NÃO altere as linhas com `<!-- pfq-id: ... -->`."
    )
    lines.append("")
    for idx, p in enumerate(rows, start=1):
        lines.append(f"## Q{idx}")
        lines.append(f"<!-- pfq-id: {p.id} -->")
        lines.append("")
        lines.append(f"**Pergunta**: {p.question_text}")
        if p.context:
            lines.append(f"_Contexto_: {p.context}")
        lines.append("")
        lines.append("**Resposta**:")
        lines.append("")
        lines.append("<sua resposta aqui>")
        lines.append("")

    content = "\n".join(lines)
    filename = f"questoes-aberto-{persona_id_norm.lower()}.md"
    return PlainTextResponse(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
