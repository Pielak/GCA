"""MVP 20 Fase 20.1a — Porta canônica de Issue Tracker.

Adapters concretos (JiraAdapter, TrelloAdapter, …) herdam de
`IssueTrackerPort` e implementam o contrato mínimo. A porta não conhece
detalhes específicos de provider — Jira-isms ficam em `provider_specific`
do payload de saída.

Decisões binárias refletidas aqui (ver §7 MVP 20 do contrato canônico):
- #1 config é por projeto (recebida via `ProviderConfig` a cada chamada)
- #2 status mapping configurável por projeto (resolvido no adapter)
- #5 webhooks exigem signing secret + idempotência + replay prevention
  (método `verify_webhook` obrigatório)

Zero LLM no caminho crítico — adapter é determinístico.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# ─── Tipos canônicos ───────────────────────────────────────────────────

CanonicalStatus = Literal["todo", "in_progress", "review", "done", "cancelled"]
CanonicalPriority = Literal["low", "medium", "high", "critical"]
Provider = Literal["jira", "trello", "linear", "asana", "github"]


@dataclass
class ProviderConfig:
    """Config opaca por projeto — adapter interpreta conforme seu schema.

    Campos canônicos:
      - `credentials`: dict com chaves do vault (nunca plaintext em logs).
      - `base_url`: endpoint do provider (on-prem ou cloud).
      - `default_project_key`: identificador do "projeto" no provider
        (board do Trello, projeto do Jira, etc).
      - `status_mapping`: dict {status_raw → CanonicalStatus} configurável
        pelo GP; adapter aplica na entrada de webhook e na saída de create.
      - `extra`: campos específicos que só o adapter conhece.
    """

    credentials: dict[str, str]
    base_url: str
    default_project_key: str
    status_mapping: dict[str, CanonicalStatus] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class IssuePayload:
    """Payload canônico retornado por `create_issue` / `get_issue`.

    O `provider_specific` absorve campos que não cabem no schema canônico
    (epic_key do Jira, list_id do Trello, etc) sem poluir a porta.
    """

    external_id: str
    url: Optional[str]
    title: str
    status_canonical: CanonicalStatus
    status_raw: str
    priority: Optional[CanonicalPriority] = None
    provider_specific: dict[str, Any] = field(default_factory=dict)


@dataclass
class IssueEvent:
    """Evento normalizado emitido por `webhook_handler`.

    `event_type` canônico:
      - `issue_created`    — issue nasceu no provider externamente ao GCA.
      - `issue_updated`    — qualquer campo mudou.
      - `status_changed`   — transição de status (subset de updated, útil).
      - `issue_deleted`    — issue foi removida no provider.

    `project_id` do GCA é resolvido pelo adapter a partir do payload do
    provider (ex: Jira project key → lookup em `project_settings.integrations`).
    """

    event_type: Literal["issue_created", "issue_updated", "status_changed", "issue_deleted"]
    external_id: str
    project_id: str
    status_canonical: Optional[CanonicalStatus] = None
    status_raw: Optional[str] = None
    title: Optional[str] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


# ─── Porta canônica ────────────────────────────────────────────────────


class IssueTrackerPort(ABC):
    """Interface mínima que todo adapter de tracker deve implementar.

    Operações canônicas:
      - create_issue      : cria issue no provider a partir de módulo aprovado
      - update_status     : força transição canônica (ex: módulo done → issue done)
      - get_issue         : busca estado atual (reconciliação)
      - add_comment       : comentário em markdown (rastro do GCA no tracker)
      - verify_webhook    : valida assinatura do payload recebido
      - parse_webhook     : converte payload bruto em IssueEvent normalizado

    Adapter NÃO decide se deve criar/sincronizar — quem orquestra é o
    `issue_tracker_service`. Adapter só executa.
    """

    #: Provider canônico que este adapter implementa. Subclasse define.
    provider: Provider

    @abstractmethod
    async def create_issue(
        self,
        config: ProviderConfig,
        *,
        title: str,
        description_markdown: str,
        priority: Optional[CanonicalPriority] = None,
        labels: Optional[list[str]] = None,
    ) -> IssuePayload:
        """Cria issue no provider. Retorna payload canônico.

        Adapter é responsável por:
          - traduzir markdown do GCA pro formato aceito pelo provider
            (ADF no Jira, Markdown no Trello, etc);
          - aplicar `config.status_mapping` reverso (canônico → raw);
          - popular `provider_specific` com IDs nativos do provider.

        Erros esperados: `IssueTrackerAuthError`, `IssueTrackerAPIError`,
        `IssueTrackerRateLimitError`. Caller trata.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self,
        config: ProviderConfig,
        external_id: str,
        status: CanonicalStatus,
    ) -> IssuePayload:
        """Aplica transição canônica no provider.

        Adapter resolve workflow específico (Jira transitions ID, mover
        Trello card pra lista correta, etc). Retorna payload canônico
        atualizado — `status_raw` reflete o estado final no provider.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_issue(
        self,
        config: ProviderConfig,
        external_id: str,
    ) -> IssuePayload:
        """Busca estado atual — usado em reconciliação e debug.

        Pode retornar `IssueTrackerNotFound` se issue foi removida no
        provider externamente.
        """
        raise NotImplementedError

    @abstractmethod
    async def add_comment(
        self,
        config: ProviderConfig,
        external_id: str,
        comment_markdown: str,
    ) -> None:
        """Comentário com rastro do GCA (ex: link pro commit, menção a
        finding de segurança). Adapter traduz markdown conforme provider."""
        raise NotImplementedError

    @abstractmethod
    def verify_webhook(
        self,
        config: ProviderConfig,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Valida assinatura + replay prevention do webhook.

        Contrato obrigatório:
          - HMAC/signature do provider validado contra `config.credentials`;
          - timestamp/nonce checado contra janela máxima (canônico: 5 min);
          - retorna True se payload é autêntico e não-replay; False caso contrário.

        Nunca levanta — falha silenciosa retorna False pro caller decidir
        resposta HTTP (tipicamente 401).
        """
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(
        self,
        config: ProviderConfig,
        payload: dict[str, Any],
    ) -> Optional[IssueEvent]:
        """Converte payload bruto em IssueEvent normalizado.

        Retorna None quando o evento não é relevante (ex: watcher adicionado,
        comentário não-GCA) — caller descarta sem erro.

        Adapter aplica `config.status_mapping` pra traduzir status raw → canônico.
        """
        raise NotImplementedError


# ─── Exceções canônicas ────────────────────────────────────────────────


class IssueTrackerError(Exception):
    """Base — todos os erros de adapter herdam daqui."""


class IssueTrackerAuthError(IssueTrackerError):
    """Credencial inválida ou expirada."""


class IssueTrackerAPIError(IssueTrackerError):
    """Erro genérico do provider (5xx, schema inesperado)."""


class IssueTrackerRateLimitError(IssueTrackerError):
    """Provider retornou 429. Caller implementa backoff."""


class IssueTrackerNotFound(IssueTrackerError):
    """Issue não existe no provider (foi deletada externamente)."""


class IssueTrackerConfigError(IssueTrackerError):
    """Config do projeto incompleta ou inválida — caller bloqueia com 400."""


# ─── Registry canônico ─────────────────────────────────────────────────

# Preenchido em runtime por `issue_tracker_service.register_adapter`.
# Mantido aqui pra que testes de contrato possam inspecionar sem circular.
_REGISTRY: dict[str, IssueTrackerPort] = {}


def register_adapter(adapter: IssueTrackerPort) -> None:
    """Registra adapter no registry canônico.

    Idempotente: registrar 2x o mesmo provider substitui o anterior
    (útil em testes). Caller é responsável por que `adapter.provider`
    esteja setado.
    """
    if not getattr(adapter, "provider", None):
        raise IssueTrackerConfigError(
            f"Adapter {type(adapter).__name__} não definiu atributo `provider`"
        )
    _REGISTRY[adapter.provider] = adapter


def get_adapter(provider: str) -> IssueTrackerPort:
    """Busca adapter registrado. Levanta `IssueTrackerConfigError` se ausente."""
    adapter = _REGISTRY.get(provider)
    if adapter is None:
        raise IssueTrackerConfigError(
            f"Provider '{provider}' não tem adapter registrado. "
            f"Providers disponíveis: {list(_REGISTRY.keys()) or '[nenhum]'}"
        )
    return adapter


def registered_providers() -> list[str]:
    """Lista providers com adapter registrado — útil pra UI de config."""
    return sorted(_REGISTRY.keys())


def _clear_registry_for_tests() -> None:
    """Uso exclusivo de testes — limpa o registry global."""
    _REGISTRY.clear()
