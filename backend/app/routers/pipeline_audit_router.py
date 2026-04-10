"""Endpoints de audit log do pipeline de qualidade."""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.services.pipeline_audit_service import PipelineAuditService

router = APIRouter(tags=["Pipeline Audit"])


@router.get("/projects/{project_id}/audit/pipeline")
async def get_pipeline_audit(
    project_id: UUID,
    phase: Optional[str] = None,
    limit: int = 100,
    permissions: dict = Depends(require_action("audit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista audit log do pipeline com filtros."""
    service = PipelineAuditService(db)
    entries = await service.get_project_audit(project_id, phase=phase, limit=limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/projects/{project_id}/audit/pipeline/{item_id}")
async def get_item_audit(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("audit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Trilha de auditoria completa de um item do backlog."""
    service = PipelineAuditService(db)
    entries = await service.get_item_audit(item_id)
    return {"entries": entries, "count": len(entries)}


@router.get("/projects/{project_id}/audit/pipeline/{item_id}/export")
async def export_item_audit(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("audit:export")),
    db: AsyncSession = Depends(get_db),
):
    """Exporta audit completo de um item no formato compliance."""
    service = PipelineAuditService(db)
    return await service.export_item_audit(item_id)
