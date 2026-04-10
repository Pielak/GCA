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
        stack = ocg_data.get("STACK_RECOMMENDATION", {}) or ocg_data.get("STACK_RECOMMENDATIONS", {}) or ocg_data.get("stack", {})
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
        testing = ocg_data.get("TESTING_REQUIREMENTS", {}) or ocg_data.get("qa_profile", {})
        if isinstance(testing, dict):
            for test_type, config in testing.items():
                desc = ""
                if isinstance(config, dict):
                    desc = config.get("scope", config.get("rationale", ""))
                    coverage = config.get("coverage_target", "")
                    if coverage:
                        desc = f"{desc} (cobertura: {coverage})"
                items_created.append(self._create_item(
                    project_id, "tests", f"Implementar: {test_type.replace('_', ' ').title()}",
                    desc[:200] if desc else f"Tipo de teste requerido pelo OCG",
                    "high", "ocg", version,
                ))

        # === COMPLIANCE ===
        compliance = ocg_data.get("COMPLIANCE_CHECKLIST", []) or ocg_data.get("compliance", [])
        if isinstance(compliance, list):
            for item in compliance[:10]:
                if isinstance(item, dict):
                    items_created.append(self._create_item(
                        project_id, "compliance",
                        item.get("item", item.get("requirement", "Item de compliance"))[:200],
                        f"Status: {item.get('status', 'PENDENTE')} — {item.get('owner', '')}",
                        "critical", "ocg", version,
                    ))
                elif isinstance(item, str):
                    items_created.append(self._create_item(
                        project_id, "compliance", item[:200], "", "critical", "ocg", version,
                    ))

        # === CRITICAL FINDINGS → segurança e módulos ===
        findings = ocg_data.get("CRITICAL_FINDINGS", [])
        if isinstance(findings, list):
            for f in findings[:5]:
                if isinstance(f, dict):
                    category = "security" if "segurança" in str(f).lower() or "security" in str(f).lower() else "modules"
                    items_created.append(self._create_item(
                        project_id, category,
                        f.get("finding", f.get("risk", "Achado crítico"))[:200],
                        f"Pilar: {f.get('pillar', '—')} · Severidade: {f.get('severity', '—')}",
                        "critical", "ocg", version,
                    ))

        # === RISK ANALYSIS ===
        risks = ocg_data.get("RISK_ANALYSIS", {})
        if isinstance(risks, dict):
            for level, risk_list in risks.items():
                if isinstance(risk_list, list):
                    priority = "critical" if "high" in level.lower() else "high" if "medium" in level.lower() else "medium"
                    for r in risk_list[:3]:
                        if isinstance(r, dict):
                            items_created.append(self._create_item(
                                project_id, "agile",
                                r.get("risk", "Risco identificado")[:200],
                                f"Mitigação: {r.get('mitigation', '—')[:150]}",
                                priority, "ocg", version,
                            ))

        # === DELIVERABLES ===
        deliverables = ocg_data.get("DELIVERABLES", [])
        if isinstance(deliverables, list):
            for d in deliverables[:8]:
                title = d if isinstance(d, str) else d.get("title", d.get("name", "Entregável"))
                items_created.append(self._create_item(
                    project_id, "modules", str(title)[:200],
                    "Entregável definido no OCG", "medium", "ocg", version,
                ))
        elif isinstance(deliverables, dict):
            for key, val in deliverables.items():
                items_created.append(self._create_item(
                    project_id, "modules", f"{key}: {str(val)[:150]}",
                    "Entregável definido no OCG", "medium", "ocg", version,
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

    async def ingest_module_candidates(self, project_id: UUID) -> dict:
        """Converte ModuleCandidates do Arguider em BacklogItems."""
        from app.models.base import ModuleCandidate
        from app.services.artifact_verification_service import ArtifactVerificationService

        # Buscar candidates que ainda nao estao no backlog
        candidates = await self.db.execute(
            select(ModuleCandidate).where(
                ModuleCandidate.project_id == project_id,
            )
        )
        all_candidates = candidates.scalars().all()

        # Buscar titulos existentes para evitar duplicatas
        existing = await self.db.execute(
            select(BacklogItem.title).where(
                BacklogItem.project_id == project_id,
                BacklogItem.source == "arguider",
            )
        )
        existing_titles = {r.title for r in existing.all()}

        created = 0
        for mc in all_candidates:
            if mc.name in existing_titles:
                continue

            item = BacklogItem(
                project_id=project_id,
                category="modules",
                module_type=mc.module_type or "service",
                title=mc.name,
                description=mc.description,
                priority=mc.priority or "medium",
                status="pending",
                source="arguider",
                dependencies=mc.dependencies,
            )
            self.db.add(item)
            created += 1

        await self.db.commit()

        # Verificar artefatos de itens novos
        verifier = ArtifactVerificationService()
        await verifier.verify_all_items(self.db, project_id)

        logger.info("backlog.arguider_ingested", project_id=str(project_id), created=created)
        return {"created": created, "skipped": len(all_candidates) - created}

    async def list_backlog(self, project_id: UUID, category: Optional[str] = None) -> list[dict]:
        """Lista itens do backlog por projeto (exclui sub-items, mostra contagem)"""
        from sqlalchemy import func

        # Listar apenas itens raiz (sem parent_item_id)
        query = select(BacklogItem).where(
            BacklogItem.project_id == project_id,
            BacklogItem.parent_item_id == None,
        )
        if category:
            query = query.where(BacklogItem.category == category)
        query = query.order_by(
            BacklogItem.priority.asc(),
            BacklogItem.created_at.desc(),
        )

        result = await self.db.execute(query)
        items = result.scalars().all()

        # Contar sub-items por item pai
        items_list = []
        for i in items:
            child_count_result = await self.db.execute(
                select(
                    func.count().label("total"),
                    func.count().filter(BacklogItem.status == "done").label("resolved"),
                ).where(BacklogItem.parent_item_id == i.id)
            )
            child_row = child_count_result.first()
            issues_total = child_row.total if child_row else 0
            issues_resolved = child_row.resolved if child_row else 0

            items_list.append({
                "id": str(i.id),
                "category": i.category,
                "module_type": i.module_type,
                "title": i.title,
                "description": i.description,
                "priority": i.priority,
                "status": i.status,
                "source": i.source,
                "source_version": i.source_version,
                "required_artifacts": json.loads(i.required_artifacts) if i.required_artifacts else [],
                "present_artifacts": json.loads(i.present_artifacts) if i.present_artifacts else [],
                "compliance_iso27001": json.loads(i.compliance_iso27001) if i.compliance_iso27001 else [],
                "warnings": json.loads(i.warnings) if i.warnings else [],
                "generated_code_path": i.generated_code_path,
                "commit_sha": i.commit_sha,
                "fix_severity": i.fix_severity,
                "fix_remediation": i.fix_remediation,
                "issues_total": issues_total,
                "issues_resolved": issues_resolved,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            })

        return items_list
