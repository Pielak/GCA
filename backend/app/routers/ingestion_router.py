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

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestion"])


@router.post("/projects/{project_id}/ingestion")
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
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
