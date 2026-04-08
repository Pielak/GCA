"""Project Team Management Service"""
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional, Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
import secrets

from app.models.base import User, Project, ProjectMember
from app.core.security import hash_password
from app.services.email_service import EmailService

logger = structlog.get_logger(__name__)


class ProjectTeamService:
    """Service for managing project team members and invitations"""

    @staticmethod
    async def invite_team_member(
        db: AsyncSession,
        project_id: UUID,
        gp_user_id: UUID,
        email: str,
        role: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Invite user to join project (GP invites team member).
        Returns (success, invite_token, error_message)
        """
        try:
            # Verify GP is actually a project GP
            result = await db.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id) &
                    (ProjectMember.user_id == gp_user_id) &
                    (ProjectMember.role == "gp")
                )
            )
            gp_member = result.scalar_one_or_none()
            if not gp_member:
                logger.warning("project_team.invite_not_gp", gp_user_id=str(gp_user_id))
                return False, None, "Apenas GPs podem convidar membros para o projeto"

            # Get project details
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                return False, None, "Projeto não encontrado"

            # Check if user already in project
            result = await db.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id) &
                    (ProjectMember.user_id == email) |  # Check by email or user_id
                    (ProjectMember.user_id.in_(
                        select(User.id).where(User.email == email)
                    ))
                )
            )
            existing_member = result.scalar_one_or_none()
            if existing_member:
                logger.warning("project_team.user_already_member", email=email)
                return False, None, "Usuário já é membro do projeto"

            # Find or create user
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if not user:
                # Create new user with temporary password
                temp_password = secrets.token_urlsafe(12)
                user = User(
                    email=email,
                    full_name=email.split("@")[0],  # Use email prefix as default name
                    password_hash=hash_password(temp_password),
                    is_active=True,
                    is_admin=False,
                    first_access_completed=False,
                )
                db.add(user)
                await db.flush()
            else:
                temp_password = None

            # Create invitation token
            invite_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)

            project_member = ProjectMember(
                project_id=project_id,
                user_id=user.id,
                role=role,
                invited_by=gp_user_id,
                invite_token=invite_token,
                invite_expires_at=expires_at,
            )
            db.add(project_member)
            await db.commit()

            # Get GP name for email
            result = await db.execute(select(User).where(User.id == gp_user_id))
            gp_user = result.scalar_one_or_none()
            gp_name = gp_user.full_name if gp_user else "Gestor do Projeto"

            # Send invitation email
            accept_link = f"https://gca.com/projects/{project_id}/accept-invite?token={invite_token}"
            EmailService.send_team_invitation_email(
                to_email=email,
                user_name=user.full_name,
                project_name=project.name,
                gp_name=gp_name,
                role_name=role.replace("_", " ").title(),
                accept_link=accept_link,
            )

            logger.info("project_team.member_invited", project_id=str(project_id), email=email)
            return True, invite_token, None

        except Exception as e:
            await db.rollback()
            logger.error("project_team.invite_failed", error=str(e))
            return False, None, str(e)

    @staticmethod
    async def get_pending_invites(
        db: AsyncSession,
        project_id: UUID,
    ) -> List[dict]:
        """Get list of pending invitations for a project"""
        try:
            result = await db.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == project_id) &
                    (ProjectMember.accepted_at == None)  # Pending
                )
            )
            members = result.scalars().all()

            invites = []
            for member in members:
                # Get user email
                user_result = await db.execute(
                    select(User).where(User.id == member.user_id)
                )
                user = user_result.scalar_one_or_none()

                if user:
                    invites.append({
                        "invite_id": str(member.id),
                        "email": user.email,
                        "role": member.role,
                        "status": "pending",
                        "invited_at": member.invited_at.isoformat() if member.invited_at else None,
                        "expires_at": member.invite_expires_at.isoformat() if member.invite_expires_at else None,
                    })

            return invites

        except Exception as e:
            logger.error("project_team.get_invites_failed", error=str(e))
            return []

    @staticmethod
    async def accept_invite(
        db: AsyncSession,
        project_id: UUID,
        token: str,
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Accept project invitation (user accepts team invitation).
        Returns (success, project_info, error_message)
        """
        try:
            # Find invitation by token
            result = await db.execute(
                select(ProjectMember).where(
                    (ProjectMember.invite_token == token) &
                    (ProjectMember.project_id == project_id)
                )
            )
            member = result.scalar_one_or_none()

            if not member:
                logger.warning("project_team.accept_invite_not_found")
                return False, None, "Convite não encontrado"

            # Check if expired
            if member.invite_expires_at and member.invite_expires_at < datetime.now(timezone.utc):
                logger.warning("project_team.accept_invite_expired")
                return False, None, "Convite expirado"

            # Check if already accepted
            if member.accepted_at:
                logger.warning("project_team.accept_invite_already_accepted")
                return False, None, "Convite já foi aceito"

            # Mark as accepted
            member.accepted_at = datetime.now(timezone.utc)
            member.joined_at = datetime.now(timezone.utc)
            db.add(member)

            # Get project info
            project_result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = project_result.scalar_one_or_none()

            # Get user info
            user_result = await db.execute(
                select(User).where(User.id == member.user_id)
            )
            user = user_result.scalar_one_or_none()

            await db.commit()

            project_info = {
                "project_id": str(project.id) if project else None,
                "project_name": project.name if project else None,
                "role": member.role,
                "message": "Bem-vindo ao projeto! Se for sua primeira vez, configure sua senha",
                "first_access_required": not user.first_access_completed if user else True,
            }

            logger.info(
                "project_team.invite_accepted",
                project_id=str(project_id),
                user_id=str(member.user_id),
            )
            return True, project_info, None

        except Exception as e:
            await db.rollback()
            logger.error("project_team.accept_invite_failed", error=str(e))
            return False, None, str(e)
