"""
Backlog Service — Backlog vivo do projeto (spec seção 7.2)
O backlog não é estático; deriva do OCG vigente.
Sempre que OCG muda, backlog é recalculado.
"""
import json
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import structlog

from app.models.base import BacklogItem, OCG

logger = structlog.get_logger(__name__)


# Categorias do backlog (spec seção 7.2)
BACKLOG_CATEGORIES = {
    "modules": "Módulos a serem construídos",
    "tests": "Tipos de testes",
    "compliance": "Compliance e normas",
    "security": "Segurança",
    "agile": "Projetos ágeis",
    "other": "Outros",
}


class BacklogService:
    """Serviço de backlog vivo por projeto"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def regenerate_from_ocg(self, project_id: UUID, ocg_version: Optional[int] = None) -> dict:
        """Regenera o backlog a partir do OCG atual do projeto.
        Remove itens gerados automaticamente e recria com base no OCG.
        Itens manuais (source='manual') são preservados.
        """
        # Buscar OCG mais recente
        result = await self.db.execute(
            select(OCG)
            .where(OCG.project_id == project_id)
            .order_by(OCG.created_at.desc())
            .limit(1)
        )
        ocg = result.scalar_one_or_none()
        if not ocg or not ocg.ocg_data:
            return {"regenerated": 0, "message": "OCG não encontrado"}

        try:
            ocg_data = json.loads(ocg.ocg_data)
        except json.JSONDecodeError:
            return {"regenerated": 0, "message": "OCG data inválido"}

        version = ocg_version or getattr(ocg, 'version', 1)

        # Remover itens auto-gerados (preservar manuais)
        await self.db.execute(
            delete(BacklogItem).where(
                (BacklogItem.project_id == project_id) &
                (BacklogItem.source != "manual")
            )
        )

        items_created = []

        # === MÓDULOS: extrair do OCG ===
        stack = ocg_data.get("stack", {}) or ocg_data.get("STACK_RECOMMENDATIONS", {})
        if stack:
            items_created.append(self._create_item(
                project_id, "modules", "Configurar stack do projeto",
                f"Stack recomendada: {json.dumps(stack, ensure_ascii=False)[:200]}",
                "high", "ocg", version,
            ))

        # Módulos de cada pilar
        for i in range(1, 8):
            pillar_key = f"P{i}"
            pillar_data = ocg_data.get(pillar_key, {})
            if isinstance(pillar_data, dict):
                recommendations = pillar_data.get("recommendations", [])
                if isinstance(recommendations, list):
                    for rec in recommendations[:3]:  # top 3 por pilar
                        if isinstance(rec, str) and len(rec) > 5:
                            items_created.append(self._create_item(
                                project_id, "modules", rec[:200],
                                f"Recomendação do pilar {pillar_key}",
                                "medium", "ocg", version,
                            ))

        # === TESTES: tipos necessários ===
        qa_profile = ocg_data.get("qa_profile", {})
        test_types = qa_profile.get("required_test_types", [])
        if test_types:
            for tt in test_types:
                items_created.append(self._create_item(
                    project_id, "tests", f"Implementar testes: {tt}",
                    f"Tipo de teste requerido pelo OCG: {tt}",
                    "high", "ocg", version,
                ))

        # === COMPLIANCE ===
        compliance = ocg_data.get("compliance", {})
        if compliance.get("lgpd"):
            items_created.append(self._create_item(
                project_id, "compliance", "Adequação LGPD",
                "Projeto requer conformidade com LGPD",
                "critical", "ocg", version,
            ))
        if compliance.get("gdpr"):
            items_created.append(self._create_item(
                project_id, "compliance", "Adequação GDPR",
                "Projeto requer conformidade com GDPR",
                "critical", "ocg", version,
            ))
        if compliance.get("audit_required"):
            items_created.append(self._create_item(
                project_id, "compliance", "Trilha de auditoria obrigatória",
                "Todas as ações devem ser registradas",
                "high", "ocg", version,
            ))

        # === SEGURANÇA ===
        security_controls = ocg_data.get("security", {})
        if isinstance(security_controls, dict):
            for control, enabled in security_controls.items():
                if enabled and isinstance(enabled, bool):
                    items_created.append(self._create_item(
                        project_id, "security", f"Implementar: {control}",
                        f"Controle de segurança requerido",
                        "high", "ocg", version,
                    ))

        # === DELIVERY STATE ===
        delivery = ocg_data.get("delivery_state", {})
        if delivery:
            for key, val in delivery.items():
                if val and isinstance(val, str) and val not in ("not_started",):
                    items_created.append(self._create_item(
                        project_id, "agile", f"Acompanhar: {key} ({val})",
                        f"Estado de entrega do OCG",
                        "medium", "ocg", version,
                    ))

        # Persistir
        for item in items_created:
            self.db.add(item)
        await self.db.commit()

        logger.info("backlog.regenerated",
                    project_id=str(project_id),
                    ocg_version=version,
                    items_created=len(items_created))

        return {
            "regenerated": len(items_created),
            "ocg_version": version,
            "categories": {cat: sum(1 for i in items_created if i.category == cat)
                          for cat in BACKLOG_CATEGORIES},
        }

    def _create_item(
        self, project_id: UUID, category: str, title: str,
        description: str, priority: str, source: str, version: int,
    ) -> BacklogItem:
        return BacklogItem(
            project_id=project_id,
            category=category,
            title=title,
            description=description,
            priority=priority,
            source=source,
            source_version=version,
        )

    async def list_backlog(self, project_id: UUID, category: Optional[str] = None) -> list[dict]:
        """Lista itens do backlog por projeto"""
        query = select(BacklogItem).where(BacklogItem.project_id == project_id)
        if category:
            query = query.where(BacklogItem.category == category)
        query = query.order_by(
            BacklogItem.priority.asc(),  # critical first
            BacklogItem.created_at.desc(),
        )

        result = await self.db.execute(query)
        items = result.scalars().all()

        return [
            {
                "id": str(i.id),
                "category": i.category,
                "title": i.title,
                "description": i.description,
                "priority": i.priority,
                "status": i.status,
                "source": i.source,
                "source_version": i.source_version,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in items
        ]
