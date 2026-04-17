"""
Ingestion Router — Upload e gestão de documentos por projeto
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
import structlog

from app.db.database import get_db
from app.services.ingestion_service import IngestionService
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_project_setup import require_project_setup_complete

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestion"])


@router.post("/projects/{project_id}/ingestion")
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
    _setup: dict = Depends(require_project_setup_complete),
):
    """Upload de documento para análise pelo Arguidor."""
    file_bytes = await file.read()
    service = IngestionService(db)
    result = await service.upload_document(
        project_id=project_id,
        uploaded_by=current_user_id,
        file_bytes=file_bytes,
        original_filename=file.filename or "unnamed",
        content_type=file.content_type or "",
    )

    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", result.get("message", "")))
    return result


@router.get("/projects/{project_id}/ingestion")
async def list_documents(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista documentos ingeridos do projeto."""
    service = IngestionService(db)
    return await service.list_documents(project_id)


@router.get("/projects/{project_id}/ingestion/{document_id}")
async def get_document_detail(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Documento + análise completa do Arguidor."""
    service = IngestionService(db)
    result = await service.get_document_detail(project_id, document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return result


@router.get("/projects/{project_id}/ingestion/{document_id}/status")
async def get_document_status(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Status para polling (a cada 3s)."""
    service = IngestionService(db)
    result = await service.get_document_status(project_id, document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return result


@router.delete("/projects/{project_id}/ingestion/{document_id}")
async def delete_document(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Remove documento. GP apenas."""
    service = IngestionService(db)
    result = await service.delete_document(project_id, document_id)
    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", ""))
    return result


@router.post("/projects/{project_id}/ingestion/{document_id}/release")
async def release_from_quarantine(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Liberar documento da quarentena e disparar análise + OCG update."""
    from app.models.base import IngestedDocument

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc.quarantine_status != "quarantined":
        raise HTTPException(status_code=400, detail="Documento não está em quarentena")

    doc.quarantine_status = "released"
    doc.arguider_status = "pending"
    await db.commit()

    return {"message": "Documento liberado da quarentena. Análise será iniciada.", "document_id": str(document_id)}


@router.get("/projects/{project_id}/ingestion/{document_id}/content")
async def get_document_content(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Serve o conteúdo original do documento (read-only, inline)."""
    from fastapi.responses import Response
    from app.models.base import IngestedDocument
    from app.utils.ingested_storage import read_ingested

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Soft-delete: doc marcado como bytes perdidos (script de inventário).
    # 410 Gone é o status semanticamente correto — recurso existiu, foi perdido.
    if doc.content_status == "lost":
        raise HTTPException(
            status_code=410,
            detail=(
                "Conteúdo perdido permanentemente. O arquivo foi ingerido antes "
                "da feature de persistência e não é recuperável automaticamente. "
                "Re-faça o upload se ainda tiver o original."
            ),
        )

    content = read_ingested(project_id, doc.filename)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail="Conteúdo não disponível. Documento foi ingerido antes da persistência — requer re-ingestão.",
        )

    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "markdown": "text/markdown; charset=utf-8",
        "image": "image/png",
        "spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "code": "text/plain; charset=utf-8",
    }
    content_type = mime_map.get(doc.file_type, "application/octet-stream")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.original_filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )
