"""
Servico de verificacao de artefatos por IA.

Analisa completude dos artefatos necessarios para cada item do backlog.
Verifica contra ISO 27001 e LGPD. Atualiza status e avisos.
"""
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BacklogItem, ProjectSettings
from app.services.vault_service import VaultService

import structlog
logger = structlog.get_logger(__name__)

vault = VaultService()

# Artefatos tipicos por tipo de modulo
MODULE_REQUIRED_ARTIFACTS: dict[str, list[str]] = {
    "service": ["requisitos_tecnicos", "regras_negocio", "modelo_dados"],
    "controller": ["requisitos_tecnicos", "regras_negocio", "modelo_dados", "endpoints_spec"],
    "model": ["modelo_dados", "regras_negocio"],
    "middleware": ["requisitos_tecnicos", "regras_seguranca"],
    "test": ["requisitos_tecnicos", "casos_teste"],
    "migration": ["modelo_dados"],
    "ui_screen": ["spec_tela", "fluxo_navegacao"],
    "ui_flow": ["fluxo_navegacao", "regras_negocio"],
}

# Checklist ISO 27001 por tipo
ISO27001_CHECKLIST: dict[str, list[str]] = {
    "service": [
        "A.10.1.1 - Controle de acesso por papel (RBAC)",
        "A.12.4 - Logs de auditoria para acoes sensiveis",
        "A.13.1 - Criptografia de dados em transito (TLS 1.2+)",
    ],
    "controller": [
        "A.10.1.1 - Controle de acesso por papel (RBAC)",
        "A.14.1.2 - Validacao de entrada (prevenir injection)",
        "A.12.4 - Logs de auditoria",
    ],
    "model": [
        "A.13.1 - Criptografia de dados sensiveis em repouso",
        "A.18.1 - Conformidade LGPD para dados pessoais",
    ],
    "middleware": [
        "A.10.1.1 - Autenticacao e autorizacao",
        "A.14.1 - Gestao de vulnerabilidades",
    ],
    "ui_screen": [
        "A.14.1.2 - Validacao de entrada no frontend",
        "A.9.4.1 - Protecao contra XSS/CSRF",
    ],
}


class ArtifactVerificationService:
    """Verifica completude de artefatos para itens do backlog."""

    async def verify_item_artifacts(
        self, db: AsyncSession, item: BacklogItem
    ) -> dict:
        """
        Verifica artefatos de um item do backlog.
        Retorna status atualizado e avisos.
        """
        module_type = item.module_type or "service"

        # Determinar artefatos necessarios
        required = MODULE_REQUIRED_ARTIFACTS.get(module_type, ["requisitos_tecnicos"])

        # Determinar artefatos presentes (dos documentos ingeridos)
        present = json.loads(item.present_artifacts) if item.present_artifacts else []

        # Verificar completude
        missing = [a for a in required if a not in present]
        warnings = []

        # Verificar ferramenta de design para UI
        if module_type in ("ui_screen", "ui_flow"):
            has_design_tool = await self._has_design_tool(db, item.project_id)
            if not has_design_tool:
                warnings.append(
                    "Sem ferramenta de design configurada. Documentacao detalhada "
                    "de telas (wireframes, layout, componentes) sera necessaria "
                    "para geracao de codigo frontend."
                )
                # Se nao tem ferramenta, exige spec_tela detalhada
                if "spec_tela_detalhada" not in present and "spec_tela" not in present:
                    missing.append("spec_tela_detalhada")

        # ISO 27001 checklist
        iso_checklist = ISO27001_CHECKLIST.get(module_type, [])

        # Determinar status
        if missing:
            status = "blocked"
            for m in missing:
                warnings.append(f"Artefato faltante: {m}")
        else:
            status = "ready"

        # Atualizar item
        item.required_artifacts = json.dumps(required)
        item.present_artifacts = json.dumps(present)
        item.compliance_iso27001 = json.dumps(iso_checklist)
        item.warnings = json.dumps(warnings)
        if item.status in ("pending", "blocked"):
            item.status = status

        await db.commit()

        return {
            "item_id": str(item.id),
            "status": status,
            "required": required,
            "present": present,
            "missing": missing,
            "warnings": warnings,
            "iso27001": iso_checklist,
        }

    async def verify_all_items(
        self, db: AsyncSession, project_id: UUID
    ) -> list[dict]:
        """Verifica artefatos de todos os itens pendentes/bloqueados do projeto."""
        result = await db.execute(
            select(BacklogItem).where(
                BacklogItem.project_id == project_id,
                BacklogItem.status.in_(["pending", "blocked"]),
            )
        )
        items = result.scalars().all()

        results = []
        for item in items:
            verification = await self.verify_item_artifacts(db, item)
            results.append(verification)

        return results

    async def update_present_artifacts(
        self, db: AsyncSession, item_id: UUID, artifacts: list[str]
    ) -> dict:
        """Atualiza artefatos presentes de um item (quando novo doc ingerido)."""
        item = await db.get(BacklogItem, item_id)
        if not item:
            return {"success": False, "error": "Item nao encontrado"}

        item.present_artifacts = json.dumps(artifacts)
        verification = await self.verify_item_artifacts(db, item)
        return {"success": True, **verification}

    async def _has_design_tool(self, db: AsyncSession, project_id: UUID) -> bool:
        """Verifica se o projeto tem ferramenta de design configurada (ex: Figma)."""
        result = await db.execute(
            select(ProjectSettings).where(
                ProjectSettings.project_id == project_id,
                ProjectSettings.setting_type == "figma",
            )
        )
        return result.scalar_one_or_none() is not None
