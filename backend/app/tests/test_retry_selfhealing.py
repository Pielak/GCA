"""Testa que gca_retry executa retentativas corretamente."""
import pytest
from app.utils.retry import gca_retry


@pytest.mark.asyncio
async def test_retry_executa_max_vezes_em_falha_total():
    """Deve tentar MAX_RETRIES vezes e relançar a exceção."""
    call_count = 0

    @gca_retry()
    async def falha_sempre():
        nonlocal call_count
        call_count += 1
        raise ValueError("Falha simulada")

    with pytest.raises(ValueError):
        await falha_sempre()

    assert call_count == 3  # MAX_RETRIES padrão


@pytest.mark.asyncio
async def test_retry_sucede_na_segunda_tentativa():
    """Deve retornar resultado correto após 1 falha."""
    call_count = 0

    @gca_retry()
    async def falha_primeira_vez():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Timeout simulado")
        return "ok"

    result = await falha_primeira_vez()
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_sucesso_imediato_nao_retenta():
    """Serviço que não falha não deve ter overhead de retry."""
    call_count = 0

    @gca_retry()
    async def sucesso_direto():
        nonlocal call_count
        call_count += 1
        return "sucesso"

    result = await sucesso_direto()
    assert result == "sucesso"
    assert call_count == 1
