"""
Gatekeeper Router — Consolidação de items + Aprovação/Rejeição de módulos
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
import structlog

from app.db.database import get_db
from app.services.gatekeeper_service import GatekeeperService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["gatekeeper"])


class ResolveRequest(BaseModel):
    resolution_note: str


class IgnoreRequest(BaseModel):
    reason: str


class RejectRequest(BaseModel):
    reason: str


@router.get("/projects/{project_id}/gatekeeper")
async def get_gatekeeper(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Consolidado completo do Gatekeeper."""
    service = GatekeeperService(db)
    return await service.get_project_gatekeeper(project_id)


@router.get("/projects/{project_id}/gatekeeper/modules")
async def get_modules(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista módulos candidatos."""
    service = GatekeeperService(db)
    return await service.get_modules(project_id)


@router.post("/projects/{project_id}/gatekeeper/items/{item_id}/resolve")
async def resolve_item(
    project_id: UUID,
    item_id: UUID,
    req: ResolveRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Marca item como resolvido."""
    service = GatekeeperService(db)
    success = await service.resolve_item(project_id, item_id, current_user_id, req.resolution_note)
    if not success:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return {"success": True}


@router.post("/projects/{project_id}/gatekeeper/items/{item_id}/ignore")
async def ignore_item(
    project_id: UUID,
    item_id: UUID,
    req: IgnoreRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Marca item como ignorado (reason obrigatório)."""
    service = GatekeeperService(db)
    result = await service.ignore_item(project_id, item_id, current_user_id, req.reason)
    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", ""))
    return result


@router.post("/projects/{project_id}/gatekeeper/modules/{module_id}/approve")
async def approve_module(
    project_id: UUID,
    module_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Aprova módulo candidato."""
    service = GatekeeperService(db)
    result = await service.approve_module(project_id, module_id, current_user_id)
    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", ""))
    return result


@router.post("/projects/{project_id}/gatekeeper/modules/{module_id}/reject")
async def reject_module(
    project_id: UUID,
    module_id: UUID,
    req: RejectRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Rejeita módulo candidato (reason obrigatório)."""
    service = GatekeeperService(db)
    result = await service.reject_module(project_id, module_id, current_user_id, req.reason)
    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", ""))
    return result


@router.get("/projects/{project_id}/gatekeeper/report")
async def download_report(
    project_id: UUID,
    format: str = "markdown",
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Download do relatório do Gatekeeper."""
    service = GatekeeperService(db)
    md = await service.generate_report_markdown(project_id)

    if format == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
            import io
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4)
            styles = getSampleStyleSheet()
            story = [Paragraph(line.replace("**", "<b>").replace("**", "</b>"), styles["Normal"]) for line in md.split("\n") if line.strip()]
            doc.build(story)
            return Response(
                content=buf.getvalue(),
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=gatekeeper_report_{project_id}.pdf"},
            )
        except ImportError:
            raise HTTPException(status_code=501, detail="Geração de PDF não disponível (reportlab não instalado)")

    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=gatekeeper_report_{project_id}.md"},
    )


# ─── MVP 24 Fase 24.1 — Questionário técnico retroativo ───────────────
# Gera PDF editável (AcroForm) com gaps pendentes agrupados por seção
# canônica. GP baixa, responde offline, reingere via /ingestion — parser
# da Fase 24.2 reconhece o PDF e aplica as respostas automaticamente.


@router.get("/projects/{project_id}/arguider/questionnaire.pdf")
async def download_arguider_questionnaire_pdf(
    project_id: UUID,
    section: str,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """PDF editável por seção canônica.

    `section` é um de: governance, architecture, capacity, security, legal.
    Seção vazia ainda retorna PDF válido (com o campo Complementos).
    """
    from app.services.arguider_questionnaire_service import (
        CANONICAL_SECTIONS, generate_section_pdf,
    )

    if section not in CANONICAL_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"section inválida. Aceitas: {list(CANONICAL_SECTIONS)}",
            },
        )

    pdf_bytes = await generate_section_pdf(db, project_id, section)  # type: ignore[arg-type]
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="questionario_{section}_{project_id}.pdf"'
            ),
        },
    )
