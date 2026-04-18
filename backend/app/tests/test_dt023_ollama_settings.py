"""DT-023 Commit 1 — schema e endpoint aceitam Ollama.

Cobertura:
- LlmSettingsRequest: api_key opcional, base_url opcional
- valid_providers inclui "ollama"
- Validação de model permite `:` (llama3.1:8b)
- Provider="ollama" exige base_url; demais exigem api_key
- base_url deve começar com http(s)
- Persistência de base_url no provider record (settings_json)
"""
import pytest

from app.routers.settings_router import LlmSettingsRequest


# ---------------------------------------------------------------------------
# Schema (LlmSettingsRequest)
# ---------------------------------------------------------------------------

def test_schema_accepts_ollama_without_api_key():
    """Ollama com base_url e sem api_key — caso típico (sem auth)."""
    req = LlmSettingsRequest(provider="ollama", base_url="http://host.docker.internal:11434")
    assert req.provider == "ollama"
    assert req.api_key is None
    assert req.base_url == "http://host.docker.internal:11434"


def test_schema_accepts_ollama_with_api_key():
    """Ollama atrás de reverse proxy com Bearer token — também ok."""
    req = LlmSettingsRequest(
        provider="ollama",
        base_url="https://ollama.empresa.com",
        api_key="bearer-from-proxy",
    )
    assert req.api_key == "bearer-from-proxy"


def test_schema_accepts_ollama_model_with_colon():
    """Modelos Ollama típicos (llama3.1:8b, qwen2.5-coder:7b) têm `:`."""
    req = LlmSettingsRequest(
        provider="ollama",
        base_url="http://host.docker.internal:11434",
        model_preference="llama3.1:8b",
    )
    assert req.model_preference == "llama3.1:8b"


def test_schema_accepts_anthropic_without_base_url():
    """Anthropic continua igual — só api_key."""
    req = LlmSettingsRequest(provider="anthropic", api_key="sk-ant-...")
    assert req.api_key == "sk-ant-..."
    assert req.base_url is None


def test_schema_api_key_optional_field_default_none():
    req = LlmSettingsRequest(provider="ollama", base_url="http://localhost:11434")
    assert req.api_key is None  # default None, não exception


# ---------------------------------------------------------------------------
# Endpoint POST /settings/llm — validações específicas (chamada direta da função)
#
# Não usamos TestClient (sync) com async db_session pra evitar conflito
# de loops do asyncio. Chamamos `save_llm_settings` diretamente como
# coroutine, bypassando os Depends — é a forma canônica de testar
# lógica de routers async sem o overhead do HTTP.
# ---------------------------------------------------------------------------

from fastapi import HTTPException

from app.routers.settings_router import save_llm_settings


async def _gp_permissions(test_user) -> dict:
    """Mock dos `permissions` que `Depends(require_action)` produziria."""
    return {"user_id": test_user.id, "actions": {"project:edit"}, "role": "gp"}


@pytest.mark.asyncio
async def test_endpoint_rejects_ollama_without_base_url(db_session, test_project, test_user):
    perms = await _gp_permissions(test_user)
    with pytest.raises(HTTPException) as exc:
        await save_llm_settings(
            project_id=test_project.id,
            req=LlmSettingsRequest(provider="ollama"),
            permissions=perms,
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert "base_url" in exc.value.detail


@pytest.mark.asyncio
async def test_endpoint_rejects_ollama_with_invalid_url_scheme(db_session, test_project, test_user):
    perms = await _gp_permissions(test_user)
    with pytest.raises(HTTPException) as exc:
        await save_llm_settings(
            project_id=test_project.id,
            req=LlmSettingsRequest(provider="ollama", base_url="host.docker.internal:11434"),
            permissions=perms,
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert "http" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_endpoint_accepts_ollama_with_base_url(db_session, test_project, test_user):
    """Ollama válido: sem api_key, base_url http, model com `:`."""
    perms = await _gp_permissions(test_user)
    res = await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(
            provider="ollama",
            base_url="http://host.docker.internal:11434",
            model_preference="llama3.1:8b",
        ),
        permissions=perms,
        db=db_session,
    )
    assert res == {"success": True}


@pytest.mark.asyncio
async def test_endpoint_persists_base_url_in_provider_record(db_session, test_project, test_user):
    """Após salvar, settings_json.providers[].base_url está populado."""
    perms = await _gp_permissions(test_user)
    await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(
            provider="ollama",
            base_url="http://host.docker.internal:11434",
            model_preference="llama3.1:8b",
        ),
        permissions=perms,
        db=db_session,
    )

    from sqlalchemy import select
    from app.models.base import ProjectSettings
    import json as _json

    result = await db_session.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == test_project.id,
            ProjectSettings.setting_type == "llm",
        )
    )
    row = result.scalar_one_or_none()
    assert row is not None
    data = _json.loads(row.settings_json)
    providers = data["providers"]
    assert len(providers) == 1
    ollama = providers[0]
    assert ollama["provider"] == "ollama"
    assert ollama["base_url"] == "http://host.docker.internal:11434"
    assert ollama["model"] == "llama3.1:8b"
    assert ollama["is_default"] is True


@pytest.mark.asyncio
async def test_endpoint_rejects_non_ollama_without_api_key(db_session, test_project, test_user):
    perms = await _gp_permissions(test_user)
    with pytest.raises(HTTPException) as exc:
        await save_llm_settings(
            project_id=test_project.id,
            req=LlmSettingsRequest(provider="anthropic"),
            permissions=perms,
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert "api_key" in exc.value.detail


@pytest.mark.asyncio
async def test_endpoint_rejects_invalid_provider(db_session, test_project, test_user):
    perms = await _gp_permissions(test_user)
    with pytest.raises(HTTPException) as exc:
        await save_llm_settings(
            project_id=test_project.id,
            req=LlmSettingsRequest(provider="claude-clone", api_key="x"),
            permissions=perms,
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert "Aceitos" in exc.value.detail


@pytest.mark.asyncio
async def test_endpoint_accepts_model_with_colon(db_session, test_project, test_user):
    """Validação de model aceita `:` (llama3.1:8b, qwen2.5-coder:7b)."""
    perms = await _gp_permissions(test_user)
    res = await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(
            provider="ollama",
            base_url="http://host.docker.internal:11434",
            model_preference="qwen2.5-coder:7b",
        ),
        permissions=perms,
        db=db_session,
    )
    assert res == {"success": True}


# ---------------------------------------------------------------------------
# Commit 2 — endpoint POST /settings/llm/validate aceita Ollama
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, patch
from app.routers.settings_router import validate_llm_settings


@pytest.mark.asyncio
async def test_validate_ollama_pings_api_tags(db_session, test_project, test_user):
    """Quando provider=ollama, validate faz GET {base_url}/api/tags."""
    perms = await _gp_permissions(test_user)

    # Setup: cria o provider Ollama no projeto
    await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(
            provider="ollama",
            base_url="http://host.docker.internal:11434",
            model_preference="llama3.1:8b",
        ),
        permissions=perms,
        db=db_session,
    )

    # Mock httpx pra não bater no Ollama real
    captured_url = {}

    class _FakeResp:
        status_code = 200
        text = '{"models": [{"name": "llama3.1:8b"}]}'

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def get(self, url, headers=None):
            captured_url["url"] = url
            captured_url["headers"] = headers or {}
            return _FakeResp()

    with patch("httpx.AsyncClient", _FakeClient):
        res = await validate_llm_settings(
            project_id=test_project.id,
            provider="ollama",
            permissions=perms,
            db=db_session,
        )

    assert res["valid"] is True
    assert res["provider"] == "ollama"
    # Confirma URL canônica do daemon Ollama
    assert captured_url["url"] == "http://host.docker.internal:11434/api/tags"
    # Sem api_key configurada → sem Authorization header
    assert "Authorization" not in captured_url["headers"]


@pytest.mark.asyncio
async def test_validate_ollama_with_bearer_when_api_key_set(db_session, test_project, test_user):
    """Ollama atrás de proxy com Bearer: api_key opcional vai como header."""
    perms = await _gp_permissions(test_user)

    await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(
            provider="ollama",
            base_url="https://ollama.empresa.com",
            api_key="bearer-from-proxy",
        ),
        permissions=perms,
        db=db_session,
    )

    captured_headers = {}

    class _FakeResp:
        status_code = 200

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return None
        async def get(self, url, headers=None):
            captured_headers.update(headers or {})
            return _FakeResp()

    with patch("httpx.AsyncClient", _FakeClient):
        res = await validate_llm_settings(
            project_id=test_project.id,
            provider="ollama",
            permissions=perms,
            db=db_session,
        )

    assert res["valid"] is True
    assert captured_headers.get("Authorization") == "Bearer bearer-from-proxy"


@pytest.mark.asyncio
async def test_validate_ollama_missing_base_url_returns_400(db_session, test_project, test_user):
    """Edge case defensivo: base_url some por inconsistência de schema → 400 claro."""
    perms = await _gp_permissions(test_user)

    # Insere Ollama bypassing o save_llm_settings pra simular dados sujos
    from sqlalchemy import select
    from app.models.base import ProjectSettings
    import json as _json

    settings_row = ProjectSettings(
        project_id=test_project.id,
        setting_type="llm",
        settings_json=_json.dumps({
            "providers": [{"provider": "ollama", "is_default": True, "model": None,
                           "last_validated_at": None, "last_validation_ok": None}],
            "default_provider": "ollama",
        }),
    )
    db_session.add(settings_row)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await validate_llm_settings(
            project_id=test_project.id,
            provider="ollama",
            permissions=perms,
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert "base_url" in exc.value.detail


@pytest.mark.asyncio
async def test_validate_anthropic_still_works_unchanged(db_session, test_project, test_user):
    """Path original (Anthropic) não foi quebrado pelo Commit 2."""
    perms = await _gp_permissions(test_user)
    await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(provider="anthropic", api_key="sk-ant-fake"),
        permissions=perms,
        db=db_session,
    )

    captured_url = {}

    class _FakeResp:
        status_code = 200

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return None
        async def get(self, url, headers=None):
            captured_url["url"] = url
            captured_url["headers"] = headers or {}
            return _FakeResp()

    with patch("httpx.AsyncClient", _FakeClient):
        res = await validate_llm_settings(
            project_id=test_project.id,
            provider="anthropic",
            permissions=perms,
            db=db_session,
        )

    assert res["valid"] is True
    assert captured_url["url"] == "https://api.anthropic.com/v1/models"
    assert captured_url["headers"]["x-api-key"] == "sk-ant-fake"
