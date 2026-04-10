"""
Servico de integracao Figma para geracao de designs a partir de specs.

Usa a Figma API para criar/ler designs.
Quando nao ha Figma configurado, o sistema avisa que documentacao
detalhada de telas sera necessaria.
"""
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.models.base import ProjectSettings
from app.services.vault_service import VaultService

import structlog
logger = structlog.get_logger(__name__)

vault = VaultService()


class FigmaService:

    async def is_configured(self, db: AsyncSession, project_id: UUID) -> bool:
        """Verifica se o projeto tem Figma configurado."""
        result = await db.execute(
            select(ProjectSettings).where(
                ProjectSettings.project_id == project_id,
                ProjectSettings.setting_type == "figma",
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_file(self, db: AsyncSession, project_id: UUID, file_key: str) -> dict:
        """Busca um arquivo Figma pelo file key."""
        token = await vault.get_secret(db, project_id, "figma_token", "main")
        if not token:
            return {"success": False, "error": "Token Figma nao configurado"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.figma.com/v1/files/{file_key}",
                    headers={"X-Figma-Token": token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "success": True,
                        "name": data.get("name"),
                        "last_modified": data.get("lastModified"),
                        "pages": [
                            {"name": page.get("name"), "id": page.get("id")}
                            for page in data.get("document", {}).get("children", [])
                        ],
                    }
                else:
                    return {"success": False, "error": f"Figma API: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_components(self, db: AsyncSession, project_id: UUID, file_key: str) -> dict:
        """Lista componentes de um arquivo Figma."""
        token = await vault.get_secret(db, project_id, "figma_token", "main")
        if not token:
            return {"success": False, "error": "Token Figma nao configurado"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.figma.com/v1/files/{file_key}/components",
                    headers={"X-Figma-Token": token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    components = []
                    for comp in data.get("meta", {}).get("components", []):
                        components.append({
                            "key": comp.get("key"),
                            "name": comp.get("name"),
                            "description": comp.get("description", ""),
                        })
                    return {"success": True, "components": components}
                else:
                    return {"success": False, "error": f"Figma API: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def export_images(
        self, db: AsyncSession, project_id: UUID, file_key: str, node_ids: list[str], format: str = "png"
    ) -> dict:
        """Exporta nodes como imagens (PNG/SVG/PDF)."""
        token = await vault.get_secret(db, project_id, "figma_token", "main")
        if not token:
            return {"success": False, "error": "Token Figma nao configurado"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.figma.com/v1/images/{file_key}",
                    params={"ids": ",".join(node_ids), "format": format, "scale": 2},
                    headers={"X-Figma-Token": token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"success": True, "images": data.get("images", {})}
                else:
                    return {"success": False, "error": f"Figma API: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
