"""M01 — router Questões em Aberto."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import CustomQuestionnaireIteration, Project
from app.services.iterative_questionnaire_service import (
    compute_status_snapshot,
    generate_iteration,
)
from app.services.pdf_questionnaire_generator import pdf_generator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/iterative-questionnaire",
    tags=["iterative-questionnaire"],
)


class StatusResponse(BaseModel):
    overall: float | None
    deficit_pillars: dict[str, float]
    eligible_for_iteration: bool
    has_pending: bool
    converged: bool
    latest_iteration: dict[str, Any] | None


class GenerateResponse(BaseModel):
    id: str
    iteration: int
    question_count: int
    target_pillars: list[str]


@router.get("/status", response_model=StatusResponse)
async def get_status(
    project_id: UUID,
    ctx: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Usado pelo sidebar/badge + página."""
    return await compute_status_snapshot(db, project_id)


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    project_id: UUID,
    ctx: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """GP dispara geração de nova iteração (quando eligible)."""
    try:
        row = await generate_iteration(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return GenerateResponse(
        id=str(row.id),
        iteration=row.iteration,
        question_count=len(row.questions or []),
        target_pillars=list(row.target_pillars or []),
    )


@router.get("/{iteration_id}/pdf")
async def download_pdf(
    project_id: UUID,
    iteration_id: UUID,
    ctx: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Gera PDF sob demanda (lazy — economiza storage de BLOB até primeiro download)."""
    result = await db.execute(
        select(CustomQuestionnaireIteration).where(
            (CustomQuestionnaireIteration.id == iteration_id)
            & (CustomQuestionnaireIteration.project_id == project_id)
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Iteração não encontrada")

    pdf_bytes = row.pdf_blob
    if not pdf_bytes:
        proj = await db.get(Project, project_id)
        pdf_bytes = pdf_generator.generate_pdf(
            project_name=proj.name if proj else "Projeto",
            questions=row.questions or [],
            iteration=row.iteration,
            iteration_id=str(row.id),
        )
        row.pdf_blob = pdf_bytes
        await db.commit()

    filename = f"Questoes_Abertas_Iter{row.iteration}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{iteration_id}/upload-answers")
async def upload_answers(
    project_id: UUID,
    iteration_id: UUID,
    file: UploadFile = File(...),
    ctx: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Upload do PDF respondido.

    Cria IngestedDocument via `IngestionService.upload_document` com
    category='iterative_questionnaire_answer'. O pipeline canônico de
    ingestão (canonização MVP 29 → Arguidor → OCG Updater) processa
    normalmente. O hook no updater detecta o trigger via
    `answer_document_id` desta linha de iteração e chama
    `evaluate_convergence_after_ocg_update`.
    """
    result = await db.execute(
        select(CustomQuestionnaireIteration).where(
            (CustomQuestionnaireIteration.id == iteration_id)
            & (CustomQuestionnaireIteration.project_id == project_id)
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Iteração não encontrada")
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Iteração já está em estado '{row.status}' — não aceita novo upload.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    from app.services.ingestion_service import IngestionService

    service = IngestionService(db)
    upload_result = await service.upload_document(
        project_id=project_id,
        uploaded_by=ctx["user_id"],
        file_bytes=content,
        original_filename=file.filename or f"questoes_iter{row.iteration}.pdf",
        content_type=file.content_type or "application/pdf",
        category="iterative_questionnaire_answer",
        target_module_id=None,
    )
    sc = upload_result.pop("status_code", 200)
    is_duplicate = bool(upload_result.get("duplicate"))

    # Caso dedupe: arquivo idêntico já foi ingerido antes (provavelmente
    # subido via aba Ingestão comum antes do usuário descobrir a aba
    # correta). Em vez de falhar, reaproveita o doc existente — ele já
    # passou pelo pipeline canônico (Arguidor + OCG Updater) e atualizou
    # o OCG. Como o hook de convergência NÃO rodou naquele momento (o doc
    # não estava linkado à iteração), disparamos manualmente abaixo.
    if is_duplicate:
        doc_id = upload_result.get("existing_document_id")
        reused = True
    elif sc >= 400:
        raise HTTPException(status_code=sc, detail=upload_result.get("error", "Falha ao ingerir resposta"))
    else:
        doc_id = upload_result.get("document_id")
        reused = False

    if not doc_id:
        raise HTTPException(status_code=500, detail="Ingestão retornou sem document_id")

    row.answer_document_id = UUID(doc_id)
    await db.commit()

    # Se o doc é reaproveitado (duplicate), o Arguidor já rodou E o OCG
    # já foi atualizado antes — o hook de convergência no updater não
    # será disparado de novo. Chamamos manualmente pra fechar o ciclo.
    # Em upload novo (pipeline assíncrono), o hook dispara quando o
    # Arguidor terminar e o updater rodar.
    if reused:
        from app.services.iterative_questionnaire_service import (
            evaluate_convergence_after_ocg_update,
        )
        try:
            await evaluate_convergence_after_ocg_update(db, project_id, UUID(doc_id))
        except Exception as hook_exc:  # noqa: BLE001
            logger.warning(
                "m01.manual_convergence_hook_failed",
                extra={
                    "project_id": str(project_id),
                    "iteration_id": str(iteration_id),
                    "document_id": doc_id,
                    "error": str(hook_exc),
                },
            )

    return {
        "document_id": doc_id,
        "iteration_id": str(iteration_id),
        "reused_existing": reused,
        "message": (
            "Resposta já estava ingerida — vinculada à iteração e convergência avaliada."
            if reused
            else "Resposta em processamento. O OCG será re-avaliado automaticamente e o status de convergência aparecerá aqui."
        ),
    }
