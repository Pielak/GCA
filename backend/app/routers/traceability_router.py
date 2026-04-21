"""MVP 19 Fase 19.4 — Endpoint da matriz de rastreabilidade (read-only).

1 endpoint:
- `GET /api/v1/projects/{project_id}/traceability` — retorna a matriz
  requisito × test_spec × código gerado sob demanda.

RBAC: membro aceito do projeto OR Admin (read-only; sem escrita).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectMember, User
from app.services.traceability_service import build_traceability_matrix


router = APIRouter(prefix="/projects/{project_id}/traceability", tags=["traceability"])


async def _require_project_member_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    """Autoriza Admin ou membro aceito do projeto."""
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória",
        )
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
        raise HTTPException(
            status_code=403,
            detail="Apenas membros aceitos do projeto ou Admin podem ver a matriz",
        )
    return user


@router.get("")
async def get_traceability_matrix(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retorna a matriz consolidada sob demanda.

    Payload: ver `traceability_service.build_traceability_matrix`.
    """
    await _require_project_member_or_admin(project_id, user_id, db)
    return await build_traceability_matrix(db, project_id)
