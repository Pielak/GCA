"""Servico para gestao de papeis multiplos por membro."""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectMember, User
from app.models.project_member_role import ProjectMemberRole

import structlog
logger = structlog.get_logger(__name__)


class MemberRolesService:

    async def get_member_roles(
        self, db: AsyncSession, project_id: UUID, user_id: UUID
    ) -> list[dict]:
        """Retorna todos os papeis de um membro no projeto."""
        member = await self._get_member(db, project_id, user_id)
        if not member:
            return []

        roles_result = await db.execute(
            select(ProjectMemberRole).where(
                ProjectMemberRole.member_id == member.id,
            )
        )
        additional_roles = roles_result.scalars().all()

        result = [{"role": member.role, "is_base": True, "assigned_at": str(member.joined_at or member.invited_at)}]
        for r in additional_roles:
            result.append({"role": r.role, "is_base": False, "assigned_at": str(r.assigned_at)})

        return result

    async def add_roles(
        self, db: AsyncSession, project_id: UUID, user_id: UUID, roles: list[str], assigned_by: UUID
    ) -> dict:
        """Adiciona papeis ao membro logado."""
        member = await self._get_member(db, project_id, user_id)
        if not member:
            return {"success": False, "error": "Voce nao e membro deste projeto"}

        added = []
        skipped = []
        for role in roles:
            if role == member.role:
                skipped.append(role)
                continue

            existing = await db.execute(
                select(ProjectMemberRole).where(
                    ProjectMemberRole.member_id == member.id,
                    ProjectMemberRole.role == role,
                )
            )
            if existing.scalar_one_or_none():
                skipped.append(role)
                continue

            new_role = ProjectMemberRole(
                id=uuid4(),
                member_id=member.id,
                role=role,
                assigned_at=datetime.now(timezone.utc),
                assigned_by=assigned_by,
            )
            db.add(new_role)
            added.append(role)

        await db.commit()
        logger.info("roles_added", project_id=str(project_id), user_id=str(user_id), added=added, skipped=skipped)
        return {"success": True, "added": added, "skipped": skipped}

    async def get_role_audit(
        self, db: AsyncSession, project_id: UUID
    ) -> list[dict]:
        """Historico de atribuicoes de papeis no projeto."""
        members = await db.execute(
            select(ProjectMember.id, ProjectMember.user_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.is_active == True,
            )
        )
        member_rows = members.all()
        member_ids = [m.id for m in member_rows]
        user_map = {m.id: m.user_id for m in member_rows}

        if not member_ids:
            return []

        roles = await db.execute(
            select(ProjectMemberRole).where(
                ProjectMemberRole.member_id.in_(member_ids),
            ).order_by(ProjectMemberRole.assigned_at.desc())
        )

        result = []
        for r in roles.scalars().all():
            uid = user_map.get(r.member_id)
            user = await db.get(User, uid) if uid else None
            result.append({
                "role": r.role,
                "user_email": user.email if user else "?",
                "assigned_at": str(r.assigned_at),
                "assigned_by": str(r.assigned_by),
            })

        return result

    async def _get_member(
        self, db: AsyncSession, project_id: UUID, user_id: UUID
    ) -> ProjectMember | None:
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True,
            )
        )
        return result.scalar_one_or_none()
