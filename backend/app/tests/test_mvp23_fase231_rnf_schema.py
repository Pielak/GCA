"""MVP 23 Fase 23.1 — testes do schema RNF_CONTRACTS + helpers canônicos.

Valida:
- `OCGResponse` aceita RNF_CONTRACTS ausente, vazio, parcial, completo.
- OCGs pré-23 (sem RNF_CONTRACTS) desserializam sem quebra.
- `from_ocg_dict` é tolerante (None, dict errado, campos erradamente tipados).
- `validate_contract_dict` retorna erros canônicos sem levantar.
- `contract_as_prompt_block` gera texto vazio quando contrato vazio;
  texto estruturado quando há conteúdo.
- `extract_static_checks` detecta rate_limit, CWEs canônicos.
- `extract_test_scenarios` gera cenários latency, rate_limit, compliance.
"""
from datetime import datetime
from uuid import uuid4

import pytest

from app.schemas.ocg import OCGResponse
from app.services.rnf_contracts import (
    AvailabilityContract,
    ComplianceItem,
    PerformanceContract,
    RnfContracts,
    SecurityContract,
    contract_as_prompt_block,
    extract_static_checks,
    extract_test_scenarios,
    from_ocg_dict,
    validate_contract_dict,
)


# ===========================================================================
# Schema OCGResponse — backward compat + aceite de RNF_CONTRACTS
# ===========================================================================


def test_ocg_sem_rnf_contracts_usa_default():
    """OCG pré-23 (sem campo) continua válido com default {}."""
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
    )
    assert ocg.RNF_CONTRACTS == {}


def test_ocg_com_rnf_contracts_vazio_ok():
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
        RNF_CONTRACTS={},
    )
    assert ocg.RNF_CONTRACTS == {}


def test_ocg_com_rnf_contracts_completo():
    payload = {
        "performance": {
            "latency_p95_ms": 200,
            "throughput_rps": 500,
            "per_operation": [{"op": "POST /orders", "budget_ms": 150}],
        },
        "security": {
            "required_cwe_protections": ["CWE-89", "CWE-798"],
            "rate_limit_rpm_public": 60,
            "rate_limit_rpm_authenticated": 600,
            "sensitive_data_categories": ["PII", "financial"],
        },
        "compliance": [
            {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "runtime"},
        ],
        "availability": {"uptime_pct": 99.5, "rpo_minutes": 60, "rto_minutes": 30},
    }
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
        RNF_CONTRACTS=payload,
    )
    assert ocg.RNF_CONTRACTS == payload


def test_ocg_serializa_rnf_no_dict():
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
        RNF_CONTRACTS={"performance": {"latency_p95_ms": 100}},
    )
    dumped = ocg.dict()
    assert "RNF_CONTRACTS" in dumped
    assert dumped["RNF_CONTRACTS"]["performance"]["latency_p95_ms"] == 100


# ===========================================================================
# from_ocg_dict — tolerância
# ===========================================================================


def test_from_ocg_dict_none_retorna_vazio():
    rnf = from_ocg_dict(None)
    assert rnf.is_empty


def test_from_ocg_dict_dict_vazio_retorna_vazio():
    rnf = from_ocg_dict({})
    assert rnf.is_empty


def test_from_ocg_dict_tipo_errado_retorna_vazio():
    rnf = from_ocg_dict("not a dict")
    assert rnf.is_empty
    rnf2 = from_ocg_dict([1, 2, 3])
    assert rnf2.is_empty


def test_from_ocg_dict_campo_performance_parcial():
    rnf = from_ocg_dict({"performance": {"latency_p95_ms": 150}})
    assert rnf.performance.latency_p95_ms == 150
    assert rnf.performance.throughput_rps is None
    assert rnf.security.is_empty


def test_from_ocg_dict_ignora_per_operation_malformado():
    rnf = from_ocg_dict({
        "performance": {
            "per_operation": [
                {"op": "GET /x", "budget_ms": 100},  # válido
                {"op": "missing budget"},  # inválido, ignorado
                "não é dict",  # inválido, ignorado
            ],
        },
    })
    assert len(rnf.performance.per_operation) == 1
    assert rnf.performance.per_operation[0].op == "GET /x"


def test_from_ocg_dict_compliance_items():
    rnf = from_ocg_dict({
        "compliance": [
            {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "runtime"},
            {"regulation": "GDPR", "requirement_id": "ART-32"},  # enforcement default = "both"
            {"regulation": "", "requirement_id": "X"},  # sem regulação → ignorado
        ],
    })
    assert len(rnf.compliance) == 2
    assert rnf.compliance[0].enforcement == "runtime"
    assert rnf.compliance[1].enforcement == "both"


def test_from_ocg_dict_availability_clamps():
    rnf = from_ocg_dict({
        "availability": {"uptime_pct": 99.9, "rpo_minutes": 30, "rto_minutes": 60},
    })
    assert rnf.availability.uptime_pct == 99.9
    assert rnf.availability.rpo_minutes == 30
    assert rnf.availability.rto_minutes == 60


def test_from_ocg_dict_booleano_nao_vira_int():
    """Python trata bool como int — guarda defensivo impede latency_p95_ms=True virar 1."""
    rnf = from_ocg_dict({"performance": {"latency_p95_ms": True}})
    assert rnf.performance.latency_p95_ms is None


# ===========================================================================
# validate_contract_dict — feedback canônico sem levantar
# ===========================================================================


def test_validate_vazio_sem_erros():
    assert validate_contract_dict(None) == []
    assert validate_contract_dict({}) == []


def test_validate_tipo_errado_root():
    errors = validate_contract_dict("não é dict")
    assert len(errors) == 1
    assert errors[0].path == "$"


def test_validate_rejeita_chave_desconhecida():
    errors = validate_contract_dict({"unknown_root": {}})
    assert any("unknown_root" in e.path for e in errors)


def test_validate_performance_latency_negativo_erro():
    errors = validate_contract_dict({
        "performance": {"latency_p95_ms": -10},
    })
    assert any("latency_p95_ms" in e.path for e in errors)


def test_validate_security_rate_limit_negativo():
    errors = validate_contract_dict({
        "security": {"rate_limit_rpm_public": -1},
    })
    assert any("rate_limit_rpm_public" in e.path for e in errors)


def test_validate_compliance_sem_regulation():
    errors = validate_contract_dict({
        "compliance": [{"requirement_id": "X"}],  # sem regulation
    })
    assert any("regulation" in e.path for e in errors)


def test_validate_compliance_enforcement_invalido():
    errors = validate_contract_dict({
        "compliance": [{
            "regulation": "LGPD", "requirement_id": "X",
            "enforcement": "invalid_mode",
        }],
    })
    assert any("enforcement" in e.path for e in errors)


def test_validate_availability_uptime_fora_de_range():
    errors = validate_contract_dict({
        "availability": {"uptime_pct": 150},
    })
    assert any("uptime_pct" in e.path for e in errors)


def test_validate_contrato_completo_valido_sem_erros():
    """Contrato canônico válido passa sem erro."""
    errors = validate_contract_dict({
        "performance": {
            "latency_p95_ms": 200,
            "throughput_rps": 500,
            "per_operation": [{"op": "POST /orders", "budget_ms": 150}],
        },
        "security": {
            "required_cwe_protections": ["CWE-89"],
            "rate_limit_rpm_public": 60,
            "sensitive_data_categories": ["PII"],
        },
        "compliance": [
            {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "both"},
        ],
        "availability": {"uptime_pct": 99.5, "rpo_minutes": 60, "rto_minutes": 30},
    })
    assert errors == []


# ===========================================================================
# contract_as_prompt_block — Fase 23.3 preview
# ===========================================================================


def test_prompt_block_vazio_quando_contrato_vazio():
    assert contract_as_prompt_block(RnfContracts()) == ""


def test_prompt_block_performance():
    rnf = RnfContracts(
        performance=PerformanceContract(latency_p95_ms=200, throughput_rps=100),
    )
    block = contract_as_prompt_block(rnf)
    assert "Performance" in block
    assert "200 ms" in block
    assert "100 req/s" in block


def test_prompt_block_security_com_cwe():
    rnf = RnfContracts(
        security=SecurityContract(
            required_cwe_protections=("CWE-89", "CWE-798"),
            rate_limit_rpm_public=60,
        ),
    )
    block = contract_as_prompt_block(rnf)
    assert "Segurança" in block
    assert "CWE-89" in block
    assert "CWE-798" in block
    assert "60 req/min" in block


def test_prompt_block_compliance():
    rnf = RnfContracts(
        compliance=(
            ComplianceItem("LGPD", "ART-18", "runtime"),
            ComplianceItem("GDPR", "ART-32", "static"),
        ),
    )
    block = contract_as_prompt_block(rnf)
    assert "LGPD" in block
    assert "ART-18" in block
    assert "runtime" in block
    assert "GDPR" in block


def test_prompt_block_instrucao_docstring_obrigatoria():
    """Todo bloco não-vazio menciona que código deve documentar qual contrato atende."""
    rnf = RnfContracts(performance=PerformanceContract(latency_p95_ms=100))
    block = contract_as_prompt_block(rnf)
    assert "docstring" in block.lower()


# ===========================================================================
# extract_static_checks — Fase 23.4 preview
# ===========================================================================


def test_static_checks_vazio_quando_contrato_vazio():
    assert extract_static_checks(RnfContracts()) == []


def test_static_checks_rate_limit_middleware():
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    checks = extract_static_checks(rnf)
    ids = [c["id"] for c in checks]
    assert "rate_limit_middleware" in ids


def test_static_checks_cwe_89_sql_injection():
    rnf = RnfContracts(
        security=SecurityContract(required_cwe_protections=("CWE-89",)),
    )
    checks = extract_static_checks(rnf)
    ids = [c["id"] for c in checks]
    assert "cwe_89_sql_injection" in ids


def test_static_checks_cwe_798_hardcoded_credentials():
    rnf = RnfContracts(
        security=SecurityContract(required_cwe_protections=("CWE-798",)),
    )
    checks = extract_static_checks(rnf)
    ids = [c["id"] for c in checks]
    assert "cwe_798_hardcoded_credentials" in ids


def test_static_checks_sensitive_data_not_logged():
    rnf = RnfContracts(
        security=SecurityContract(sensitive_data_categories=("PII",)),
    )
    checks = extract_static_checks(rnf)
    ids = [c["id"] for c in checks]
    assert "sensitive_data_not_logged" in ids


# ===========================================================================
# extract_test_scenarios — Fase 23.4 preview
# ===========================================================================


def test_test_scenarios_vazio_quando_contrato_vazio():
    assert extract_test_scenarios(RnfContracts()) == []


def test_test_scenarios_latency_p95():
    rnf = RnfContracts(
        performance=PerformanceContract(latency_p95_ms=200),
    )
    scenarios = extract_test_scenarios(rnf)
    assert any(s["id"] == "latency_p95" for s in scenarios)


def test_test_scenarios_rate_limit_public():
    rnf = RnfContracts(
        security=SecurityContract(rate_limit_rpm_public=60),
    )
    scenarios = extract_test_scenarios(rnf)
    assert any(s["id"] == "rate_limit_public" for s in scenarios)


def test_test_scenarios_compliance():
    rnf = RnfContracts(
        compliance=(ComplianceItem("LGPD", "ART-18", "both"),),
    )
    scenarios = extract_test_scenarios(rnf)
    assert any(s["kind"] == "compliance" for s in scenarios)


def test_test_scenarios_per_operation():
    rnf = from_ocg_dict({
        "performance": {"per_operation": [{"op": "POST /orders", "budget_ms": 150}]},
    })
    scenarios = extract_test_scenarios(rnf)
    assert any("latency_POST" in s["id"] for s in scenarios)
