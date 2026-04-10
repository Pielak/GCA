"""
Dependency FastAPI para verificar permissoes por acao.

Uso:
    @router.post("/projects/{project_id}/settings")
    async def update_settings(
        project_id: UUID,
        permissions: dict = Depends(require_action("project:edit")),
    ):
        user_id = permissions["user_id"]
"""
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import has_action
from app.db.database import get_db
from app.dependencies.project_access import get_user_project_role
from app.middleware.auth import get_current_user_from_token
from app.models.base import User


async def _get_user_is_admin(user_id: UUID, db: AsyncSession) -> bool:
    result = await db.execute(select(User.is_admin).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row is True


async def resolve_user_role_in_project(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> str:
    """
    Resolve o papel efetivo do usuario no projeto.

    - Se e membro -> retorna papel do ProjectMember
    - Se NAO e membro mas e Admin -> retorna 'admin_viewer'
    - Se NAO e membro e NAO e Admin -> 403
    """
    role = await get_user_project_role(user_id, project_id, db)

    if role is not None:
        return role

    is_admin = await _get_user_is_admin(user_id, db)
    if is_admin:
        return "admin_viewer"

    raise HTTPException(
        status_code=403,
        detail="Acesso negado: voce nao e membro deste projeto",
    )


def require_action(action: str):
    """
    Dependency factory que verifica se o usuario tem a acao no projeto.

    Retorna dict com user_id, role e project_id.
    """

    async def _dependency(
        project_id: UUID,
        user_id: UUID = Depends(get_current_user_from_token),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        role = await resolve_user_role_in_project(user_id, project_id, db)

        if not has_action(role, action):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso negado: seu papel '{role}' nao tem permissao para '{action}'",
            )

        return {"user_id": user_id, "role": role, "project_id": project_id}

    return _dependency
