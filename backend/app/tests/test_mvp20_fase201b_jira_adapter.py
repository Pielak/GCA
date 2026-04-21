"""MVP 20 Fase 20.1b — testes do JiraAdapter.

Sem chamar Jira real — usamos httpx.MockTransport pra interceptar
requests e devolver payloads canônicos da REST API v3.

Valida:
- Auth Basic correto a partir de credentials.
- create_issue POST /rest/api/3/issue + follow-up GET pra popular payload.
- update_status resolve transição canônica certa.
- get_issue normaliza status Jira → canônico (via statusCategory + mapping custom).
- add_comment POST no endpoint certo com ADF body.
- verify_webhook: HMAC válido/inválido, sem secret, timestamp antigo.
- parse_webhook: issue_created, issue_updated (status_changed), issue_deleted.
- markdown_to_adf: parágrafo, bold, italic, code, link, code block, bullet list.
- Erros: 401 → IssueTrackerAuthError; 404 → NotFound; 429 → RateLimit.
"""
import hashlib
import hmac
import json
import time

import httpx
import pytest

from app.services.adapters.jira_adapter import (
    JiraAdapter,
    _classify_status,
    _resolve_transition_id,
    markdown_to_adf,
)
from app.services.ports.issue_tracker_port import (
    IssueTrackerAPIError,
    IssueTrackerAuthError,
    IssueTrackerConfigError,
    IssueTrackerNotFound,
    IssueTrackerRateLimitError,
    ProviderConfig,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _config(
    *,
    status_mapping=None,
    extra=None,
    webhook_secret=None,
) -> ProviderConfig:
    return ProviderConfig(
        credentials={
            "email": "gca@example.com",
            "api_token": "test-token",
            **({"webhook_secret": webhook_secret} if webhook_secret else {}),
        },
        base_url="https://example.atlassian.net",
        default_project_key="PROJ",
        status_mapping=status_mapping or {},
        extra=extra or {"gca_project_id": "proj-uuid-123"},
    )


def _transport(handler):
    """Wrapper que cria um MockTransport com o handler dado."""
    return httpx.MockTransport(handler)


def _adapter_with(handler) -> JiraAdapter:
    client = httpx.AsyncClient(transport=_transport(handler))
    return JiraAdapter(client=client)


# ===========================================================================
# Auth
# ===========================================================================


@pytest.mark.asyncio
async def test_create_issue_envia_basic_auth_correto():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        if request.url.path == "/rest/api/3/issue" and request.method == "POST":
            return httpx.Response(201, json={"key": "PROJ-1"})
        # follow-up get_issue
        return httpx.Response(200, json={
            "id": "10001",
            "key": "PROJ-1",
            "fields": {
                "summary": "RF-001 Login",
                "status": {
                    "name": "To Do",
                    "statusCategory": {"key": "new"},
                },
                "priority": None,
                "labels": [],
                "issuetype": {"name": "Task"},
            },
        })

    adapter = _adapter_with(handler)
    config = _config()
    payload = await adapter.create_issue(
        config, title="RF-001 Login",
        description_markdown="Login via **email** e senha.",
    )
    assert payload.external_id == "PROJ-1"
    assert payload.status_canonical == "todo"
    # Basic auth header presente.
    assert captured["auth"] is not None
    assert captured["auth"].startswith("Basic ")


@pytest.mark.asyncio
async def test_create_issue_sem_credentials_levanta_config_error():
    adapter = _adapter_with(lambda r: httpx.Response(200, json={}))
    config = ProviderConfig(
        credentials={},  # vazio
        base_url="https://x.atlassian.net",
        default_project_key="P",
    )
    with pytest.raises(IssueTrackerConfigError):
        await adapter.create_issue(
            config, title="t", description_markdown="d",
        )


@pytest.mark.asyncio
async def test_create_issue_sem_default_project_key_levanta_config_error():
    adapter = _adapter_with(lambda r: httpx.Response(200, json={}))
    config = ProviderConfig(
        credentials={"email": "a@b", "api_token": "t"},
        base_url="https://x.atlassian.net",
        default_project_key="",
    )
    with pytest.raises(IssueTrackerConfigError):
        await adapter.create_issue(
            config, title="t", description_markdown="d",
        )


# ===========================================================================
# create_issue
# ===========================================================================


@pytest.mark.asyncio
async def test_create_issue_trunca_summary_longo():
    captured = {}

    def handler(request):
        if request.method == "POST":
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"key": "PROJ-2"})
        return httpx.Response(200, json={
            "id": "2", "key": "PROJ-2",
            "fields": {"summary": captured["body"]["fields"]["summary"],
                       "status": {"name": "To Do",
                                  "statusCategory": {"key": "new"}}},
        })

    adapter = _adapter_with(handler)
    long_title = "X" * 500
    payload = await adapter.create_issue(
        _config(), title=long_title, description_markdown="d",
    )
    assert len(captured["body"]["fields"]["summary"]) <= 255


@pytest.mark.asyncio
async def test_create_issue_converte_labels_com_espaco():
    captured = {}

    def handler(request):
        if request.method == "POST":
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"key": "PROJ-L"})
        return httpx.Response(200, json={
            "id": "1", "key": "PROJ-L",
            "fields": {"summary": "x", "labels": captured["body"]["fields"].get("labels"),
                       "status": {"name": "To Do",
                                  "statusCategory": {"key": "new"}}},
        })

    adapter = _adapter_with(handler)
    await adapter.create_issue(
        _config(), title="t", description_markdown="d",
        labels=["regra de negócio", "high priority"],
    )
    labels = captured["body"]["fields"]["labels"]
    # Jira labels não aceitam espaço.
    assert all(" " not in label for label in labels)


@pytest.mark.asyncio
async def test_create_issue_usa_priority_canonica_traduzida():
    captured = {}

    def handler(request):
        if request.method == "POST":
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"key": "PROJ-P"})
        return httpx.Response(200, json={
            "id": "1", "key": "PROJ-P",
            "fields": {"summary": "x",
                       "priority": {"name": "High"},
                       "status": {"name": "To Do",
                                  "statusCategory": {"key": "new"}}},
        })

    adapter = _adapter_with(handler)
    payload = await adapter.create_issue(
        _config(), title="t", description_markdown="d", priority="high",
    )
    assert captured["body"]["fields"]["priority"]["name"] == "High"
    assert payload.priority == "high"


# ===========================================================================
# update_status
# ===========================================================================


@pytest.mark.asyncio
async def test_update_status_resolve_transicao_por_statusCategory():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/transitions") and request.method == "GET":
            return httpx.Response(200, json={
                "transitions": [
                    {"id": "11", "to": {"name": "To Do",
                                        "statusCategory": {"key": "new"}}},
                    {"id": "21", "to": {"name": "In Progress",
                                        "statusCategory": {"key": "indeterminate"}}},
                    {"id": "31", "to": {"name": "Done",
                                        "statusCategory": {"key": "done"}}},
                ],
            })
        if request.url.path.endswith("/transitions") and request.method == "POST":
            body = json.loads(request.content.decode())
            assert body["transition"]["id"] == "31"
            return httpx.Response(204)
        # follow-up get_issue
        return httpx.Response(200, json={
            "id": "1", "key": "PROJ-5",
            "fields": {"summary": "x",
                       "status": {"name": "Done",
                                  "statusCategory": {"key": "done"}}},
        })

    adapter = _adapter_with(handler)
    payload = await adapter.update_status(_config(), "PROJ-5", "done")
    assert payload.status_canonical == "done"


@pytest.mark.asyncio
async def test_update_status_sem_transicao_disponivel_levanta_api_error():
    def handler(request):
        if request.url.path.endswith("/transitions") and request.method == "GET":
            # Sem transição canônica mapeável.
            return httpx.Response(200, json={
                "transitions": [
                    {"id": "99", "to": {"name": "Custom",
                                        "statusCategory": {"key": "unknown"}}},
                ],
            })
        return httpx.Response(200, json={})

    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerAPIError) as exc:
        await adapter.update_status(_config(), "PROJ-7", "in_progress")
    assert "transição" in str(exc.value).lower() or "transicao" in str(exc.value).lower()


# ===========================================================================
# get_issue + _classify_status
# ===========================================================================


@pytest.mark.asyncio
async def test_get_issue_mapeia_status_via_statusCategory_default():
    def handler(request):
        return httpx.Response(200, json={
            "id": "1", "key": "PROJ-X",
            "fields": {
                "summary": "X",
                "status": {"name": "Em Review",
                           "statusCategory": {"key": "indeterminate"}},
                "priority": {"name": "Medium"},
                "labels": ["foo"],
                "issuetype": {"name": "Story"},
            },
        })

    adapter = _adapter_with(handler)
    payload = await adapter.get_issue(_config(), "PROJ-X")
    assert payload.status_canonical == "in_progress"  # indeterminate default
    assert payload.status_raw == "Em Review"
    assert payload.priority == "medium"
    assert payload.provider_specific["issuetype"] == "Story"
    assert payload.url == "https://example.atlassian.net/browse/PROJ-X"


def test_classify_status_respeita_mapping_customizado_do_projeto():
    status_obj = {"name": "Em análise pelo jurídico",
                  "statusCategory": {"key": "indeterminate"}}
    config = _config(status_mapping={"Em análise pelo jurídico": "review"})
    assert _classify_status(status_obj, config) == "review"


def test_classify_status_fallback_para_todo_quando_desconhecido():
    status_obj = {"name": "Algo Estranho",
                  "statusCategory": {"key": "unknown"}}
    assert _classify_status(status_obj, _config()) == "todo"


def test_resolve_transition_id_usa_mapping_custom():
    transitions = [
        {"id": "71", "to": {"name": "Em análise pelo jurídico",
                            "statusCategory": {"key": "indeterminate"}}},
        {"id": "72", "to": {"name": "Em Progresso",
                            "statusCategory": {"key": "indeterminate"}}},
    ]
    config = _config(status_mapping={"Em análise pelo jurídico": "review"})
    assert _resolve_transition_id(transitions, "review", config) == "71"


# ===========================================================================
# add_comment
# ===========================================================================


@pytest.mark.asyncio
async def test_add_comment_envia_adf_para_endpoint_correto():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(201, json={"id": "c1"})

    adapter = _adapter_with(handler)
    await adapter.add_comment(_config(), "PROJ-1", "Fix referenced in commit **abc123**.")
    assert captured["path"] == "/rest/api/3/issue/PROJ-1/comment"
    assert captured["body"]["body"]["type"] == "doc"  # ADF doc
    assert captured["body"]["body"]["version"] == 1


# ===========================================================================
# verify_webhook
# ===========================================================================


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_verify_webhook_hmac_valido_retorna_true():
    adapter = JiraAdapter()
    config = _config(webhook_secret="s3cret")
    body = b'{"event": "x"}'
    headers = {"X-Hub-Signature-256": _sign("s3cret", body)}
    assert adapter.verify_webhook(config, headers, body) is True


def test_verify_webhook_hmac_invalido_retorna_false():
    adapter = JiraAdapter()
    config = _config(webhook_secret="s3cret")
    body = b'{"event": "x"}'
    headers = {"X-Hub-Signature-256": "sha256=" + "0" * 64}
    assert adapter.verify_webhook(config, headers, body) is False


def test_verify_webhook_sem_secret_configurado_retorna_false():
    """Fail-closed quando admin não configurou secret."""
    adapter = JiraAdapter()
    config = _config()  # sem webhook_secret
    assert adapter.verify_webhook(config, {"X-Hub-Signature-256": "sha256=xx"}, b"{}") is False


def test_verify_webhook_timestamp_antigo_retorna_false():
    adapter = JiraAdapter()
    config = _config(webhook_secret="s")
    body = b'{}'
    old_ts_ms = int((time.time() - 3600) * 1000)  # 1 hora atrás
    headers = {
        "X-Hub-Signature-256": _sign("s", body),
        "X-Atlassian-Webhook-Timestamp": str(old_ts_ms),
    }
    assert adapter.verify_webhook(config, headers, body) is False


def test_verify_webhook_timestamp_recente_aceito():
    adapter = JiraAdapter()
    config = _config(webhook_secret="s")
    body = b'{}'
    recent_ts_ms = int(time.time() * 1000)
    headers = {
        "X-Hub-Signature-256": _sign("s", body),
        "X-Atlassian-Webhook-Timestamp": str(recent_ts_ms),
    }
    assert adapter.verify_webhook(config, headers, body) is True


def test_verify_webhook_header_atlassian_tambem_aceito():
    adapter = JiraAdapter()
    config = _config(webhook_secret="s")
    body = b'{}'
    headers = {"X-Atlassian-Webhook-Signature": _sign("s", body)}
    assert adapter.verify_webhook(config, headers, body) is True


# ===========================================================================
# parse_webhook
# ===========================================================================


def test_parse_webhook_issue_created():
    adapter = JiraAdapter()
    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "PROJ-9",
            "fields": {
                "summary": "Novo módulo",
                "status": {"name": "To Do",
                           "statusCategory": {"key": "new"}},
            },
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev is not None
    assert ev.event_type == "issue_created"
    assert ev.external_id == "PROJ-9"
    assert ev.status_canonical == "todo"
    assert ev.project_id == "proj-uuid-123"


def test_parse_webhook_issue_updated_com_status_changed():
    adapter = JiraAdapter()
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "PROJ-10",
            "fields": {
                "summary": "x",
                "status": {"name": "Done",
                           "statusCategory": {"key": "done"}},
            },
        },
        "changelog": {
            "items": [{"field": "status", "fromString": "To Do", "toString": "Done"}],
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "status_changed"
    assert ev.status_canonical == "done"


def test_parse_webhook_issue_updated_sem_status_vira_updated():
    adapter = JiraAdapter()
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "PROJ-11",
            "fields": {"summary": "novo título",
                       "status": {"name": "To Do",
                                  "statusCategory": {"key": "new"}}},
        },
        "changelog": {"items": [{"field": "summary"}]},
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "issue_updated"


def test_parse_webhook_issue_deleted():
    adapter = JiraAdapter()
    payload = {
        "webhookEvent": "jira:issue_deleted",
        "issue": {"key": "PROJ-12", "fields": {}},
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "issue_deleted"


def test_parse_webhook_evento_irrelevante_retorna_none():
    adapter = JiraAdapter()
    payload = {"webhookEvent": "jira:user_created"}
    assert adapter.parse_webhook(_config(), payload) is None


def test_parse_webhook_sem_project_binding_retorna_none():
    adapter = JiraAdapter()
    config = ProviderConfig(
        credentials={"email": "a@b", "api_token": "t"},
        base_url="https://x.atlassian.net",
        default_project_key="P",
        extra={},  # sem gca_project_id
    )
    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {"key": "PROJ-X", "fields": {}},
    }
    assert adapter.parse_webhook(config, payload) is None


# ===========================================================================
# Erros HTTP
# ===========================================================================


@pytest.mark.asyncio
async def test_401_levanta_auth_error():
    def handler(r):
        return httpx.Response(401, json={"message": "Unauthorized"})
    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerAuthError):
        await adapter.get_issue(_config(), "PROJ-1")


@pytest.mark.asyncio
async def test_404_levanta_not_found():
    def handler(r):
        return httpx.Response(404, json={})
    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerNotFound):
        await adapter.get_issue(_config(), "PROJ-X")


@pytest.mark.asyncio
async def test_429_levanta_rate_limit():
    def handler(r):
        return httpx.Response(429, json={})
    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerRateLimitError):
        await adapter.get_issue(_config(), "PROJ-Y")


@pytest.mark.asyncio
async def test_500_levanta_api_error():
    def handler(r):
        return httpx.Response(500, text="boom")
    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerAPIError):
        await adapter.get_issue(_config(), "PROJ-Z")


# ===========================================================================
# markdown_to_adf
# ===========================================================================


def test_adf_paragrafo_simples():
    doc = markdown_to_adf("texto simples")
    assert doc["version"] == 1
    assert doc["type"] == "doc"
    assert len(doc["content"]) == 1
    assert doc["content"][0]["type"] == "paragraph"


def test_adf_bold():
    doc = markdown_to_adf("isto é **negrito** aqui")
    para = doc["content"][0]
    bold_frags = [f for f in para["content"]
                  if any(m.get("type") == "strong" for m in f.get("marks", []))]
    assert len(bold_frags) == 1
    assert bold_frags[0]["text"] == "negrito"


def test_adf_italic():
    doc = markdown_to_adf("isto é *itálico* aqui")
    para = doc["content"][0]
    it_frags = [f for f in para["content"]
                if any(m.get("type") == "em" for m in f.get("marks", []))]
    assert len(it_frags) == 1


def test_adf_code_inline():
    doc = markdown_to_adf("chame `init()` primeiro")
    para = doc["content"][0]
    code_frags = [f for f in para["content"]
                  if any(m.get("type") == "code" for m in f.get("marks", []))]
    assert len(code_frags) == 1
    assert code_frags[0]["text"] == "init()"


def test_adf_link():
    doc = markdown_to_adf("veja [docs](https://example.com)")
    para = doc["content"][0]
    link_frags = [f for f in para["content"]
                  if any(m.get("type") == "link" for m in f.get("marks", []))]
    assert len(link_frags) == 1
    assert link_frags[0]["marks"][0]["attrs"]["href"] == "https://example.com"


def test_adf_code_block():
    md = "```\ndef foo():\n    pass\n```"
    doc = markdown_to_adf(md)
    assert doc["content"][0]["type"] == "codeBlock"
    assert "def foo" in doc["content"][0]["content"][0]["text"]


def test_adf_bullet_list():
    md = "- um\n- dois\n- três"
    doc = markdown_to_adf(md)
    assert doc["content"][0]["type"] == "bulletList"
    assert len(doc["content"][0]["content"]) == 3


def test_adf_vazio_retorna_doc_vazio():
    doc = markdown_to_adf("")
    assert doc == {"version": 1, "type": "doc", "content": []}
