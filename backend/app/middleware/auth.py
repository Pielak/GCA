"""Authentication Middleware"""
from typing import Optional
from fastapi import HTTPException, status, Request
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
