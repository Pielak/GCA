"""Testes do avaliador de thresholds por pilar (camada base F3)."""
from app.services.pillar_threshold_evaluator import (
    derive_project_status,
    evaluate_blocking_pillars,
)


# ────────────────────────── thresholds tipicamente usados ────────────────

DEFAULT_THRESHOLDS = {
    "p1_blocking_threshold": 0,
    "p2_blocking_threshold": 0,
    "p3_blocking_threshold": 0,
    "p4_blocking_threshold": 0,
    "p5_blocking_threshold": 0,
    "p6_blocking_threshold": 0,
    "p7_blocking_threshold": 70,
    "ready_threshold": 90,
    "needs_review_threshold": 70,
    "at_risk_threshold": 50,
}


# ────────────────────────── evaluate_blocking_pillars ───────────────────

def test_no_blocking_when_all_thresholds_zero_except_p7_satisfied():
    scores = {
        "P1_Business_Case": 60.0,
        "P2_Compliance": 80.0,
        "P3_Scope_Management": 50.0,
        "P4_Performance": 75.0,
        "P5_Architecture": 65.0,
        "P6_Data_Management": 55.0,
        "P7_Security": 80.0,  # > 70
    }
    blocking = evaluate_blocking_pillars(scores, DEFAULT_THRESHOLDS)
    assert blocking == []


def test_p7_blocks_when_below_70():
    scores = {"P7_Security": 65.0}
    blocking = evaluate_blocking_pillars(scores, DEFAULT_THRESHOLDS)
    assert len(blocking) == 1
    assert blocking[0]["pillar"] == "P7"
    assert blocking[0]["score"] == 65.0
    assert blocking[0]["threshold"] == 70
    assert blocking[0]["deficit"] == 5.0


def test_custom_threshold_per_pillar():
    """Admin pode setar threshold em qualquer pilar, não só P7."""
    custom = dict(DEFAULT_THRESHOLDS)
    custom["p1_blocking_threshold"] = 50
    custom["p3_blocking_threshold"] = 60
    scores = {
        "P1_Business_Case": 25.0,  # < 50, bloqueia
        "P3_Scope_Management": 70.0,  # > 60, ok
        "P5_Architecture": 40.0,  # threshold=0, não bloqueia
        "P7_Security": 80.0,  # > 70, ok
    }
    blocking = evaluate_blocking_pillars(scores, custom)
    pillars = {b["pillar"] for b in blocking}
    assert pillars == {"P1"}
    assert blocking[0]["deficit"] == 25.0


def test_multiple_blocking_sorted_by_deficit():
    custom = dict(DEFAULT_THRESHOLDS)
    custom["p1_blocking_threshold"] = 70
    custom["p3_blocking_threshold"] = 70
    custom["p5_blocking_threshold"] = 70
    scores = {
        "P1_Business_Case": 60.0,  # deficit 10
        "P3_Scope_Management": 30.0,  # deficit 40
        "P5_Architecture": 50.0,  # deficit 20
        "P7_Security": 80.0,
    }
    blocking = evaluate_blocking_pillars(scores, custom)
    assert [b["pillar"] for b in blocking] == ["P3", "P5", "P1"]
    assert blocking[0]["deficit"] == 40


def test_short_pillar_keys_also_recognized():
    """Aceita keys 'P1', 'P3', etc. sem sufixo descritivo."""
    scores = {"P7": 50.0}
    blocking = evaluate_blocking_pillars(scores, DEFAULT_THRESHOLDS)
    assert len(blocking) == 1
    assert blocking[0]["pillar"] == "P7"


def test_invalid_keys_ignored():
    scores = {
        "OVERALL": 80.0,
        "MALFORMED_PX": 50.0,
        "P7_Security": 80.0,
        "P10_Future": 30.0,  # fora de 1-7
    }
    blocking = evaluate_blocking_pillars(scores, DEFAULT_THRESHOLDS)
    assert blocking == []


def test_invalid_score_values_ignored():
    scores = {"P7_Security": "not a number", "P3_Scope": None}
    blocking = evaluate_blocking_pillars(scores, DEFAULT_THRESHOLDS)
    assert blocking == []


# ────────────────────────── derive_project_status ───────────────────────

def test_status_blocked_when_pillar_blocking():
    """Qualquer pilar bloqueando força BLOCKED, mesmo com overall alto."""
    blocking = [{"pillar": "P7", "score": 50, "threshold": 70, "deficit": 20}]
    assert derive_project_status(95.0, blocking, DEFAULT_THRESHOLDS) == "BLOCKED"


def test_status_ready_when_high_overall_no_blocking():
    assert derive_project_status(92.0, [], DEFAULT_THRESHOLDS) == "READY"


def test_status_needs_review():
    assert derive_project_status(75.0, [], DEFAULT_THRESHOLDS) == "NEEDS_REVIEW"


def test_status_at_risk():
    assert derive_project_status(55.0, [], DEFAULT_THRESHOLDS) == "AT_RISK"


def test_status_blocked_when_overall_below_at_risk():
    assert derive_project_status(30.0, [], DEFAULT_THRESHOLDS) == "BLOCKED"


def test_status_uses_custom_bands():
    custom = {"ready_threshold": 95, "needs_review_threshold": 85, "at_risk_threshold": 60}
    assert derive_project_status(90.0, [], custom) == "NEEDS_REVIEW"
    assert derive_project_status(95.0, [], custom) == "READY"
    assert derive_project_status(70.0, [], custom) == "AT_RISK"
