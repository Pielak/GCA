"""MVP 20 Fase 20.1c — TrelloAdapter.

Implementa `IssueTrackerPort` para Trello via API v1 (único canônico
do produto, docs: https://developer.atlassian.com/cloud/trello/rest/).

Modelo de dados do Trello é mais simples que Jira: boards contêm listas
que contêm cards. Não tem "status" como campo — o status é a LISTA onde
o card está. Ex: lista "Backlog" = todo, lista "Doing" = in_progress,
etc. Mapeamento canônico vem do `config.status_mapping` invertido
(status_canonical → list_id).

Auth: query params `key` (API key) + `token` (user token). Ambos passados
em toda chamada — padrão Trello.

Webhook: Trello assina webhooks com HMAC-SHA1(callbackURL + body, secret).
Header `X-Trello-Webhook`. `config.credentials['webhook_secret']` = o
mesmo secret usado no registro do webhook + `config.extra['callback_url']`
é o URL público que recebe.

Markdown: Trello aceita markdown nativo em `desc` e `commentCard` — zero
conversão necessária.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Optional

import httpx
import structlog

from app.services.ports.issue_tracker_port import (
    CanonicalPriority,
    CanonicalStatus,
    IssueEvent,
    IssuePayload,
    IssueTrackerAPIError,
    IssueTrackerAuthError,
    IssueTrackerConfigError,
    IssueTrackerNotFound,
    IssueTrackerPort,
    IssueTrackerRateLimitError,
    ProviderConfig,
)


logger = structlog.get_logger(__name__)


TRELLO_API_BASE = "https://api.trello.com/1"


# Status canônicos → nomes de lista padrão do Trello (usado quando
# config.status_mapping está vazio e default_project_key aponta para
# um board com essas listas exatas).
_DEFAULT_LIST_NAMES: dict[CanonicalStatus, str] = {
    "todo": "Backlog",
    "in_progress": "Doing",
    "review": "Review",
    "done": "Done",
    "cancelled": "Cancelled",
}

# Priority → label color canônico (criticando via labels nativas do Trello).
_PRIORITY_LABEL_COLOR: dict[CanonicalPriority, str] = {
    "critical": "red",
    "high": "orange",
    "medium": "yellow",
    "low": "green",
}


class TrelloAdapter(IssueTrackerPort):
    """Adapter para Trello REST API v1."""

    provider = "trello"

    _client: Optional[httpx.AsyncClient]

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None, timeout: float = 15.0):
        self._client = client
        self._timeout = timeout

    # ─── HTTP helpers ─────────────────────────────────────────────────

    def _auth_params(self, config: ProviderConfig) -> dict[str, str]:
        key = config.credentials.get("api_key")
        token = config.credentials.get("api_token")
        if not key or not token:
            raise IssueTrackerConfigError(
                "Trello exige credentials={'api_key': ..., 'api_token': ...}"
            )
        return {"key": key, "token": token}

    async def _request(
        self,
        config: ProviderConfig,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> Any:
        url = f"{TRELLO_API_BASE}{path}"
        merged_params = {**self._auth_params(config), **(params or {})}

        async def _do(client: httpx.AsyncClient) -> httpx.Response:
            return await client.request(
                method, url,
                params=merged_params,
                data=data,  # Trello prefere form-encoded
                timeout=self._timeout,
            )

        try:
            if self._client is not None:
                resp = await _do(self._client)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await _do(c)
        except httpx.HTTPError as exc:
            logger.warning("trello.http_error", url=url, error=str(exc))
            raise IssueTrackerAPIError(f"falha HTTP chamando {url}: {exc}") from exc

        if resp.status_code in (401, 403):
            raise IssueTrackerAuthError(
                f"Trello rejeitou credencial ({resp.status_code}): "
                f"confira api_key + api_token no vault"
            )
        if resp.status_code == 404:
            raise IssueTrackerNotFound(f"Trello 404 em {path}")
        if resp.status_code == 429:
            raise IssueTrackerRateLimitError(
                f"Trello 429 em {path} — backoff necessário"
            )
        if resp.status_code >= 400:
            raise IssueTrackerAPIError(
                f"Trello {resp.status_code} em {path}: {resp.text[:200]}"
            )

        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise IssueTrackerAPIError(
                f"Trello retornou conteúdo não-JSON em {path}"
            ) from exc

    async def _resolve_list_id(
        self,
        config: ProviderConfig,
        target_status: CanonicalStatus,
    ) -> Optional[str]:
        """Resolve o ID da lista no board correspondente ao status canônico.

        Estratégia:
          1. Se config.extra['list_ids'] (dict canônico → list_id) existir,
             usa diretamente (mais rápido, sem chamar API).
          2. Senão, lista as listas do board e tenta match por:
             2a. nome customizado via config.status_mapping reverso;
             2b. nomes default (_DEFAULT_LIST_NAMES).
        """
        list_ids = config.extra.get("list_ids") or {}
        explicit = list_ids.get(target_status)
        if explicit:
            return explicit

        board_id = config.default_project_key
        if not board_id:
            raise IssueTrackerConfigError(
                "Trello exige default_project_key = board_id no ProviderConfig"
            )

        lists = await self._request(
            config, "GET", f"/boards/{board_id}/lists",
            params={"fields": "id,name"},
        )
        name_to_id = {lst["name"]: lst["id"] for lst in lists}

        preferred_names = [
            raw for raw, canonical in config.status_mapping.items()
            if canonical == target_status
        ]
        for name in preferred_names:
            if name in name_to_id:
                return name_to_id[name]

        default_name = _DEFAULT_LIST_NAMES.get(target_status)
        if default_name and default_name in name_to_id:
            return name_to_id[default_name]
        return None

    def _classify_list_name(
        self,
        list_name: str,
        config: ProviderConfig,
    ) -> CanonicalStatus:
        """Resolve lista → status canônico.

        Ordem:
          1. config.status_mapping (override do GP).
          2. _DEFAULT_LIST_NAMES inverso (Backlog → todo, etc).
          3. Fallback todo.
        """
        mapped = config.status_mapping.get(list_name)
        if mapped:
            return mapped
        for canonical, name in _DEFAULT_LIST_NAMES.items():
            if name.lower() == list_name.lower():
                return canonical
        return "todo"

    # ─── Contrato IssueTrackerPort ────────────────────────────────────

    async def create_issue(
        self,
        config: ProviderConfig,
        *,
        title: str,
        description_markdown: str,
        priority: Optional[CanonicalPriority] = None,
        labels: Optional[list[str]] = None,
    ) -> IssuePayload:
        target_list_id = await self._resolve_list_id(config, "todo")
        if not target_list_id:
            raise IssueTrackerConfigError(
                "Nenhuma lista Trello mapeada para status 'todo'. "
                "Configure list_ids no config.extra ou crie lista 'Backlog' no board."
            )

        data: dict[str, Any] = {
            "idList": target_list_id,
            "name": title[:512],  # Trello limita 16k mas truncamos defensivamente
            "desc": description_markdown or "",
        }
        if labels:
            # Trello aceita idLabels (strings), não nomes — assumimos que
            # caller passou IDs de label já resolvidos. Labels de priority
            # são tratadas abaixo via color.
            data["idLabels"] = ",".join(labels)

        result = await self._request(config, "POST", "/cards", data=data)
        external_id = result.get("id")
        if not external_id:
            raise IssueTrackerAPIError(
                f"Trello criou card mas não retornou id: {result!r}"
            )

        # Se prioridade definida, adiciona label por cor (Trello idiomático).
        if priority and priority in _PRIORITY_LABEL_COLOR:
            try:
                await self._request(
                    config, "POST", f"/cards/{external_id}/labels",
                    data={"color": _PRIORITY_LABEL_COLOR[priority],
                          "name": f"priority-{priority}"},
                )
            except IssueTrackerError:
                # Label é cosmético; falha não deve quebrar criação.
                logger.warning("trello.label_add_failed",
                                card_id=external_id, priority=priority)

        return await self.get_issue(config, external_id)

    async def update_status(
        self,
        config: ProviderConfig,
        external_id: str,
        status: CanonicalStatus,
    ) -> IssuePayload:
        target_list_id = await self._resolve_list_id(config, status)
        if not target_list_id:
            raise IssueTrackerAPIError(
                f"Nenhuma lista Trello mapeada para status '{status}'. "
                f"Configure status_mapping ou list_ids no projeto."
            )

        await self._request(
            config, "PUT", f"/cards/{external_id}",
            data={"idList": target_list_id},
        )
        return await self.get_issue(config, external_id)

    async def get_issue(
        self,
        config: ProviderConfig,
        external_id: str,
    ) -> IssuePayload:
        card = await self._request(
            config, "GET", f"/cards/{external_id}",
            params={"fields": "name,shortUrl,idList,labels,closed"},
        )

        # Resolve nome da lista — 1 chamada extra por get_issue, aceitável
        # pro volume esperado (<1k/dia). Se virar gargalo, cache em memória
        # por board_id com TTL curto.
        list_id = card.get("idList")
        list_name = ""
        if list_id:
            try:
                lst = await self._request(
                    config, "GET", f"/lists/{list_id}",
                    params={"fields": "name"},
                )
                list_name = lst.get("name", "")
            except IssueTrackerError:
                pass

        canonical = self._classify_list_name(list_name, config) if list_name else "todo"
        if card.get("closed"):
            # Card arquivado no Trello = cancelado pro GCA.
            canonical = "cancelled"

        labels = card.get("labels", []) or []
        priority: Optional[CanonicalPriority] = None
        for label in labels:
            color = label.get("color")
            for pri, col in _PRIORITY_LABEL_COLOR.items():
                if col == color:
                    priority = pri
                    break
            if priority:
                break

        return IssuePayload(
            external_id=external_id,
            url=card.get("shortUrl"),
            title=card.get("name", "") or "(sem título)",
            status_canonical=canonical,
            status_raw=list_name,
            priority=priority,
            provider_specific={
                "list_id": list_id,
                "labels": [{"id": l.get("id"), "name": l.get("name"), "color": l.get("color")}
                           for l in labels],
                "closed": card.get("closed", False),
            },
        )

    async def add_comment(
        self,
        config: ProviderConfig,
        external_id: str,
        comment_markdown: str,
    ) -> None:
        await self._request(
            config, "POST", f"/cards/{external_id}/actions/comments",
            data={"text": comment_markdown or ""},
        )

    # ─── Webhook ──────────────────────────────────────────────────────

    def verify_webhook(
        self,
        config: ProviderConfig,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Valida X-Trello-Webhook: HMAC-SHA1(callbackURL + body, secret) em base64.

        Trello espec: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/#webhook-signatures

        `config.extra['callback_url']` é o URL público que recebe o webhook
        (exatamente como foi registrado na criação do webhook).
        """
        secret = config.credentials.get("webhook_secret")
        callback_url = config.extra.get("callback_url")
        if not secret or not callback_url:
            logger.warning("trello.webhook.missing_config")
            return False

        provided = (
            headers.get("X-Trello-Webhook")
            or headers.get("x-trello-webhook")
            or ""
        )
        if not provided:
            return False

        mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha1)
        mac.update(raw_body)
        mac.update(callback_url.encode("utf-8"))
        expected = base64.b64encode(mac.digest()).decode("ascii")
        return hmac.compare_digest(provided, expected)

    def parse_webhook(
        self,
        config: ProviderConfig,
        payload: dict[str, Any],
    ) -> Optional[IssueEvent]:
        """Converte payload bruto de webhook Trello em IssueEvent canônico.

        Trello envia `action.type` identificando o tipo de evento. Relevantes:
          - createCard        → issue_created
          - updateCard        → issue_updated OU status_changed (se mudou idList)
          - commentCard       → issue_updated (cosmético)
          - deleteCard        → issue_deleted
          - copyCard          → issue_created (duplicata)
        """
        action = payload.get("action", {}) or {}
        action_type = action.get("type")
        data = action.get("data", {}) or {}
        card = data.get("card", {}) or {}
        external_id = card.get("id")
        if not external_id or not action_type:
            return None

        project_id = _resolve_project_id_from_webhook(config)
        if not project_id:
            logger.warning("trello.webhook.no_project_binding",
                            external_id=external_id)
            return None

        title = card.get("name")
        list_after = (data.get("listAfter") or data.get("list") or {}).get("name", "")
        status_raw = list_after or ""
        canonical = (
            self._classify_list_name(list_after, config)
            if list_after else None
        )

        if action_type in ("createCard", "copyCard"):
            return IssueEvent(
                event_type="issue_created",
                external_id=external_id,
                project_id=project_id,
                status_canonical=canonical,
                status_raw=status_raw,
                title=title,
                raw_payload=payload,
            )
        if action_type == "deleteCard":
            return IssueEvent(
                event_type="issue_deleted",
                external_id=external_id,
                project_id=project_id,
                raw_payload=payload,
            )
        if action_type == "updateCard":
            # listBefore vs listAfter indica mudança de status.
            list_before = data.get("listBefore")
            if list_before:
                return IssueEvent(
                    event_type="status_changed",
                    external_id=external_id,
                    project_id=project_id,
                    status_canonical=canonical,
                    status_raw=status_raw,
                    title=title,
                    raw_payload=payload,
                )
            # Card arquivado = fechado = cancelled.
            if data.get("old", {}).get("closed") is False and card.get("closed"):
                return IssueEvent(
                    event_type="status_changed",
                    external_id=external_id,
                    project_id=project_id,
                    status_canonical="cancelled",
                    status_raw="archived",
                    title=title,
                    raw_payload=payload,
                )
            return IssueEvent(
                event_type="issue_updated",
                external_id=external_id,
                project_id=project_id,
                status_canonical=canonical,
                status_raw=status_raw,
                title=title,
                raw_payload=payload,
            )
        if action_type == "commentCard":
            return IssueEvent(
                event_type="issue_updated",
                external_id=external_id,
                project_id=project_id,
                title=title,
                raw_payload=payload,
            )
        return None


# ─── Helpers internos ─────────────────────────────────────────────────


def _resolve_project_id_from_webhook(config: ProviderConfig) -> Optional[str]:
    pid = config.extra.get("gca_project_id")
    return str(pid) if pid else None


# Re-export base class do Port pra simplificar imports.
from app.services.ports.issue_tracker_port import IssueTrackerError  # noqa: E402
