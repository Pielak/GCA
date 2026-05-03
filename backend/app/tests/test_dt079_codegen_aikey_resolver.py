"""DT-079 — Hardcode Anthropic em CodeGen substituído por AIKeyResolver.

Antes: 8 pontos em `module_codegen_service.py` + `code_generation.py`
instanciavam `AsyncAnthropic` direto e liam `settings.ANTHROPIC_API_KEY` /
`settings.ANTHROPIC_MODEL`. Violava §3.1 (porta única `AIKeyResolver`).

Depois: novo helper `app/services/codegen_llm.py` (`call_codegen_llm`)
delega a `AIKeyResolver` + `llm_low_criticality.call_llm`. Provider/modelo
vêm de `project_settings.setting_type='llm'` por projeto.

Cobre:
  - Guards estáticos: nenhum dos 2 arquivos importa `AsyncAnthropic` ou
    referencia `ANTHROPIC_API_KEY` para resolver provider.
  - call_codegen_llm levanta 503 quando projeto não tem provider.
  - call_codegen_llm chama call_llm com config resolvido (mock).
  - resolve_codegen_provider_meta retorna {provider, model} ou None.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_dt079_codegen_aikey_resolver.py -v"
"""
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.codegen_llm import call_codegen_llm, resolve_codegen_provider_meta


# =============================================================================
# Guards estáticos — DT-079 não pode regredir
# =============================================================================

_BACKEND = Path(__file__).parent.parent
_MODULE_CODEGEN = _BACKEND / "services" / "module_codegen_service.py"
_CODE_GENERATION = _BACKEND / "routers" / "code_generation.py"


def test_module_codegen_no_async_anthropic_import():
    """module_codegen_service.py NÃO importa AsyncAnthropic direto."""
    src = _MODULE_CODEGEN.read_text(encoding="utf-8")
    assert "from anthropic import AsyncAnthropic" not in src, (
        "module_codegen_service.py voltou a importar AsyncAnthropic — viola §3.1"
    )
    assert "AsyncAnthropic(" not in src, (
        "module_codegen_service.py voltou a instanciar AsyncAnthropic — viola §3.1"
    )


def test_module_codegen_no_anthropic_api_key_for_provider():
    """module_codegen_service.py NÃO usa settings.ANTHROPIC_API_KEY para resolver provider."""
    src = _MODULE_CODEGEN.read_text(encoding="utf-8")
    assert "settings.ANTHROPIC_API_KEY" not in src, (
        "module_codegen_service.py voltou a usar settings.ANTHROPIC_API_KEY — viola §3.1"
    )


def test_code_generation_no_async_anthropic_import():
    """code_generation.py NÃO importa AsyncAnthropic direto."""
    src = _CODE_GENERATION.read_text(encoding="utf-8")
    assert "from anthropic import AsyncAnthropic" not in src, (
        "code_generation.py voltou a importar AsyncAnthropic — viola §3.1"
    )
    assert "AsyncAnthropic(" not in src, (
        "code_generation.py voltou a instanciar AsyncAnthropic — viola §3.1"
    )


def test_code_generation_no_anthropic_api_key_for_provider():
    """code_generation.py NÃO usa app_settings.ANTHROPIC_API_KEY para resolver provider.

    Aceita app_settings.ANTHROPIC_MAX_TOKENS (constante numérica de budget,
    não viola §3.1 que é sobre porta única de PROVIDER).
    """
    src = _CODE_GENERATION.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in src, (
        "code_generation.py voltou a usar ANTHROPIC_API_KEY — viola §3.1"
    )


def test_module_codegen_uses_call_codegen_llm():
    """module_codegen_service.py importa call_codegen_llm da porta única."""
    src = _MODULE_CODEGEN.read_text(encoding="utf-8")
    assert "from app.services.codegen_llm import" in src, (
        "module_codegen_service.py não importa porta única codegen_llm — DT-079 incompleta"
    )


def test_code_generation_uses_call_codegen_llm():
    """code_generation.py importa call_codegen_llm da porta única."""
    src = _CODE_GENERATION.read_text(encoding="utf-8")
    assert "from app.services.codegen_llm import call_codegen_llm" in src, (
        "code_generation.py não importa call_codegen_llm — DT-079 incompleta"
    )


# =============================================================================
# call_codegen_llm — comportamento
# =============================================================================


@pytest.mark.asyncio
async def test_call_codegen_llm_raises_503_when_no_provider():
    """Sem provider configurado para o projeto → HTTPException 503."""
    project_id = uuid4()
    db_mock = AsyncMock()

    with patch(
        "app.services.codegen_llm.resolve_llm_config",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await call_codegen_llm(
                db=db_mock,
                project_id=project_id,
                user_prompt="prompt",
            )

    assert exc.value.status_code == 503
    assert "configurado" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_call_codegen_llm_delegates_to_call_llm_with_resolved_config():
    """Quando provider resolvido, delega para call_llm com config correto."""
    project_id = uuid4()
    db_mock = AsyncMock()
    resolved_config = {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "sk-test",
        "base_url": None,
    }

    with patch(
        "app.services.codegen_llm.resolve_llm_config",
        new=AsyncMock(return_value=resolved_config),
    ), patch(
        "app.services.codegen_llm.call_llm",
        new=AsyncMock(return_value="resposta do llm"),
    ) as mock_call_llm, patch(
        "app.services.codegen_llm.clamp_max_tokens",
        return_value=8192,
    ):
        result = await call_codegen_llm(
            db=db_mock,
            project_id=project_id,
            user_prompt="prompt teste",
            max_tokens=4096,
            temperature=0.3,
        )

    assert result == "resposta do llm"
    mock_call_llm.assert_awaited_once()
    kwargs = mock_call_llm.await_args.kwargs
    assert kwargs["config"] == resolved_config
    assert kwargs["user_prompt"] == "prompt teste"
    assert kwargs["max_tokens"] == 8192  # clamped
    assert kwargs["temperature"] == 0.3


@pytest.mark.asyncio
async def test_call_codegen_llm_uses_prefer_ollama_false():
    """resolve_llm_config deve ser chamado com prefer_ollama=False (CodeGen é alta criticidade)."""
    project_id = uuid4()
    db_mock = AsyncMock()
    resolved_config = {
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "api_key": "sk-ant",
        "base_url": None,
    }

    with patch(
        "app.services.codegen_llm.resolve_llm_config",
        new=AsyncMock(return_value=resolved_config),
    ) as mock_resolve, patch(
        "app.services.codegen_llm.call_llm",
        new=AsyncMock(return_value="ok"),
    ), patch(
        "app.services.codegen_llm.clamp_max_tokens",
        return_value=4096,
    ):
        await call_codegen_llm(
            db=db_mock,
            project_id=project_id,
            user_prompt="x",
        )

    # Verifica que prefer_ollama=False foi passado
    mock_resolve.assert_awaited_once()
    kwargs = mock_resolve.await_args.kwargs
    assert kwargs.get("prefer_ollama") is False, (
        "CodeGen deve usar prefer_ollama=False — alta criticidade respeita "
        "escolha do owner, não cai em Ollama silenciosamente"
    )


# =============================================================================
# resolve_codegen_provider_meta — comportamento
# =============================================================================


@pytest.mark.asyncio
async def test_resolve_codegen_provider_meta_returns_dict_when_resolved():
    """Quando provider resolvido, retorna {provider, model}."""
    project_id = uuid4()
    db_mock = AsyncMock()

    with patch(
        "app.services.codegen_llm.resolve_llm_config",
        new=AsyncMock(return_value={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "x",
            "base_url": None,
        }),
    ):
        result = await resolve_codegen_provider_meta(db_mock, project_id)

    assert result == {"provider": "deepseek", "model": "deepseek-chat"}


@pytest.mark.asyncio
async def test_resolve_codegen_provider_meta_returns_none_when_unconfigured():
    """Quando nenhum provider configurado, retorna None (sem raise)."""
    project_id = uuid4()
    db_mock = AsyncMock()

    with patch(
        "app.services.codegen_llm.resolve_llm_config",
        new=AsyncMock(return_value=None),
    ):
        result = await resolve_codegen_provider_meta(db_mock, project_id)

    assert result is None
