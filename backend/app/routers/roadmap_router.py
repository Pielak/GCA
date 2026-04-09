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


# ============================================================================
# Backlog Vivo (spec seção 7.2)
# ============================================================================

@router.get("/projects/{project_id}/backlog")
async def get_backlog(
    project_id: UUID,
    category: str = None,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista o backlog vivo do projeto, opcionalmente filtrado por categoria."""
    from app.services.backlog_service import BacklogService
    service = BacklogService(db)
    items = await service.list_backlog(project_id, category=category)
    return {"items": items, "count": len(items)}


@router.post("/projects/{project_id}/backlog/regenerate")
async def regenerate_backlog(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Regenera o backlog a partir do OCG atual (spec seção 7.2).
    Remove itens auto-gerados e recria. Itens manuais são preservados."""
    from app.services.backlog_service import BacklogService
    from app.services.audit_service import AuditService, AuditEvents

    service = BacklogService(db)
    result = await service.regenerate_from_ocg(project_id)

    # Registrar evento
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEvents.BACKLOG_REGENERATED,
        resource_type="backlog",
        actor_id=current_user_id,
        resource_id=project_id,
        details=result,
    )
    await db.commit()

    return result
