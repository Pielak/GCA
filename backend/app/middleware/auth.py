"""Authentication Middleware"""
from typing import Optional
from fastapi import HTTPException, status, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import structlog

from app.core.security import verify_token

logger = structlog.get_logger(__name__)


async def get_current_user_from_token(request: Request) -> Optional[UUID]:
    """
    Extract and verify JWT token from Authorization header.
    Returns user_id if valid, raises HTTPException if invalid.
    """
    # Get authorization header
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return None

    # Expected format: "Bearer <token>"
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # Verify token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user_id from token
    user_id_str = payload.get("sub")
    if not user_id_str:
        logger.warning("auth.token_missing_user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(user_id_str)
        return user_id
    except ValueError:
        logger.warning("auth.invalid_user_id_format", user_id=user_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(
    request: Request,
    current_user_id: UUID = Depends(get_current_user_from_token),
) -> UUID:
    """
    Verifica que o usuário autenticado é admin.
    Retorna user_id se admin, 403 caso contrário.
    """
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    if not current_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == current_user_id))
        user = result.scalar_one_or_none()

    if not user or not user.is_admin:
        logger.warning("auth.admin_access_denied", user_id=str(current_user_id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )

    return current_user_id
