"""MVP 20 Fase 20.3 — testes do Slack Notifier uni-direcional.

Cobre:
- Porta + registry (register/get/clear).
- NotifierConfig.is_opted_in — default opted in todos, lista explícita respeita.
- SlackAdapter:
    - sem webhook_url → fail non-retryable
    - evento fora de opted_in → fail non-retryable
    - sucesso 200 (body estruturado Block Kit com header + fields + botão)
    - 429/5xx → retryable
    - 4xx non-retryable
    - link_only_mode degrada formatação mantendo link
- Service:
    - build_notifier_config retorna None quando sem config/credencial
    - send_event sem config → ok=False não retryable
    - send_event envia com mock e retorna delivery_id
    - event_type desconhecido → fail non-retryable
"""
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.core.security import hash_password
from app.models.base import (
    Organization,
    Project,
    User,
)
from app.services.adapters.slack_adapter import SlackAdapter
from app.services.notifier_service import (
    build_notifier_config,
    register_builtin_notifiers,
    save_settings_json,
    send_event,
)
from app.services.ports.notifier_port import (
    ALL_CANONICAL_EVENTS,
    DeliveryResult,
    EventPayload,
    NotifierConfig,
    NotifierConfigError,
    _clear_notifier_registry_for_tests,
    get_notifier,
    register_notifier,
    registered_notifiers,
)
from app.services.integration_config_service import set_credential as _set_cred_it
# Reuso do mesmo vault — só muda secret_type.
from app.services.vault_service import VaultService


# ===========================================================================
# Helpers
# ===========================================================================


async def _make_user(db) -> User:
    uid = uuid4()
    user = User(
        id=uid, email=f"ntf-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="Ntf Tester", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db, user) -> Project:
    org = Organization(
        id=uuid4(), name=f"Org {uuid4().hex[:6]}",
        slug=f"org-ntf-{uuid4().hex[:6]}", owner_id=user.id,
        is_active=True, created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id, name="Ntf Proj",
        slug=f"ntf-{uuid4().hex[:6]}", description="t",
        deliverable_type="web_app", status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


@pytest.fixture(autouse=True)
def _registry_setup():
    _clear_notifier_registry_for_tests()
    register_builtin_notifiers()
    yield
    _clear_notifier_registry_for_tests()


def _payload(event_type="MODULE_APPROVED", **kw):
    defaults = dict(
        event_type=event_type,
        title="Módulo aprovado",
        project_name="FinanceHub Pro",
        project_id=str(uuid4()),
        fields=[("RF", "RF-001"), ("Status", "approved")],
        link_path="/projects/abc/backlog",
        severity="success",
    )
    defaults.update(kw)
    return EventPayload(**defaults)


def _config(**kw) -> NotifierConfig:
    defaults = dict(
        credentials={"webhook_url": "https://hooks.slack.com/services/X/Y/Z"},
        channel="#gca-events",
        opted_in_events=None,
        link_only_mode=False,
        gca_base_url="https://gca.cliente.com",
        extra={},
    )
    defaults.update(kw)
    return NotifierConfig(**defaults)


# ===========================================================================
# Registry + opt-in
# ===========================================================================


def test_register_builtin_notifiers_registra_slack():
    _clear_notifier_registry_for_tests()
    register_builtin_notifiers()
    assert "slack" in registered_notifiers()


def test_notifier_config_default_opted_in_todos():
    c = _config(opted_in_events=None)
    for e in ALL_CANONICAL_EVENTS:
        assert c.is_opted_in(e)


def test_notifier_config_opted_in_lista_especifica():
    c = _config(opted_in_events=["MODULE_APPROVED", "BACKUP_FAILED"])
    assert c.is_opted_in("MODULE_APPROVED")
    assert c.is_opted_in("BACKUP_FAILED")
    assert not c.is_opted_in("OCG_CONSOLIDATED")


# ===========================================================================
# SlackAdapter
# ===========================================================================


@pytest.mark.asyncio
async def test_slack_sem_webhook_url_fail_non_retryable():
    adapter = SlackAdapter()
    config = _config(credentials={})
    result = await adapter.send(config, _payload())
    assert result.ok is False
    assert result.retryable is False
    assert "webhook_url" in (result.error or "")


@pytest.mark.asyncio
async def test_slack_evento_fora_de_opted_in_fail_non_retryable():
    adapter = SlackAdapter()
    config = _config(opted_in_events=["BACKUP_FAILED"])
    result = await adapter.send(config, _payload(event_type="MODULE_APPROVED"))
    assert result.ok is False
    assert result.retryable is False


@pytest.mark.asyncio
async def test_slack_sucesso_200_body_contem_blocks_canonicos():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200, text="ok",
            headers={"x-slack-req-id": "req-123"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SlackAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is True
    assert result.delivery_id == "req-123"

    body = captured["body"]
    assert "text" in body  # fallback plaintext
    attachments = body["attachments"]
    assert len(attachments) == 1
    blocks = attachments[0]["blocks"]
    types = [b["type"] for b in blocks]
    assert "header" in types
    assert "context" in types
    assert "section" in types  # fields
    assert "actions" in types  # botão


@pytest.mark.asyncio
async def test_slack_link_only_mode_nao_vaza_fields():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SlackAdapter(client=client)

    config = _config(link_only_mode=True)
    result = await adapter.send(config, _payload(
        fields=[("Secret", "DADO-SENSIVEL")],
    ))
    assert result.ok is True

    # Body não pode conter o valor sensível (garantia de não vazamento).
    serialized = json.dumps(captured["body"])
    assert "DADO-SENSIVEL" not in serialized


@pytest.mark.asyncio
async def test_slack_429_retryable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(429, text="rate limited")
    ))
    adapter = SlackAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is True


@pytest.mark.asyncio
async def test_slack_500_retryable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(502, text="bad gateway")
    ))
    adapter = SlackAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is True


@pytest.mark.asyncio
async def test_slack_400_non_retryable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, text="invalid_payload")
    ))
    adapter = SlackAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is False


@pytest.mark.asyncio
async def test_slack_http_error_retryable():
    """Network failure → retryable."""
    def handler(r):
        raise httpx.ReadTimeout("timeout")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SlackAdapter(client=client)
    result = await adapter.send(_config(), _payload())
    assert result.ok is False
    assert result.retryable is True


# ===========================================================================
# Service — build_notifier_config
# ===========================================================================


@pytest.mark.asyncio
async def test_build_config_sem_settings_retorna_none(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    result = await build_notifier_config(db_session, project.id)
    assert result is None


@pytest.mark.asyncio
async def test_build_config_desabilitado_retorna_none(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await save_settings_json(db_session, project.id, {
        "enabled": False,
        "active_provider": "slack",
    })
    await db_session.flush()
    result = await build_notifier_config(db_session, project.id)
    assert result is None


@pytest.mark.asyncio
async def test_build_config_sem_credencial_retorna_none(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await save_settings_json(db_session, project.id, {
        "enabled": True,
        "active_provider": "slack",
        "providers": {"slack": {"channel": "#x"}},
    })
    await db_session.flush()
    result = await build_notifier_config(db_session, project.id)
    assert result is None


@pytest.mark.asyncio
async def test_build_config_completo_retorna_provider_e_config(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await save_settings_json(db_session, project.id, {
        "enabled": True,
        "active_provider": "slack",
        "providers": {"slack": {
            "channel": "#gca",
            "opted_in_events": ["MODULE_APPROVED", "UNKNOWN_EVT"],
            "link_only_mode": False,
            "gca_base_url": "https://gca.x",
        }},
    })
    await db_session.flush()

    vault = VaultService()
    await vault.store_secret(
        db_session, project.id, "notifier_credentials",
        "slack:webhook_url", "https://hooks.slack.com/services/X/Y/Z",
    )

    result = await build_notifier_config(db_session, project.id)
    assert result is not None
    provider, config = result
    assert provider == "slack"
    assert config.credentials["webhook_url"].startswith("https://hooks.slack")
    # Evento desconhecido é filtrado silenciosamente.
    assert config.opted_in_events == ["MODULE_APPROVED"]


# ===========================================================================
# Service — send_event
# ===========================================================================


@pytest.mark.asyncio
async def test_send_event_sem_config_retorna_fail(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    result = await send_event(
        db_session, project.id, "MODULE_APPROVED",
        title="x",
    )
    assert result.ok is False
    assert result.retryable is False


@pytest.mark.asyncio
async def test_send_event_fluxo_completo_com_mock(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await save_settings_json(db_session, project.id, {
        "enabled": True,
        "active_provider": "slack",
        "providers": {"slack": {
            "channel": "#gca",
            "gca_base_url": "https://gca.x",
        }},
    })
    await db_session.flush()

    vault = VaultService()
    await vault.store_secret(
        db_session, project.id, "notifier_credentials",
        "slack:webhook_url", "https://hooks.slack.com/services/X/Y/Z",
    )

    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        captured["url"] = str(request.url)
        return httpx.Response(200, headers={"x-slack-req-id": "r-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # Substitui adapter registrado com mock.
    _clear_notifier_registry_for_tests()
    register_notifier(SlackAdapter(client=client))

    result = await send_event(
        db_session, project.id, "MODULE_APPROVED",
        title="Módulo Login aprovado",
        fields=[("RF", "RF-001")],
        link_path="/projects/x/backlog",
        severity="success",
    )
    assert result.ok is True
    assert result.delivery_id == "r-1"
    # Captured URL deve bater com webhook configurado.
    assert "hooks.slack.com" in captured["url"]


@pytest.mark.asyncio
async def test_send_event_type_desconhecido_fail(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    result = await send_event(
        db_session, project.id, "EVENT_INVENTADO",  # type: ignore[arg-type]
        title="x",
    )
    assert result.ok is False
    assert "desconhecido" in (result.error or "").lower()


# ===========================================================================
# Porta — registry
# ===========================================================================


def test_get_notifier_sem_registro_levanta_config_error():
    _clear_notifier_registry_for_tests()
    with pytest.raises(NotifierConfigError):
        get_notifier("slack")


def test_register_notifier_sem_provider_levanta():
    _clear_notifier_registry_for_tests()

    class _Bad(SlackAdapter):
        provider = ""  # inválido
    with pytest.raises(NotifierConfigError):
        register_notifier(_Bad())
