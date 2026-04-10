"""Servico para gestao de GPs em projetos (adicionar, remover, substituir)."""
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import User, Project, ProjectMember
from app.core.security import hash_password

import structlog
logger = structlog.get_logger(__name__)


class GPManagementService:

    async def add_gp(self, db: AsyncSession, project_id: UUID, email: str, admin_id: UUID) -> dict:
        user_id, is_new = await self._get_or_create_user(db, email)
        existing = await self._check_existing_membership(db, project_id, user_id)
        if existing:
            return {"success": False, "error": f"Usuario {email} ja e membro deste projeto"}
        await self._create_gp_member(db, project_id, user_id, admin_id)
        project = await db.get(Project, project_id)
        logger.info("gp_added", project_id=str(project_id), admin_id=str(admin_id), email=email)
        await db.commit()
        return {"success": True, "user_id": str(user_id), "email": email}

    async def remove_gp(self, db: AsyncSession, project_id: UUID, gp_user_id: UUID, admin_id: UUID) -> dict:
        active_gps = await self._count_active_gps(db, project_id)
        if active_gps <= 1:
            return {"success": False, "error": "Nao e possivel remover o ultimo GP do projeto. Adicione outro GP primeiro ou use substituir."}
        await self._deactivate_member(db, project_id, gp_user_id)
        logger.info("gp_removed", project_id=str(project_id), admin_id=str(admin_id), gp_user_id=str(gp_user_id))
        await db.commit()
        return {"success": True}

    async def replace_gp(self, db: AsyncSession, project_id: UUID, old_gp_id: UUID, new_email: str, admin_id: UUID) -> dict:
        new_user_id, is_new = await self._get_or_create_user(db, new_email)
        existing = await self._check_existing_membership(db, project_id, new_user_id)
        if existing:
            return {"success": False, "error": f"Usuario {new_email} ja e membro deste projeto"}
        await self._deactivate_member(db, project_id, old_gp_id)
        await self._create_gp_member(db, project_id, new_user_id, admin_id)
        logger.info("gp_replaced", project_id=str(project_id), admin_id=str(admin_id), old_gp_id=str(old_gp_id), new_email=new_email)
        await db.commit()
        return {"success": True, "new_user_id": str(new_user_id), "email": new_email}

    async def _get_or_create_user(self, db: AsyncSession, email: str) -> tuple[UUID, bool]:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            return user.id, False
        temp_password = secrets.token_urlsafe(12)
        new_user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(temp_password),
            full_name="",
            is_active=True,
            is_admin=False,
            first_access_completed=False,
        )
        db.add(new_user)
        await db.flush()
        return new_user.id, True

    async def _check_existing_membership(self, db: AsyncSession, project_id: UUID, user_id: UUID):
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def _create_gp_member(self, db: AsyncSession, project_id: UUID, user_id: UUID, invited_by: UUID) -> ProjectMember:
        now = datetime.now(timezone.utc)
        member = ProjectMember(
            id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            role="gp",
            invited_by=invited_by,
            invited_at=now,
            accepted_at=now,
            joined_at=now,
            is_active=True,
        )
        db.add(member)
        await db.flush()
        return member

    async def _count_active_gps(self, db: AsyncSession, project_id: UUID) -> int:
        result = await db.execute(
            select(func.count()).select_from(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "gp",
                ProjectMember.is_active == True,
            )
        )
        return result.scalar()

    async def _deactivate_member(self, db: AsyncSession, project_id: UUID, user_id: UUID):
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.is_active = False
            member.revoked_at = datetime.now(timezone.utc)
