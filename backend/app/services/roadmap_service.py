"""
Roadmap Service — Geração dinâmica de roadmap a partir dos módulos candidatos e gerados.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.constants.module_categories import normalize_module_status
from app.models.base import (
    ModuleCandidate,
    GeneratedModule,
    BacklogItem,
    Project,
)

logger = structlog.get_logger(__name__)


class RoadmapService:
    """Serviço de roadmap do projeto — agrupa módulos por fase e prioridade."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_roadmap(self, project_id: UUID) -> dict:
        """
        Gera roadmap dinâmico a partir do BACKLOG do projeto.

        Cascata canônica (2026-04-24): Backlog → Roadmap → Scaffold.
        O roadmap é a vista ordenada do backlog. Lemos `BacklogItem` direto
        e enriquecemos via LEFT JOIN com `ModuleCandidate` quando o item
        veio do Arguidor (puxa `ready_for_codegen` e `readiness_status`).

        - Itens com priority='critical' ou 'high' → Fase 1 (Fundação)
        - 'medium' → Fase 2 (Funcionalidades Principais)
        - 'low' → Fase 3 (Complementos)
        - category='governance' fica oculto quando o projeto está em
          governance_mode='solo_owner' (mesmo critério do list_backlog).
        """
        try:
            # governance_mode dita filtragem de categorias de PM
            gov_row = await self.db.execute(
                select(Project.governance_mode).where(Project.id == project_id)
            )
            governance_mode = gov_row.scalar() or "solo_owner"

            # Backlog é fonte canônica; LEFT JOIN traz readiness do candidato
            stmt = (
                select(BacklogItem, ModuleCandidate)
                .outerjoin(ModuleCandidate, ModuleCandidate.id == BacklogItem.module_candidate_id)
                .where(
                    BacklogItem.project_id == project_id,
                    BacklogItem.parent_item_id.is_(None),
                )
            )
            if governance_mode == "solo_owner":
                stmt = stmt.where(BacklogItem.category != "governance")

            rows = (await self.db.execute(stmt)).all()

            # Buscar módulos gerados (chave por module_candidate_id —
            # CodeGen registra qual candidato foi materializado)
            generated_result = await self.db.execute(
                select(GeneratedModule).where(GeneratedModule.project_id == project_id)
            )
            generated_by_candidate = {
                str(m.module_candidate_id): m for m in generated_result.scalars().all()
            }

            # Organizar por fases canônicas — critical+high vão pra Fase 1
            phases = {
                "high": {"name": "Fase 1 — Fundação", "modules": [], "status": "pending"},
                "medium": {"name": "Fase 2 — Funcionalidades Principais", "modules": [], "status": "pending"},
                "low": {"name": "Fase 3 — Complementos", "modules": [], "status": "pending"},
            }

            total_modules = len(rows)
            completed_modules = 0

            for backlog_item, candidate in rows:
                # Status efetivo: CodeGen finalizou? então usa GeneratedModule.
                # Caso contrário, usa o status do BacklogItem (canônico do roadmap)
                # com fallback no ModuleCandidate quando há vínculo.
                gen = None
                if candidate is not None:
                    gen = generated_by_candidate.get(str(candidate.id))
                if gen is not None:
                    raw_status = gen.status
                else:
                    raw_status = backlog_item.status or (candidate.status if candidate else None)
                module_status = normalize_module_status(raw_status)
                if module_status in ("concluido", "completed"):
                    completed_modules += 1

                # Normaliza prioridade canônica do backlog (4 níveis) pra
                # 3 fases. critical e high entram na fundação juntos.
                bl_priority = (backlog_item.priority or "medium").lower()
                if bl_priority in ("critical", "high"):
                    phase_key = "high"
                elif bl_priority == "low":
                    phase_key = "low"
                else:
                    phase_key = "medium"

                module_info = {
                    "id": str(candidate.id) if candidate else str(backlog_item.id),
                    "backlog_item_id": str(backlog_item.id),
                    "name": backlog_item.title,
                    "status": module_status,
                    "description": backlog_item.description or "",
                    "module_type": backlog_item.module_type or (candidate.module_type if candidate else "feature"),
                    "priority": bl_priority,
                    "readiness_status": (candidate.readiness_status if candidate else None),
                    "ready_for_codegen": bool(candidate.ready_for_codegen) if candidate else False,
                    "category": backlog_item.category,
                    "source": backlog_item.source,
                    "created_at": backlog_item.created_at.isoformat() if backlog_item.created_at else None,
                }

                phases[phase_key]["modules"].append(module_info)

            # Determinar status das fases (MVP 9 Fase 9.1.2 — inclui
            # canônicos pt-BR + terminais do CodeGen).
            for key in phases:
                mods = phases[key]["modules"]
                if not mods:
                    phases[key]["status"] = "pending"
                elif all(m["status"] in ("concluido", "completed") for m in mods):
                    phases[key]["status"] = "completed"
                elif any(m["status"] in (
                    "aguardando_resposta", "adicionado",
                    "generating", "in_progress",
                ) for m in mods):
                    phases[key]["status"] = "in_progress"
                else:
                    phases[key]["status"] = "pending"

            # Próxima ação recomendada — prioriza items prontos pra CodeGen
            # (ready_for_codegen=true) dentro da fase mais alta com pendência.
            next_action = "Backlog vazio — nenhum item disponível"
            for key in ["high", "medium", "low"]:
                pendentes = [m for m in phases[key]["modules"] if m["status"] not in ("completed", "concluido")]
                if not pendentes:
                    continue
                prontos = [m for m in pendentes if m.get("ready_for_codegen")]
                escolhido = prontos[0] if prontos else pendentes[0]
                rotulo = "pronto pra CodeGen" if prontos else "aguarda informação"
                next_action = f"{phases[key]['name']}: '{escolhido['name']}' ({rotulo})"
                break

            return {
                "phases": [phases[k] for k in ("high", "medium", "low")],
                "total_modules": total_modules,
                "completed_modules": completed_modules,
                "progress_percent": round(completed_modules / total_modules * 100, 1) if total_modules > 0 else 0,
                "next_action": next_action,
            }

        except Exception as e:
            logger.error("roadmap.erro", project_id=str(project_id), error=str(e))
            return {"phases": [], "total_modules": 0, "completed_modules": 0, "next_action": "Erro ao gerar roadmap"}
