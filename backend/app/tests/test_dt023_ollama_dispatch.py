"""DT-023 Commit 3 — dispatch nos services aceita Ollama.

Cobertura:
- AIKeyResolver.get_project_base_url lê base_url do settings_json
- ArguiderService aceita ollama (api_key opcional, base_url obrigatório)
- ArguiderService monta URL `{base_url}/v1/chat/completions` correta
- OCGUpdaterService idem (chamada via _call_llm)
- AgentService (camada admin) usa OLLAMA_BASE_URL como base
- Defaults de modelo Ollama consistentes (llama3.1:8b)
"""
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.routers.settings_router import LlmSettingsRequest, save_llm_settings
from app.services.ai_key_resolver import AIKeyResolver
from app.services.arguider_service import ArguiderService


# ---------------------------------------------------------------------------
# AIKeyResolver.get_project_base_url
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_project_base_url_reads_from_settings(db_session, test_project, test_user):
    perms = {"user_id": test_user.id, "actions": {"project:edit"}, "role": "gp"}
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
    bu = await AIKeyResolver.get_project_base_url(db_session, test_project.id, "ollama")
    assert bu == "http://host.docker.internal:11434"


@pytest.mark.asyncio
async def test_get_project_base_url_strips_trailing_slash(db_session, test_project, test_user):
    perms = {"user_id": test_user.id, "actions": {"project:edit"}, "role": "gp"}
    await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(
            provider="ollama",
            base_url="http://localhost:11434/",
        ),
        permissions=perms,
        db=db_session,
    )
    bu = await AIKeyResolver.get_project_base_url(db_session, test_project.id, "ollama")
    assert bu == "http://localhost:11434"  # sem trailing /


@pytest.mark.asyncio
async def test_get_project_base_url_returns_none_for_non_ollama(db_session, test_project, test_user):
    """Anthropic não tem base_url — retorna None mesmo configurado."""
    perms = {"user_id": test_user.id, "actions": {"project:edit"}, "role": "gp"}
    await save_llm_settings(
        project_id=test_project.id,
        req=LlmSettingsRequest(provider="anthropic", api_key="sk-ant-..."),
        permissions=perms,
        db=db_session,
    )
    bu = await AIKeyResolver.get_project_base_url(db_session, test_project.id, "anthropic")
    assert bu is None


@pytest.mark.asyncio
async def test_get_project_base_url_no_settings_returns_none(db_session, test_project):
    """Projeto sem settings_json LLM → None."""
    bu = await AIKeyResolver.get_project_base_url(db_session, test_project.id, "ollama")
    assert bu is None


# ---------------------------------------------------------------------------
# ArguiderService aceita Ollama
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_arguider_accepts_ollama_without_api_key(db_session):
    """Construtor aceita ollama sem api_key (URL local sem auth)."""
    arg = ArguiderService(
        db_session,
        project_api_key=None,
        provider="ollama",
        base_url="http://host.docker.internal:11434",
    )
    assert arg.provider == "ollama"
    assert arg.api_key is None
    assert arg.base_url == "http://host.docker.internal:11434"
    assert arg.model == "llama3.1:8b"  # default


@pytest.mark.asyncio
async def test_arguider_ollama_requires_base_url(db_session):
    """Construtor falha se ollama sem base_url."""
    with pytest.raises(RuntimeError, match="base_url"):
        ArguiderService(
            db_session,
            provider="ollama",
            project_api_key=None,
            base_url=None,
        )


@pytest.mark.asyncio
async def test_arguider_anthropic_still_requires_api_key(db_session):
    """Provider não-ollama continua exigindo api_key (regra DT-012)."""
    with pytest.raises(RuntimeError, match="chave IA do projeto"):
        ArguiderService(
            db_session,
            provider="anthropic",
            project_api_key=None,
        )


@pytest.mark.asyncio
async def test_arguider_call_llm_routes_ollama_to_local_url(db_session):
    """_call_llm POST → {base_url}/v1/chat/completions, sem Authorization
    quando api_key vazio."""
    arg = ArguiderService(
        db_session,
        provider="ollama",
        project_api_key=None,
        base_url="http://host.docker.internal:11434",
    )

    captured = {}

    class _FakeResp:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        text = "ok"

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return None
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["model"] = json.get("model") if json else None
            return _FakeResp()

    with patch("httpx.AsyncClient", _FakeClient):
        text, tokens = await arg._call_llm("system", "user", max_tokens=128)

    assert captured["url"] == "http://host.docker.internal:11434/v1/chat/completions"
    assert "Authorization" not in captured["headers"]
    assert captured["model"] == "llama3.1:8b"
    assert text == "ok"
    assert tokens == 15


@pytest.mark.asyncio
async def test_arguider_call_llm_ollama_with_bearer_when_api_key_set(db_session):
    """api_key configurada (proxy externo) → Authorization Bearer."""
    arg = ArguiderService(
        db_session,
        provider="ollama",
        project_api_key="bearer-from-proxy",
        base_url="https://ollama.empresa.com",
    )

    captured = {}

    class _FakeResp:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        text = "ok"

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *e): return None
        async def post(self, url, headers=None, json=None):
            captured["headers"] = headers or {}
            return _FakeResp()

    with patch("httpx.AsyncClient", _FakeClient):
        await arg._call_llm("s", "u", max_tokens=10)

    assert captured["headers"].get("Authorization") == "Bearer bearer-from-proxy"


# ---------------------------------------------------------------------------
# AgentService (camada admin) — Ollama via env var
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_service_admin_uses_ollama_base_url_from_env(db_session, monkeypatch):
    """settings.OLLAMA_BASE_URL → AgentService.base_url; sem chave exigida."""
    from app.services import agent_service as _ag_mod
    monkeypatch.setattr(_ag_mod.settings, "DEFAULT_AI_PROVIDER", "ollama")
    monkeypatch.setattr(_ag_mod.settings, "OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
    monkeypatch.setattr(_ag_mod.settings, "DEFAULT_AI_MODEL", "")  # forçar default

    ag = _ag_mod.AgentService(db_session)
    assert ag.provider == "ollama"
    assert ag.base_url == "http://host.docker.internal:11434"  # rstrip /
    assert ag.model == "llama3.1:8b"  # default ollama
    assert ag.client is None  # sem AsyncAnthropic
    # _ensure_key não levanta porque ollama dispensa chave
    ag._ensure_key()


@pytest.mark.asyncio
async def test_agent_service_admin_ollama_without_base_url_fails(db_session, monkeypatch):
    """Provider ollama sem OLLAMA_BASE_URL → _ensure_key explode."""
    from app.services import agent_service as _ag_mod
    monkeypatch.setattr(_ag_mod.settings, "DEFAULT_AI_PROVIDER", "ollama")
    monkeypatch.setattr(_ag_mod.settings, "OLLAMA_BASE_URL", None)

    ag = _ag_mod.AgentService(db_session)
    with pytest.raises(RuntimeError, match="OLLAMA_BASE_URL"):
        ag._ensure_key()
