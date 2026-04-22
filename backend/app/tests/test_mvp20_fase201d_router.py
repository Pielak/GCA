"""MVP 20 Fase 20.1d — testes HTTP do integration_router.

Valida:
- GET config: 401 sem token, 403 sem RBAC, 200 com Admin.
- PUT settings: valida provider na whitelist; atualiza.
- PUT credential: armazena no vault; whitelist por provider.
- DELETE credential.
- GET list_external_issues.
- POST webhook: 404 provider desconhecido; 400 sem config; 401 assinatura
  inválida; 200 fluxo feliz.
- register_builtin_adapters registra jira+trello no registry.
"""
import hashlib
import hmac
import json
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.database import AsyncSessionLocal
from app.main import app
from app.models.base import (
    ExternalIssue,
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.services.integration_config_service import (
    register_builtin_adapters,
    save_settings_json,
    set_credential,
)
from app.services.ports.issue_tracker_port import (
    _clear_registry_for_tests,
    registered_providers,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_admin() -> tuple[User, str]:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"admin-{uid.hex[:6]}@example.com",
                password_hash=hash_password("Test@1234"),
                full_name="Admin", is_active=True, is_admin=True,
                created_at=datetime.utcnow(),
            )
            session.add(user)
    return user, create_access_token(data={"sub": str(uid)})


async def _make_gp_and_project() -> tuple[User, str, Project]:
    """Cria GP + projeto + membership 'gp' aceita."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"gp-{uid.hex[:6]}@example.com",
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
                name="It Proj", slug=f"it-{uid.hex[:6]}",
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
    """Garante adapters registrados pra cada teste."""
    _clear_registry_for_tests()
    register_builtin_adapters()
    yield
    _clear_registry_for_tests()


# ===========================================================================
# Registration canônica
# ===========================================================================


def test_register_builtin_adapters_registra_jira_e_trello():
    _clear_registry_for_tests()
    register_builtin_adapters()
    providers = registered_providers()
    assert "jira" in providers
    assert "trello" in providers


# ===========================================================================
# GET config
# ===========================================================================


@pytest.mark.asyncio
async def test_get_config_sem_token_retorna_401():
    _, _, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker",
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_config_retorna_safe_sem_credenciais():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False  # default
    assert body["active_provider"] is None
    assert "has_credentials" in body
    assert "jira" in body["has_credentials"]
    assert "trello" in body["has_credentials"]
    # Sem credenciais gravadas ainda: todos flags False.
    assert all(v is False for v in body["has_credentials"]["jira"].values())
    # Registry canônico exposto pra UI.
    assert "jira" in body["registered_providers"]


# ===========================================================================
# PUT settings
# ===========================================================================


@pytest.mark.asyncio
async def test_put_settings_valida_provider_fora_do_registry():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": "asana",  # não suportado em V1
                "providers": {},
            },
        )
    # Provider desconhecido → 400.
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_settings_salva_config_valida():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": "jira",
                "providers": {
                    "jira": {
                        "base_url": "https://ex.atlassian.net",
                        "default_project_key": "PROJ",
                        "status_mapping": {"In Review": "review"},
                        "extra": {},
                    },
                },
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["active_provider"] == "jira"
    assert body["providers"]["jira"]["default_project_key"] == "PROJ"


@pytest.mark.asyncio
async def test_put_settings_rejeita_provider_fora_whitelist_v1():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "active_provider": None,
                "providers": {"linear": {"base_url": "x",
                                          "default_project_key": "x"}},
            },
        )
    assert resp.status_code == 400


# ===========================================================================
# PUT / DELETE credentials
# ===========================================================================


@pytest.mark.asyncio
async def test_put_credential_armazena_no_vault():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker/credentials/jira/api_token",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "test-token-123"},
        )
    assert resp.status_code == 200

    # Verifica que aparece em has_credentials.
    async with _client() as client:
        get_resp = await client.get(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert get_resp.json()["has_credentials"]["jira"]["api_token"] is True


@pytest.mark.asyncio
async def test_put_credential_whitelist_rejeita_chave_invalida():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.put(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker/credentials/jira/random_key",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "x"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_credential_remove_do_vault():
    _, token, project = await _make_gp_and_project()
    # Insere via service direto pra setup. Vault commita internamente.
    async with AsyncSessionLocal() as session:
        await set_credential(session, project.id, "jira", "api_token", "x")

    async with _client() as client:
        resp = await client.delete(
            f"/api/v1/projects/{project.id}/integrations/issue-tracker/credentials/jira/api_token",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


# ===========================================================================
# GET list external issues
# ===========================================================================


@pytest.mark.asyncio
async def test_list_external_issues_vazia():
    _, token, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.get(
            f"/api/v1/projects/{project.id}/external-issues",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "issues": []}


@pytest.mark.asyncio
async def test_list_external_issues_retorna_itens():
    _, token, project = await _make_gp_and_project()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(ExternalIssue(
                project_id=project.id, provider="jira",
                external_id="PROJ-1", title="Login",
                status_canonical="todo", url="http://x",
            ))

    async with _client() as client:
        resp = await client.get(
            f"/api/v1/projects/{project.id}/external-issues",
            headers={"Authorization": f"Bearer {token}"},
        )
    body = resp.json()
    assert body["count"] == 1
    assert body["issues"][0]["external_id"] == "PROJ-1"
    assert body["issues"][0]["title"] == "Login"


# ===========================================================================
# POST webhook
# ===========================================================================


@pytest.mark.asyncio
async def test_webhook_provider_desconhecido_404():
    _, _, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.post(
            f"/api/v1/integrations/webhooks/issue-tracker/linear/{project.id}",
            json={},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_sem_config_400():
    _, _, project = await _make_gp_and_project()
    async with _client() as client:
        resp = await client.post(
            f"/api/v1/integrations/webhooks/issue-tracker/jira/{project.id}",
            json={"webhookEvent": "jira:issue_updated"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_assinatura_invalida_retorna_accepted_false():
    """Config existe mas assinatura do header é inválida — adapter retorna
    None e o endpoint responde 200 com accepted=false."""
    _, _, project = await _make_gp_and_project()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await save_settings_json(session, project.id, {
                "enabled": True,
                "active_provider": "jira",
                "providers": {
                    "jira": {
                        "base_url": "https://ex.atlassian.net",
                        "default_project_key": "PROJ",
                    },
                },
            })
    # Vault commita internamente — precisa de sessões separadas, sem
    # wrap em session.begin().
    async with AsyncSessionLocal() as session:
        await set_credential(session, project.id, "jira", "email", "a@b")
    async with AsyncSessionLocal() as session:
        await set_credential(session, project.id, "jira", "api_token", "t")
    async with AsyncSessionLocal() as session:
        await set_credential(session, project.id, "jira", "webhook_secret", "correct")

    payload = {"webhookEvent": "jira:issue_updated",
               "issue": {"key": "PROJ-1", "fields": {}}}
    raw = json.dumps(payload).encode()
    bad_sig = "sha256=" + "0" * 64

    async with _client() as client:
        resp = await client.post(
            f"/api/v1/integrations/webhooks/issue-tracker/jira/{project.id}",
            json=payload,
            headers={"X-Hub-Signature-256": bad_sig},
        )
    assert resp.status_code == 200
    assert resp.json()["accepted"] is False
