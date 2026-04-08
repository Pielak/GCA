"""User schemas (request/response)"""
from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Request: Create a new user"""
    email: EmailStr
    full_name: str
    password: str = Field(
        ...,
        description="Senha deve ter: mínimo 10 caracteres, pelo menos 1 letra maiúscula, 1 número e 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"
    )


class UserUpdate(BaseModel):
    """Request: Update user"""
    full_name: Optional[str] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    """Response: User data"""
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserDetailedResponse(UserResponse):
    """Response: User with all details"""
    organizations: list[UUID] = []
    projects: dict[UUID, list[str]] = {}


class LoginRequest(BaseModel):
    """Request: User login"""
    email: EmailStr
    password: str


class LoginUserInfo(BaseModel):
    """User info returned on login"""
    id: str
    email: str
    full_name: str | None = None
    is_admin: bool = False
    is_active: bool = True
    first_access_completed: bool = False


class LoginResponse(BaseModel):
    """Response: Login successful"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: LoginUserInfo | None = None


class RefreshTokenRequest(BaseModel):
    """Request: Refresh access token"""
    refresh_token: str


class BootstrapAdminRequest(BaseModel):
    """Request: Bootstrap first admin user (no password required in system yet)"""
    email: EmailStr
    full_name: str
    password: str = Field(
        ...,
        description="Senha deve ter: mínimo 10 caracteres, pelo menos 1 letra maiúscula, 1 número e 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"
    )


class ChangePasswordRequest(BaseModel):
    """Request: Change user password"""
    current_password: str
    new_password: str = Field(
        ...,
        description="Senha deve ter: mínimo 10 caracteres, pelo menos 1 letra maiúscula, 1 número e 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"
    )


class ResetPasswordRequest(BaseModel):
    """Request: Request password reset link (forgot password)"""
    email: EmailStr


class ResetPasswordResponse(BaseModel):
    """Response: Password reset link sent"""
    message: str
    security_note: str = "Por segurança, não confirmamos se o email existe no sistema"


class VerifyResetTokenRequest(BaseModel):
    """Request: Verify reset token is valid"""
    token: str


class VerifyResetTokenResponse(BaseModel):
    """Response: Token validity"""
    valid: bool
    message: str


class ConfirmPasswordResetRequest(BaseModel):
    """Request: Confirm password reset with token and new password"""
    token: str
    new_password: str = Field(
        ...,
        description="Senha deve ter: mínimo 10 caracteres, pelo menos 1 letra maiúscula, 1 número e 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"
    )


class ConfirmPasswordResetResponse(BaseModel):
    """Response: Password reset successful"""
    message: str = "Senha alterada com sucesso. Faça login com a nova senha"


class ChangeFirstPasswordRequest(BaseModel):
    """Request: Change temporary password on first login (mandatory)"""
    temporary_password: str
    new_password: str = Field(
        ...,
        description="Senha deve ter: mínimo 10 caracteres, pelo menos 1 letra maiúscula, 1 número e 1 caractere especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"
    )


class ChangeFirstPasswordResponse(BaseModel):
    """Response: First password change successful"""
    message: str = "Senha alterada com sucesso. Bem-vindo ao GCA!"
    user: UserResponse


class PasswordRequirementsResponse(BaseModel):
    """Response: Password requirements for UI display"""
    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_digits: bool
    require_symbols: bool
    symbols_allowed: str
    instructions: str
