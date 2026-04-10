"""
Servico de SAST (Static Application Security Testing).

Integra com Semgrep e SonarQube quando tokens estao configurados.
Fallback para analise via LLM quando ferramentas externas nao disponiveis.
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


class SASTService:
    """Servico de analise estatica de seguranca."""

    async def scan_with_semgrep(
        self, db: AsyncSession, project_id: UUID, code: str, language: str = "python"
    ) -> dict | None:
        """Executa scan via Semgrep API se token configurado."""
        token = await vault.get_secret(db, project_id, "semgrep_token", "main")
        if not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://semgrep.dev/api/v1/deployments/scan",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "targets": [{"content": code, "language": language}],
                        "rules_config": "p/owasp-top-ten",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    findings = data.get("findings", [])
                    return {
                        "tool": "semgrep",
                        "findings": [
                            {
                                "severity": f.get("severity", "WARNING"),
                                "type": f.get("check_id", "unknown"),
                                "message": f.get("extra", {}).get("message", ""),
                                "location": f"line {f.get('start', {}).get('line', '?')}",
                            }
                            for f in findings
                        ],
                        "count": len(findings),
                    }
                else:
                    logger.warning("semgrep.api_error", status=resp.status_code)
                    return None
        except Exception as e:
            logger.warning("semgrep.failed", error=str(e))
            return None

    async def scan_with_sonarqube(
        self, db: AsyncSession, project_id: UUID, project_key: str
    ) -> dict | None:
        """Busca resultados do SonarQube se token configurado."""
        result = await db.execute(
            select(ProjectSettings).where(
                ProjectSettings.project_id == project_id,
                ProjectSettings.setting_type == "sonarqube",
            )
        )
        settings = result.scalar_one_or_none()
        if not settings:
            return None

        config = json.loads(settings.settings_json)
        base_url = config.get("url", "")
        token = await vault.get_secret(db, project_id, "sonarqube_token", "main")
        if not base_url or not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{base_url}/api/issues/search",
                    params={"componentKeys": project_key, "types": "VULNERABILITY,BUG", "ps": 50},
                    auth=(token, ""),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    issues = data.get("issues", [])
                    return {
                        "tool": "sonarqube",
                        "findings": [
                            {
                                "severity": i.get("severity", "MINOR"),
                                "type": i.get("type", "unknown"),
                                "message": i.get("message", ""),
                                "location": i.get("component", ""),
                            }
                            for i in issues
                        ],
                        "count": len(issues),
                    }
                else:
                    return None
        except Exception as e:
            logger.warning("sonarqube.failed", error=str(e))
            return None

    async def get_available_tools(self, db: AsyncSession, project_id: UUID) -> list[str]:
        """Retorna lista de ferramentas SAST configuradas."""
        tools = []

        semgrep_token = await vault.get_secret(db, project_id, "semgrep_token", "main")
        if semgrep_token:
            tools.append("semgrep")

        sonar_result = await db.execute(
            select(ProjectSettings).where(
                ProjectSettings.project_id == project_id,
                ProjectSettings.setting_type == "sonarqube",
            )
        )
        if sonar_result.scalar_one_or_none():
            tools.append("sonarqube")

        return tools
