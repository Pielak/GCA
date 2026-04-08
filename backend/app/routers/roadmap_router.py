"""
Roadmap Router — Endpoint de roadmap dinâmico do projeto.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import structlog

from app.db.database import get_db
from app.services.roadmap_service import RoadmapService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["roadmap"])


@router.get("/projects/{project_id}/roadmap")
async def get_roadmap(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Roadmap dinâmico — módulos agrupados por fase e prioridade."""
    service = RoadmapService(db)
    return await service.get_roadmap(project_id)
