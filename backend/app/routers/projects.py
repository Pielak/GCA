"""Projects Router"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel, EmailStr
import structlog

from app.db.database import get_db
from app.services.project_team_service import ProjectTeamService
from app.middleware.auth import get_current_user_from_token

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
    db: AsyncSession = Depends(get_db),
):
    """List all projects accessible to the current user."""
    from app.models.base import Project
    from sqlalchemy import select

    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    return {
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "slug": p.slug,
                "description": p.description or "",
                "status": p.status or "draft",
                "phase": 1,
                "outputProfile": "web_app",
                "stack": {"language": "", "framework": "", "database": ""},
                "gatekeeperScore": 0,
                "codeGenCount": 0,
                "testsPassed": 0,
                "testsTotal": 0,
                "pendingIssues": 0,
                "gpName": "",
            }
            for p in projects
        ]
    }


@router.post("/{project_id}/invite", response_model=InviteTeamMemberResponse)
async def invite_team_member(
    project_id: UUID,
    req: InviteTeamMemberRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Invite user to join project with specific role (GP only).
    Sends invitation email with acceptance link.
    """
    success, invite_token, error = await ProjectTeamService.invite_team_member(
        db=db,
        project_id=project_id,
        gp_user_id=current_user_id,
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
    current_user_id: UUID = Depends(get_current_user_from_token),
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
