"""Serviço de notificações in-app (distinto de notification_service para Slack/Discord).

Uso típico:
    svc = InAppNotificationService(db)
    await svc.notify(
        user_id=uuid_do_usuario,
        event_type="invite_received",
        title="Você foi convidado para um projeto",
        message="O GP X adicionou você ao projeto Y como Dev Pleno.",
        link="/projects/<uuid>",
        severity="info",
    )
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import UserNotification


class InAppNotificationService:
    """CRUD de notificações in-app."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(
        self,
        user_id: UUID,
        event_type: str,
        title: str,
        message: str,
        project_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        link: Optional[str] = None,
        severity: str = "info",
    ) -> UserNotification:
        """Cria notificação in-app. Retorna a entidade persistida."""
        n = UserNotification(
            user_id=user_id,
            project_id=project_id,
            event_type=event_type,
            title=title,
            message=message,
            resource_type=resource_type,
            resource_id=resource_id,
            link=link,
            severity=severity,
        )
        self.db.add(n)
        await self.db.commit()
        await self.db.refresh(n)
        return n

    async def list_for_user(
        self,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 30,
    ) -> List[UserNotification]:
        """Lista notificações do usuário (mais recentes primeiro)."""
        q = select(UserNotification).where(UserNotification.user_id == user_id)
        if unread_only:
            q = q.where(UserNotification.read_at.is_(None))
        q = q.order_by(UserNotification.created_at.desc()).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def count_unread(self, user_id: UUID) -> int:
        """Quantidade de não-lidas do usuário."""
        from sqlalchemy import func
        q = (
            select(func.count(UserNotification.id))
            .where(and_(UserNotification.user_id == user_id, UserNotification.read_at.is_(None)))
        )
        result = await self.db.execute(q)
        return int(result.scalar() or 0)

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> bool:
        """Marca uma notificação como lida. Retorna True se atualizou."""
        now = datetime.now(timezone.utc)
        q = (
            update(UserNotification)
            .where(
                and_(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == user_id,
                    UserNotification.read_at.is_(None),
                )
            )
            .values(read_at=now)
        )
        result = await self.db.execute(q)
        await self.db.commit()
        return (result.rowcount or 0) > 0

    async def mark_all_read(self, user_id: UUID) -> int:
        """Marca todas as não-lidas como lidas. Retorna quantidade afetada."""
        now = datetime.now(timezone.utc)
        q = (
            update(UserNotification)
            .where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.read_at.is_(None),
                )
            )
            .values(read_at=now)
        )
        result = await self.db.execute(q)
        await self.db.commit()
        return result.rowcount or 0
