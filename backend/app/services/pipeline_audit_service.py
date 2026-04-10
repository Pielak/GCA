"""Servico de audit log para pipeline de qualidade."""
import json
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_audit import PipelineAuditEntry
from app.models.base import User, BacklogItem

import structlog
logger = structlog.get_logger(__name__)


class PipelineAuditService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_phase(
        self,
        project_id: UUID,
        backlog_item_id: UUID,
        user_id: UUID,
        role_used: str,
        phase: str,
        status: str,
        duration_seconds: float | None = None,
        context: dict | None = None,
    ) -> PipelineAuditEntry:
        """Registra uma fase do pipeline no audit log."""
        entry = PipelineAuditEntry(
            id=uuid4(),
            project_id=project_id,
            backlog_item_id=backlog_item_id,
            user_id=user_id,
            role_used=role_used,
            phase=phase,
            status=status,
            duration_seconds=duration_seconds,
            context=json.dumps(context, ensure_ascii=False) if context else None,
        )
        self.db.add(entry)
        await self.db.flush()
        logger.info(
            "pipeline.audit",
            project_id=str(project_id),
            item_id=str(backlog_item_id),
            phase=phase,
            status=status,
        )
        return entry

    async def get_item_audit(self, backlog_item_id: UUID) -> list[dict]:
        """Retorna trilha de auditoria completa de um item."""
        result = await self.db.execute(
            select(PipelineAuditEntry)
            .where(PipelineAuditEntry.backlog_item_id == backlog_item_id)
            .order_by(PipelineAuditEntry.timestamp.asc())
        )
        entries = result.scalars().all()
        return [self._to_dict(e) for e in entries]

    async def get_project_audit(
        self,
        project_id: UUID,
        phase: str | None = None,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retorna audit log do projeto com filtros."""
        query = select(PipelineAuditEntry).where(
            PipelineAuditEntry.project_id == project_id
        )
        if phase:
            query = query.where(PipelineAuditEntry.phase == phase)
        if user_id:
            query = query.where(PipelineAuditEntry.user_id == user_id)

        query = query.order_by(PipelineAuditEntry.timestamp.desc()).limit(limit)
        result = await self.db.execute(query)
        entries = result.scalars().all()
        return [self._to_dict(e) for e in entries]

    async def export_item_audit(self, backlog_item_id: UUID) -> dict:
        """Exporta audit completo de um item no formato compliance (spec secao 9)."""
        entries = await self.get_item_audit(backlog_item_id)
        item = await self.db.get(BacklogItem, backlog_item_id)

        if not item:
            return {}

        # Buscar usuario principal
        user_ids = set(e["user_id"] for e in entries)
        users = {}
        for uid in user_ids:
            user = await self.db.get(User, uid)
            if user:
                users[str(uid)] = user.email

        total_duration = sum(e.get("duration_seconds") or 0 for e in entries)
        last_status = entries[-1]["status"] if entries else "UNKNOWN"

        return {
            "entry_id": f"audit-{item.id}",
            "project_id": str(item.project_id),
            "item_id": str(item.id),
            "item_title": item.title,
            "users": users,
            "phases": entries,
            "total_duration_seconds": round(total_duration, 2),
            "result": "SUCCESS" if last_status in ("COMPLETED", "APPROVED") else "INCOMPLETE",
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def _to_dict(self, entry: PipelineAuditEntry) -> dict:
        return {
            "id": str(entry.id),
            "user_id": str(entry.user_id),
            "role_used": entry.role_used,
            "phase": entry.phase,
            "status": entry.status,
            "duration_seconds": entry.duration_seconds,
            "context": json.loads(entry.context) if entry.context else None,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        }
