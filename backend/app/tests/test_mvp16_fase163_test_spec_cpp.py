"""MVP 16 Fase 16.3 — test_spec_generator é C++-aware (GoogleTest idioms).

Valida:
- `_detect_test_framework(stack)` retorna `"googletest"` quando
  `backend.language` é C++/cpp/cplusplus; `None` caso contrário.
- `_build_prompt` anexa o bloco `CPP_GOOGLETEST_GUIDANCE` ao final do
  prompt quando o backend é C++.
- `_build_provenance` inclui `test_framework: "googletest"` no JSON de
  provenance quando C++; omite a chave nas demais linguagens.
- Zero regressão em specs de unit/integration/e2e para linguagens
  não-C++ (prompt inalterado, sem `TEST(`).
"""
import json
from unittest.mock import MagicMock

from app.models.base import ModuleCandidate
from app.services.test_spec_generator_service import (
    CPP_GOOGLETEST_GUIDANCE,
    _build_prompt,
    _build_provenance,
    _detect_test_framework,
)


# ===========================================================================
# _detect_test_framework
# ===========================================================================

def test_detect_googletest_for_cpp():
    assert _detect_test_framework({"backend": {"language": "C++"}}) == "googletest"


def test_detect_googletest_for_cpp_lowercase():
    assert _detect_test_framework({"backend": {"language": "c++"}}) == "googletest"


def test_detect_googletest_for_cpp_aliases():
    assert _detect_test_framework({"backend": {"language": "cpp"}}) == "googletest"
    assert _detect_test_framework({"backend": {"language": "cplusplus"}}) == "googletest"


def test_detect_none_for_other_languages():
    for lang in ("Java", "Python", "Go", "Node.js", "PHP", "C#", "Kotlin", "Rust"):
        assert _detect_test_framework({"backend": {"language": lang}}) is None, (
            f"Regressão: {lang} virou googletest inesperadamente"
        )


def test_detect_none_when_backend_missing():
    assert _detect_test_framework({}) is None
    assert _detect_test_framework({"backend": None}) is None
    assert _detect_test_framework({"backend": {}}) is None


def test_detect_none_when_language_not_string():
    # LLM pode emitir language como int/list/null — guard-rail.
    assert _detect_test_framework({"backend": {"language": None}}) is None
    assert _detect_test_framework({"backend": {"language": 17}}) is None
    assert _detect_test_framework({"backend": {"language": ["C++"]}}) is None


# ===========================================================================
# _build_prompt — apêndice GoogleTest
# ===========================================================================

def _mock_module():
    m = MagicMock(spec=ModuleCandidate)
    m.name = "DomainService"
    m.module_type = "backend_service"
    m.description = "core do módulo"
    m.dependencies_inferred = None
    return m


def _ocg_ctx_cpp():
    return {
        "version": 1,
        "questionnaire_id": None,
        "ingested_doc_ids": [],
        "data": {
            "STACK_RECOMMENDATION": {
                "backend": {"language": "C++", "enabled": True, "framework": "—"},
            }
        },
    }


def _ocg_ctx_java():
    return {
        "version": 1,
        "questionnaire_id": None,
        "ingested_doc_ids": [],
        "data": {
            "STACK_RECOMMENDATION": {
                "backend": {"language": "Java", "enabled": True, "framework": "Spring"},
            }
        },
    }


def test_prompt_unit_cpp_inclui_googletest_guidance():
    prompt = _build_prompt(
        spec_type="unit", module=_mock_module(), details={},
        ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
    )
    assert "## Convenção C++ / GoogleTest (obrigatória)" in prompt
    assert "TEST(SuiteName, TestName)" in prompt
    assert "TEST_F(FixtureClass" in prompt
    assert "EXPECT_EQ" in prompt
    assert "GTEST_SKIP()" in prompt
    assert "gtest_discover_tests" in prompt


def test_prompt_integration_cpp_inclui_googletest_guidance():
    prompt = _build_prompt(
        spec_type="integration", module=_mock_module(), details={},
        ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
    )
    assert CPP_GOOGLETEST_GUIDANCE.strip() in prompt


def test_prompt_e2e_cpp_inclui_googletest_guidance():
    prompt = _build_prompt(
        spec_type="e2e", module=_mock_module(), details={},
        ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
    )
    assert "GoogleTest" in prompt


def test_prompt_cpp_guidance_comes_at_the_end():
    """Apêndice deve vir após todas as seções canônicas do template,
    não interromper a estrutura markdown original."""
    prompt = _build_prompt(
        spec_type="unit", module=_mock_module(), details={},
        ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
    )
    cpp_idx = prompt.find("## Convenção C++ / GoogleTest")
    obj_idx = prompt.find("## Objetivo")
    casos_idx = prompt.find("## Casos de teste")
    assert obj_idx < cpp_idx
    assert casos_idx < cpp_idx


# ===========================================================================
# _build_prompt — non-C++ deve ser inalterado (regressão)
# ===========================================================================

def test_prompt_java_nao_inclui_googletest_guidance():
    prompt = _build_prompt(
        spec_type="unit", module=_mock_module(), details={},
        ocg_ctx=_ocg_ctx_java(), neighbors=[],
    )
    assert "GoogleTest" not in prompt
    assert "TEST(SuiteName" not in prompt
    assert "EXPECT_EQ" not in prompt


def test_prompt_sem_stack_nao_inclui_googletest_guidance():
    """Projeto novo sem OCG.STACK — prompt deve permanecer no formato
    livre (default pre-16.3)."""
    ctx = {"version": 1, "questionnaire_id": None, "ingested_doc_ids": [], "data": {}}
    prompt = _build_prompt(
        spec_type="unit", module=_mock_module(), details={},
        ocg_ctx=ctx, neighbors=[],
    )
    assert "GoogleTest" not in prompt


# ===========================================================================
# _build_provenance — test_framework
# ===========================================================================

def _config_stub():
    return {"model": "qwen2.5-coder:7b", "base_url": "http://localhost:11434"}


def test_provenance_inclui_test_framework_quando_cpp():
    module = _mock_module()
    module.id = "00000000-0000-0000-0000-000000000001"
    prov = _build_provenance(
        module=module, ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
        prompt="any", config=_config_stub(),
    )
    assert prov.get("test_framework") == "googletest"


def test_provenance_omite_test_framework_para_java():
    module = _mock_module()
    module.id = "00000000-0000-0000-0000-000000000002"
    prov = _build_provenance(
        module=module, ocg_ctx=_ocg_ctx_java(), neighbors=[],
        prompt="any", config=_config_stub(),
    )
    assert "test_framework" not in prov


def test_provenance_inclui_campos_canonicos_prev_165():
    """Guard-rail: chaves pré-16.3 continuam todas presentes."""
    module = _mock_module()
    module.id = "00000000-0000-0000-0000-000000000003"
    prov = _build_provenance(
        module=module, ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
        prompt="any", config=_config_stub(),
    )
    required = {
        "ocg_version", "questionnaire_id", "ingested_doc_ids",
        "module_snapshot", "neighbors_considered", "llm",
        "prompt_hash", "generated_at",
    }
    assert required.issubset(prov.keys())
    # llm sub-chaves preservadas
    assert set(prov["llm"].keys()) == {"provider", "model", "base_url_host"}


def test_provenance_eh_json_serializable():
    """JSON serialize é pré-requisito pro banco persistir como TEXT."""
    module = _mock_module()
    module.id = "00000000-0000-0000-0000-000000000004"
    prov = _build_provenance(
        module=module, ocg_ctx=_ocg_ctx_cpp(), neighbors=[],
        prompt="any", config=_config_stub(),
    )
    as_str = json.dumps(prov, default=str)
    decoded = json.loads(as_str)
    assert decoded["test_framework"] == "googletest"
