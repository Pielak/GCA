"""Authentication Service"""
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
import secrets

from app.models.base import User, ResetToken
from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    create_refresh_token,
    verify_token,
    TokenPayload,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)


class AuthService:
    """Authentication service for user login, signup, token management"""

    @staticmethod
    async def bootstrap_admin(
        db: AsyncSession,
        email: str,
        full_name: str,
        password: str,
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Bootstrap the first admin user (typically done once during setup).
        Returns (success, user, error_message)
        """
        # Check if any users exist
        result = await db.execute(select(User))
        existing_users = result.scalars().all()
        if len(existing_users) > 0:
            error_msg = "Cannot bootstrap admin: users already exist"
            logger.warning("auth.bootstrap_failed", reason=error_msg)
            return False, None, error_msg

        # Validate password strength
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            logger.warning("auth.bootstrap_weak_password", error=error_msg)
            return False, None, error_msg

        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            error_msg = "Email already registered"
            logger.warning("auth.bootstrap_email_exists", email=email)
            return False, None, error_msg

        # Create admin user
        try:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                is_active=True,
                is_admin=True,
                first_access_completed=True,
                password_changed_at=datetime.now(timezone.utc),
                last_login_at=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            logger.info("auth.bootstrap_admin_created", user_id=str(user.id), email=email)
            return True, user, None

        except Exception as e:
            await db.rollback()
            logger.error("auth.bootstrap_admin_failed", error=str(e))
            return False, None, str(e)

    @staticmethod
    async def login(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Authenticate user by email and password.
        Returns (success, user, error_message)
        """
        # Find user by email
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            logger.warning("auth.login_user_not_found", email=email)
            return False, None, "Invalid email or password"

        if not user.is_active:
            logger.warning("auth.login_user_inactive", user_id=str(user.id), email=email)
            return False, None, "User account is inactive"

        # Verify password
        if not verify_password(password, user.password_hash):
            logger.warning("auth.login_invalid_password", email=email)
            return False, None, "Invalid email or password"

        # Update last login
        try:
            user.last_login_at = datetime.now(timezone.utc)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info("auth.login_success", user_id=str(user.id), email=email)
            return True, user, None
        except Exception as e:
            await db.rollback()
            logger.error("auth.login_failed", email=email, error=str(e))
            return False, None, str(e)

    @staticmethod
    def create_tokens(
        user: User,
        project_id: Optional[str] = None,
        project_slug: Optional[str] = None,
    ) -> Tuple[str, str, int]:
        """
        Create access and refresh tokens for user.
        Opcionalmente inclui project_id e project_slug no payload JWT
        para login com contexto de projeto.
        Returns (access_token, refresh_token, expires_in_seconds)
        """
        # Prepare token payload
        token_payload = TokenPayload(
            user_id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            organizations=[],  # Will be loaded from DB if needed
            projects={},  # Will be loaded from DB if needed
            exp=datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

        token_data = token_payload.to_dict()

        # Incluir contexto de projeto no JWT, se fornecido
        if project_id:
            token_data["project_id"] = project_id
        if project_slug:
            token_data["project_slug"] = project_slug

        # Create tokens
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(user.id)
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        logger.info("auth.tokens_created", user_id=str(user.id), project_id=project_id)
        return access_token, refresh_token, expires_in

    @staticmethod
    async def refresh_access_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create new access token from refresh token.
        Returns (success, new_access_token, error_message)
        """
        # Verify refresh token
        payload = verify_token(refresh_token, token_type="refresh")
        if not payload:
            logger.warning("auth.refresh_token_invalid")
            return False, None, "Invalid refresh token"

        # Get user
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("auth.refresh_token_no_user")
            return False, None, "Invalid refresh token"

        try:
            result = await db.execute(select(User).where(User.id == UUID(user_id)))
            user = result.scalar_one_or_none()
            if not user:
                logger.warning("auth.refresh_token_user_not_found", user_id=user_id)
                return False, None, "User not found"

            if not user.is_active:
                logger.warning("auth.refresh_token_user_inactive", user_id=user_id)
                return False, None, "User account is inactive"

            # Create new access token
            token_payload = TokenPayload(
                user_id=user.id,
                email=user.email,
                is_admin=user.is_admin,
                organizations=[],
                projects={},
                exp=datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            )
            new_access_token = create_access_token(token_payload.to_dict())

            logger.info("auth.access_token_refreshed", user_id=str(user.id))
            return True, new_access_token, None

        except Exception as e:
            logger.error("auth.refresh_failed", error=str(e))
            return False, None, str(e)

    @staticmethod
    def verify_current_password(user: User, password: str) -> bool:
        """Verify that provided password matches user's current password"""
        return verify_password(password, user.password_hash)

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Change user password.
        Returns (success, error_message)
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return False, "User not found"

        # Verify current password
        if not verify_password(current_password, user.password_hash):
            logger.warning("auth.change_password_invalid_current", user_id=str(user_id))
            return False, "Current password is incorrect"

        # Validate new password strength
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg

        # Update password
        try:
            user.password_hash = hash_password(new_password)
            user.updated_at = datetime.now(timezone.utc)
            db.add(user)
            await db.commit()

            logger.info("auth.password_changed", user_id=str(user_id))
            return True, None

        except Exception as e:
            await db.rollback()
            logger.error("auth.change_password_failed", user_id=str(user_id), error=str(e))
            return False, str(e)

    @staticmethod
    async def request_password_reset(
        db: AsyncSession,
        email: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Request password reset token for email.
        Returns (success, reset_token, error_message)
        Note: Always returns success for security (no email enumeration)
        """
        try:
            # Find user by email (silently skip if not found)
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if not user:
                logger.info("auth.reset_password_requested_nonexistent_email", email=email)
                return True, None, None

            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            # Create reset token entry
            reset_token = ResetToken(
                user_id=user.id,
                token=token,
                expires_at=expires_at,
                used=False,
            )
            db.add(reset_token)
            await db.commit()
            await db.refresh(reset_token)

            logger.info("auth.reset_password_token_created", user_id=str(user.id), email=email)
            return True, token, None

        except Exception as e:
            await db.rollback()
            logger.error("auth.request_password_reset_failed", email=email, error=str(e))
            return True, None, None  # Still return success for security

    @staticmethod
    async def verify_reset_token(
        db: AsyncSession,
        token: str,
    ) -> Tuple[bool, Optional[UUID], Optional[str]]:
        """
        Verify reset token is valid and not expired/used.
        Returns (valid, user_id, error_message)
        """
        try:
            result = await db.execute(
                select(ResetToken).where(ResetToken.token == token)
            )
            reset_token = result.scalar_one_or_none()

            if not reset_token:
                logger.warning("auth.verify_reset_token_not_found")
                return False, None, "Token não encontrado"

            if reset_token.used:
                logger.warning("auth.verify_reset_token_already_used")
                return False, None, "Token já foi utilizado"

            if reset_token.expires_at < datetime.now(timezone.utc):
                logger.warning("auth.verify_reset_token_expired")
                return False, None, "Token expirado"

            return True, reset_token.user_id, None

        except Exception as e:
            logger.error("auth.verify_reset_token_failed", error=str(e))
            return False, None, str(e)

    @staticmethod
    async def confirm_password_reset(
        db: AsyncSession,
        token: str,
        new_password: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Confirm password reset with token and new password.
        Returns (success, error_message)
        """
        try:
            # Verify token
            valid, user_id, error = await AuthService.verify_reset_token(db, token)
            if not valid:
                return False, error

            # Validate new password
            is_valid, error_msg = validate_password_strength(new_password)
            if not is_valid:
                return False, error_msg

            # Get user
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return False, "Usuário não encontrado"

            # Update password and mark token as used
            result = await db.execute(
                select(ResetToken).where(ResetToken.token == token)
            )
            reset_token = result.scalar_one_or_none()

            user.password_hash = hash_password(new_password)
            user.password_changed_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)

            reset_token.used = True
            reset_token.used_at = datetime.now(timezone.utc)

            db.add(user)
            db.add(reset_token)
            await db.commit()

            logger.info("auth.password_reset_completed", user_id=str(user_id))
            return True, None

        except Exception as e:
            await db.rollback()
            logger.error("auth.confirm_password_reset_failed", error=str(e))
            return False, str(e)

    @staticmethod
    async def change_first_password(
        db: AsyncSession,
        user_id: UUID,
        temporary_password: str,
        new_password: str,
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Change first access temporary password (mandatory on first login).
        Returns (success, user, error_message)
        """
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return False, None, "Usuário não encontrado"

            # Verify temporary password
            if not verify_password(temporary_password, user.password_hash):
                logger.warning("auth.change_first_password_invalid_temp", user_id=str(user_id))
                return False, None, "Senha temporária incorreta"

            # Validate new password
            is_valid, error_msg = validate_password_strength(new_password)
            if not is_valid:
                return False, None, error_msg

            # Update password and mark first access as complete
            user.password_hash = hash_password(new_password)
            user.password_changed_at = datetime.now(timezone.utc)
            user.first_access_completed = True
            user.updated_at = datetime.now(timezone.utc)

            db.add(user)
            await db.commit()
            await db.refresh(user)

            logger.info("auth.first_password_changed", user_id=str(user_id))
            return True, user, None

        except Exception as e:
            await db.rollback()
            logger.error("auth.change_first_password_failed", user_id=str(user_id), error=str(e))
            return False, None, str(e)
