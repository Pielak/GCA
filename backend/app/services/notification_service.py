"""
Servico de notificacao para Slack, Discord e Email.

Envia notificacoes sobre eventos do pipeline (QA pendente, security issues, etc.).
Configuravel por projeto via Settings.
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


class NotificationService:

    async def notify_pipeline_event(
        self,
        db: AsyncSession,
        project_id: UUID,
        event: str,
        item_title: str,
        details: str = "",
    ) -> dict:
        """Envia notificacao sobre evento do pipeline."""
        # Buscar config de notificacao
        result = await db.execute(
            select(ProjectSettings).where(
                ProjectSettings.project_id == project_id,
                ProjectSettings.setting_type == "notifications",
            )
        )
        settings = result.scalar_one_or_none()
        if not settings:
            return {"sent": False, "reason": "Notificacoes nao configuradas"}

        config = json.loads(settings.settings_json)
        results = []

        # Slack
        slack_url = config.get("slack_webhook_url")
        if slack_url:
            sent = await self._send_slack(slack_url, event, item_title, details)
            results.append({"channel": "slack", "sent": sent})

        # Discord
        discord_url = config.get("discord_webhook_url")
        if discord_url:
            sent = await self._send_discord(discord_url, event, item_title, details)
            results.append({"channel": "discord", "sent": sent})

        return {"sent": len(results) > 0, "channels": results}

    async def _send_slack(self, webhook_url: str, event: str, title: str, details: str) -> bool:
        """Envia mensagem para Slack via webhook."""
        emoji_map = {
            "qa_pending": ":mag:",
            "security_issues": ":warning:",
            "compliance_fail": ":no_entry:",
            "code_generated": ":rocket:",
            "pipeline_complete": ":white_check_mark:",
        }
        emoji = emoji_map.get(event, ":bell:")

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"{emoji} GCA Pipeline — {event.replace('_', ' ').title()}"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Modulo:* {title}\n{details}"}
                },
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                success = resp.status_code == 200
                if success:
                    logger.info("notification.slack_sent", event=event, title=title)
                return success
        except Exception as e:
            logger.warning("notification.slack_failed", error=str(e))
            return False

    async def _send_discord(self, webhook_url: str, event: str, title: str, details: str) -> bool:
        """Envia mensagem para Discord via webhook."""
        color_map = {
            "qa_pending": 0x3498DB,
            "security_issues": 0xE67E22,
            "compliance_fail": 0xE74C3C,
            "code_generated": 0x9B59B6,
            "pipeline_complete": 0x2ECC71,
        }
        color = color_map.get(event, 0x95A5A6)

        payload = {
            "embeds": [
                {
                    "title": f"GCA Pipeline — {event.replace('_', ' ').title()}",
                    "description": f"**Modulo:** {title}\n{details}",
                    "color": color,
                    "footer": {"text": "GCA - Gerenciador Central de Arquiteturas"},
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                success = resp.status_code in (200, 204)
                if success:
                    logger.info("notification.discord_sent", event=event, title=title)
                return success
        except Exception as e:
            logger.warning("notification.discord_failed", error=str(e))
            return False
