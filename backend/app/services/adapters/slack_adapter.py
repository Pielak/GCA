"""MVP 20 Fase 20.3 — SlackAdapter via Incoming Webhook.

Uni-direcional em V1 (decisão binária #4 MVP 20). OAuth app + interações
bi-direcionais ficam pra MVP 23 (ChatOps).

Config mínimo:
  - `credentials['webhook_url']`: URL do Incoming Webhook do Slack
    (formato: https://hooks.slack.com/services/T.../B.../xxx).

Formato canônico: Block Kit com:
  - header block (emoji + título curto)
  - context block (projeto + timestamp)
  - section fields (key/value estruturado)
  - actions block com botão "Abrir no GCA" (link profundo)

Modo `link_only_mode`: degrada para mensagem minimalista sem payload
sensível — só header + botão.
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


# Emoji + cor canônica por tipo de evento.
_EVENT_EMOJI: dict[str, str] = {
    "MODULE_APPROVED": ":white_check_mark:",
    "OCG_CONSOLIDATED": ":arrows_counterclockwise:",
    "CODEGEN_COMPLETED": ":hammer_and_wrench:",
    "ERS_REGENERATED": ":page_facing_up:",
    "SECURITY_FINDING_HIGH": ":rotating_light:",
    "BACKUP_FAILED": ":warning:",
}

# Slack aceita attachment color em hex. Mapeia severity canônica.
_SEVERITY_COLOR: dict[str, str] = {
    "info": "#3b82f6",      # blue
    "success": "#10b981",   # emerald
    "warning": "#f59e0b",   # amber
    "danger": "#ef4444",    # red
}


class SlackAdapter(NotifierPort):
    provider = "slack"

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

        # Respeita opt-in events.
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

        if resp.status_code == 200:
            return DeliveryResult(ok=True, delivery_id=resp.headers.get("x-slack-req-id"))
        if resp.status_code in (429, 500, 502, 503, 504):
            return DeliveryResult(
                ok=False,
                error=f"Slack {resp.status_code}: {resp.text[:100]}",
                retryable=True,
            )
        # 4xx (exceto 429) = config ruim; não-retryable.
        return DeliveryResult(
            ok=False,
            error=f"Slack {resp.status_code}: {resp.text[:100]}",
            retryable=False,
        )

    def _build_body(
        self,
        config: NotifierConfig,
        payload: EventPayload,
    ) -> dict:
        """Monta o body Block Kit canônico.

        Link-only mode: retorna mensagem minimalista (só header + link).
        """
        emoji = _EVENT_EMOJI.get(payload.event_type, ":bell:")
        color = _SEVERITY_COLOR.get(payload.severity, "#64748b")

        link_url = self._build_link(config, payload)

        if config.link_only_mode:
            return {
                "text": f"{emoji} {payload.event_type} — {payload.project_name}",
                "attachments": [{
                    "color": color,
                    "blocks": [{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*{emoji} {payload.event_type}*\n"
                                f"Projeto: `{payload.project_name}`\n"
                                f"<{link_url}|Ver detalhes no GCA →>"
                                if link_url else
                                f"*{emoji} {payload.event_type}*\n"
                                f"Projeto: `{payload.project_name}`"
                            ),
                        },
                    }],
                }],
            }

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {payload.title}"[:150],
                    "emoji": True,
                },
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        f"Projeto: *{payload.project_name}* · "
                        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                    ),
                }],
            },
        ]

        if payload.fields:
            # Block Kit aceita até 10 fields por section.
            section_fields = []
            for label, value in payload.fields[:10]:
                section_fields.append({
                    "type": "mrkdwn",
                    "text": f"*{label}*\n{value}",
                })
            blocks.append({
                "type": "section",
                "fields": section_fields,
            })

        if link_url:
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Abrir no GCA"},
                    "url": link_url,
                    "style": "primary",
                }],
            })

        return {
            "text": f"{emoji} {payload.title}",  # fallback plaintext
            "attachments": [{
                "color": color,
                "blocks": blocks,
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
