"""
Dependency para verificação de acesso a projetos.
Admin sem papel no projeto = 403 (apenas audit log).
"""
from uuid import UUID
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import ProjectMember, User

logger = structlog.get_logger(__name__)


async def get_user_project_role(
    user_id: UUID,
    project_id: UUID,
    db: AsyncSession,
) -> str | None:
    """
    Retorna o papel do usuário no projeto ('gp', 'developer', 'qa', 'tester', 'viewer')
    ou None se o usuário não tem papel no projeto.
    """
    result = await db.execute(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.accepted_at.isnot(None),  # Só membros que aceitaram
        )
    )
    row = result.scalar_one_or_none()
    return row


async def verify_project_access(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession,
    required_roles: list[str] | None = None,
) -> str:
    """
    Verifica se o usuário tem acesso ao projeto e retorna seu papel.

    Lógica:
    1. Se user é admin global:
       a. Sem papel no projeto → 403 (só pode ver audit log)
       b. Com papel → continua como usuário normal com aquele papel
    2. Se user não é admin:
       a. Sem papel → 403
       b. Com papel → verifica required_roles
    3. Retorna o papel do usuário
    """
    # Buscar dados do usuário
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )

    # Buscar papel no projeto
    role = await get_user_project_role(user_id, project_id, db)

    if user.is_admin and role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não está cadastrado neste projeto. "
                   "Como admin, você tem acesso apenas ao log de auditoria.",
        )

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não é membro deste projeto.",
        )

    if required_roles and role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado: seu papel '{role}' não tem permissão. "
                   f"Papéis necessários: {', '.join(required_roles)}.",
        )

    return role
