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
from app.services.pillar_threshold_evaluator import (
    derive_project_status,
    evaluate_blocking_pillars,
)

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

        # Buscar dados do OCG para scores reais dos pilares
        from app.models.base import OCG
        ocg_result = await self.db.execute(
            select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
        )
        ocg = ocg_result.scalar_one_or_none()

        ocg_scores = {}
        ocg_status = None
        ocg_health = {}
        if ocg:
            # Ler scores do ocg_data JSON (mais completo) com fallback para colunas individuais
            ocg_data_scores = {}
            if ocg.ocg_data:
                try:
                    od = json.loads(ocg.ocg_data)
                    ps = od.get("PILLAR_SCORES", {})
                    for key, val in ps.items():
                        score = val.get("score", val) if isinstance(val, dict) else val
                        ocg_data_scores[key] = score if isinstance(score, (int, float)) else 0
                except (json.JSONDecodeError, AttributeError):
                    pass

            pillar_names = {
                1: "P1_Negócio", 2: "P2_Compliance", 3: "P3_Escopo",
                4: "P4_Performance", 5: "P5_Arquitetura", 6: "P6_Dados", 7: "P7_Segurança",
            }
            db_scores = [
                ocg.p1_business_score, ocg.p2_rules_score, ocg.p3_features_score,
                ocg.p4_nfr_score, ocg.p5_architecture_score, ocg.p6_data_score, ocg.p7_security_score,
            ]

            for i, (num, name) in enumerate(pillar_names.items()):
                # Preferência: coluna DB (se > 0) → ocg_data JSON → 0
                db_val = db_scores[i] or 0
                json_val = 0
                for k, v in ocg_data_scores.items():
                    if f"P{num}" in k:
                        json_val = v
                        break
                ocg_scores[name] = db_val if db_val > 0 else json_val
            ocg_status = {
                "overall_score": ocg.overall_score or 0,
                "status": ocg.status,
                "is_blocking": ocg.is_blocking,
                "version": getattr(ocg, 'version', 1),
                "change_type": getattr(ocg, 'change_type', 'INITIAL'),
            }
            if hasattr(ocg, 'context_health') and ocg.context_health:
                try:
                    ocg_health = json.loads(ocg.context_health)
                except json.JSONDecodeError:
                    pass

        # === Avaliação determinística de thresholds ===
        # Aplica os thresholds configurados no Admin (per-pilar + bandas
        # de composite). Resultado fica disponível no payload do Gatekeeper
        # como `blocking_pillars` (lista) e `derived_status` (string).
        from app.routers.admin_gca_router import _current_settings
        thresholds_cfg = _current_settings.get("score_thresholds", {})
        blocking_pillars = evaluate_blocking_pillars(ocg_scores, thresholds_cfg)
        overall = (ocg_status or {}).get("overall_score", 0) if ocg_status else 0
        derived_status = derive_project_status(overall, blocking_pillars, thresholds_cfg)

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
            "ocg": {
                "pillar_scores": ocg_scores,
                "status": ocg_status,
                "health": ocg_health,
                "blocking_pillars": blocking_pillars,
                "derived_status": derived_status,
                "thresholds_applied": thresholds_cfg,
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
