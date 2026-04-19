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

from app.models.base import ModuleCandidate, GeneratedModule

logger = structlog.get_logger(__name__)


class RoadmapService:
    """Serviço de roadmap do projeto — agrupa módulos por fase e prioridade."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_roadmap(self, project_id: UUID) -> dict:
        """
        Gera roadmap dinâmico a partir do estado dos module_candidates e generated_modules.
        Módulos com priority='high' → Fase 1, 'medium' → Fase 2, 'low' → Fase 3.
        """
        try:
            # Buscar candidatos
            result = await self.db.execute(
                select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
            )
            candidates = result.scalars().all()

            # Buscar módulos gerados
            result = await self.db.execute(
                select(GeneratedModule).where(GeneratedModule.project_id == project_id)
            )
            generated = result.scalars().all()
            generated_by_candidate = {str(m.module_candidate_id): m for m in generated}

            # Organizar por fases
            phases = {
                "high": {"name": "Fase 1 — Fundação", "modules": [], "status": "pending"},
                "medium": {"name": "Fase 2 — Funcionalidades Principais", "modules": [], "status": "pending"},
                "low": {"name": "Fase 3 — Complementos", "modules": [], "status": "pending"},
            }

            total_modules = len(candidates)
            completed_modules = 0

            for c in candidates:
                gen = generated_by_candidate.get(str(c.id))
                module_status = gen.status if gen else c.status
                if module_status == "completed":
                    completed_modules += 1

                # MVP 9 Fase 9.1 — expõe categoria canônica + descrição
                # pra UI agrupar/filtrar por camada (feature/backend/infra/etc).
                module_info = {
                    "id": str(c.id),
                    "name": c.name,
                    "status": module_status,
                    "description": c.description or "",
                    "module_type": c.module_type or "feature",
                    "priority": c.priority or "medium",
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }

                priority = c.priority if c.priority in phases else "medium"
                phases[priority]["modules"].append(module_info)

            # Determinar status das fases
            for key in phases:
                mods = phases[key]["modules"]
                if not mods:
                    phases[key]["status"] = "pending"
                elif all(m["status"] == "completed" for m in mods):
                    phases[key]["status"] = "completed"
                elif any(m["status"] in ("generating", "in_progress", "approved") for m in mods):
                    phases[key]["status"] = "in_progress"
                else:
                    phases[key]["status"] = "pending"

            # Próxima ação recomendada
            next_action = "Nenhum módulo candidato encontrado"
            for key in ["high", "medium", "low"]:
                pending = [m for m in phases[key]["modules"] if m["status"] not in ("completed",)]
                if pending:
                    next_action = f"Continuar com '{pending[0]['name']}' na {phases[key]['name']}"
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
