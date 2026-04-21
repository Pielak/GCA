"""MVP 19 Fase 19.3 — Endpoints do glossário vivo por projeto."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectMember, User
from app.services.glossary_service import (
    STATUS_APPROVED,
    STATUS_CANDIDATE,
    STATUS_REJECTED,
    approve_term,
    create_manual_term,
    extract_glossary_candidates,
    list_terms,
    reject_term,
    update_term_definition,
)


router = APIRouter(prefix="/projects/{project_id}/glossary", tags=["glossary"])


class ManualTermCreate(BaseModel):
    term: str = Field(..., min_length=1, max_length=200)
    definition: str = Field("", max_length=2000)


class DefinitionUpdate(BaseModel):
    definition: str = Field("", max_length=2000)


async def _require_member_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação obrigatória")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido ou inativo")
    if user.is_admin or user.is_support:
        return user
    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at or not member.is_active:
        raise HTTPException(status_code=403, detail="Apenas membros aceitos do projeto ou Admin")
    return user


async def _require_gp_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    user = await _require_member_or_admin(project_id, user_id, db)
    if user.is_admin:
        return user
    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )).scalar_one_or_none()
    if member and member.role == "gp":
        return user
    raise HTTPException(status_code=403, detail="Apenas GP do projeto ou Admin pode aprovar/editar termos")


def _term_as_dict(term) -> dict:
    return {
        "id": str(term.id),
        "term": term.term,
        "definition": term.definition,
        "source": term.source,
        "source_reference": term.source_reference,
        "status": term.status,
        "created_at": term.created_at.isoformat() if term.created_at else None,
        "approved_at": term.approved_at.isoformat() if term.approved_at else None,
        "rejected_at": term.rejected_at.isoformat() if term.rejected_at else None,
    }


@router.get("")
async def get_glossary(
    project_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_member_or_admin(project_id, user_id, db)
    if status_filter and status_filter not in {STATUS_CANDIDATE, STATUS_APPROVED, STATUS_REJECTED}:
        raise HTTPException(
            status_code=400,
            detail=f"status inválido: use um de {STATUS_CANDIDATE} | {STATUS_APPROVED} | {STATUS_REJECTED}",
        )
    terms = await list_terms(db, project_id, status_filter=status_filter)
    return {
        "count": len(terms),
        "terms": [_term_as_dict(t) for t in terms],
    }


@router.post("/extract")
async def extract_candidates(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Varre o corpus do projeto e insere novos candidatos. Idempotente."""
    user = await _require_gp_or_admin(project_id, user_id, db)
    result = await extract_glossary_candidates(db, project_id, actor_id=user.id)
    return result.as_dict()


@router.post("/{term_id}/approve")
async def approve(
    project_id: UUID,
    term_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        term = await approve_term(db, term_id, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if term.project_id != project_id:
        raise HTTPException(status_code=404, detail="Termo não pertence ao projeto")
    return _term_as_dict(term)


@router.post("/{term_id}/reject")
async def reject(
    project_id: UUID,
    term_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        term = await reject_term(db, term_id, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if term.project_id != project_id:
        raise HTTPException(status_code=404, detail="Termo não pertence ao projeto")
    return _term_as_dict(term)


@router.patch("/{term_id}")
async def update_definition(
    project_id: UUID,
    term_id: UUID,
    body: DefinitionUpdate,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        term = await update_term_definition(db, term_id, body.definition, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if term.project_id != project_id:
        raise HTTPException(status_code=404, detail="Termo não pertence ao projeto")
    return _term_as_dict(term)


@router.post("")
async def create_manual(
    project_id: UUID,
    body: ManualTermCreate,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GP cadastra um termo manualmente já como `approved`."""
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        term = await create_manual_term(
            db,
            project_id=project_id,
            term=body.term,
            definition=body.definition,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _term_as_dict(term)
