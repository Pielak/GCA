"""MVP 22 Fase única — TeamsAdapter via Incoming Webhook + Adaptive Card.

Implementa `NotifierPort` para Microsoft Teams. Segue o mesmo padrão do
SlackAdapter (MVP 20.3): uni-direcional, nunca levanta, retorna
DeliveryResult com retryable.

V1 usa **Incoming Webhook** apontando para Power Automate Workflow
(substituto canônico do Office 365 Connector deprecated em Dez/2024)
ou Connector legado. Payload: Adaptive Card v1.4 envelope dentro de
`attachments`.

Bot Framework + interações bi-direcionais ficam parked para MVP futuro
(ChatOps). Em V1 a integração é **apenas envio**.

Config mínimo:
  - `credentials['webhook_url']`: URL do webhook do Teams (Power Automate
    ou Office 365 Connector).

Formato Teams canônico com Adaptive Card:
  - TextBlock header + FactSet com fields + ActionSet com botão "Abrir no GCA"
  - `link_only_mode`: degrada pra Adaptive Card minimalista (sem FactSet)

Severity → themeColor hex canônico (mesmos valores do SlackAdapter).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from app.services.ports.notifier_port import (
    DeliveryResult,
    EventPayload,
    NotifierConfig,
    NotifierPort,
)


logger = structlog.get_logger(__name__)


_EVENT_EMOJI: dict[str, str] = {
    "MODULE_APPROVED": "✅",
    "OCG_CONSOLIDATED": "🔄",
    "CODEGEN_COMPLETED": "🛠️",
    "ERS_REGENERATED": "📄",
    "SECURITY_FINDING_HIGH": "🚨",
    "BACKUP_FAILED": "⚠️",
}

# Teams Adaptive Card accent colors (canonical semantic mapping).
_SEVERITY_COLOR: dict[str, str] = {
    "info": "default",
    "success": "good",
    "warning": "warning",
    "danger": "attention",
}


class TeamsAdapter(NotifierPort):
    provider = "teams"

    _client: Optional[httpx.AsyncClient]

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None, timeout: float = 10.0):
        self._client = client
        self._timeout = timeout

    async def send(
        self,
        config: NotifierConfig,
        payload: EventPayload,
    ) -> DeliveryResult:
        webhook_url = config.credentials.get("webhook_url")
        if not webhook_url:
            return DeliveryResult(
                ok=False,
                error="webhook_url ausente em credentials",
                retryable=False,
            )

        if not config.is_opted_in(payload.event_type):
            return DeliveryResult(
                ok=False,
                error=f"event_type {payload.event_type} não está em opted_in_events",
                retryable=False,
            )

        body = self._build_body(config, payload)

        try:
            async def _do(client: httpx.AsyncClient) -> httpx.Response:
                return await client.post(
                    webhook_url, json=body, timeout=self._timeout,
                )

            if self._client is not None:
                resp = await _do(self._client)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await _do(c)
        except httpx.HTTPError as exc:
            return DeliveryResult(
                ok=False,
                error=f"HTTP error: {exc}",
                retryable=True,
            )

        # Teams webhook retorna 200 (Workflows) ou 202 (legacy connectors).
        if resp.status_code in (200, 202):
            return DeliveryResult(
                ok=True,
                delivery_id=resp.headers.get("request-id") or resp.headers.get("x-ms-correlation-request-id"),
            )
        if resp.status_code in (429, 500, 502, 503, 504):
            return DeliveryResult(
                ok=False,
                error=f"Teams {resp.status_code}: {resp.text[:100]}",
                retryable=True,
            )
        return DeliveryResult(
            ok=False,
            error=f"Teams {resp.status_code}: {resp.text[:100]}",
            retryable=False,
        )

    def _build_body(
        self,
        config: NotifierConfig,
        payload: EventPayload,
    ) -> dict:
        emoji = _EVENT_EMOJI.get(payload.event_type, "🔔")
        accent = _SEVERITY_COLOR.get(payload.severity, "default")
        link_url = self._build_link(config, payload)

        if config.link_only_mode:
            body_elements = [
                {
                    "type": "TextBlock",
                    "text": f"{emoji} {payload.event_type}",
                    "weight": "Bolder",
                    "size": "Medium",
                    "color": accent,
                },
                {
                    "type": "TextBlock",
                    "text": f"Projeto: **{payload.project_name}**",
                    "wrap": True,
                    "spacing": "Small",
                },
            ]
            if link_url:
                body_elements.append({
                    "type": "TextBlock",
                    "text": f"[Ver detalhes no GCA →]({link_url})",
                    "wrap": True,
                    "spacing": "Small",
                })
        else:
            body_elements = [
                {
                    "type": "TextBlock",
                    "text": f"{emoji} {payload.title}",
                    "weight": "Bolder",
                    "size": "Large",
                    "color": accent,
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": (
                        f"Projeto: **{payload.project_name}** · "
                        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                    ),
                    "wrap": True,
                    "isSubtle": True,
                    "spacing": "Small",
                },
            ]

            if payload.fields:
                # FactSet é o idioma canônico Adaptive Card pra key/value.
                body_elements.append({
                    "type": "FactSet",
                    "facts": [
                        {"title": label, "value": value}
                        for label, value in payload.fields[:10]
                    ],
                })

        card: dict = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": body_elements,
        }

        if link_url and not config.link_only_mode:
            card["actions"] = [{
                "type": "Action.OpenUrl",
                "title": "Abrir no GCA",
                "url": link_url,
            }]

        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }],
        }

    def _build_link(
        self,
        config: NotifierConfig,
        payload: EventPayload,
    ) -> Optional[str]:
        if not config.gca_base_url or not payload.link_path:
            return None
        base = config.gca_base_url.rstrip("/")
        path = payload.link_path if payload.link_path.startswith("/") else f"/{payload.link_path}"
        return f"{base}{path}"
