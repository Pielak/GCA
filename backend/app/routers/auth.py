"""Authentication Router"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.db.database import get_db
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    LoginUserInfo,
    ProjectRole,
    RefreshTokenRequest,
    BootstrapAdminRequest,
    UserResponse,
    ChangePasswordRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyResetTokenRequest,
    VerifyResetTokenResponse,
    ConfirmPasswordResetRequest,
    ConfirmPasswordResetResponse,
    ChangeFirstPasswordRequest,
    ChangeFirstPasswordResponse,
    PasswordRequirementsResponse,
)
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.core.security import verify_token, verify_password, hash_password
from app.core.config import settings
from app.models.base import User
from app.middleware.auth import get_current_user_from_token
from uuid import UUID

logger = structlog.get_logger(__name__)

router = APIRouter()


async def _get_user_project_roles(db: AsyncSession, user_id: UUID) -> list[ProjectRole]:
    """Busca projetos e papéis do usuário."""
    from app.models.base import ProjectMember, Project

    result = await db.execute(
        select(ProjectMember, Project)
        .join(Project, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id)
    )
    rows = result.all()
    return [
        ProjectRole(
            project_id=str(pm.project_id),
            project_name=proj.name,
            project_slug=proj.slug or "",
            role=pm.role,
            status=proj.status or "active",
        )
        for pm, proj in rows
    ]


@router.post("/bootstrap-admin", response_model=LoginResponse)
async def bootstrap_admin(
    req: BootstrapAdminRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Bootstrap the first admin user.
    Only works if no users exist in the system.
    """
    success, user, error = await AuthService.bootstrap_admin(
        db=db,
        email=req.email,
        full_name=req.full_name,
        password=req.password,
    )

    if not success:
        logger.warning("auth.bootstrap_admin_failed_request", error=error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Create tokens
    access_token, refresh_token, expires_in = AuthService.create_tokens(user)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        user=LoginUserInfo(
            id=str(user.id), email=user.email, full_name=user.full_name,
            is_admin=user.is_admin, is_active=user.is_active,
            first_access_completed=user.first_access_completed,
        ),
    )


@router.get("/projects")
async def list_active_projects_for_login(
    db: AsyncSession = Depends(get_db),
):
    """Lista pública de projetos ativos para popular o combo da página de login.

    Não exige autenticação — usuário ainda nem entrou. Devolve apenas dados
    mínimos (id, name, slug) para o seletor. Projetos arquivados/inativos
    não aparecem.
    """
    from app.models.base import Project
    result = await db.execute(
        select(Project)
        .where(Project.status == "active")
        .order_by(Project.name)
    )
    projects = result.scalars().all()
    return {
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "slug": p.short_slug or p.slug,
            }
            for p in projects
        ],
        "count": len(projects),
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login SEM contexto de projeto — exclusivo para administradores.

    Para login de membros de projeto, usar /auth/project-login (com slug do
    projeto). Esta rota rejeita não-admins com 403, redirecionando o caller
    para o fluxo correto.
    """
    success, user, error = await AuthService.login(
        db=db,
        email=req.email,
        password=req.password,
    )

    if not success:
        # Generic error message for security
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha inválidos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Não-admin sem projeto selecionado: bloqueia + sinaliza ao frontend
    # mostrar combo de projetos.
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "project_required",
                "message": "Selecione um projeto para entrar (apenas administradores podem entrar sem projeto).",
            },
        )

    # Create tokens
    access_token, refresh_token, expires_in = AuthService.create_tokens(user)

    # Buscar projetos e papéis do usuário (admin pode ter projetos também)
    project_roles = await _get_user_project_roles(db, user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        user=LoginUserInfo(
            id=str(user.id), email=user.email, full_name=user.full_name,
            is_admin=user.is_admin, is_active=user.is_active,
            first_access_completed=user.first_access_completed,
            project_roles=project_roles,
        ),
    )


class ProjectLoginRequest(BaseModel):
    """Request: Login com contexto de projeto"""
    email: str
    password: str
    project_slug: str


@router.post("/project-login")
async def project_login(
    req: ProjectLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Login com contexto de projeto via short_slug.
    Valida credenciais + membership no projeto.
    Retorna JWT com project_id e project_slug no payload.
    """
    from app.models.base import Project, ProjectMember

    # 1. Resolver project_slug → Project
    result = await db.execute(
        select(Project).where(Project.short_slug == req.project_slug)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado",
        )

    if project.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Projeto arquivado",
        )

    # 2. Autenticar usuário (email + password) — lógica existente
    success, user, error = await AuthService.login(
        db=db,
        email=req.email,
        password=req.password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha inválidos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Verificar membership no projeto
    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.is_active == True,
        )
    )
    member = member_result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro deste projeto",
        )

    # 4. Criar tokens com contexto de projeto no JWT
    access_token, refresh_token, expires_in = AuthService.create_tokens(
        user,
        project_id=str(project.id),
        project_slug=project.short_slug,
    )

    # Buscar papel do usuário no projeto
    project_roles = await _get_user_project_roles(db, user.id)

    logger.info(
        "auth.project_login_success",
        user_id=str(user.id),
        project_id=str(project.id),
        project_slug=project.short_slug,
        role=member.role,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "first_access_completed": user.first_access_completed,
            "project_roles": [pr.model_dump() if hasattr(pr, 'model_dump') else pr.dict() for pr in project_roles],
        },
        "project": {
            "id": str(project.id),
            "name": project.name,
            "short_slug": project.short_slug,
            "status": project.status,
            "role": member.role,
        },
    }


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    req: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using refresh token.
    """
    success, new_access_token, error = await AuthService.refresh_access_token(
        db=db,
        refresh_token=req.refresh_token,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de atualização inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the new token to get user info for expires_in
    payload = verify_token(new_access_token)
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return LoginResponse(
        access_token=new_access_token,
        refresh_token=req.refresh_token,  # Refresh token remains the same
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    req: ChangePasswordRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Change current user's password.
    Requires valid access token.
    """
    user_id = current_user_id

    success, error = await AuthService.change_password(
        db=db,
        user_id=user_id,
        current_password=req.current_password,
        new_password=req.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return None


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Request password reset token (forgot password flow).
    Always returns 200 OK for security (no email enumeration).
    """
    success, token, error = await AuthService.request_password_reset(
        db=db,
        email=req.email,
    )

    if success and token:
        # Send reset email
        EmailService.send_password_reset_email(
            user_email=req.email,
            user_name="Usuário",  # Would be fetched in real scenario
            reset_link=f"{settings.FRONTEND_URL}/reset-password?token={token}",
        )

    return ResetPasswordResponse(
        message="Se o email existe no sistema, um link de recuperação foi enviado"
    )


@router.post("/verify-reset-token", response_model=VerifyResetTokenResponse)
async def verify_reset_token(
    req: VerifyResetTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify reset token is valid and not expired/used.
    """
    valid, user_id, error = await AuthService.verify_reset_token(
        db=db,
        token=req.token,
    )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Token inválido ou expirado",
        )

    return VerifyResetTokenResponse(
        valid=True,
        message="Token válido, proceda com a alteração de senha",
    )


@router.post("/reset-password-confirm", response_model=ConfirmPasswordResetResponse)
async def confirm_password_reset(
    req: ConfirmPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm password reset with token and new password.
    """
    success, error = await AuthService.confirm_password_reset(
        db=db,
        token=req.token,
        new_password=req.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return ConfirmPasswordResetResponse()


@router.post("/change-first-password", response_model=ChangeFirstPasswordResponse)
async def change_first_password(
    req: ChangeFirstPasswordRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Change temporary password on first login (mandatory).
    Requires valid access token.
    """
    success, user, error = await AuthService.change_first_password(
        db=db,
        user_id=current_user_id,
        temporary_password=req.temporary_password,
        new_password=req.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return ChangeFirstPasswordResponse(user=user)


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user's profile.
    Requires valid access token.
    """
    user_id = current_user_id

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )

    return user


@router.get("/password-requirements", response_model=PasswordRequirementsResponse)
async def get_password_requirements():
    """
    Get password requirements for UI display.
    Can be called without authentication to show requirements on login/reset screens.
    """
    symbols_allowed = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    instructions = (
        f"A senha deve ter:\n"
        f"• Mínimo de {settings.PASSWORD_MIN_LENGTH} caracteres\n"
    )

    if settings.PASSWORD_REQUIRE_UPPERCASE:
        instructions += "• Pelo menos 1 letra maiúscula (A-Z)\n"

    if settings.PASSWORD_REQUIRE_LOWERCASE:
        instructions += "• Pelo menos 1 letra minúscula (a-z)\n"

    if settings.PASSWORD_REQUIRE_DIGITS:
        instructions += "• Pelo menos 1 número (0-9)\n"

    if settings.PASSWORD_REQUIRE_SYMBOLS:
        instructions += f"• Pelo menos 1 caractere especial: {symbols_allowed}\n"

    return PasswordRequirementsResponse(
        min_length=settings.PASSWORD_MIN_LENGTH,
        require_uppercase=settings.PASSWORD_REQUIRE_UPPERCASE,
        require_lowercase=settings.PASSWORD_REQUIRE_LOWERCASE,
        require_digits=settings.PASSWORD_REQUIRE_DIGITS,
        require_symbols=settings.PASSWORD_REQUIRE_SYMBOLS,
        symbols_allowed=symbols_allowed,
        instructions=instructions.strip(),
    )


# ============================================================================
# Invitation Token Flow (RF-001)
# ============================================================================

class ValidateInvitationRequest(BaseModel):
    token: str
    temporary_password: str

class ValidateInvitationResponse(BaseModel):
    valid: bool
    email: str | None = None
    message: str | None = None

class SetPermanentPasswordRequest(BaseModel):
    token: str
    temporary_password: str
    new_password: str

class SetPermanentPasswordResponse(BaseModel):
    success: bool
    message: str = "Conta criada com sucesso"


@router.post("/validate-invitation-token", response_model=ValidateInvitationResponse)
async def validate_invitation_token(
    req: ValidateInvitationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1: Validate invitation token + temporary password.
    Token expires in 2 hours. Max 3 failed attempts.
    """
    from app.models.base import InvitationToken
    from datetime import datetime, timezone

    # Find invitation by token
    result = await db.execute(
        select(InvitationToken).where(
            InvitationToken.token == req.token,
            InvitationToken.is_used == False,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        return ValidateInvitationResponse(valid=False, message="Token de convite invalido ou ja utilizado")

    # Check expiration
    if invitation.expires_at < datetime.now(timezone.utc):
        return ValidateInvitationResponse(valid=False, message="Token expirado. Solicite um novo convite ao administrador.")

    # Check max attempts
    if invitation.validation_attempts >= 3:
        return ValidateInvitationResponse(valid=False, message="Maximo de tentativas excedido. Solicite um novo convite.")

    # Validate temporary password
    if not verify_password(req.temporary_password, invitation.temporary_password_hash):
        invitation.validation_attempts += 1
        await db.commit()
        remaining = 3 - invitation.validation_attempts
        logger.warning("auth.invitation_validation_failed", email=invitation.email, attempts=invitation.validation_attempts)
        return ValidateInvitationResponse(valid=False, message=f"Senha temporaria incorreta. {remaining} tentativa(s) restante(s).")

    logger.info("auth.invitation_validated", email=invitation.email)
    return ValidateInvitationResponse(valid=True, email=invitation.email)


@router.post("/set-permanent-password-from-invitation", response_model=SetPermanentPasswordResponse)
async def set_permanent_password_from_invitation(
    req: SetPermanentPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2: Set permanent password and create user account.
    Requires valid token + correct temporary password.
    After this, the invitation token is marked as used and the user is created.
    """
    from app.models.base import InvitationToken
    from app.core.security import validate_password_strength
    from datetime import datetime, timezone

    # Validate new password strength
    is_valid, error_msg = validate_password_strength(req.new_password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # Find and validate invitation
    result = await db.execute(
        select(InvitationToken).where(
            InvitationToken.token == req.token,
            InvitationToken.is_used == False,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token invalido")

    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token expirado")

    if not verify_password(req.temporary_password, invitation.temporary_password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha temporaria incorreta")

    # Check user doesn't already exist
    result = await db.execute(select(User).where(User.email == invitation.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario ja existe")

    # Create user with permanent password
    from uuid import uuid4
    new_user = User(
        id=uuid4(),
        email=invitation.email,
        full_name=invitation.full_name,
        password_hash=hash_password(req.new_password),
        is_admin=(invitation.role == "admin"),
        is_active=True,
        first_access_completed=True,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(new_user)

    # Mark invitation as used
    invitation.is_used = True
    await db.commit()

    logger.info("auth.user_created_from_invitation", email=invitation.email, user_id=str(new_user.id))

    return SetPermanentPasswordResponse(success=True, message="Conta criada com sucesso")
