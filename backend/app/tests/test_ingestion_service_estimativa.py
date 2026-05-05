"""Testes para estimativa dinâmica de tempo OCG (MVP 39)."""
import pytest
from app.services.ingestion_service import _estimate_ocg_updating_time


class TestEstimativaOCGUpdatingTime:
    """Suite de testes para _estimate_ocg_updating_time."""

    def test_estimativa_anthropic_doc_pequeno(self):
        """Anthropic com doc pequeno (~50KB)."""
        min_time, max_time = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=50_000,
            num_personas=12,
        )
        # Anthropic base 35s + 25% size factor (50KB/1024 ≈ 49KB, 49/200 ≈ 0.25) ≈ 43s
        assert isinstance(min_time, int)
        assert isinstance(max_time, int)
        assert 30 < min_time < 60
        assert max_time > min_time
        assert max_time - min_time <= 40  # margem razoável

    def test_estimativa_ollama_qualquer_doc(self):
        """Ollama (local) com doc médio (~200KB)."""
        min_time, max_time = _estimate_ocg_updating_time(
            provider="ollama",
            file_size_bytes=200_000,
            num_personas=12,
        )
        # Ollama base 120s + 100% size factor (200KB/1024 ≈ 195KB, 195/200 ≈ 0.98) ≈ 237s
        assert isinstance(min_time, int)
        assert isinstance(max_time, int)
        assert min_time >= 10  # sempre >= 10s per spec
        assert max_time > min_time
        # Ollama lento, então deve ser substancialmente maior que Anthropic
        assert min_time > 100

    def test_estimativa_provider_none_usa_deepseek_default(self):
        """Quando provider=None, usa DeepSeek como default."""
        min_time, max_time = _estimate_ocg_updating_time(
            provider=None,
            file_size_bytes=100_000,
            num_personas=12,
        )
        # DeepSeek base 50s + 50% size factor (100KB/1024 ≈ 98KB, 98/200 ≈ 0.49) ≈ 74s
        assert isinstance(min_time, int)
        assert isinstance(max_time, int)
        assert 40 < min_time < 90

    def test_estimativa_provider_desconhecido_usa_fallback_50s(self):
        """Provider desconhecido cai para 50s base."""
        min_time, max_time = _estimate_ocg_updating_time(
            provider="unknown_provider_xyz",
            file_size_bytes=100_000,
            num_personas=12,
        )
        # Fallback base 50s + 50% size factor ≈ 75s
        assert isinstance(min_time, int)
        assert isinstance(max_time, int)
        assert 40 < min_time < 90

    def test_estimativa_retorna_tuple_sempre(self):
        """Retorno sempre é (min, max), nunca int."""
        result = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=50_000,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_estimativa_min_maior_igual_10s(self):
        """Min sempre >= 10s mesmo com doc muito pequeno."""
        min_time, max_time = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=1_000,  # 1KB
            num_personas=12,
        )
        assert min_time >= 10
        assert max_time > min_time

    def test_estimativa_case_insensitive_provider(self):
        """Provider case-insensitive: 'ANTHROPIC' == 'anthropic'."""
        min1, max1 = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=100_000,
        )
        min2, max2 = _estimate_ocg_updating_time(
            provider="ANTHROPIC",
            file_size_bytes=100_000,
        )
        assert min1 == min2
        assert max1 == max2

    def test_estimativa_ajusta_por_numero_personas(self):
        """Mais personas = tempo ligeiramente maior."""
        min_12, max_12 = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=100_000,
            num_personas=12,
        )
        min_20, max_20 = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=100_000,
            num_personas=20,  # 8 personas a mais
        )
        # 8 personas acima de 12 = +40% de overhead → (+8 * 0.05)
        # min_12 ≈ 73s → min_20 ≈ 73 * 1.4 ≈ 102s
        assert min_20 > min_12  # deve ser ligeiramente maior

    def test_estimativa_doc_zero_bytes_handled(self):
        """Doc com 0 bytes não quebra (size_kb força minimo 1)."""
        min_time, max_time = _estimate_ocg_updating_time(
            provider="anthropic",
            file_size_bytes=0,
            num_personas=12,
        )
        assert min_time >= 10
        assert max_time > min_time
