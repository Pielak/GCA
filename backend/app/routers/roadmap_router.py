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
from app.dependencies.require_action import require_action

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


@router.post("/projects/{project_id}/backlog/generate")
async def generate_backlog(
    project_id: UUID,
    permissions: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Gera backlog inteligente: OCG + Arguider module_candidates + verificacao de artefatos."""
    from app.services.backlog_service import BacklogService
    from app.services.artifact_verification_service import ArtifactVerificationService

    service = BacklogService(db)

    # 1. Regenerar do OCG
    ocg_result = await service.regenerate_from_ocg(project_id)

    # 2. Ingerir module_candidates do Arguider
    arguider_result = await service.ingest_module_candidates(project_id)

    # 3. Verificar artefatos de todos os itens
    verifier = ArtifactVerificationService()
    verifications = await verifier.verify_all_items(db, project_id)

    return {
        "ocg_items": ocg_result.get("total", 0),
        "arguider_items": arguider_result.get("created", 0),
        "verified": len(verifications),
        "ready": sum(1 for v in verifications if v["status"] == "ready"),
        "blocked": sum(1 for v in verifications if v["status"] == "blocked"),
    }


@router.post("/projects/{project_id}/backlog/verify")
async def verify_backlog_artifacts(
    project_id: UUID,
    permissions: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Reverifica artefatos de todos os itens pendentes/bloqueados."""
    from app.services.artifact_verification_service import ArtifactVerificationService

    verifier = ArtifactVerificationService()
    results = await verifier.verify_all_items(db, project_id)
    return {
        "verified": len(results),
        "ready": sum(1 for v in results if v["status"] == "ready"),
        "blocked": sum(1 for v in results if v["status"] == "blocked"),
        "items": results,
    }


@router.post("/projects/{project_id}/backlog/ingest-arguider")
async def ingest_arguider_candidates(
    project_id: UUID,
    permissions: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Converte ModuleCandidates do Arguider em itens do backlog."""
    from app.services.backlog_service import BacklogService

    service = BacklogService(db)
    result = await service.ingest_module_candidates(project_id)
    return result
