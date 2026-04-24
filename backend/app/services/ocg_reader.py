"""Leitor canônico do OCG mais recente por projeto.

Função extraída em 2026-04-24 após auditoria arquitetural identificar 4
duplicações (module_details_service, module_orchestration_service,
roadmap_foundation_service, iterative_questionnaire_service) — todas
com a mesma query e zero cache. Fonte única evita drift de lógica e
permite futuro cache compartilhado (DT potencial).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OCG


async def load_latest_ocg(db: AsyncSession, project_id: UUID) -> OCG | None:
    """Retorna o OCG snapshot mais recente do projeto (maior `version`),
    ou None se o projeto não tem OCG ainda."""
    result = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(desc(OCG.version))
        .limit(1)
    )
    return result.scalar_one_or_none()
