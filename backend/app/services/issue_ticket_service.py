"""
Servico de criacao automatica de tickets a partir de issues de security/compliance.

Cada vulnerabilidade ou falha de compliance vira um BacklogItem vinculado
ao item original como sub-item (parent_item_id).
"""
import json
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BacklogItem

import structlog
logger = structlog.get_logger(__name__)

SEVERITY_TO_PRIORITY = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "high",
    "LOW": "medium",
}


class IssueTicketService:

    async def create_tickets_from_security(
        self,
        db: AsyncSession,
        project_id: UUID,
        parent_item_id: UUID,
        vulnerabilities: list[dict],
    ) -> list[dict]:
        """Cria tickets no backlog para cada vulnerabilidade encontrada."""
        created = []
        for vuln in vulnerabilities:
            severity = vuln.get("severity", "MEDIUM")
            ticket = BacklogItem(
                id=uuid4(),
                project_id=project_id,
                parent_item_id=parent_item_id,
                category="security",
                module_type="fix",
                title=f"[SEC] {vuln.get('type', 'Vulnerabilidade')}",
                description=vuln.get("location", ""),
                priority=SEVERITY_TO_PRIORITY.get(severity, "medium"),
                status="pending",
                source="security_scan",
                fix_severity=severity,
                fix_remediation=vuln.get("remediation", ""),
                warnings=json.dumps([f"Severidade: {severity}"]),
            )
            db.add(ticket)
            created.append({
                "id": str(ticket.id),
                "title": ticket.title,
                "severity": severity,
                "remediation": ticket.fix_remediation,
            })

        await db.flush()
        logger.info("tickets.security_created", parent_id=str(parent_item_id), count=len(created))
        return created

    async def create_tickets_from_compliance(
        self,
        db: AsyncSession,
        project_id: UUID,
        parent_item_id: UUID,
        issues: list[dict],
    ) -> list[dict]:
        """Cria tickets no backlog para cada falha de compliance."""
        created = []
        for issue in issues:
            ticket = BacklogItem(
                id=uuid4(),
                project_id=project_id,
                parent_item_id=parent_item_id,
                category="compliance",
                module_type="fix",
                title=f"[COMPLIANCE] {issue.get('rule', 'Issue')}",
                description=issue.get("issue", ""),
                priority="high",
                status="pending",
                source="compliance_check",
                fix_severity="HIGH",
                fix_remediation=issue.get("remediation", ""),
                warnings=json.dumps([f"Regra: {issue.get('rule', '')}"]),
            )
            db.add(ticket)
            created.append({
                "id": str(ticket.id),
                "title": ticket.title,
                "rule": issue.get("rule", ""),
                "remediation": ticket.fix_remediation,
            })

        await db.flush()
        logger.info("tickets.compliance_created", parent_id=str(parent_item_id), count=len(created))
        return created

    async def get_child_tickets(
        self, db: AsyncSession, parent_item_id: UUID
    ) -> list[dict]:
        """Retorna todos os sub-items (fixes) de um item pai."""
        result = await db.execute(
            select(BacklogItem).where(
                BacklogItem.parent_item_id == parent_item_id,
            ).order_by(BacklogItem.priority.asc(), BacklogItem.created_at.asc())
        )
        items = result.scalars().all()
        return [
            {
                "id": str(i.id),
                "category": i.category,
                "title": i.title,
                "description": i.description,
                "priority": i.priority,
                "status": i.status,
                "fix_severity": i.fix_severity,
                "fix_remediation": i.fix_remediation,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in items
        ]

    async def get_fix_progress(
        self, db: AsyncSession, parent_item_id: UUID
    ) -> dict:
        """Retorna progresso de resolucao dos fixes."""
        result = await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(BacklogItem.status == "done").label("resolved"),
            ).where(BacklogItem.parent_item_id == parent_item_id)
        )
        row = result.first()
        total = row.total if row else 0
        resolved = row.resolved if row else 0
        return {
            "total": total,
            "resolved": resolved,
            "pending": total - resolved,
            "all_resolved": total > 0 and resolved == total,
            "progress_pct": round((resolved / total) * 100, 1) if total > 0 else 0,
        }

    async def mark_fix_done(
        self, db: AsyncSession, fix_id: UUID
    ) -> dict:
        """Marca um fix como resolvido."""
        item = await db.get(BacklogItem, fix_id)
        if not item:
            return {"success": False, "error": "Fix nao encontrado"}
        item.status = "done"
        await db.commit()
        return {"success": True, "id": str(fix_id)}
