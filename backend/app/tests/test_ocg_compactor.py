"""Testes do compactor de OCG para prompts LLM (Fase 3)."""
import json

from app.services.ocg_compactor import (
    DEFAULT_MIN_SIZE_CHARS,
    compact_ocg_for_prompt,
)


def _ocg_with_long_rationale(n_chars: int = 500) -> dict:
    """OCG com rationale verboso pra forçar trim."""
    long_text = "Lorem ipsum " * (n_chars // 12)
    return {
        "PROJECT_PROFILE": {"project_name": "P"},
        "PILLAR_SCORES": {"P1_Business_Case": 70.0, "P5_Architecture": 80.0},
        "STACK_RECOMMENDATION": {
            "backend": {
                "language": "Python",
                "framework": "FastAPI",
                "rationale": long_text,
            },
            "frontend": {
                "framework": "React",
                "rationale": long_text,
            },
        },
        "TESTING_REQUIREMENTS": {
            "unit_testing": {"tools": "pytest", "rationale": long_text},
        },
        "ARCHITECTURE_OVERVIEW": {
            "style": "Modular",
            "description": long_text,
            "data_flow": long_text,
            "key_components": ["A", "B"],
        },
        "RISK_ANALYSIS": {
            "high_risks": [
                {"risk": "R1", "impact": long_text, "mitigation": long_text},
                {"risk": "R2", "impact": long_text, "mitigation": long_text},
            ],
            "medium_risks": [
                {"risk": "M1", "impact": long_text, "mitigation": long_text},
            ],
        },
        "CRITICAL_FINDINGS": {"finding": "F", "recommendation": long_text},
        "APPROVAL_STATUS": {"status": "AT_RISK", "reason": long_text},
        "DELIVERABLES": ["D1", "D2", "D3"],
        "COMPLIANCE_CHECKLIST": [{"item": "X", "status": "PENDING"}],
        "COMPOSITE_SCORE": {"overall": 75.0},
    }


def test_small_ocg_returns_copy_untouched():
    """OCG abaixo do threshold é devolvido inalterado (deepcopy)."""
    small = {"PILLAR_SCORES": {"P1": 50.0}, "DELIVERABLES": ["x"]}
    out = compact_ocg_for_prompt(small)
    assert out == small
    assert out is not small  # cópia, não referência


def test_large_ocg_triggers_trim():
    """OCG acima do threshold tem rationale/description/mitigation trimados."""
    big = _ocg_with_long_rationale(n_chars=2000)
    original_size = len(json.dumps(big, ensure_ascii=False))
    assert original_size > DEFAULT_MIN_SIZE_CHARS  # confirma threshold ultrapassado

    out = compact_ocg_for_prompt(big)
    new_size = len(json.dumps(out, ensure_ascii=False))

    assert new_size < original_size  # ficou menor
    # Rationale dos serviços trimado
    assert "<trimmed:" in out["STACK_RECOMMENDATION"]["backend"]["rationale"]
    assert "<trimmed:" in out["STACK_RECOMMENDATION"]["frontend"]["rationale"]
    # Description e data_flow trimados
    assert "<trimmed:" in out["ARCHITECTURE_OVERVIEW"]["description"]
    assert "<trimmed:" in out["ARCHITECTURE_OVERVIEW"]["data_flow"]
    # Mitigations dentro de listas trimadas
    assert "<trimmed:" in out["RISK_ANALYSIS"]["high_risks"][0]["mitigation"]
    assert "<trimmed:" in out["RISK_ANALYSIS"]["high_risks"][1]["mitigation"]
    assert "<trimmed:" in out["RISK_ANALYSIS"]["medium_risks"][0]["mitigation"]


def test_preserves_structural_values():
    """Trim NÃO toca em scores, listas de strings, status, item names."""
    big = _ocg_with_long_rationale(n_chars=2000)
    out = compact_ocg_for_prompt(big)

    # Scores intactos
    assert out["PILLAR_SCORES"]["P1_Business_Case"] == 70.0
    assert out["PILLAR_SCORES"]["P5_Architecture"] == 80.0
    assert out["COMPOSITE_SCORE"]["overall"] == 75.0
    # Strings curtas (framework, language, style) intactas
    assert out["STACK_RECOMMENDATION"]["backend"]["language"] == "Python"
    assert out["STACK_RECOMMENDATION"]["backend"]["framework"] == "FastAPI"
    assert out["ARCHITECTURE_OVERVIEW"]["style"] == "Modular"
    # Listas de strings (DELIVERABLES) intactas
    assert out["DELIVERABLES"] == ["D1", "D2", "D3"]
    # Item names em checklists intactos
    assert out["COMPLIANCE_CHECKLIST"][0]["item"] == "X"
    assert out["COMPLIANCE_CHECKLIST"][0]["status"] == "PENDING"
    # Risk titles intactos (só impact/mitigation trimados)
    assert out["RISK_ANALYSIS"]["high_risks"][0]["risk"] == "R1"
    assert out["RISK_ANALYSIS"]["high_risks"][1]["risk"] == "R2"
    # Status do approval intacto
    assert out["APPROVAL_STATUS"]["status"] == "AT_RISK"


def test_does_not_mutate_input():
    """compact_ocg_for_prompt nunca muta o OCG passado."""
    big = _ocg_with_long_rationale(n_chars=2000)
    snapshot = json.dumps(big, ensure_ascii=False)
    _ = compact_ocg_for_prompt(big)
    assert json.dumps(big, ensure_ascii=False) == snapshot


def test_idempotent_on_already_compact():
    """Aplicar 2x não deve produzir resultados diferentes."""
    big = _ocg_with_long_rationale(n_chars=2000)
    once = compact_ocg_for_prompt(big)
    twice = compact_ocg_for_prompt(once)
    assert once == twice


def test_handles_missing_optional_fields():
    """OCG sem alguns top-level fields não quebra o compactor."""
    minimal = {
        "PILLAR_SCORES": {"P1": 50.0},
        "STACK_RECOMMENDATION": {"backend": {"language": "Go"}},  # sem rationale
    }
    out = compact_ocg_for_prompt(minimal)
    # Não levanta exceção, retorna estrutura intacta
    assert out["PILLAR_SCORES"]["P1"] == 50.0
    assert out["STACK_RECOMMENDATION"]["backend"]["language"] == "Go"


def test_handles_non_dict_input_gracefully():
    """Input que não é dict é devolvido como-is (defensivo)."""
    assert compact_ocg_for_prompt(None) is None  # type: ignore[arg-type]
    assert compact_ocg_for_prompt("string") == "string"  # type: ignore[arg-type]
    assert compact_ocg_for_prompt([1, 2, 3]) == [1, 2, 3]  # type: ignore[arg-type]
