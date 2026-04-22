"""MVP 20 Fase 20.3 — Porta canônica de Notifier externo.

Notifier é uni-direcional em V1 (decisão binária #4 MVP 20): mensagens
vão, reações/comandos não voltam. Bi-direcional (ChatOps) é MVP 23
separado.

Adapters concretos V1:
  - SlackAdapter (via Incoming Webhook URL)

Futuros (sob demanda): Microsoft Teams, Mattermost, Rocket.Chat, Discord.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# Eventos canônicos que o GCA pode disparar (conforme contrato §7 MVP 20).
CanonicalEventType = Literal[
    "MODULE_APPROVED",
    "OCG_CONSOLIDATED",
    "CODEGEN_COMPLETED",
    "ERS_REGENERATED",
    "SECURITY_FINDING_HIGH",
    "BACKUP_FAILED",
]

ALL_CANONICAL_EVENTS: tuple[CanonicalEventType, ...] = (
    "MODULE_APPROVED",
    "OCG_CONSOLIDATED",
    "CODEGEN_COMPLETED",
    "ERS_REGENERATED",
    "SECURITY_FINDING_HIGH",
    "BACKUP_FAILED",
)


NotifierProvider = Literal["slack", "teams", "mattermost", "discord"]


@dataclass
class NotifierConfig:
    """Config opaca por projeto. Adapter interpreta.

    Campos canônicos:
      - `credentials`: dict com chaves do vault (webhook URL, bot token, etc).
      - `channel`: canal destino (quando aplicável — #gca-events do Slack,
        canal_id do Teams, etc).
      - `opted_in_events`: eventos que o projeto quer receber. None ou
        lista vazia = todos os canônicos.
      - `link_only_mode`: se True, mensagem só tem link pro GCA (sem
        payload sensível). Pra cliente regulado.
      - `gca_base_url`: URL pública do GCA pra montar link profundo.
      - `extra`: campos específicos do adapter.
    """

    credentials: dict[str, str]
    channel: str = ""
    opted_in_events: Optional[list[CanonicalEventType]] = None
    link_only_mode: bool = False
    gca_base_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def is_opted_in(self, event_type: CanonicalEventType) -> bool:
        """Default = opted in em todos quando lista não configurada."""
        if not self.opted_in_events:
            return True
        return event_type in self.opted_in_events


@dataclass
class EventPayload:
    """Payload canônico para `NotifierPort.send`.

    Adapter traduz pra formato do provider (Slack Block Kit, Teams
    Adaptive Card, etc).

    Campos canônicos mínimos:
      - `event_type`: um dos ALL_CANONICAL_EVENTS.
      - `title`: linha principal (emoji + resumo).
      - `project_name`: nome do projeto pra contexto.
      - `project_id`: UUID do projeto (para link profundo).
      - `fields`: lista de (label, value) pra mostrar contexto estruturado.
      - `link_path`: path relativo dentro do GCA (ex: /projects/:id/gatekeeper).
      - `severity`: info | success | warning | danger — colore o adapter.
    """

    event_type: CanonicalEventType
    title: str
    project_name: str
    project_id: str
    fields: list[tuple[str, str]] = field(default_factory=list)
    link_path: Optional[str] = None
    severity: Literal["info", "success", "warning", "danger"] = "info"


@dataclass
class DeliveryResult:
    """Resultado da tentativa de envio.

    `ok=True` + `delivery_id` quando aceito pelo provider. `ok=False` +
    `error` quando falhou — caller decide retry vs. descartar.

    `retryable` é dica semântica: 5xx/429 → True; 4xx de config → False.
    """

    ok: bool
    delivery_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False


class NotifierPort(ABC):
    provider: NotifierProvider

    @abstractmethod
    async def send(
        self,
        config: NotifierConfig,
        payload: EventPayload,
    ) -> DeliveryResult:
        """Envia o evento ao provider. Nunca levanta — retorna DeliveryResult
        com ok=False + retryable quando apropriado.
        """
        raise NotImplementedError


# ─── Exceções canônicas ────────────────────────────────────────────────


class NotifierError(Exception):
    pass


class NotifierConfigError(NotifierError):
    pass


# ─── Registry canônico ─────────────────────────────────────────────────

_REGISTRY: dict[str, NotifierPort] = {}


def register_notifier(adapter: NotifierPort) -> None:
    if not getattr(adapter, "provider", None):
        raise NotifierConfigError(
            f"Adapter {type(adapter).__name__} não definiu `provider`"
        )
    _REGISTRY[adapter.provider] = adapter


def get_notifier(provider: str) -> NotifierPort:
    adapter = _REGISTRY.get(provider)
    if adapter is None:
        raise NotifierConfigError(
            f"Notifier '{provider}' não registrado. "
            f"Disponíveis: {list(_REGISTRY.keys()) or '[nenhum]'}"
        )
    return adapter


def registered_notifiers() -> list[str]:
    return sorted(_REGISTRY.keys())


def _clear_notifier_registry_for_tests() -> None:
    _REGISTRY.clear()
