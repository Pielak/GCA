"""DT-064 — Fallback automático entre providers IA.

Lógica ampla (user feedback 2026-04-19): fallback acionado em QUALQUER
falha de conexão com provider premium — rate limit, quota, 5xx, timeout,
conn refused, EOF, SSL, 401 (chave inválida do primário), etc. Só NÃO
faz fallback quando é erro específico de parâmetro/prompt (invalid
model, schema validation) que outro provider também não resolveria.
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.services.ai_key_resolver import AIKeyResolver
from app.tests.factories import create_test_organization, create_test_project


# ─── should_fallback_to_next_provider ────────────────────────────────────

def test_fallback_on_rate_limit():
    assert AIKeyResolver.should_fallback_to_next_provider("429 Too Many Requests")
    assert AIKeyResolver.should_fallback_to_next_provider("rate limit exceeded")


def test_fallback_on_quota_exhausted():
    assert AIKeyResolver.should_fallback_to_next_provider(
        "LLM API error (429): insufficient_quota"
    )


def test_fallback_on_5xx():
    assert AIKeyResolver.should_fallback_to_next_provider("503 Service Unavailable")
    assert AIKeyResolver.should_fallback_to_next_provider("502 Bad Gateway")
    assert AIKeyResolver.should_fallback_to_next_provider("504 Gateway Timeout")


def test_fallback_on_timeout_and_overloaded():
    assert AIKeyResolver.should_fallback_to_next_provider("request timed out after 30s")
    assert AIKeyResolver.should_fallback_to_next_provider("timeout")
    assert AIKeyResolver.should_fallback_to_next_provider("Anthropic API is overloaded")


def test_fallback_on_network_error():
    """Lógica ampla: qualquer falha de rede cai no fallback."""
    assert AIKeyResolver.should_fallback_to_next_provider("Connection refused")
    assert AIKeyResolver.should_fallback_to_next_provider("DNS resolution failed")
    assert AIKeyResolver.should_fallback_to_next_provider("SSL handshake failed")
    assert AIKeyResolver.should_fallback_to_next_provider("EOF while reading response")


def test_fallback_on_auth_error():
    """401/403 CAEM no fallback — outros providers têm chaves
    independentes; podem funcionar. Se todos falharem com 401, o loop
    esgota e o erro final sobe pro user."""
    assert AIKeyResolver.should_fallback_to_next_provider("401 Unauthorized")
    assert AIKeyResolver.should_fallback_to_next_provider("403 Forbidden")
    assert AIKeyResolver.should_fallback_to_next_provider("invalid api key")


def test_no_fallback_on_invalid_model():
    """Erro de parâmetro do prompt/modelo NÃO aciona fallback — outros
    providers também não vão entender a requisição mal formada."""
    assert not AIKeyResolver.should_fallback_to_next_provider(
        "invalid model parameter"
    )
    assert not AIKeyResolver.should_fallback_to_next_provider(
        "model not found in catalog"
    )
    assert not AIKeyResolver.should_fallback_to_next_provider(
        "schema validation failed"
    )
    assert not AIKeyResolver.should_fallback_to_next_provider(
        "malformed request body"
    )


def test_no_fallback_on_empty():
    assert not AIKeyResolver.should_fallback_to_next_provider("")
    assert not AIKeyResolver.should_fallback_to_next_provider(None)


def test_is_transient_alias_still_works():
    """is_transient_ai_error mantido como alias de should_fallback."""
    assert AIKeyResolver.is_transient_ai_error("429 rate limit")
    assert not AIKeyResolver.is_transient_ai_error("invalid model")


# ─── resolve_project_provider_chain ───────────────────────────────────────

async def _set_llm_settings(db, project_id, settings_dict):
    """Helper — grava project_settings(setting_type='llm') via SQL direto."""
    await db.execute(
        text(
            "INSERT INTO project_settings (id, project_id, setting_type, settings_json, created_at, updated_at) "
            "VALUES (:id, :pid, 'llm', :json, now(), now()) "
            "ON CONFLICT (project_id, setting_type) DO UPDATE SET settings_json=:json, updated_at=now()"
        ),
        {
            "id": str(uuid4()),
            "pid": str(project_id),
            "json": json.dumps(settings_dict),
        },
    )
    await db.commit()


@pytest.mark.asyncio
async def test_chain_empty_when_no_settings(db_session):
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt064-empty")
    chain = await AIKeyResolver.resolve_project_provider_chain(db_session, p.id)
    assert chain == []


@pytest.mark.asyncio
async def test_chain_default_first(db_session):
    """Default provider deve ser o primeiro da cadeia."""
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt064-default")
    await _set_llm_settings(db_session, p.id, {
        "providers": [
            {"provider": "openai", "is_default": False, "last_validation_ok": True,
             "last_validated_at": "2026-04-18T01:00:00Z"},
            {"provider": "ollama", "is_default": True, "last_validation_ok": True,
             "last_validated_at": "2026-04-18T02:00:00Z", "base_url": "http://ollama:11434",
             "model": "qwen2.5-coder:7b"},
            {"provider": "anthropic", "is_default": False, "last_validation_ok": True,
             "last_validated_at": "2026-04-18T03:00:00Z"},
        ],
        "default_provider": "ollama",
    })
    chain = await AIKeyResolver.resolve_project_provider_chain(db_session, p.id)
    assert len(chain) == 3
    assert chain[0]["provider"] == "ollama"
    assert chain[0]["base_url"] == "http://ollama:11434"
    assert chain[0]["model"] == "qwen2.5-coder:7b"
    # Os demais vêm depois, com validação OK ordenada por data desc
    provider_order = [c["provider"] for c in chain]
    assert provider_order[0] == "ollama"
    assert "openai" in provider_order[1:]
    assert "anthropic" in provider_order[1:]


@pytest.mark.asyncio
async def test_chain_invalidated_last(db_session):
    """Providers com last_validation_ok=False vão pro fim da cadeia."""
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt064-invalid")
    await _set_llm_settings(db_session, p.id, {
        "providers": [
            {"provider": "openai", "is_default": True, "last_validation_ok": True,
             "last_validated_at": "2026-04-18T01:00:00Z"},
            {"provider": "anthropic", "is_default": False, "last_validation_ok": False,
             "last_validated_at": "2026-04-15T00:00:00Z"},
            {"provider": "ollama", "is_default": False, "last_validation_ok": True,
             "last_validated_at": "2026-04-18T02:00:00Z", "base_url": "http://ollama:11434"},
        ],
        "default_provider": "openai",
    })
    chain = await AIKeyResolver.resolve_project_provider_chain(db_session, p.id)
    assert chain[0]["provider"] == "openai"
    # anthropic (inválido) deve estar por último
    last = chain[-1]
    assert last["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_chain_legacy_single_provider(db_session):
    """Formato antigo {provider: ..., model_preference: ...} ainda funciona."""
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt064-legacy")
    await _set_llm_settings(db_session, p.id, {
        "provider": "anthropic",
        "model_preference": "claude-haiku-4-5-20251001",
    })
    chain = await AIKeyResolver.resolve_project_provider_chain(db_session, p.id)
    assert len(chain) == 1
    assert chain[0]["provider"] == "anthropic"
    assert chain[0]["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_chain_providers_list_empty(db_session):
    """Lista vazia de providers retorna []."""
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="dt064-emptylist")
    await _set_llm_settings(db_session, p.id, {"providers": [], "default_provider": None})
    chain = await AIKeyResolver.resolve_project_provider_chain(db_session, p.id)
    assert chain == []
