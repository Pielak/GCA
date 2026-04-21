"""MVP 20 Fase 20.1b — JiraAdapter.

Implementa `IssueTrackerPort` para Jira Cloud (e Jira Server/Data Center
quando `base_url` apontar pra instância self-hosted). Usa Jira Cloud REST
API v3 — endpoint canônico `/rest/api/3`.

Auth: Basic Auth com `email:api_token` (Atlassian Cloud canônico).
OAuth2 fica pra V2 do MVP 20 (requer OAuth app registrada na Atlassian).

Webhook: Atlassian assina webhooks com JWT quando instalados via Connect
app. Para webhooks configurados manualmente (caminho V1), a assinatura
vem como HMAC-SHA256 no header `X-Hub-Signature` calculado com secret
gerado pelo admin do projeto Jira. Aceitamos ambos os modos.

Markdown → ADF (Atlassian Document Format): conversão simplificada que
cobre os casos comuns (parágrafo, bold, italic, inline code, code block,
link, bullet list). Markdown complexo vira parágrafo texto — descrição
sempre transmite a informação mínima.

Zero LLM, zero estado. Determinístico.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
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


# Janela máxima aceita para replay prevention de webhook (5 minutos).
WEBHOOK_MAX_AGE_SECONDS = 300

# Mapeamento default de categoria de status Jira → canônico GCA.
# Jira agrupa status por "statusCategory.key" ∈ {new, indeterminate, done}.
# Caller pode sobrescrever via config.status_mapping (status.name → canônico).
_DEFAULT_CATEGORY_MAP: dict[str, CanonicalStatus] = {
    "new": "todo",
    "indeterminate": "in_progress",
    "done": "done",
}

# Mapeamento canônico → prioridade Jira (Cloud: Highest/High/Medium/Low/Lowest).
_PRIORITY_OUT: dict[CanonicalPriority, str] = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

_PRIORITY_IN: dict[str, CanonicalPriority] = {
    "Highest": "critical",
    "High": "high",
    "Medium": "medium",
    "Low": "low",
    "Lowest": "low",
}


class JiraAdapter(IssueTrackerPort):
    """Adapter para Jira Cloud via REST API v3."""

    provider = "jira"

    #: HTTP client injetável (útil em testes que mockam transport).
    _client: Optional[httpx.AsyncClient]

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None, timeout: float = 15.0):
        self._client = client
        self._timeout = timeout

    # ─── HTTP helpers ─────────────────────────────────────────────────

    def _auth_header(self, config: ProviderConfig) -> dict[str, str]:
        email = config.credentials.get("email")
        token = config.credentials.get("api_token")
        if not email or not token:
            raise IssueTrackerConfigError(
                "Jira exige credentials={'email': ..., 'api_token': ...}"
            )
        raw = f"{email}:{token}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        config: ProviderConfig,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        base = config.base_url.rstrip("/")
        url = f"{base}{path}"
        headers = self._auth_header(config)

        async def _do(client: httpx.AsyncClient) -> httpx.Response:
            return await client.request(
                method, url, headers=headers,
                json=json_body, params=params, timeout=self._timeout,
            )

        try:
            if self._client is not None:
                resp = await _do(self._client)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await _do(c)
        except httpx.HTTPError as exc:
            logger.warning("jira.http_error", url=url, error=str(exc))
            raise IssueTrackerAPIError(f"falha HTTP chamando {url}: {exc}") from exc

        if resp.status_code == 401 or resp.status_code == 403:
            raise IssueTrackerAuthError(
                f"Jira rejeitou credencial ({resp.status_code}): "
                f"confira email + api_token no vault"
            )
        if resp.status_code == 404:
            raise IssueTrackerNotFound(f"Jira 404 em {path}")
        if resp.status_code == 429:
            raise IssueTrackerRateLimitError(
                f"Jira 429 em {path} — backoff necessário"
            )
        if resp.status_code >= 400:
            raise IssueTrackerAPIError(
                f"Jira {resp.status_code} em {path}: {resp.text[:200]}"
            )

        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise IssueTrackerAPIError(
                f"Jira retornou conteúdo não-JSON em {path}"
            ) from exc

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
        project_key = config.default_project_key
        if not project_key:
            raise IssueTrackerConfigError(
                "Jira exige default_project_key (ex: 'PROJ') no ProviderConfig"
            )

        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": title[:254],  # Jira limita a 255 chars
            "description": markdown_to_adf(description_markdown),
            "issuetype": {"name": config.extra.get("issuetype", "Task")},
        }
        if priority and priority in _PRIORITY_OUT:
            fields["priority"] = {"name": _PRIORITY_OUT[priority]}
        if labels:
            # Jira labels não aceitam espaços — substitui por hífen.
            fields["labels"] = [re.sub(r"\s+", "-", label) for label in labels]

        result = await self._request(
            config, "POST", "/rest/api/3/issue",
            json_body={"fields": fields},
        )
        external_id = result.get("key")
        if not external_id:
            raise IssueTrackerAPIError(
                f"Jira criou issue mas não retornou key: {result!r}"
            )

        # Busca o issue recém-criado pra popular status + url + campos derivados.
        return await self.get_issue(config, external_id)

    async def update_status(
        self,
        config: ProviderConfig,
        external_id: str,
        status: CanonicalStatus,
    ) -> IssuePayload:
        # Jira usa `transitions` (IDs numéricos) — precisamos resolver a
        # transição cujo destino bate com o status canônico solicitado.
        transitions = await self._request(
            config, "GET", f"/rest/api/3/issue/{external_id}/transitions",
        )
        target_transition_id = _resolve_transition_id(
            transitions.get("transitions", []), status, config,
        )
        if target_transition_id is None:
            raise IssueTrackerAPIError(
                f"Nenhuma transição Jira mapeia para status canônico '{status}' "
                f"em {external_id}. Configure status_mapping no projeto."
            )

        await self._request(
            config, "POST", f"/rest/api/3/issue/{external_id}/transitions",
            json_body={"transition": {"id": target_transition_id}},
        )
        return await self.get_issue(config, external_id)

    async def get_issue(
        self,
        config: ProviderConfig,
        external_id: str,
    ) -> IssuePayload:
        data = await self._request(
            config, "GET", f"/rest/api/3/issue/{external_id}",
            params={"fields": "summary,status,priority,labels,issuetype"},
        )
        fields = data.get("fields", {}) or {}
        status_obj = fields.get("status", {}) or {}
        status_raw = status_obj.get("name", "")
        canonical = _classify_status(status_obj, config)

        priority_obj = fields.get("priority") or {}
        priority_name = priority_obj.get("name")
        canonical_priority = _PRIORITY_IN.get(priority_name) if priority_name else None

        base = config.base_url.rstrip("/")
        url = f"{base}/browse/{external_id}"

        return IssuePayload(
            external_id=external_id,
            url=url,
            title=fields.get("summary", "") or "(sem título)",
            status_canonical=canonical,
            status_raw=status_raw,
            priority=canonical_priority,
            provider_specific={
                "issuetype": (fields.get("issuetype") or {}).get("name"),
                "labels": fields.get("labels") or [],
                "jira_id": data.get("id"),
            },
        )

    async def add_comment(
        self,
        config: ProviderConfig,
        external_id: str,
        comment_markdown: str,
    ) -> None:
        await self._request(
            config, "POST", f"/rest/api/3/issue/{external_id}/comment",
            json_body={"body": markdown_to_adf(comment_markdown)},
        )

    # ─── Webhook ──────────────────────────────────────────────────────

    def verify_webhook(
        self,
        config: ProviderConfig,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Valida HMAC-SHA256 + janela de replay prevention.

        Aceita header `X-Hub-Signature-256: sha256=<hex>` ou
        `X-Atlassian-Webhook-Signature: sha256=<hex>`. Timestamp opcional
        em `X-Atlassian-Webhook-Timestamp` (epoch ms); se presente,
        rejeita se fora da janela de 5 min.
        """
        secret = config.credentials.get("webhook_secret")
        if not secret:
            # Sem secret configurado, considera inválido — segurança fail-closed.
            logger.warning("jira.webhook.no_secret")
            return False

        signature_header = (
            headers.get("X-Hub-Signature-256")
            or headers.get("x-hub-signature-256")
            or headers.get("X-Atlassian-Webhook-Signature")
            or headers.get("x-atlassian-webhook-signature")
            or ""
        )
        if not signature_header.startswith("sha256="):
            return False
        expected_hex = signature_header[len("sha256="):].strip()

        mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
        if not hmac.compare_digest(mac.hexdigest(), expected_hex):
            return False

        # Replay prevention (opcional).
        ts_header = (
            headers.get("X-Atlassian-Webhook-Timestamp")
            or headers.get("x-atlassian-webhook-timestamp")
        )
        if ts_header:
            try:
                ts_ms = int(ts_header)
            except ValueError:
                return False
            delta = abs(time.time() - (ts_ms / 1000.0))
            if delta > WEBHOOK_MAX_AGE_SECONDS:
                logger.warning("jira.webhook.expired", delta_seconds=delta)
                return False

        return True

    def parse_webhook(
        self,
        config: ProviderConfig,
        payload: dict[str, Any],
    ) -> Optional[IssueEvent]:
        """Converte payload de webhook do Jira em IssueEvent canônico.

        Eventos relevantes:
          - jira:issue_created  → issue_created
          - jira:issue_updated  → status_changed se o campo 'status' aparece
                                   em `changelog.items`; caso contrário issue_updated
          - jira:issue_deleted  → issue_deleted
        """
        event_type_raw = payload.get("webhookEvent")
        issue = payload.get("issue") or {}
        external_id = issue.get("key")
        if not external_id or not event_type_raw:
            return None

        project_id = _resolve_project_id_from_webhook(config)
        if not project_id:
            logger.warning("jira.webhook.no_project_binding",
                            external_id=external_id)
            return None

        fields = issue.get("fields", {}) or {}
        status_obj = fields.get("status", {}) or {}
        status_raw = status_obj.get("name")
        canonical = _classify_status(status_obj, config) if status_obj else None
        title = fields.get("summary")

        if event_type_raw == "jira:issue_created":
            return IssueEvent(
                event_type="issue_created",
                external_id=external_id,
                project_id=project_id,
                status_canonical=canonical,
                status_raw=status_raw,
                title=title,
                raw_payload=payload,
            )
        if event_type_raw == "jira:issue_deleted":
            return IssueEvent(
                event_type="issue_deleted",
                external_id=external_id,
                project_id=project_id,
                raw_payload=payload,
            )
        if event_type_raw == "jira:issue_updated":
            changelog = payload.get("changelog", {}) or {}
            items = changelog.get("items", []) or []
            status_changed = any(
                item.get("field") == "status" for item in items
            )
            return IssueEvent(
                event_type="status_changed" if status_changed else "issue_updated",
                external_id=external_id,
                project_id=project_id,
                status_canonical=canonical,
                status_raw=status_raw,
                title=title,
                raw_payload=payload,
            )
        return None


# ─── Helpers internos ─────────────────────────────────────────────────


def _classify_status(
    status_obj: dict,
    config: ProviderConfig,
) -> CanonicalStatus:
    """Resolve status canônico a partir do status Jira.

    Ordem de resolução:
      1. Nome do status em `config.status_mapping` (override do GP).
      2. `statusCategory.key` do Jira (new/indeterminate/done) → default map.
      3. Fallback: 'todo'.
    """
    status_name = (status_obj.get("name") or "").strip()
    mapped = config.status_mapping.get(status_name)
    if mapped:
        return mapped

    category = (status_obj.get("statusCategory") or {}).get("key", "")
    return _DEFAULT_CATEGORY_MAP.get(category, "todo")


def _resolve_transition_id(
    transitions: list[dict],
    target: CanonicalStatus,
    config: ProviderConfig,
) -> Optional[str]:
    """Escolhe a transição cujo `to.name` ou `to.statusCategory.key` bate
    com o status canônico solicitado.
    """
    # Status custom primeiro (mapping inverso).
    preferred_names = [
        name for name, canonical in config.status_mapping.items()
        if canonical == target
    ]
    for t in transitions:
        to = t.get("to", {}) or {}
        if to.get("name") in preferred_names:
            return t.get("id")

    # Default category map.
    target_category = {v: k for k, v in _DEFAULT_CATEGORY_MAP.items()}.get(target)
    if target_category:
        for t in transitions:
            to = t.get("to", {}) or {}
            if (to.get("statusCategory") or {}).get("key") == target_category:
                return t.get("id")
    return None


def _resolve_project_id_from_webhook(config: ProviderConfig) -> Optional[str]:
    """Em V1 o project_id do GCA é guardado em `config.extra['gca_project_id']`
    quando o webhook é registrado. Caller é responsável por popular.
    """
    pid = config.extra.get("gca_project_id")
    return str(pid) if pid else None


# ─── Markdown → ADF (Atlassian Document Format) ──────────────────────
# Conversor mínimo: cobre parágrafo, bold, italic, code inline, code block,
# link, unordered list. Markdown mais rico degrada para texto plano dentro
# do parágrafo — ninguém perde informação.

_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_ITALIC = re.compile(r"(?<!\*)\*([^*\s][^*]*?)\*(?!\*)")
_RE_CODE_INLINE = re.compile(r"`([^`]+)`")
_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def markdown_to_adf(markdown: str) -> dict:
    """Converte markdown simples em ADF mínimo.

    Retorna um doc ADF com versão 1. Casos cobertos:
      - linhas começando por ``` → code block
      - linhas começando por '- ' ou '* ' → bullet list
      - outras linhas → parágrafo com inline marks (bold/italic/code/link)

    Linhas em branco viram quebra de parágrafo.
    """
    if not markdown:
        return {"version": 1, "type": "doc", "content": []}

    content: list[dict] = []
    lines = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            content.append({
                "type": "codeBlock",
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            })
            i += 1
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            items: list[dict] = []
            while i < len(lines):
                s = lines[i].strip()
                if not (s.startswith("- ") or s.startswith("* ")):
                    break
                items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": _inline_text_to_adf(s[2:]),
                    }],
                })
                i += 1
            content.append({"type": "bulletList", "content": items})
            continue

        if stripped == "":
            i += 1
            continue

        content.append({
            "type": "paragraph",
            "content": _inline_text_to_adf(line),
        })
        i += 1

    return {"version": 1, "type": "doc", "content": content}


def _inline_text_to_adf(text: str) -> list[dict]:
    """Aplica marks inline (bold, italic, code, link) sobre um trecho.

    Implementação ingênua em passes sequenciais — extrai match, emite
    fragmentos antes/depois. Casos interpretação ambígua caem em texto plano.
    """
    if not text:
        return [{"type": "text", "text": " "}]

    # Ordem: code (mais forte) → link → bold → italic.
    fragments: list[dict] = [{"type": "text", "text": text}]

    def apply_pattern(pattern: re.Pattern, mark: dict, wrap: Optional[str] = None):
        out: list[dict] = []
        for frag in fragments:
            if frag["type"] != "text" or "marks" in frag:
                out.append(frag)
                continue
            s = frag["text"]
            idx = 0
            while True:
                m = pattern.search(s, idx)
                if not m:
                    break
                if m.start() > idx:
                    out.append({"type": "text", "text": s[idx:m.start()]})
                content = m.group(1)
                if wrap == "link":
                    out.append({
                        "type": "text",
                        "text": content,
                        "marks": [{"type": "link", "attrs": {"href": m.group(2)}}],
                    })
                else:
                    out.append({
                        "type": "text", "text": content, "marks": [mark],
                    })
                idx = m.end()
            if idx < len(s):
                out.append({"type": "text", "text": s[idx:]})
        return out

    fragments = apply_pattern(_RE_CODE_INLINE, {"type": "code"})
    fragments = apply_pattern(_RE_LINK, {}, wrap="link")
    fragments = apply_pattern(_RE_BOLD, {"type": "strong"})
    fragments = apply_pattern(_RE_ITALIC, {"type": "em"})

    # ADF não aceita fragmento vazio; remove.
    return [f for f in fragments if f.get("text")]
