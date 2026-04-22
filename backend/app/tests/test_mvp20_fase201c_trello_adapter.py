"""MVP 20 Fase 20.1c — testes do TrelloAdapter.

Sem chamar Trello real — httpx.MockTransport intercepta.

Valida:
- Auth via query params (key + token).
- _resolve_list_id: direto de config.extra['list_ids']; fallback busca
  no board; fallback default names (Backlog/Doing/Done).
- _classify_list_name: mapping custom; default name; fallback todo.
- create_card POST /cards com idList + name + desc; label por priority.
- update_status PUT /cards/:id com novo idList.
- get_issue enriquece com lista atual (extra chamada) + labels.
- add_comment endpoint correto.
- verify_webhook: HMAC-SHA1(body + callbackURL) base64; falha sem secret,
  sem callback_url, sem header, inválido.
- parse_webhook: createCard, updateCard com listBefore=status_changed,
  updateCard arquivado, deleteCard, commentCard.
- Erros HTTP 401/404/429/500.
"""
import base64
import hashlib
import hmac
import json

import httpx
import pytest

from app.services.adapters.trello_adapter import TrelloAdapter
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
    list_ids=None,
    webhook_secret=None,
    callback_url=None,
    gca_project_id="proj-uuid-001",
) -> ProviderConfig:
    extra = {"gca_project_id": gca_project_id}
    if list_ids:
        extra["list_ids"] = list_ids
    if callback_url:
        extra["callback_url"] = callback_url
    return ProviderConfig(
        credentials={
            "api_key": "key123",
            "api_token": "tok456",
            **({"webhook_secret": webhook_secret} if webhook_secret else {}),
        },
        base_url="https://api.trello.com",
        default_project_key="board-abc",
        status_mapping=status_mapping or {},
        extra=extra,
    )


def _adapter_with(handler) -> TrelloAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TrelloAdapter(client=client)


# ===========================================================================
# Auth / config
# ===========================================================================


@pytest.mark.asyncio
async def test_auth_params_incluem_key_e_token():
    captured = {}

    def handler(request):
        captured["params"] = dict(request.url.params)
        # Mock mínimo pra fluxo completar.
        if request.url.path == "/1/boards/board-abc/lists":
            return httpx.Response(200, json=[
                {"id": "list-todo", "name": "Backlog"},
            ])
        if request.url.path == "/1/cards":
            return httpx.Response(201, json={"id": "card-1"})
        if request.url.path == "/1/cards/card-1":
            return httpx.Response(200, json={
                "id": "card-1", "name": "T", "idList": "list-todo",
                "shortUrl": "https://trello.com/c/x", "labels": [],
                "closed": False,
            })
        if request.url.path == "/1/lists/list-todo":
            return httpx.Response(200, json={"id": "list-todo", "name": "Backlog"})
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    await adapter.create_issue(
        _config(), title="T", description_markdown="d",
    )
    assert captured["params"].get("key") == "key123"
    assert captured["params"].get("token") == "tok456"


@pytest.mark.asyncio
async def test_sem_credentials_levanta_config_error():
    adapter = _adapter_with(lambda r: httpx.Response(200, json={}))
    config = ProviderConfig(
        credentials={},
        base_url="https://api.trello.com",
        default_project_key="b",
    )
    with pytest.raises(IssueTrackerConfigError):
        await adapter.get_issue(config, "card-x")


# ===========================================================================
# _resolve_list_id
# ===========================================================================


@pytest.mark.asyncio
async def test_resolve_list_id_via_config_extra_sem_chamar_api():
    """list_ids explícito no config → não chama /boards."""
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    adapter = _adapter_with(handler)
    config = _config(list_ids={"todo": "cached-list-id"})
    resolved = await adapter._resolve_list_id(config, "todo")
    assert resolved == "cached-list-id"
    assert "/boards" not in " ".join(calls)


@pytest.mark.asyncio
async def test_resolve_list_id_via_default_name():
    def handler(request):
        if "/boards/" in request.url.path and request.url.path.endswith("/lists"):
            return httpx.Response(200, json=[
                {"id": "l1", "name": "Backlog"},
                {"id": "l2", "name": "Doing"},
                {"id": "l3", "name": "Done"},
            ])
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    config = _config()
    assert await adapter._resolve_list_id(config, "todo") == "l1"
    assert await adapter._resolve_list_id(config, "in_progress") == "l2"
    assert await adapter._resolve_list_id(config, "done") == "l3"


@pytest.mark.asyncio
async def test_resolve_list_id_via_status_mapping_custom():
    def handler(request):
        return httpx.Response(200, json=[
            {"id": "l-analise", "name": "Em análise pelo jurídico"},
        ])

    adapter = _adapter_with(handler)
    config = _config(status_mapping={"Em análise pelo jurídico": "review"})
    resolved = await adapter._resolve_list_id(config, "review")
    assert resolved == "l-analise"


@pytest.mark.asyncio
async def test_resolve_list_id_retorna_none_quando_nao_ha_match():
    def handler(request):
        return httpx.Response(200, json=[{"id": "x", "name": "Qualquer"}])

    adapter = _adapter_with(handler)
    result = await adapter._resolve_list_id(_config(), "review")
    assert result is None


# ===========================================================================
# _classify_list_name
# ===========================================================================


def test_classify_list_name_via_default():
    adapter = TrelloAdapter()
    assert adapter._classify_list_name("Backlog", _config()) == "todo"
    assert adapter._classify_list_name("Doing", _config()) == "in_progress"
    assert adapter._classify_list_name("Done", _config()) == "done"


def test_classify_list_name_via_mapping_custom():
    adapter = TrelloAdapter()
    config = _config(status_mapping={"A Revisar": "review"})
    assert adapter._classify_list_name("A Revisar", config) == "review"


def test_classify_list_name_case_insensitive_no_default():
    adapter = TrelloAdapter()
    # "backlog" minúsculo bate com default "Backlog".
    assert adapter._classify_list_name("backlog", _config()) == "todo"


def test_classify_list_name_fallback_todo():
    adapter = TrelloAdapter()
    assert adapter._classify_list_name("Algo Custom", _config()) == "todo"


# ===========================================================================
# create_issue
# ===========================================================================


@pytest.mark.asyncio
async def test_create_issue_fluxo_completo():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/1/cards" and request.method == "POST":
            return httpx.Response(201, json={"id": "card-X"})
        if request.url.path == "/1/cards/card-X" and request.method == "GET":
            return httpx.Response(200, json={
                "id": "card-X", "name": "Login", "idList": "list-todo",
                "shortUrl": "https://trello.com/c/xyz", "labels": [],
                "closed": False,
            })
        if request.url.path == "/1/lists/list-todo":
            return httpx.Response(200, json={"name": "Backlog"})
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    config = _config(list_ids={"todo": "list-todo"})
    payload = await adapter.create_issue(
        config, title="Login", description_markdown="detalhes",
    )
    assert payload.external_id == "card-X"
    assert payload.status_canonical == "todo"
    assert payload.url == "https://trello.com/c/xyz"


@pytest.mark.asyncio
async def test_create_issue_com_priority_adiciona_label():
    methods_called = []

    def handler(request):
        methods_called.append((request.method, request.url.path))
        if request.url.path == "/1/cards" and request.method == "POST":
            return httpx.Response(201, json={"id": "card-P"})
        if request.url.path.endswith("/labels"):
            return httpx.Response(201, json={"id": "label-1"})
        if request.url.path == "/1/cards/card-P":
            return httpx.Response(200, json={
                "id": "card-P", "name": "x", "idList": "l-todo",
                "labels": [{"color": "red", "name": "priority-critical"}],
                "closed": False, "shortUrl": "u",
            })
        if request.url.path == "/1/lists/l-todo":
            return httpx.Response(200, json={"name": "Backlog"})
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    payload = await adapter.create_issue(
        _config(list_ids={"todo": "l-todo"}),
        title="t", description_markdown="d", priority="critical",
    )
    assert any(m for m, p in methods_called if p.endswith("/labels"))
    assert payload.priority == "critical"


@pytest.mark.asyncio
async def test_create_issue_sem_lista_mapeada_levanta_config_error():
    def handler(request):
        if request.url.path.endswith("/lists"):
            return httpx.Response(200, json=[])  # board sem listas
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerConfigError):
        await adapter.create_issue(
            _config(), title="t", description_markdown="d",
        )


# ===========================================================================
# update_status
# ===========================================================================


@pytest.mark.asyncio
async def test_update_status_move_card_para_lista_correta():
    captured = {}

    def handler(request):
        if request.url.path.endswith("/lists") and request.method == "GET":
            return httpx.Response(200, json=[
                {"id": "l-todo", "name": "Backlog"},
                {"id": "l-done", "name": "Done"},
            ])
        if request.url.path == "/1/cards/card-5" and request.method == "PUT":
            # Trello recebe via form-data (parsed como bytes no mock);
            # verificamos que idList alvo está no corpo.
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"id": "card-5"})
        if request.url.path == "/1/cards/card-5" and request.method == "GET":
            return httpx.Response(200, json={
                "id": "card-5", "name": "x", "idList": "l-done",
                "labels": [], "closed": False, "shortUrl": "u",
            })
        if request.url.path == "/1/lists/l-done":
            return httpx.Response(200, json={"name": "Done"})
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    payload = await adapter.update_status(_config(), "card-5", "done")
    assert "idList=l-done" in captured["body"]
    assert payload.status_canonical == "done"


@pytest.mark.asyncio
async def test_update_status_sem_lista_levanta_api_error():
    def handler(request):
        if request.url.path.endswith("/lists"):
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    with pytest.raises(IssueTrackerAPIError):
        await adapter.update_status(_config(), "card-X", "review")


# ===========================================================================
# get_issue
# ===========================================================================


@pytest.mark.asyncio
async def test_get_issue_arquivado_vira_cancelled():
    def handler(request):
        if request.url.path == "/1/cards/card-A":
            return httpx.Response(200, json={
                "id": "card-A", "name": "archived-one",
                "idList": "l-done", "closed": True,
                "labels": [], "shortUrl": "u",
            })
        if request.url.path == "/1/lists/l-done":
            return httpx.Response(200, json={"name": "Done"})
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    payload = await adapter.get_issue(_config(), "card-A")
    assert payload.status_canonical == "cancelled"


@pytest.mark.asyncio
async def test_get_issue_com_label_priority_mapeada():
    def handler(request):
        if request.url.path == "/1/cards/card-L":
            return httpx.Response(200, json={
                "id": "card-L", "name": "x", "idList": "l1",
                "labels": [{"id": "lab1", "color": "orange", "name": "priority-high"}],
                "closed": False, "shortUrl": "u",
            })
        if request.url.path == "/1/lists/l1":
            return httpx.Response(200, json={"name": "Doing"})
        return httpx.Response(404, json={})

    adapter = _adapter_with(handler)
    payload = await adapter.get_issue(_config(), "card-L")
    assert payload.priority == "high"
    assert payload.status_canonical == "in_progress"


# ===========================================================================
# add_comment
# ===========================================================================


@pytest.mark.asyncio
async def test_add_comment_envia_texto_markdown_no_endpoint_correto():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(201, json={"id": "c1"})

    adapter = _adapter_with(handler)
    await adapter.add_comment(_config(), "card-Z", "tudo **ok**")
    assert captured["path"] == "/1/cards/card-Z/actions/comments"
    assert "text=tudo" in captured["body"]


# ===========================================================================
# verify_webhook
# ===========================================================================


def _sign_trello(secret: str, body: bytes, callback_url: str) -> str:
    mac = hmac.new(secret.encode(), digestmod=hashlib.sha1)
    mac.update(body)
    mac.update(callback_url.encode())
    return base64.b64encode(mac.digest()).decode("ascii")


def test_verify_webhook_valido():
    adapter = TrelloAdapter()
    config = _config(webhook_secret="s3cret", callback_url="https://gca/wh/trello")
    body = b'{"action": {"type": "createCard"}}'
    headers = {"X-Trello-Webhook": _sign_trello("s3cret", body, "https://gca/wh/trello")}
    assert adapter.verify_webhook(config, headers, body) is True


def test_verify_webhook_assinatura_invalida():
    adapter = TrelloAdapter()
    config = _config(webhook_secret="s", callback_url="https://gca/wh")
    headers = {"X-Trello-Webhook": "invalid=="}
    assert adapter.verify_webhook(config, headers, b'{}') is False


def test_verify_webhook_sem_secret():
    adapter = TrelloAdapter()
    config = _config(callback_url="https://x")
    assert adapter.verify_webhook(config, {"X-Trello-Webhook": "x"}, b'{}') is False


def test_verify_webhook_sem_callback_url():
    adapter = TrelloAdapter()
    config = _config(webhook_secret="s")
    assert adapter.verify_webhook(config, {"X-Trello-Webhook": "x"}, b'{}') is False


def test_verify_webhook_sem_header():
    adapter = TrelloAdapter()
    config = _config(webhook_secret="s", callback_url="u")
    assert adapter.verify_webhook(config, {}, b'{}') is False


# ===========================================================================
# parse_webhook
# ===========================================================================


def test_parse_webhook_create_card():
    adapter = TrelloAdapter()
    payload = {
        "action": {
            "type": "createCard",
            "data": {
                "card": {"id": "c1", "name": "Nova feature"},
                "list": {"name": "Backlog"},
            },
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "issue_created"
    assert ev.external_id == "c1"
    assert ev.status_canonical == "todo"


def test_parse_webhook_update_com_listBefore_vira_status_changed():
    adapter = TrelloAdapter()
    payload = {
        "action": {
            "type": "updateCard",
            "data": {
                "card": {"id": "c2", "name": "x"},
                "listBefore": {"name": "Backlog"},
                "listAfter": {"name": "Done"},
            },
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "status_changed"
    assert ev.status_canonical == "done"


def test_parse_webhook_archive_vira_status_changed_cancelled():
    adapter = TrelloAdapter()
    payload = {
        "action": {
            "type": "updateCard",
            "data": {
                "card": {"id": "c3", "name": "x", "closed": True},
                "old": {"closed": False},
            },
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "status_changed"
    assert ev.status_canonical == "cancelled"


def test_parse_webhook_delete_card():
    adapter = TrelloAdapter()
    payload = {
        "action": {
            "type": "deleteCard",
            "data": {"card": {"id": "c4"}},
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "issue_deleted"


def test_parse_webhook_comment_card():
    adapter = TrelloAdapter()
    payload = {
        "action": {
            "type": "commentCard",
            "data": {"card": {"id": "c5", "name": "x"}},
        },
    }
    ev = adapter.parse_webhook(_config(), payload)
    assert ev.event_type == "issue_updated"


def test_parse_webhook_action_irrelevante_retorna_none():
    adapter = TrelloAdapter()
    payload = {"action": {"type": "addMemberToBoard", "data": {}}}
    assert adapter.parse_webhook(_config(), payload) is None


def test_parse_webhook_sem_project_binding_retorna_none():
    adapter = TrelloAdapter()
    config = _config(gca_project_id="")
    # gca_project_id vazio → None.
    payload = {
        "action": {"type": "createCard",
                   "data": {"card": {"id": "c1"}, "list": {"name": "Backlog"}}},
    }
    # Força config.extra['gca_project_id'] vazio
    config.extra["gca_project_id"] = ""
    assert adapter.parse_webhook(config, payload) is None


# ===========================================================================
# Erros HTTP
# ===========================================================================


@pytest.mark.asyncio
async def test_401_levanta_auth_error():
    adapter = _adapter_with(lambda r: httpx.Response(401, json={}))
    with pytest.raises(IssueTrackerAuthError):
        await adapter.get_issue(_config(), "x")


@pytest.mark.asyncio
async def test_404_levanta_not_found():
    adapter = _adapter_with(lambda r: httpx.Response(404, json={}))
    with pytest.raises(IssueTrackerNotFound):
        await adapter.get_issue(_config(), "x")


@pytest.mark.asyncio
async def test_429_levanta_rate_limit():
    adapter = _adapter_with(lambda r: httpx.Response(429, json={}))
    with pytest.raises(IssueTrackerRateLimitError):
        await adapter.get_issue(_config(), "x")


@pytest.mark.asyncio
async def test_500_levanta_api_error():
    adapter = _adapter_with(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(IssueTrackerAPIError):
        await adapter.get_issue(_config(), "x")
