"""
Propagation Service — Propaga mudanças do OCG para módulos dependentes.
Analisa campos alterados e dispara regeneração seletiva do backlog.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.services.backlog_service import BacklogService
from app.services.audit_service import AuditService, AuditEvents

logger = structlog.get_logger(__name__)

PROPAGATION_MAP = {
    "STACK_RECOMMENDATION": ["modules"],
    "COMPLIANCE_CHECKLIST": ["compliance"],
    "TESTING_REQUIREMENTS": ["tests"],
    "ARCHITECTURE_OVERVIEW": ["modules", "security"],
    "RISK_ANALYSIS": [],
    "PILLAR_SCORES": ["modules", "tests", "compliance", "security"],
    "CRITICAL_FINDINGS": ["modules"],
}


class PropagationService:
    """Propaga mudanças do OCG para backlog e módulos dependentes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def propagate(
        self,
        project_id: UUID,
        changes: list[dict],
        ocg_version: Optional[int] = None,
    ) -> dict:
        """Analisa campos alterados e dispara regeneração seletiva."""
        affected_categories = set()

        for change in changes:
            field = change.get("field", "")
            top_level = field.split(".")[0] if "." in field else field
            categories = PROPAGATION_MAP.get(top_level, [])
            affected_categories.update(categories)

        if changes:
            affected_categories.add("modules")

        backlog_svc = BacklogService(self.db)
        backlog_result = await backlog_svc.regenerate_from_ocg(project_id, ocg_version)

        audit = AuditService(self.db)
        await audit.log_event(
            event_type=AuditEvents.BACKLOG_REGENERATED,
            resource_type="backlog",
            resource_id=project_id,
            details={
                "affected_categories": list(affected_categories),
                "changes_count": len(changes),
                "backlog_regenerated": backlog_result.get("regenerated", 0),
            },
        )
        await self.db.commit()

        logger.info("propagation.completed",
                   project_id=str(project_id),
                   categories=list(affected_categories),
                   backlog_items=backlog_result.get("regenerated", 0))

        return {
            "affected_categories": list(affected_categories),
            "backlog_result": backlog_result,
        }
