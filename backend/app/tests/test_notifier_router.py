"""Fix pós-MVP 22 — testes HTTP dos endpoints de notifier.

Análogo a test_mvp20_fase201d_router mas pra notifier (Slack + Teams).

Cobre:
- GET config: 401 sem token, 200 safe sem credenciais, estrutura canônica.
- PUT settings: valida provider contra registry, salva, rejeita fora whitelist V1.
- PUT credential: armazena no vault, whitelist rejeita chave inválida.
- DELETE credential: remove.
"""
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.database import AsyncSessionLocal
from app.main import app
from app.models.base import (
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.services.notifier_service import (
    register_builtin_notifiers,
    set_notifier_credential,
)
from app.services.ports.notifier_port import (
    _clear_notifier_registry_for_tests,
    registered_notifiers,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_gp_and_project():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"gp-notif-{uid.hex[:6]}@example.com",
                password_hash=hash_password("Test@1234"),
                full_name="GP", is_active=True, is_admin=False,
                created_at=datetime.utcnow(),
            )
            session.add(user)
            org = Organization(
                id=uuid4(), name=f"Org {uid.hex[:6]}",
                slug=f"org-{uid.hex[:6]}", owner_id=user.id,
                is_active=True, created_at=datetime.utcnow(),
            )
            session.add(org)
            project = Project(
                id=uuid4(), organization_id=org.id,
                name="Notif Proj", slug=f"notif-{uid.hex[:6]}",
                description="t", deliverable_type="web_app",
                status="active", created_at=datetime.utcnow(),
            )
            session.add(project)
            await session.flush()
            member = ProjectMember(
                id=uuid4(), project_id=project.id, user_id=user.id,
                role="gp", is_active=True,
                accepted_at=datetime.utcnow(), joined_at=datetime.utcnow(),
            )
            session.add(member)
    token = create_access_token(data={"sub": str(uid)})
    return user, token, project


@pytest.fixture(autouse=True)
def _registry_setup():
    _clear_notifier_registry_for_tests()
    register_builtin_notifiers()
    yield
    _clear_notifier_registry_for_tests()


# ===========================================================================
# GET config
# ===========================================================================


@pytest.mark.asyncio
async def test_get_notifier_sem_token_401():
    _, _, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/notifier",
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_notifier_retorna_safe_config_canonica():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["active_provider"] is None
    assert "has_credentials" in body
    assert "slack" in body["has_credentials"]
    assert "teams" in body["has_credentials"]
    # Sem credenciais ainda — flags False.
    assert body["has_credentials"]["slack"]["webhook_url"] is False
    assert body["has_credentials"]["teams"]["webhook_url"] is False
    # Registry canônico exposto pra UI.
    assert set(body["registered_providers"]) >= {"slack", "teams"}
    # Lista de eventos canônicos.
    assert "MODULE_APPROVED" in body["canonical_events"]
    assert "BACKUP_FAILED" in body["canonical_events"]
    assert len(body["canonical_events"]) == 6


# ===========================================================================
# PUT settings
# ===========================================================================


@pytest.mark.asyncio
async def test_put_settings_salva_slack_ativo_com_eventos_opt_in():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": "slack",
                "providers": {
                    "slack": {
                        "channel": "#gca-eventos",
                        "opted_in_events": ["MODULE_APPROVED", "ERS_REGENERATED"],
                        "link_only_mode": False,
                        "gca_base_url": "https://gca.cliente.com",
                        "extra": {},
                    },
                },
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["active_provider"] == "slack"
    slack = body["providers"]["slack"]
    assert slack["channel"] == "#gca-eventos"
    assert set(slack["opted_in_events"]) == {"MODULE_APPROVED", "ERS_REGENERATED"}


@pytest.mark.asyncio
async def test_put_settings_filtra_eventos_desconhecidos_silenciosamente():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": "slack",
                "providers": {
                    "slack": {
                        "channel": "#x",
                        "opted_in_events": ["MODULE_APPROVED", "EVENTO_INVENTADO"],
                        "link_only_mode": False,
                        "gca_base_url": "",
                        "extra": {},
                    },
                },
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    # Evento inválido filtrado silenciosamente.
    assert body["providers"]["slack"]["opted_in_events"] == ["MODULE_APPROVED"]


@pytest.mark.asyncio
async def test_put_settings_rejeita_provider_fora_whitelist_v1():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": None,
                "providers": {"mattermost": {"channel": "x",
                                              "link_only_mode": False,
                                              "gca_base_url": "",
                                              "extra": {}}},
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_settings_rejeita_active_provider_nao_registrado():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": "discord",
                "providers": {},
            },
        )
    assert resp.status_code == 400


# ===========================================================================
# PUT / DELETE credential
# ===========================================================================


@pytest.mark.asyncio
async def test_put_credential_slack_webhook_armazena_no_vault():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier/credentials/slack/webhook_url",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "https://hooks.slack.com/services/X/Y/Z"},
        )
    assert resp.status_code == 200

    # Confirma via GET que flag virou True.
    async with _client() as client:
        get_resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert get_resp.json()["has_credentials"]["slack"]["webhook_url"] is True


@pytest.mark.asyncio
async def test_put_credential_teams_webhook_armazena_no_vault():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier/credentials/teams/webhook_url",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "https://prod-xx.logic.azure.com/..."},
        )
    assert resp.status_code == 200

    async with _client() as client:
        get_resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert get_resp.json()["has_credentials"]["teams"]["webhook_url"] is True


@pytest.mark.asyncio
async def test_put_credential_chave_fora_whitelist_400():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier/credentials/slack/random_key",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "x"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_credential_provider_sem_whitelist_400():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/notifier/credentials/mattermost/webhook_url",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "x"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_credential_remove_do_vault():
    _, token, project = await _make_gp_and_project()
    # Insere via service direto.
    async with AsyncSessionLocal() as session:
        await set_notifier_credential(
            session, project.id, "slack", "webhook_url", "https://x",
        )

    async with _client() as client:
        resp = await client.delete(
            f"/api/v1/projects/{project.id}/integrations/notifier/credentials/slack/webhook_url",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200

    # Confirma que flag virou False.
    async with _client() as client:
        get_resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/notifier",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert get_resp.json()["has_credentials"]["slack"]["webhook_url"] is False
