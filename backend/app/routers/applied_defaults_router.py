"""M02 — router de decisões automáticas (applied_defaults)."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.services.domain_defaults_resolver import contest_decision, list_applied

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/applied-defaults", tags=["applied-defaults"])


class AppliedDefaultItem(BaseModel):
    id: str
    gap_id: str
    category: str
    decision_key: str
    decision_value: str
    source_citation: str
    rationale: str | None = None
    applied_at: str
    contested_at: str | None = None
    contested_value: str | None = None
    effective_value: str


class AppliedDefaultsListResponse(BaseModel):
    items: list[AppliedDefaultItem]
    count_by_category: dict[str, int]
    contested_count: int


class ContestRequest(BaseModel):
    new_value: str = Field(..., min_length=1, max_length=4000)


@router.get("", response_model=AppliedDefaultsListResponse)
async def list_defaults(
    project_id: UUID,
    ctx: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os defaults aplicados ao projeto, agrupados por categoria."""
    rows = await list_applied(db, project_id)
    items: list[AppliedDefaultItem] = []
    count_by_cat: dict[str, int] = {}
    contested = 0
    for r in rows:
        count_by_cat[r.category] = count_by_cat.get(r.category, 0) + 1
        if r.contested_at is not None:
            contested += 1
        effective = r.contested_value or r.decision_value
        items.append(AppliedDefaultItem(
            id=str(r.id),
            gap_id=r.gap_id,
            category=r.category,
            decision_key=r.decision_key,
            decision_value=r.decision_value,
            source_citation=r.source_citation,
            rationale=r.rationale,
            applied_at=r.applied_at.isoformat() if r.applied_at else "",
            contested_at=r.contested_at.isoformat() if r.contested_at else None,
            contested_value=r.contested_value,
            effective_value=effective,
        ))
    return AppliedDefaultsListResponse(
        items=items,
        count_by_category=count_by_cat,
        contested_count=contested,
    )


@router.post("/{decision_id}/contest", response_model=AppliedDefaultItem)
async def contest(
    project_id: UUID,
    decision_id: UUID,
    req: ContestRequest,
    ctx: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Usuário contesta uma decisão aplicada, informando o valor específico do caso dele."""
    row = await contest_decision(
        db=db,
        project_id=project_id,
        decision_id=decision_id,
        contested_by=ctx["user_id"],
        new_value=req.new_value,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Decisão não encontrada")
    return AppliedDefaultItem(
        id=str(row.id),
        gap_id=row.gap_id,
        category=row.category,
        decision_key=row.decision_key,
        decision_value=row.decision_value,
        source_citation=row.source_citation,
        rationale=row.rationale,
        applied_at=row.applied_at.isoformat() if row.applied_at else "",
        contested_at=row.contested_at.isoformat() if row.contested_at else None,
        contested_value=row.contested_value,
        effective_value=row.contested_value or row.decision_value,
    )
