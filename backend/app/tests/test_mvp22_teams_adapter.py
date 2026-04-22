"""MVP 22 — testes do TeamsAdapter uni-direcional.

Cobre:
- Registry builtin inclui teams após register_builtin_notifiers.
- Sem webhook_url → fail non-retryable.
- Evento fora de opted_in → fail non-retryable.
- Sucesso 200 (Workflows) / 202 (legacy connector) com body Adaptive Card.
- Body link_only_mode não vaza fields.
- 429/5xx → retryable; 4xx → non-retryable; timeout → retryable.
- Card canônico: $schema + type AdaptiveCard + version 1.4 + TextBlock header.
- FactSet presente com fields; actions Action.OpenUrl quando há link.
"""
import json

import httpx
import pytest

from app.services.adapters.teams_adapter import TeamsAdapter
from app.services.notifier_service import register_builtin_notifiers
from app.services.ports.notifier_port import (
    DeliveryResult,
    EventPayload,
    NotifierConfig,
    _clear_notifier_registry_for_tests,
    registered_notifiers,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _config(**kw) -> NotifierConfig:
    defaults = dict(
        credentials={"webhook_url": "https://prod-xx.eastus.logic.azure.com/workflows/.../triggers/manual/paths/invoke?api-version=..."},
        channel="#gca-events",
        opted_in_events=None,
        link_only_mode=False,
        gca_base_url="https://gca.cliente.com",
        extra={},
    )
    defaults.update(kw)
    return NotifierConfig(**defaults)


def _payload(event_type="MODULE_APPROVED", **kw):
    defaults = dict(
        event_type=event_type,
        title="Módulo aprovado",
        project_name="FinanceHub Pro",
        project_id="proj-uuid-001",
        fields=[("RF", "RF-001"), ("Status", "approved")],
        link_path="/projects/abc/backlog",
        severity="success",
    )
    defaults.update(kw)
    return EventPayload(**defaults)


@pytest.fixture(autouse=True)
def _registry_setup():
    _clear_notifier_registry_for_tests()
    register_builtin_notifiers()
    yield
    _clear_notifier_registry_for_tests()


# ===========================================================================
# Registry
# ===========================================================================


def test_register_builtin_inclui_teams():
    _clear_notifier_registry_for_tests()
    register_builtin_notifiers()
    assert "teams" in registered_notifiers()
    assert "slack" in registered_notifiers()


# ===========================================================================
# send — casos negativos
# ===========================================================================


@pytest.mark.asyncio
async def test_sem_webhook_url_fail_non_retryable():
    adapter = TeamsAdapter()
    config = _config(credentials={})
    result = await adapter.send(config, _payload())
    assert result.ok is False
    assert result.retryable is False
    assert "webhook_url" in (result.error or "")


@pytest.mark.asyncio
async def test_evento_fora_de_opted_in_fail_non_retryable():
    adapter = TeamsAdapter()
    config = _config(opted_in_events=["BACKUP_FAILED"])
    result = await adapter.send(config, _payload(event_type="MODULE_APPROVED"))
    assert result.ok is False
    assert result.retryable is False


# ===========================================================================
# send — sucesso + body canônico
# ===========================================================================


@pytest.mark.asyncio
async def test_sucesso_200_teams_workflow():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        captured["url"] = str(request.url)
        return httpx.Response(
            200, text="ok",
            headers={"request-id": "req-teams-1"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is True
    assert result.delivery_id == "req-teams-1"

    body = captured["body"]
    # Teams message envelope.
    assert body["type"] == "message"
    assert len(body["attachments"]) == 1
    attachment = body["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = attachment["content"]
    # Adaptive Card canônico.
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert "$schema" in card
    # Header TextBlock + context + FactSet presentes.
    types = [el["type"] for el in card["body"]]
    assert "TextBlock" in types  # header + context
    assert "FactSet" in types
    # Action OpenUrl presente.
    assert card.get("actions", [])
    assert card["actions"][0]["type"] == "Action.OpenUrl"
    assert card["actions"][0]["url"] == "https://gca.cliente.com/projects/abc/backlog"


@pytest.mark.asyncio
async def test_sucesso_202_legacy_connector():
    """Office 365 Connector legacy retorna 202, deve ser aceito."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(202)
    ))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is True


@pytest.mark.asyncio
async def test_link_only_mode_nao_vaza_fields():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = TeamsAdapter(client=client)

    config = _config(link_only_mode=True)
    result = await adapter.send(config, _payload(
        fields=[("Secret", "DADO-SENSIVEL")],
    ))
    assert result.ok is True

    serialized = json.dumps(captured["body"])
    assert "DADO-SENSIVEL" not in serialized


@pytest.mark.asyncio
async def test_link_only_mode_sem_actions():
    """Em link-only, o card não tem Action.OpenUrl — apenas link markdown inline."""
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(link_only_mode=True), _payload())
    assert result.ok is True

    card = captured["body"]["attachments"][0]["content"]
    assert card.get("actions", []) == []


# ===========================================================================
# send — erros HTTP
# ===========================================================================


@pytest.mark.asyncio
async def test_429_retryable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(429, text="rate limited")
    ))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is True


@pytest.mark.asyncio
async def test_502_retryable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(502, text="bad gateway")
    ))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is True


@pytest.mark.asyncio
async def test_400_non_retryable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, text="invalid_body")
    ))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is False


@pytest.mark.asyncio
async def test_http_timeout_retryable():
    def handler(r):
        raise httpx.ConnectTimeout("timeout")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = TeamsAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is True


# ===========================================================================
# Severity → themeColor
# ===========================================================================


@pytest.mark.asyncio
async def test_severity_mapeia_para_color_canonico():
    """danger → attention; success → good; warning → warning; info → default."""
    captured: list[dict] = []

    def handler(request):
        captured.append(json.loads(request.content.decode()))
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = TeamsAdapter(client=client)

    for sev, expected_color in [
        ("info", "default"),
        ("success", "good"),
        ("warning", "warning"),
        ("danger", "attention"),
    ]:
        await adapter.send(_config(), _payload(severity=sev))

    for i, (_, expected) in enumerate([
        ("info", "default"), ("success", "good"),
        ("warning", "warning"), ("danger", "attention"),
    ]):
        card = captured[i]["attachments"][0]["content"]
        header = card["body"][0]
        assert header["color"] == expected
