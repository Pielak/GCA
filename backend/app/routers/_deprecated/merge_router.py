"""
Merge Router — Endpoints do motor de merge inteligente.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
from typing import Dict, Any
import structlog

from app.db.database import get_db
from app.services.merge_service import MergeService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["merge"])


class CompareRequest(BaseModel):
    generated_module_id: UUID
    existing_file_path: str


class ApplyMergeRequest(BaseModel):
    merge_result: Dict[str, Any]
    target_path: str


@router.post("/projects/{project_id}/merge/compare")
async def compare_code(
    project_id: UUID,
    req: CompareRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Compara código gerado com arquivo existente no repositório."""
    service = MergeService(db)
    return await service.compare(
        project_id=project_id,
        generated_module_id=req.generated_module_id,
        existing_file_path=req.existing_file_path,
    )


@router.post("/projects/{project_id}/merge/apply")
async def apply_merge(
    project_id: UUID,
    req: ApplyMergeRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Aplica resultado de merge ao repositório."""
    service = MergeService(db)
    result = await service.apply_merge(
        project_id=project_id,
        merge_result=req.merge_result,
        target_path=req.target_path,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", result.get("error", "Falha ao aplicar merge")),
        )
    return result
