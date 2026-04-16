"""Testes do aplicador determinístico de deltas OCG.

Cobre os casos que o OCGUpdaterService precisa executar após receber o
delta do LLM: replace com/sem old_value, append em listas, rejeição de
paths fora do schema e de old_value divergente.
"""
import pytest

from app.services.ocg_delta_applier import (
    DeltaError,
    apply_deltas,
)


def _base_ocg() -> dict:
    """OCG mínimo com todos os top-level keys relevantes para os testes."""
    return {
        "ocg_id": "dummy",
        "PROJECT_PROFILE": {
            "project_name": "Test Project",
            "criticality": "Média",
        },
        "PILLAR_SCORES": {
            "P1_Business_Case": 70.0,
            "P3_Scope_Management": 60.0,
            "P5_Architecture": 80.0,
        },
        "COMPOSITE_SCORE": {"overall": 70.0, "is_blocking": False},
        "STACK_RECOMMENDATION": {
            "backend": {"language": "Python", "framework": "FastAPI"},
        },
        "DELIVERABLES": ["Doc de Arquitetura", "API Spec"],
        "RISK_ANALYSIS": {
            "high_risks": [
                {"risk": "R1", "mitigation": "M1"},
            ],
            "medium_risks": [],
        },
        "APPROVAL_STATUS": {"status": "READY", "reason": "ok"},
    }


# ────────────────────────── replace (dict) ──────────────────────────

def test_replace_scalar_dict_no_oldvalue():
    ocg = _base_ocg()
    updated, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": "PILLAR_SCORES.P3_Scope_Management", "new_value": 45.0}],
    )
    assert len(applied) == 1
    assert rejected == []
    assert updated["PILLAR_SCORES"]["P3_Scope_Management"] == 45.0
    # OCG original não foi mutado
    assert ocg["PILLAR_SCORES"]["P3_Scope_Management"] == 60.0


def test_replace_nested_object():
    ocg = _base_ocg()
    updated, applied, _ = apply_deltas(
        ocg,
        [{
            "op": "replace",
            "path": "STACK_RECOMMENDATION.backend.language",
            "old_value": "Python",
            "new_value": "Go",
        }],
    )
    assert len(applied) == 1
    assert updated["STACK_RECOMMENDATION"]["backend"]["language"] == "Go"


def test_replace_optimistic_concurrency_ok():
    ocg = _base_ocg()
    updated, applied, rejected = apply_deltas(
        ocg,
        [{
            "op": "replace",
            "path": "PILLAR_SCORES.P1_Business_Case",
            "old_value": 70.0,
            "new_value": 50.0,
        }],
    )
    assert len(applied) == 1
    assert rejected == []
    assert updated["PILLAR_SCORES"]["P1_Business_Case"] == 50.0


def test_replace_optimistic_concurrency_mismatch_rejects():
    ocg = _base_ocg()
    updated, applied, rejected = apply_deltas(
        ocg,
        [{
            "op": "replace",
            "path": "PILLAR_SCORES.P1_Business_Case",
            "old_value": 99.0,  # divergente do atual (70.0)
            "new_value": 50.0,
        }],
    )
    assert applied == []
    assert len(rejected) == 1
    assert "old_value não confere" in rejected[0]["_reason"]
    # OCG preservado — mudança não foi aplicada
    assert updated["PILLAR_SCORES"]["P1_Business_Case"] == 70.0


def test_replace_missing_key_rejects():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": "PILLAR_SCORES.P9_Does_Not_Exist", "new_value": 50.0}],
    )
    assert applied == []
    assert "não existe" in rejected[0]["_reason"]


# ────────────────────────── replace (lista por índice) ──────────────────

def test_replace_array_item_by_index():
    ocg = _base_ocg()
    updated, applied, _ = apply_deltas(
        ocg,
        [{
            "op": "replace",
            "path": "RISK_ANALYSIS.high_risks.0.mitigation",
            "old_value": "M1",
            "new_value": "Mitigação revisada",
        }],
    )
    assert len(applied) == 1
    assert updated["RISK_ANALYSIS"]["high_risks"][0]["mitigation"] == "Mitigação revisada"


def test_replace_array_index_out_of_range_rejects():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": "RISK_ANALYSIS.high_risks.5.mitigation", "new_value": "M"}],
    )
    assert applied == []
    assert "fora de range" in rejected[0]["_reason"] or "não encontrado" in rejected[0]["_reason"]


# ────────────────────────── append (lista) ──────────────────────────

def test_append_to_string_list():
    ocg = _base_ocg()
    updated, applied, _ = apply_deltas(
        ocg,
        [{"op": "append", "path": "DELIVERABLES", "value": "SBOM"}],
    )
    assert len(applied) == 1
    assert updated["DELIVERABLES"] == ["Doc de Arquitetura", "API Spec", "SBOM"]


def test_append_object_to_nested_list():
    ocg = _base_ocg()
    new_risk = {"risk": "Nova dependência externa", "mitigation": "Monitorar"}
    updated, applied, _ = apply_deltas(
        ocg,
        [{"op": "append", "path": "RISK_ANALYSIS.medium_risks", "value": new_risk}],
    )
    assert len(applied) == 1
    assert updated["RISK_ANALYSIS"]["medium_risks"] == [new_risk]


def test_append_to_non_list_rejects():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "append", "path": "PILLAR_SCORES.P1_Business_Case", "value": 99}],
    )
    assert applied == []
    assert "append requer lista" in rejected[0]["_reason"]


def test_append_missing_path_rejects():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "append", "path": "DELIVERABLES_NOVO", "value": "x"}],
    )
    assert applied == []
    # Falha primeiro na whitelist (top-level não permitido)
    assert rejected[0]["_reason"]


# ────────────────────────── validação de whitelist ──────────────────────

def test_rejects_top_level_outside_whitelist():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": "MALICIOUS_FIELD.sub", "new_value": "x"}],
    )
    assert applied == []
    assert "whitelist" in rejected[0]["_reason"]


def test_rejects_ocg_id_modification():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": "ocg_id", "new_value": "hijacked"}],
    )
    assert applied == []
    assert ocg["ocg_id"] == "dummy"  # não alterado no original também
    assert "whitelist" in rejected[0]["_reason"]


# ────────────────────────── validação de formato ────────────────────────

def test_rejects_unsupported_op():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "delete", "path": "DELIVERABLES"}],
    )
    assert applied == []
    assert "op não suportada" in rejected[0]["_reason"]


def test_rejects_empty_path():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": "", "new_value": "x"}],
    )
    assert applied == []
    assert rejected[0]["_reason"]


def test_rejects_non_string_path():
    ocg = _base_ocg()
    _, applied, rejected = apply_deltas(
        ocg,
        [{"op": "replace", "path": 123, "new_value": "x"}],
    )
    assert applied == []


def test_raises_on_non_list_deltas():
    with pytest.raises(DeltaError):
        apply_deltas({}, {"not": "a list"})  # type: ignore[arg-type]


# ────────────────────────── batch: parcial success ──────────────────────

def test_batch_partial_success():
    """Mistura deltas válidos e inválidos — válidos passam, inválidos vão para rejected."""
    ocg = _base_ocg()
    updated, applied, rejected = apply_deltas(
        ocg,
        [
            {"op": "replace", "path": "PILLAR_SCORES.P5_Architecture", "new_value": 70.0},
            {"op": "replace", "path": "DOES_NOT_EXIST.sub", "new_value": "x"},
            {"op": "append", "path": "DELIVERABLES", "value": "ADR novo"},
        ],
    )
    assert len(applied) == 2
    assert len(rejected) == 1
    assert updated["PILLAR_SCORES"]["P5_Architecture"] == 70.0
    assert "ADR novo" in updated["DELIVERABLES"]
    assert rejected[0]["path"] == "DOES_NOT_EXIST.sub"


def test_idempotent_on_noop_changes():
    """Aplicar os mesmos deltas duas vezes produz o mesmo resultado final."""
    ocg = _base_ocg()
    deltas = [{"op": "replace", "path": "PILLAR_SCORES.P1_Business_Case", "new_value": 50.0}]
    once, _, _ = apply_deltas(ocg, deltas)
    twice, _, _ = apply_deltas(once, deltas)
    assert once == twice
