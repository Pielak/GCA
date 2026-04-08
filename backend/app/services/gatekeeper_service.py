"""
Gatekeeper Service — Consolidação de items do Arguidor + Aprovação/Rejeição de módulos.
"""
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import GatekeeperItem, ModuleCandidate, ArguiderAnalysis

logger = structlog.get_logger(__name__)


class GatekeeperService:
    """Consolidação e gestão de items do Gatekeeper por projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_project_gatekeeper(self, project_id: UUID) -> dict:
        """Consolida todos os items e módulos do projeto."""
        # Items
        items_result = await self.db.execute(
            select(GatekeeperItem).where(GatekeeperItem.project_id == project_id)
        )
        items = items_result.scalars().all()

        gaps = [i for i in items if i.item_type == "gap"]
        show_stoppers = [i for i in items if i.item_type == "show_stopper"]
        poor_defs = [i for i in items if i.item_type == "poor_definition"]
        improvements = [i for i in items if i.item_type == "improvement"]

        # Módulos
        modules_result = await self.db.execute(
            select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
        )
        modules = modules_result.scalars().all()

        def item_to_dict(item):
            try:
                data = json.loads(item.item_data) if item.item_data else {}
            except json.JSONDecodeError:
                data = {}
            return {
                "id": str(item.id),
                "item_type": item.item_type,
                "item_id": item.item_id_in_analysis,
                "data": data,
                "status": item.status,
                "resolution_note": item.resolution_note,
                "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
            }

        def module_to_dict(m):
            return {
                "id": str(m.id),
                "name": m.name,
                "description": m.description,
                "module_type": m.module_type,
                "priority": m.priority,
                "status": m.status,
                "ready_for_codegen": m.ready_for_codegen,
                "approved_at": m.approved_at.isoformat() if m.approved_at else None,
                "rejection_reason": m.rejection_reason,
                "dependencies": json.loads(m.dependencies) if m.dependencies else [],
                "pillar_impact": json.loads(m.pillar_impact) if m.pillar_impact else {},
            }

        open_gaps = sum(1 for g in gaps if g.status == "pending")
        open_ss = sum(1 for s in show_stoppers if s.status == "pending")
        has_blockers = any(
            json.loads(s.item_data).get("severity") == "BLOCKER"
            for s in show_stoppers if s.status == "pending" and s.item_data
        )

        return {
            "summary": {
                "total_gaps": len(gaps),
                "open_gaps": open_gaps,
                "total_show_stoppers": len(show_stoppers),
                "open_show_stoppers": open_ss,
                "total_poor_definitions": len(poor_defs),
                "total_suggestions": len(improvements),
                "total_modules": len(modules),
                "modules_pending_approval": sum(1 for m in modules if m.status == "suggested"),
                "modules_approved": sum(1 for m in modules if m.status == "approved"),
                "modules_rejected": sum(1 for m in modules if m.status == "rejected"),
                "has_blockers": has_blockers,
            },
            "gaps": [item_to_dict(g) for g in gaps],
            "show_stoppers": [item_to_dict(s) for s in show_stoppers],
            "poor_definitions": [item_to_dict(p) for p in poor_defs],
            "improvement_suggestions": [item_to_dict(i) for i in improvements],
            "module_candidates": [module_to_dict(m) for m in modules],
        }

    async def resolve_item(self, project_id: UUID, item_id: UUID, resolved_by: UUID, note: str) -> bool:
        result = await self.db.execute(
            select(GatekeeperItem).where(
                GatekeeperItem.id == item_id,
                GatekeeperItem.project_id == project_id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        item.status = "resolved"
        item.resolved_by = resolved_by
        item.resolution_note = note
        item.resolved_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True

    async def ignore_item(self, project_id: UUID, item_id: UUID, ignored_by: UUID, reason: str) -> dict:
        if not reason or not reason.strip():
            return {"success": False, "error": "Reason é obrigatório para ignorar um item", "status_code": 400}

        result = await self.db.execute(
            select(GatekeeperItem).where(
                GatekeeperItem.id == item_id,
                GatekeeperItem.project_id == project_id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return {"success": False, "error": "Item não encontrado", "status_code": 404}

        item.status = "ignored"
        item.resolved_by = ignored_by
        item.resolution_note = f"[IGNORADO] {reason}"
        item.resolved_at = datetime.now(timezone.utc)
        await self.db.commit()
        return {"success": True}

    async def approve_module(self, project_id: UUID, module_id: UUID, approved_by: UUID) -> dict:
        result = await self.db.execute(
            select(ModuleCandidate).where(
                ModuleCandidate.id == module_id,
                ModuleCandidate.project_id == project_id,
            )
        )
        module = result.scalar_one_or_none()
        if not module:
            return {"success": False, "error": "Módulo não encontrado", "status_code": 404}

        module.status = "approved"
        module.approved_by = approved_by
        module.approved_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info("gatekeeper.module_approved", module_id=str(module_id), name=module.name)

        # TODO FASE 3: disparar CodeGen do módulo via asyncio.create_task
        return {"success": True, "message": "Módulo aprovado. Geração de código será iniciada na Fase 3."}

    async def reject_module(self, project_id: UUID, module_id: UUID, rejected_by: UUID, reason: str) -> dict:
        if not reason or not reason.strip():
            return {"success": False, "error": "Reason é obrigatório", "status_code": 400}

        result = await self.db.execute(
            select(ModuleCandidate).where(
                ModuleCandidate.id == module_id,
                ModuleCandidate.project_id == project_id,
            )
        )
        module = result.scalar_one_or_none()
        if not module:
            return {"success": False, "error": "Módulo não encontrado", "status_code": 404}

        module.status = "rejected"
        module.rejected_by = rejected_by
        module.rejection_reason = reason
        await self.db.commit()

        logger.info("gatekeeper.module_rejected", module_id=str(module_id), reason=reason[:100])
        return {"success": True}

    async def get_modules(self, project_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
        )
        modules = result.scalars().all()
        return [
            {
                "id": str(m.id),
                "name": m.name,
                "description": m.description,
                "module_type": m.module_type,
                "priority": m.priority,
                "status": m.status,
                "ready_for_codegen": m.ready_for_codegen,
                "approved_at": m.approved_at.isoformat() if m.approved_at else None,
                "rejection_reason": m.rejection_reason,
            }
            for m in modules
        ]

    async def generate_report_markdown(self, project_id: UUID) -> str:
        data = await self.get_project_gatekeeper(project_id)
        s = data["summary"]

        lines = [
            "# Relatório do Gatekeeper\n",
            f"**Gaps:** {s['total_gaps']} ({s['open_gaps']} abertos)",
            f"**Show-Stoppers:** {s['total_show_stoppers']} ({s['open_show_stoppers']} abertos)",
            f"**Má Definição:** {s['total_poor_definitions']}",
            f"**Sugestões:** {s['total_suggestions']}",
            f"**Módulos:** {s['total_modules']} ({s['modules_approved']} aprovados, {s['modules_rejected']} rejeitados)\n",
        ]

        if s["has_blockers"]:
            lines.append("⚠️ **BLOQUEADORES ATIVOS** — Show-stoppers não resolvidos impedem geração de código.\n")

        for section, items in [("Gaps", data["gaps"]), ("Show Stoppers", data["show_stoppers"]),
                               ("Má Definição", data["poor_definitions"]), ("Sugestões", data["improvement_suggestions"])]:
            if items:
                lines.append(f"\n## {section}\n")
                for item in items:
                    d = item["data"]
                    lines.append(f"- **{item['item_id']}** [{item['status']}] {d.get('description', '')}")

        if data["module_candidates"]:
            lines.append("\n## Módulos Candidatos\n")
            for m in data["module_candidates"]:
                lines.append(f"- **{m['name']}** ({m['module_type']}, {m['priority']}) [{m['status']}]")
                lines.append(f"  {m['description'][:200]}")

        return "\n".join(lines)
