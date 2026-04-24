"""M01 — testes unit standalone (padrão MVP 29, sem pytest/DB de prod).

Cobre: prompt builder, parser tolerante, classificador de NSA, helpers
de extração de pilares.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.iterative_questionnaire_generator import (
    build_iterative_prompt, parse_iterative_response,
)
from app.services.iterative_questionnaire_service import (
    _extract_overall, _extract_pillar_scores, classify_not_applicable_ratio,
)


def test_prompt_contains_deficit_pillars():
    p = build_iterative_prompt(
        project_name="AJA", iteration=1, overall_before=73.7,
        target_pillars_scores={"P3_scope": 55.0, "P4_quality": 68.0},
        arguider_gaps_by_pillar={"P3_scope": [{"name": "DataJud adapter faltante", "severity": "critical"}]},
    )
    assert "P3_scope" in p
    assert "DataJud adapter" in p
    assert "73.7" in p
    assert "iteração 1" in p


def test_prompt_includes_previous_feedback_when_provided():
    p = build_iterative_prompt(
        project_name="X", iteration=2, overall_before=80.0,
        target_pillars_scores={"P7_security": 70.0},
        arguider_gaps_by_pillar={"P7_security": []},
        previous_iteration_feedback="Iter 1: overall 75->78",
    )
    assert "Iter 1: overall 75->78" in p


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"questions": [{"id":"Q1","type":"text","text":"Como é a arquitetura?","context":"P3_scope gap 20%","pillar":"P3_scope","required":true}]}\n```'
    out = parse_iterative_response(raw)
    assert len(out["questions"]) == 1
    assert out["questions"][0]["id"] == "Q1"
    assert out["questions"][0]["pillar"] == "P3_scope"


def test_parse_response_coerces_missing_ids():
    raw = '{"questions":[{"type":"text","text":"pergunta sem id"},{"type":"choice","text":"outra","options":["a","b"]}]}'
    out = parse_iterative_response(raw)
    assert out["questions"][0]["id"] == "Q1"
    assert out["questions"][1]["id"] == "Q2"


def test_parse_response_rejects_nonlist():
    raw = '{"questions": "nao e lista"}'
    try:
        parse_iterative_response(raw)
        assert False, "deveria ter levantado ValueError"
    except ValueError:
        pass


def test_parse_response_drops_empty_text_items():
    raw = '{"questions":[{"id":"Q1","type":"text","text":""},{"id":"Q2","type":"text","text":"valida"}]}'
    out = parse_iterative_response(raw)
    assert len(out["questions"]) == 1
    assert out["questions"][0]["text"] == "valida"


def test_extract_pillar_scores_canonical():
    data = {
        "PILLAR_SCORES": {
            "P1_business_case": {"score": 60, "weight": 0.10},
            "P3_scope": {"score": 55.0, "weight": 0.20},
            "P7_security": {"score": 88, "weight": 0.10},
        }
    }
    out = _extract_pillar_scores(data)
    assert out["P1_business_case"] == 60.0
    assert out["P3_scope"] == 55.0
    assert out["P7_security"] == 88.0


def test_extract_overall_from_composite():
    assert _extract_overall({"COMPOSITE_SCORE": {"value": 73.65}}) == 73.65
    assert _extract_overall({}) is None
    assert _extract_overall({"COMPOSITE_SCORE": "invalido"}) is None


def test_classify_not_applicable_ratio_majority():
    text = "Q1: não se aplica\nQ2: não se aplica\nQ3: sim, temos controles"
    ratio = classify_not_applicable_ratio(text)
    assert ratio > 0.5


def test_classify_not_applicable_ratio_minority():
    text = "Q1: temos LGPD mapeada\nQ2: não se aplica\nQ3: em progresso"
    ratio = classify_not_applicable_ratio(text)
    assert ratio < 0.5


def test_classify_not_applicable_ratio_empty():
    assert classify_not_applicable_ratio("") == 0.0


def _run_all():
    import inspect
    tests = [v for k, v in globals().items() if k.startswith("test_") and inspect.isfunction(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t(); passed += 1
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, f"assertion: {e}")); print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}")); print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*60}\nTotal: {len(tests)}  Passou: {passed}  Falhou: {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
