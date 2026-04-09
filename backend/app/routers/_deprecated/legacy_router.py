"""
Legacy Router — Endpoints de análise de codebase legado.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
import structlog

from app.db.database import get_db
from app.services.legacy_service import LegacyService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["legacy"])


class LegacyAnalyzeRequest(BaseModel):
    source_type: str  # 'zip' ou 'git_url'
    source: str
    branch: str = "main"


@router.post("/projects/{project_id}/legacy/analyze")
async def analyze_legacy(
    project_id: UUID,
    req: LegacyAnalyzeRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Inicia análise assíncrona de codebase legado."""
    service = LegacyService(db)
    result = await service.start_analysis(
        project_id=project_id,
        source_type=req.source_type,
        source=req.source,
        branch=req.branch,
    )
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )
    return result


@router.get("/projects/{project_id}/legacy/status/{job_id}")
async def get_legacy_status(
    project_id: UUID,
    job_id: str,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Status de um job de análise legado."""
    service = LegacyService(db)
    return await service.get_analysis_status(project_id, job_id)


@router.get("/projects/{project_id}/legacy/result/{job_id}")
async def get_legacy_result(
    project_id: UUID,
    job_id: str,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Resultado de análise legado completada."""
    service = LegacyService(db)
    result = await service.get_analysis_result(project_id, job_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resultado não encontrado ou análise ainda em andamento.",
        )
    return result
