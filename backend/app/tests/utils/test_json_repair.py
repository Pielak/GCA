"""Testes para app.utils.json_repair — provider-agnostic JSON hardening."""
import pytest
from app.utils.json_repair import (
    normalize_llm_json,
    repair_llm_json,
    safe_parse_llm_json,
)


# ============================================================================
# normalize_llm_json
# ============================================================================
class TestNormalizeJson:
    def test_passes_dict_through(self):
        data = {"scores": {"escopo": 80}, "summary": "ok"}
        result = normalize_llm_json(data)
        assert result["scores"] == {"escopo": 80}
        assert result["summary"] == "ok"

    def test_string_dict_key_becomes_empty_dict(self):
        data = {"scores": "", "summary": "teste"}
        result = normalize_llm_json(data)
        assert result["scores"] == {}

    def test_string_list_key_becomes_empty_list(self):
        data = {"issues": "", "risks": "[]"}
        result = normalize_llm_json(data)
        assert result["issues"] == []
        assert result["risks"] == []

    def test_nested_dict_recursion(self):
        data = {"audit_findings": {"scores": ""}}
        result = normalize_llm_json(data)
        assert result["audit_findings"]["scores"] == {}

    def test_non_dict_input_returns_empty_dict(self):
        assert normalize_llm_json("string literal") == {}
        assert normalize_llm_json(None) == {}
        assert normalize_llm_json(42) == {}
        assert normalize_llm_json([1, 2, 3]) == {}

    def test_list_recursion_normalizes_dict_items(self):
        data = {"issues": [{"description": "ok"}, {"description": ""}]}
        result = normalize_llm_json(data)
        assert result["issues"][0] == {"description": "ok"}
        assert result["issues"][1] == {"description": ""}

    def test_mixed_list_with_strings_and_dicts(self):
        data = {"items": ["string", {"nested": ""}, 42]}
        result = normalize_llm_json(data)
        assert result["items"] == ["string", {"nested": ""}, 42]


# ============================================================================
# repair_llm_json
# ============================================================================
class TestRepairJson:
    def test_valid_json_returns_directly(self):
        result = repair_llm_json('{"chave": "valor"}')
        assert result.parsed == {"chave": "valor"}
        assert result.repaired is False
        assert result.strategies_used == []

    def test_json_in_markdown_fence(self):
        text = '```json\n{"ok": true}\n```'
        result = repair_llm_json(text)
        assert result.parsed == {"ok": True}
        assert result.repaired is True
        assert "strip_fence" in result.strategies_used

    def test_trailing_comma_removed(self):
        text = '{"items": [1, 2,], "meta": {"a": 1,},}'
        result = repair_llm_json(text)
        assert result.parsed == {"items": [1, 2], "meta": {"a": 1}}
        assert result.repaired is True
        assert "remove_trailing_commas" in result.strategies_used

    def test_truncated_json_closed(self):
        text = '{"summary": "teste", "chunk_tags": {"chunk_001": ["GP"'
        result = repair_llm_json(text)
        assert result.truncation_detected is True
        assert "close_truncation" in result.strategies_used
        assert "summary" in result.parsed
        assert result.parsed["summary"] == "teste"

    def test_json_extracted_from_surrounding_text(self):
        text = 'Aqui vai uma analise: {"status": "ok"} e mais texto depois.'
        result = repair_llm_json(text)
        assert result.parsed == {"status": "ok"}
        assert "extract_balanced" in result.strategies_used

    def test_empty_string_returns_empty_dict(self):
        result = repair_llm_json("")
        assert result.parsed == {}
        assert result.error_preview is not None

    def test_non_json_text_returns_empty_dict(self):
        result = repair_llm_json("apenas um texto qualquer sem json")
        assert result.parsed == {}

    def test_number_json_returns_empty(self):
        """json.loads(42) succeeds mas não é dict — repair deve retornar {}"""
        result = repair_llm_json("42")
        assert result.parsed == {}

    def test_array_json_returns_empty(self):
        """json.loads([1,2,3]) não é dict"""
        result = repair_llm_json("[1, 2, 3]")
        assert result.parsed == {}


# ============================================================================
# safe_parse_llm_json
# ============================================================================
class TestSafeParseJson:
    def test_valid_dict_level_0(self):
        data, meta = safe_parse_llm_json('{"ok": true}')
        assert data == {"ok": True}
        assert meta.level == 0
        assert meta.total_failure is False

    def test_string_literal_level_1(self):
        """LLM retorna JSON string literal — normalize_llm_json converte pra {}"""
        data, meta = safe_parse_llm_json('"apenas uma string"')
        assert data == {}
        assert meta.level == 1
        assert meta.total_failure is False

    def test_json_in_fence_level_2(self):
        text = '```json\n{"status": "ok"}\n```'
        data, meta = safe_parse_llm_json(text)
        assert data == {"status": "ok"}
        assert meta.level == 2

    def test_truncated_json_level_2(self):
        text = '{"field": "value", "array": [1, 2, 3'
        data, meta = safe_parse_llm_json(text)
        assert data == {"field": "value", "array": [1, 2, 3]}
        assert meta.level == 2
        assert "truncamento detectado" in str(meta.warnings).lower() or any(
            "truncamento" in w for w in meta.warnings
        )

    def test_extraction_from_text_level_3(self):
        text = 'explicacao antes {"key": "value"} texto depois'
        data, meta = safe_parse_llm_json(text)
        assert data == {"key": "value"}
        assert meta.level in (2, 3)

    def test_total_failure_level_4(self):
        data, meta = safe_parse_llm_json("")
        assert data == {}
        assert meta.level == 4
        assert meta.total_failure is True

    def test_garbage_text_level_4(self):
        data, meta = safe_parse_llm_json("isso nao eh json de jeito nenhum!!!")
        assert data == {}
        assert meta.total_failure is True

    def test_never_raises(self):
        """safe_parse_llm_json nunca deve levantar exceção."""
        for garbage in [None, 42, [], b"bytes", "\x00\x01\x02"]:
            try:
                data, meta = safe_parse_llm_json(str(garbage))
                assert isinstance(data, dict)
                assert isinstance(meta.level, int)
            except Exception as e:
                pytest.fail(f"safe_parse_llm_json raised {type(e).__name__} for {garbage!r}")
