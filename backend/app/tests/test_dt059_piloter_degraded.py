"""
DT-059: PiloterService resiliente quando `PILOTER_API_KEY` ausente.

Bug descoberto na auditoria DT-058: a key não está configurada no
ambiente de produção. Antes: `_call_piloter_api` enviava request com
header `Authorization: Bearer None` → 401 → exception propagava →
`code_generation_service.generate_project_code` crashava.

Bug auxiliar consertado em paralelo: `code_generation_service:214`
chamava `get_stack_recommendations(language, architecture)` sem
`project_id` (TypeError silencioso porque os testes mockavam o método).

Fix: detecção de key ausente no topo de `get_stack_recommendations`,
retorno degradado com `degraded=True` e `degraded_reason`. Caller
continua com stack vazio — LLM ainda gera código baseado em
PROJECT_PROFILE do OCG, só sem recomendações específicas do Piloter.
"""
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.piloter_service import PiloterService


@pytest.mark.asyncio
async def test_piloter_returns_degraded_when_no_api_key(db_session: AsyncSession):
    """Sem `PILOTER_API_KEY`, retorna stack vazio + flag degraded em vez
    de levantar exception. Code path real do scaffold continua.
    """
    svc = PiloterService(db_session)
    svc.api_key = None  # simula PILOTER_API_KEY=None

    result = await svc.get_stack_recommendations(
        project_id=uuid4(),
        language="java",
        architecture="microservices",
        use_cache=False,
    )

    assert result["stack"] is None
    assert result["recommendations"] == []
    assert result["alternatives"] == []
    assert result["cached"] is False
    assert result["degraded"] is True
    assert "PILOTER_API_KEY" in result["degraded_reason"]


@pytest.mark.asyncio
async def test_piloter_degraded_works_for_any_language(db_session: AsyncSession):
    """Degradação não discrimina por linguagem — Java, Go, Python, etc."""
    svc = PiloterService(db_session)
    svc.api_key = ""  # string vazia também é "ausente"

    for lang in ["python", "java", "go", "csharp", "kotlin", "php"]:
        result = await svc.get_stack_recommendations(
            project_id=uuid4(),
            language=lang,
            architecture="microservices",
            use_cache=False,
        )
        assert result["degraded"] is True, f"Falhou para {lang}"
        assert result["stack"] is None


@pytest.mark.asyncio
async def test_piloter_degraded_does_not_crash_caller_pattern(db_session: AsyncSession):
    """Reproduz o padrão de uso do code_generation_service: chama, lê
    `recommendations`/`alternatives`/`stack` — não pode crashar.
    """
    svc = PiloterService(db_session)
    svc.api_key = None

    result = await svc.get_stack_recommendations(
        project_id=uuid4(),
        language="java",
        architecture="microservices",
    )

    # Padrão do caller — todos esses acessos devem funcionar
    _ = result.get("stack")
    _ = result.get("recommendations", [])
    _ = result.get("alternatives", [])
    _ = result.get("cached", False)
    # Nenhum AttributeError nem KeyError


@pytest.mark.asyncio
async def test_piloter_with_api_key_does_not_short_circuit(db_session: AsyncSession):
    """Com key configurada, segue caminho normal (chama _call_piloter_api).
    Mock do _call_piloter_api isola o teste de chamadas externas reais."""
    svc = PiloterService(db_session)
    svc.api_key = "fake-key-for-test"

    fake_stack = {"recommendations": [{"name": "Spring Boot"}], "alternatives": []}
    with patch.object(svc, "_call_piloter_api", return_value=fake_stack), \
         patch.object(svc, "_check_quota", return_value=True), \
         patch.object(svc, "_save_to_cache", return_value=None), \
         patch.object(svc, "_log_api_call", return_value=None):
        result = await svc.get_stack_recommendations(
            project_id=uuid4(),
            language="java",
            architecture="microservices",
            use_cache=False,
        )

    # Não foi degradado — chamou a API "real" (mockada)
    assert result.get("degraded") is not True
    assert result["recommendations"] == [{"name": "Spring Boot"}]
