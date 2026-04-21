"""MVP 19 Fase 19.2 — Endpoints do ERS (generate + freshness + preview).

3 endpoints:
- `POST /api/v1/projects/{id}/docs/ers/regenerate` — gera + commita.
- `GET /api/v1/projects/{id}/docs/ers/freshness` — estado stale atual.
- `GET /api/v1/projects/{id}/docs/ers/preview` — retorna markdown sem commit.

RBAC:
- Preview + freshness: membro aceito do projeto OR Admin.
- Regenerate: GP do projeto OR Admin (ação de escrita no repo).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectMember, User
from sqlalchemy import select

from app.services.ers_doc_generator_service import (
    build_ers_markdown,
    generate_and_commit_ers,
    get_ers_freshness,
)


router = APIRouter(prefix="/projects/{project_id}/docs/ers", tags=["ers"])


async def _require_project_member_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    """Autoriza Admin ou membro aceito. Usa pattern canônico do metrics_router."""
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
        raise HTTPException(
            status_code=403,
            detail="Apenas membros aceitos do projeto ou Admin podem acessar o ERS",
        )
    return user


async def _require_gp_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    """Regenerar ERS escreve no repo — exige GP do projeto ou Admin."""
    user = await _require_project_member_or_admin(project_id, user_id, db)
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
    raise HTTPException(
        status_code=403,
        detail="Apenas GP do projeto ou Admin pode regenerar o ERS",
    )


@router.get("/freshness")
async def get_freshness(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Estado atual do ERS: se está stale, razões, último commit."""
    await _require_project_member_or_admin(project_id, user_id, db)
    return await get_ers_freshness(db, project_id)


@router.get("/preview")
async def get_preview(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retorna o markdown que seria gerado sem commitar no repo.

    Útil para o GP revisar antes de clicar "Regenerar e commit".
    """
    await _require_project_member_or_admin(project_id, user_id, db)
    markdown = await build_ers_markdown(db, project_id)
    return {"path": "docs/ERS.md", "markdown": markdown}


@router.post("/regenerate")
async def regenerate_ers(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Gera o ERS e commita `docs/ERS.md` no repositório do projeto."""
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        return await generate_and_commit_ers(
            db=db,
            project_id=project_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        # Projeto sem repo conectado, PAT inválido, etc.
        raise HTTPException(status_code=400, detail=str(exc))
