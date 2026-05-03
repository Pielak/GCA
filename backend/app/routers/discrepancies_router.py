"""
Discrepancies Router — Gestão de conflitos entre personas

Endpoints para listar, visualizar e resolver conflitos detectados.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from typing import Optional, List
from datetime import datetime, timezone
import structlog

from app.db.database import get_db
from app.models.base import Discrepancy
from app.middleware.auth import get_current_user_from_token
from pydantic import BaseModel

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["discrepancies"])


class DiscrepancyResponse(BaseModel):
    """Resposta com detalhes de uma discrepância."""
    id: str
    project_id: str
    field_path: str
    conflicting_personas: List[str]
    conflicting_values: dict
    severity: str  # low, medium, high, critical
    category: Optional[str]
    status: str  # unresolved, voted, overridden, arbitrated, resolved
    context: Optional[str]
    created_at: str


class ResolveDiscrepancyRequest(BaseModel):
    """Request para resolver uma discrepância."""
    resolved_value: str
    resolution_notes: Optional[str] = None


class DiscrepancyListResponse(BaseModel):
    """Lista de discrepâncias com filtros."""
    total: int
    unresolved: int
    resolved: int
    items: List[DiscrepancyResponse]


@router.get("/projects/{project_id}/discrepancies", response_model=DiscrepancyListResponse)
async def list_project_discrepancies(
    project_id: UUID,
    status_filter: Optional[str] = None,  # unresolved, resolved, all
    severity_filter: Optional[str] = None,  # low, medium, high, critical
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista conflitos detectados no projeto.

    Filtros opcionais:
    - status_filter: unresolved (default), resolved, all
    - severity_filter: low, medium, high, critical
    """
    # Validar projeto
    from app.models.base import Project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Build query
    stmt = select(Discrepancy).where(Discrepancy.project_id == project_id)

    # Apply filters
    if status_filter and status_filter != "all":
        stmt = stmt.where(Discrepancy.status == status_filter)
    elif not status_filter:  # Default: unresolved
        stmt = stmt.where(Discrepancy.status == "unresolved")

    if severity_filter:
        stmt = stmt.where(Discrepancy.severity == severity_filter)

    # Execute
    discrepancies = await db.scalars(stmt)
    items_list = discrepancies.all()

    # Count stats
    all_stmt = select(Discrepancy).where(Discrepancy.project_id == project_id)
    all_items = await db.scalars(all_stmt)
    all_list = all_items.all()

    unresolved_count = sum(1 for d in all_list if d.status == "unresolved")
    resolved_count = sum(1 for d in all_list if d.status in ["resolved", "voted", "overridden"])

    # Format response
    formatted_items = [
        DiscrepancyResponse(
            id=str(item.id),
            project_id=str(item.project_id),
            field_path=item.field_path,
            conflicting_personas=item.conflicting_personas or [],
            conflicting_values=item.conflicting_values or {},
            severity=item.severity,
            category=item.category,
            status=item.status,
            context=item.context,
            created_at=item.created_at.isoformat() if item.created_at else None,
        )
        for item in items_list
    ]

    return DiscrepancyListResponse(
        total=len(all_list),
        unresolved=unresolved_count,
        resolved=resolved_count,
        items=formatted_items,
    )


@router.get("/projects/{project_id}/discrepancies/{discrepancy_id}", response_model=DiscrepancyResponse)
async def get_discrepancy_detail(
    project_id: UUID,
    discrepancy_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes de uma discrepância específica."""
    discrepancy = await db.get(Discrepancy, discrepancy_id)
    if not discrepancy or discrepancy.project_id != project_id:
        raise HTTPException(status_code=404, detail="Discrepância não encontrada")

    return DiscrepancyResponse(
        id=str(discrepancy.id),
        project_id=str(discrepancy.project_id),
        field_path=discrepancy.field_path,
        conflicting_personas=discrepancy.conflicting_personas or [],
        conflicting_values=discrepancy.conflicting_values or {},
        severity=discrepancy.severity,
        category=discrepancy.category,
        status=discrepancy.status,
        context=discrepancy.context,
        created_at=discrepancy.created_at.isoformat() if discrepancy.created_at else None,
    )


@router.post("/projects/{project_id}/discrepancies/{discrepancy_id}/resolve")
async def resolve_discrepancy(
    project_id: UUID,
    discrepancy_id: UUID,
    request: ResolveDiscrepancyRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Resolve um conflito escolhendo um valor ou combinando opiniões.

    Valores propostos estão em conflicting_values.
    User escolhe um (override) ou propõe novo (arbitration).
    """
    discrepancy = await db.get(Discrepancy, discrepancy_id)
    if not discrepancy or discrepancy.project_id != project_id:
        raise HTTPException(status_code=404, detail="Discrepância não encontrada")

    if discrepancy.status != "unresolved":
        raise HTTPException(
            status_code=409,
            detail=f"Discrepância já foi resolvida (status: {discrepancy.status})"
        )

    # Update discrepancy with resolution
    discrepancy.status = "overridden"  # User chose/overrode a value
    discrepancy.resolution_notes = request.resolution_notes
    discrepancy.resolved_by = current_user_id
    discrepancy.resolved_at = datetime.now(timezone.utc)

    # Store the resolved value as metadata (não temos coluna dedicated, usar notes)
    discrepancy.resolution_notes = f"Valor: {request.resolved_value}\n{request.resolution_notes or ''}"

    await db.commit()

    logger.info(
        "discrepancy.resolved",
        discrepancy_id=str(discrepancy_id),
        resolved_by=str(current_user_id),
        resolved_value=request.resolved_value,
    )

    return {
        "success": True,
        "message": "Conflito resolvido com sucesso",
        "discrepancy_id": str(discrepancy_id),
        "status": discrepancy.status,
        "resolved_at": discrepancy.resolved_at.isoformat(),
    }


@router.post("/projects/{project_id}/discrepancies/{discrepancy_id}/accept")
async def accept_consolidated_value(
    project_id: UUID,
    discrepancy_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Aceita o valor consolidado (votação/default) sem override.

    Usa o valor que venceu na votação (crítico quando há maioria clara).
    """
    discrepancy = await db.get(Discrepancy, discrepancy_id)
    if not discrepancy or discrepancy.project_id != project_id:
        raise HTTPException(status_code=404, detail="Discrepância não encontrada")

    if discrepancy.status != "unresolved":
        raise HTTPException(
            status_code=409,
            detail=f"Discrepância já foi resolvida (status: {discrepancy.status})"
        )

    # Mark as accepted (use voting result)
    discrepancy.status = "voted"
    discrepancy.resolved_by = current_user_id
    discrepancy.resolved_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "discrepancy.accepted",
        discrepancy_id=str(discrepancy_id),
        accepted_by=str(current_user_id),
    )

    return {
        "success": True,
        "message": "Conflito aceito com valor consolidado",
        "discrepancy_id": str(discrepancy_id),
        "status": discrepancy.status,
        "resolved_at": discrepancy.resolved_at.isoformat(),
    }
