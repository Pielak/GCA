"""
DT-049: visibilidade + retry quando LLM devolve resposta não-JSON.

Antes: `_extract_json` retornava `{}` silenciosamente e o consolidator
gastava $0,59 sem avisar. Todos os campos do OCG caíam em fallback sem
ninguém saber que o LLM tinha quebrado o contrato de output.

Depois: `_extract_json` cobre markdown fence + JSON embebido em prosa +
trailing commas; `_call_llm_expecting_json` faz 1 retry com diretiva
dura pedindo JSON puro antes de desistir.
"""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_service import AgentService


# ---------------------------------------------------------------------------
# _extract_json — parsing progressivo
# ---------------------------------------------------------------------------

def test_extract_json_direct_parse():
    assert AgentService._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_markdown_fence_with_lang():
    text = '```json\n{"status": "ok", "score": 80}\n```'
    assert AgentService._extract_json(text) == {"status": "ok", "score": 80}


def test_extract_json_markdown_fence_without_lang():
    text = '```\n{"status": "ok"}\n```'
    assert AgentService._extract_json(text) == {"status": "ok"}


def test_extract_json_embedded_in_prose():
    """LLM comum: explica antes, retorna JSON, despede-se depois."""
    text = (
        "Aqui está o resultado da análise:\n"
        '{"pillar": 7, "score": 85}\n'
        "Espero que seja útil!"
    )
    assert AgentService._extract_json(text) == {"pillar": 7, "score": 85}


def test_extract_json_trailing_comma_cleanup():
    """LLM às vezes adiciona vírgula final inválida."""
    text = '{"a": 1, "b": [1, 2, 3,]}'
    result = AgentService._extract_json(text)
    assert result == {"a": 1, "b": [1, 2, 3]}


def test_extract_json_returns_empty_on_total_garbage():
    result = AgentService._extract_json("isso não é JSON, só prosa.")
    assert result == {}


def test_extract_json_empty_string():
    assert AgentService._extract_json("") == {}


def test_extract_json_none_safe():
    assert AgentService._extract_json(None) == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _call_llm_expecting_json — retry com diretiva JSON-puro
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_llm_expecting_json_succeeds_first_try(db_session: AsyncSession):
    """Caso feliz: LLM retorna JSON válido na primeira chamada; sem retry."""
    svc = AgentService(db_session)

    call_count = {"n": 0}

    async def _fake(self, system_prompt, user_prompt, max_tokens=4096, project_id=None, operation="x"):
        call_count["n"] += 1
        return json.dumps({"pillar": 1, "score": 80}), 500

    # Substitui _call_llm diretamente na instância
    svc._call_llm = _fake.__get__(svc, AgentService)

    result, tokens = await svc._call_llm_expecting_json(
        system_prompt="test", user_prompt="test", max_tokens=100, operation="test_happy"
    )
    assert result == {"pillar": 1, "score": 80}
    assert tokens == 500
    assert call_count["n"] == 1  # Sem retry


@pytest.mark.asyncio
async def test_call_llm_expecting_json_retries_on_invalid_json(db_session: AsyncSession):
    """LLM devolve prosa na 1ª; retry com diretiva retorna JSON."""
    svc = AgentService(db_session)

    call_count = {"n": 0}

    async def _fake(self, system_prompt, user_prompt, max_tokens=4096, project_id=None, operation="x"):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "Claro! Aqui vai a análise explicada:\nConsiderei os 7 pilares...", 800
        # Segunda chamada: diretiva dura foi apendada ao system_prompt
        assert "APENAS com JSON puro" in system_prompt
        return json.dumps({"rescued": True, "score": 70}), 600

    svc._call_llm = _fake.__get__(svc, AgentService)

    result, tokens = await svc._call_llm_expecting_json(
        system_prompt="original system", user_prompt="u", max_tokens=100, operation="test_retry"
    )
    assert result == {"rescued": True, "score": 70}
    assert tokens == 800 + 600  # Soma das 2 chamadas
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_call_llm_expecting_json_gives_up_after_retry(db_session: AsyncSession):
    """Ambas as tentativas falham — retorna dict vazio + tokens gastos."""
    svc = AgentService(db_session)

    call_count = {"n": 0}

    async def _fake(self, system_prompt, user_prompt, max_tokens=4096, project_id=None, operation="x"):
        call_count["n"] += 1
        return "Só prosa, sem JSON.", 400

    svc._call_llm = _fake.__get__(svc, AgentService)

    result, tokens = await svc._call_llm_expecting_json(
        system_prompt="s", user_prompt="u", max_tokens=100, operation="test_fail"
    )
    assert result == {}
    assert tokens == 800  # 2 chamadas × 400
    assert call_count["n"] == 2  # Não tenta 3x


@pytest.mark.asyncio
async def test_call_llm_expecting_json_skips_retry_on_empty_response(db_session: AsyncSession):
    """Se LLM devolve string vazia, não retentativa (provavelmente erro transportado)."""
    svc = AgentService(db_session)

    call_count = {"n": 0}

    async def _fake(self, system_prompt, user_prompt, max_tokens=4096, project_id=None, operation="x"):
        call_count["n"] += 1
        return "", 0

    svc._call_llm = _fake.__get__(svc, AgentService)

    result, tokens = await svc._call_llm_expecting_json(
        system_prompt="s", user_prompt="u", max_tokens=100, operation="test_empty"
    )
    assert result == {}
    assert tokens == 0
    assert call_count["n"] == 1  # Sem retry
