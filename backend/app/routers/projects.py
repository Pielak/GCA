"""Projects Router"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel, EmailStr
import structlog

from app.db.database import get_db
from app.services.project_team_service import ProjectTeamService
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_action import require_action, resolve_user_role_in_project
from app.core.permissions import get_actions_for_role

logger = structlog.get_logger(__name__)

router = APIRouter()


# Request/Response Models
class InviteTeamMemberRequest(BaseModel):
    """Request: Invite user to project"""
    email: EmailStr
    role: str  # tech_lead, dev_senior, dev_pleno, qa, compliance


class InviteTeamMemberResponse(BaseModel):
    """Response: Team member invited"""
    invite_id: str
    email: str
    role: str
    status: str = "pending"
    expires_at: str
    invite_url: str


class PendingInvite(BaseModel):
    """Pending invitation"""
    invite_id: str
    email: str
    role: str
    status: str
    invited_at: str
    expires_at: str


class PendingInvitesResponse(BaseModel):
    """Response: List of pending invites"""
    invites: list[PendingInvite]


class AcceptInviteRequest(BaseModel):
    """Request: Accept project invitation"""
    token: str


class AcceptInviteResponse(BaseModel):
    """Response: Invitation accepted"""
    project_id: str
    project_name: str
    role: str
    message: str
    first_access_required: bool


@router.get("/")
@router.get("")
async def list_projects(
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List projects accessible to the current user (filtered by membership)."""
    from app.models.base import Project, ProjectMember, User
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Verificar se é admin
    user_result = await db.execute(select(User).where(User.id == current_user_id))
    user = user_result.scalar_one_or_none()

    if user and user.is_admin:
        # Admin vê todos os projetos — com userRole indicando se é membro ou viewer
        all_projects = await db.execute(select(Project).order_by(Project.created_at.desc()))
        projects = all_projects.scalars().all()

        # Buscar memberships do admin
        admin_members = await db.execute(
            select(ProjectMember.project_id, ProjectMember.role).where(
                ProjectMember.user_id == current_user_id,
                ProjectMember.is_active == True,
            )
        )
        admin_roles = {row.project_id: row.role for row in admin_members.all()}

        return {
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "slug": p.slug,
                    "description": p.description or "",
                    "status": p.status or "draft",
                    "userRole": admin_roles.get(p.id, "admin_viewer"),
                    "phase": 1,
                    "gatekeeperScore": 0,
                }
                for p in projects
            ]
        }

    # Usuário comum: só projetos onde é membro ativo
    result = await db.execute(
        select(ProjectMember, Project)
        .join(Project, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == current_user_id,
            ProjectMember.is_active == True,
        )
        .order_by(Project.created_at.desc())
    )
    rows = result.all()

    return {
        "projects": [
            {
                "id": str(proj.id),
                "name": proj.name,
                "slug": proj.slug,
                "description": proj.description or "",
                "status": proj.status or "draft",
                "userRole": pm.role,
                "phase": 1,
                "gatekeeperScore": 0,
            }
            for pm, proj in rows
        ]
    }


@router.get("/{project_id}")
async def get_project_detail(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe de um projeto (usado pelo ProjectDetailLayout)."""
    from app.models.base import Project, ProjectMember, User
    from sqlalchemy import select

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Buscar papel do usuário no projeto
    user_result = await db.execute(select(User).where(User.id == current_user_id))
    user = user_result.scalar_one_or_none()

    role = "admin" if user and user.is_admin else None
    if not role:
        member_result = await db.execute(
            select(ProjectMember).where(
                (ProjectMember.project_id == project_id) &
                (ProjectMember.user_id == current_user_id)
            )
        )
        member = member_result.scalar_one_or_none()
        role = member.role if member else "viewer"

    return {
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description or "",
        "status": project.status or "active",
        "phase": 1,
        "language": "",
        "database": "",
        "gatekeeperScore": 0,
        "pendingIssues": 0,
        "role": role,
    }


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista membros ativos do projeto."""
    from app.models.base import Project, ProjectMember, User
    from sqlalchemy import select

    result = await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(
            (ProjectMember.project_id == project_id) &
            (ProjectMember.is_active == True)
        )
        .order_by(ProjectMember.invited_at.asc())
    )
    rows = result.all()

    return {
        "members": [
            {
                "id": str(pm.id),
                "user_id": str(pm.user_id),
                "email": u.email,
                "full_name": u.full_name or u.email.split("@")[0],
                "role": pm.role,
                "joined_at": pm.joined_at.isoformat() if pm.joined_at else pm.invited_at.isoformat() if pm.invited_at else None,
                "accepted": pm.accepted_at is not None,
            }
            for pm, u in rows
        ]
    }


@router.get("/{project_id}/pending-invites")
async def list_pending_invites_alias(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Alias: lista convites pendentes (usado pelo ProjectTeamPage)."""
    invites = await ProjectTeamService.get_pending_invites(db=db, project_id=project_id)
    return {"invites": invites}


@router.post("/{project_id}/invite", response_model=InviteTeamMemberResponse)
async def invite_team_member(
    project_id: UUID,
    req: InviteTeamMemberRequest,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Invite user to join project with specific role (GP only).
    Sends invitation email with acceptance link.
    """
    user_id = permissions["user_id"]
    success, invite_token, error = await ProjectTeamService.invite_team_member(
        db=db,
        project_id=project_id,
        gp_user_id=user_id,
        email=req.email,
        role=req.role,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    invite_url = f"https://gca.com/projects/{project_id}/accept-invite?token={invite_token}"

    return InviteTeamMemberResponse(
        invite_id=invite_token,
        email=req.email,
        role=req.role,
        status="pending",
        expires_at="7 dias",
        invite_url=invite_url,
    )


@router.get("/{project_id}/invites", response_model=PendingInvitesResponse)
async def list_pending_invites(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of pending team invitations for a project (GP only).
    """
    invites = await ProjectTeamService.get_pending_invites(
        db=db,
        project_id=project_id,
    )

    return PendingInvitesResponse(invites=invites)


@router.post("/{project_id}/accept-invite", response_model=AcceptInviteResponse)
async def accept_invite(
    project_id: UUID,
    req: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Accept project invitation (no auth required, token in request).
    User accepts team invitation and joins project.
    """
    success, project_info, error = await ProjectTeamService.accept_invite(
        db=db,
        project_id=project_id,
        token=req.token,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return AcceptInviteResponse(**project_info)


@router.post("/{project_id}/invites/{invite_id}/revoke")
async def revoke_invite(
    project_id: UUID,
    invite_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoga convite pendente (somente GP do projeto).
    Spec seção 6.1: revogar convite antes de ser aceito.
    """
    user_id = permissions["user_id"]
    success, error = await ProjectTeamService.revoke_invite(
        db=db,
        project_id=project_id,
        invite_id=invite_id,
        gp_user_id=user_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return {"message": "Convite revogado com sucesso", "invite_id": str(invite_id)}


@router.post("/{project_id}/activate")
async def activate_project_context(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Define o projeto como contexto ativo do usuário (spec seção 4.2).
    O GP vê apenas seus projetos; ao clicar, define o contexto ativo.
    """
    from sqlalchemy import select
    from datetime import datetime, timezone
    from app.models.base import ProjectMember, UserProjectContext

    # Verificar membership
    result = await db.execute(
        select(ProjectMember).where(
            (ProjectMember.project_id == project_id) &
            (ProjectMember.user_id == current_user_id) &
            (ProjectMember.is_active == True)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro deste projeto",
        )

    # Upsert contexto
    ctx_result = await db.execute(
        select(UserProjectContext).where(UserProjectContext.user_id == current_user_id)
    )
    ctx = ctx_result.scalar_one_or_none()

    if ctx:
        ctx.active_project_id = project_id
        ctx.last_selected_at = datetime.now(timezone.utc)
    else:
        ctx = UserProjectContext(
            user_id=current_user_id,
            active_project_id=project_id,
        )
        db.add(ctx)

    await db.commit()

    logger.info("project.context_activated",
                user_id=str(current_user_id),
                project_id=str(project_id))

    return {"active_project_id": str(project_id), "message": "Contexto ativo definido"}


# ============================================================================
# Questionário e OCG por projeto
# ============================================================================

@router.get("/{project_id}/questionnaire")
async def get_project_questionnaire(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o questionário associado ao projeto (respostas + score)."""
    from sqlalchemy import select
    from app.models.base import Questionnaire
    import json

    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.project_id == project_id)
        .order_by(Questionnaire.submitted_at.desc())
        .limit(1)
    )
    q = result.scalar_one_or_none()

    if not q:
        return {"questionnaire": None, "message": "Nenhum questionário vinculado a este projeto"}

    try:
        responses = json.loads(q.responses) if q.responses else {}
    except json.JSONDecodeError:
        responses = {}

    try:
        validations = json.loads(q.validations) if q.validations else {}
    except json.JSONDecodeError:
        validations = {}

    return {
        "questionnaire": {
            "id": str(q.id),
            "gp_email": q.gp_email,
            "responses": responses,
            "adherence_score": q.adherence_score,
            "status": q.status,
            "approved": q.approved,
            "validations": validations,
            "observations": q.observations,
            "restrictions": q.restrictions,
            "submitted_at": q.submitted_at.isoformat() if q.submitted_at else None,
            "analyzed_at": q.analyzed_at.isoformat() if q.analyzed_at else None,
        }
    }


@router.get("/{project_id}/ocg")
async def get_project_ocg(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o OCG mais recente do projeto."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    result = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc())
        .limit(1)
    )
    ocg = result.scalar_one_or_none()

    if not ocg:
        return {
            "ocg": None,
            "message": "OCG ainda não gerado para este projeto. Aguardando análise do questionário."
        }

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except json.JSONDecodeError:
        ocg_data = {}

    return {
        "ocg": {
            "id": str(ocg.id),
            "version": getattr(ocg, 'version', 1),
            "schema_version": getattr(ocg, 'schema_version', '1.0.0'),
            "overall_score": ocg.overall_score,
            "p1_business_score": ocg.p1_business_score,
            "p2_rules_score": ocg.p2_rules_score,
            "p3_features_score": ocg.p3_features_score,
            "p4_nfr_score": ocg.p4_nfr_score,
            "p5_architecture_score": ocg.p5_architecture_score,
            "p6_data_score": ocg.p6_data_score,
            "p7_security_score": ocg.p7_security_score,
            "status": ocg.status,
            "is_blocking": ocg.is_blocking,
            "ocg_data": ocg_data,
            "generated_at": ocg.generated_at.isoformat() if ocg.generated_at else None,
        }
    }


@router.get("/{project_id}/ocg/history")
async def get_ocg_history(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de versões do OCG."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog

    result = await db.execute(
        select(OCGDeltaLog)
        .where(OCGDeltaLog.project_id == project_id)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(50)
    )
    deltas = result.scalars().all()
    return {
        "history": [
            {
                "version_from": d.ocg_version_from,
                "version_to": d.ocg_version_to,
                "change_summary": d.change_summary,
                "fields_changed": d.fields_changed,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deltas
        ]
    }


@router.get("/{project_id}/ocg/health")
async def get_ocg_health(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Saúde do contexto OCG."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = result.scalar_one_or_none()
    if not ocg:
        return {"health": None, "message": "OCG não encontrado"}

    health = {}
    if hasattr(ocg, 'context_health') and ocg.context_health:
        try:
            health = json.loads(ocg.context_health)
        except json.JSONDecodeError:
            pass

    return {
        "health": health,
        "version": getattr(ocg, 'version', 1),
        "change_type": getattr(ocg, 'change_type', 'INITIAL'),
        "overall_score": ocg.overall_score,
        "status": ocg.status,
    }


@router.post("/{project_id}/ocg/propagate")
async def force_propagation(
    project_id: UUID,
    permissions: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """Forçar re-propagação do OCG para módulos dependentes."""
    from app.services.propagation_service import PropagationService
    propagator = PropagationService(db)
    result = await propagator.propagate(project_id, changes=[{"field": "MANUAL_PROPAGATION"}])
    return result


@router.get("/{project_id}/billing")
async def get_project_billing(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Resumo de gastos de IA do projeto."""
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(db)
    return await billing.get_project_summary(project_id)


@router.get("/{project_id}/billing/detail")
async def get_project_billing_detail(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Log detalhado de chamadas IA do projeto."""
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(db)
    entries = await billing.get_project_detail(project_id, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/projects/{project_id}/permissions")
async def get_user_permissions(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o papel e acoes do usuario no projeto."""
    role = await resolve_user_role_in_project(user_id, project_id, db)
    actions = get_actions_for_role(role)
    return {
        "role": role,
        "actions": sorted(actions),
        "is_read_only": role == "admin_viewer" or actions <= {"project:view", "project:manage_gp"},
    }
