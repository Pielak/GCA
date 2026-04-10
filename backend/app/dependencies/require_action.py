"""
Dependency FastAPI para verificar permissoes por acao.

Suporta multiplos papeis por membro. Acoes sao acumuladas de todos os papeis.

Uso:
    @router.post("/projects/{project_id}/settings")
    async def update_settings(
        project_id: UUID,
        permissions: dict = Depends(require_action("project:edit")),
    ):
        user_id = permissions["user_id"]
        roles = permissions["roles"]
"""
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import has_action_any
from app.db.database import get_db
from app.dependencies.project_access import get_user_project_roles
from app.middleware.auth import get_current_user_from_token
from app.models.base import User


async def _get_user_is_admin(user_id: UUID, db: AsyncSession) -> bool:
    result = await db.execute(select(User.is_admin).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row is True


async def resolve_user_roles_in_project(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> list[str]:
    """
    Resolve os papeis efetivos do usuario no projeto.

    - Se e membro -> retorna lista de papeis (base + adicionais)
    - Se NAO e membro mas e Admin -> retorna ['admin_viewer']
    - Se NAO e membro e NAO e Admin -> 403
    """
    roles = await get_user_project_roles(user_id, project_id, db)

    if roles:
        return roles

    is_admin = await _get_user_is_admin(user_id, db)
    if is_admin:
        return ["admin_viewer"]

    raise HTTPException(
        status_code=403,
        detail="Acesso negado: voce nao e membro deste projeto",
    )


async def resolve_user_role_in_project(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> str:
    """Compatibilidade: retorna primeiro papel da lista."""
    roles = await resolve_user_roles_in_project(user_id, project_id, db)
    return roles[0] if roles else "admin_viewer"


def require_action(action: str):
    """
    Dependency factory que verifica se o usuario tem a acao no projeto.

    Retorna dict com user_id, roles, role e project_id.
    """

    async def _dependency(
        project_id: UUID,
        user_id: UUID = Depends(get_current_user_from_token),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        roles = await resolve_user_roles_in_project(user_id, project_id, db)

        if not has_action_any(roles, action):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso negado: seus papeis {roles} nao tem permissao para '{action}'",
            )

        return {"user_id": user_id, "roles": roles, "role": roles[0], "project_id": project_id}

    return _dependency
