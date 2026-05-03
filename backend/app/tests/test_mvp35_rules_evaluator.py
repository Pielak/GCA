"""MVP 35 Fase 35.1 — Testes do RulesEvaluator + 30 regras seed.

Cobertura:
  - Catálogo válido (30 regras, 5 temas, IDs únicos)
  - Operadores DSL (eq, contains, AND)
  - Cada regra dispara nas condições corretas
  - Latência < 50ms (NFR Gate 2)
  - is_blocking detecta conflicts
"""
import pytest

from app.services.questionnaire_validation.rules_catalog import (
    RULES_CATALOG,
    all_rule_ids,
    get_rule_by_id,
    get_rules_by_theme,
)
from app.services.questionnaire_validation.rules_evaluator import (
    evaluate_rules,
    is_blocking,
)


# =============================================================================
# Catálogo
# =============================================================================


def test_catalog_tem_30_regras():
    assert len(RULES_CATALOG) == 30


def test_catalog_ids_unicos():
    ids = all_rule_ids()
    assert len(ids) == len(set(ids))


def test_catalog_5_temas():
    temas = {r["theme"] for r in RULES_CATALOG}
    assert temas == {"nosql_acid", "stack", "fe_be", "compliance", "infra"}


def test_get_rule_by_id():
    r = get_rule_by_id("NOSQL_001_MONGODB_ACID")
    assert r is not None
    assert r["theme"] == "nosql_acid"


def test_get_rule_by_id_not_found():
    assert get_rule_by_id("FAKE_RULE") is None


def test_get_rules_by_theme():
    nosql = get_rules_by_theme("nosql_acid")
    assert len(nosql) == 5  # tema NoSQL × ACID
    stack = get_rules_by_theme("stack")
    assert len(stack) == 6  # tema Stack runtime
    febe = get_rules_by_theme("fe_be")
    assert len(febe) == 5
    comp = get_rules_by_theme("compliance")
    assert len(comp) == 6
    infra = get_rules_by_theme("infra")
    assert len(infra) == 8


# =============================================================================
# Operadores DSL
# =============================================================================


def test_when_eq_scalar_match():
    """Q1='Novo sistema' + Q2='Curto (2-4 semanas)' dispara INFRA_008."""
    responses = {"Q1": "Novo sistema", "Q2": "Curto (2-4 semanas)"}
    result = evaluate_rules(responses)
    hit_ids = {w["rule_id"] for w in result["warnings"]}
    assert "INFRA_008_SHORT_DEADLINE_NEW_SYSTEM" in hit_ids


def test_when_eq_scalar_no_match_diferente():
    """Q1='Novo sistema' sozinho NÃO dispara INFRA_008 (precisa Q2 também)."""
    responses = {"Q1": "Novo sistema", "Q2": "Médio (1-3 meses)"}
    result = evaluate_rules(responses)
    hit_ids = {w["rule_id"] for w in result["warnings"]}
    assert "INFRA_008_SHORT_DEADLINE_NEW_SYSTEM" not in hit_ids


def test_when_contains_lista_match():
    """Q5 multiselect contendo 'PHP/Laravel' + Q14='<100ms' dispara STACK_001."""
    responses = {"Q5": ["PHP/Laravel", "Python/FastAPI"], "Q14": "<100ms"}
    result = evaluate_rules(responses)
    hit_ids = {w["rule_id"] for w in result["warnings"]}
    assert "STACK_001_PHP_REALTIME" in hit_ids


def test_when_contains_no_match_lista_sem_valor():
    """Q5 sem 'PHP/Laravel' não dispara STACK_001."""
    responses = {"Q5": ["Python/FastAPI", "Go"], "Q14": "<100ms"}
    result = evaluate_rules(responses)
    hit_ids = {w["rule_id"] for w in result["warnings"]}
    assert "STACK_001_PHP_REALTIME" not in hit_ids


def test_when_contains_falha_se_resposta_nao_lista():
    """Q5_contains exige Q5 ser lista. Se for string, não match."""
    responses = {"Q5": "PHP/Laravel", "Q14": "<100ms"}  # Q5 string, não lista
    result = evaluate_rules(responses)
    hit_ids = {w["rule_id"] for w in result["warnings"]}
    assert "STACK_001_PHP_REALTIME" not in hit_ids


def test_when_and_implicito():
    """when={Q4:..., Q13_contains:...} exige AMBOS true."""
    responses = {
        "Q4": "NoSQL (MongoDB, DynamoDB)",
        "Q13": ["PCI-DSS", "OAuth 2.0"],
    }
    result = evaluate_rules(responses)
    hit_ids = {c["rule_id"] for c in result["conflicts"]}
    assert "NOSQL_001_MONGODB_ACID" in hit_ids


# =============================================================================
# Severidade — categorização correta
# =============================================================================


def test_severity_error_vai_para_conflicts():
    responses = {"Q4": "NoSQL (MongoDB, DynamoDB)", "Q13": ["PCI-DSS"]}
    result = evaluate_rules(responses)
    assert any(c["rule_id"] == "NOSQL_001_MONGODB_ACID" for c in result["conflicts"])
    assert all(c["severity"] == "error" for c in result["conflicts"])


def test_severity_warning_vai_para_warnings():
    responses = {"Q5": ["PHP/Laravel"], "Q14": "<100ms"}
    result = evaluate_rules(responses)
    assert any(w["rule_id"] == "STACK_001_PHP_REALTIME" for w in result["warnings"])
    assert all(w["severity"] == "warning" for w in result["warnings"])


def test_severity_info_vai_para_info():
    """STACK_006 .NET+Kafka tem severity=info (verdict=ok)."""
    responses = {"Q5": ["C#/.NET"], "Q9": "Sim, Kafka"}
    result = evaluate_rules(responses)
    assert any(i["rule_id"] == "STACK_006_DOTNET_LINUX_CONTAINER" for i in result["info"])


# =============================================================================
# is_blocking
# =============================================================================


def test_is_blocking_true_quando_ha_conflict():
    responses = {"Q4": "NoSQL (MongoDB, DynamoDB)", "Q13": ["PCI-DSS"]}
    result = evaluate_rules(responses)
    assert is_blocking(result) is True


def test_is_blocking_false_quando_so_warning():
    responses = {"Q5": ["PHP/Laravel"], "Q14": "<100ms"}
    result = evaluate_rules(responses)
    assert is_blocking(result) is False


def test_is_blocking_false_quando_responses_vazias():
    result = evaluate_rules({})
    assert is_blocking(result) is False
    assert result["rules_evaluated"] == 30


# =============================================================================
# Cenários canônicos (regras específicas — sample de cobertura)
# =============================================================================


def test_kafka_sem_db_decidido():
    """NOSQL_004: Kafka como log mas Q4='Não decidido' = conflict."""
    responses = {"Q9": "Sim, Kafka", "Q4": "Não decidido"}
    result = evaluate_rules(responses)
    assert any(c["rule_id"] == "NOSQL_004_KAFKA_NO_DB" for c in result["conflicts"])


def test_sla_alto_sem_escala():
    """INFRA_002: SLA 99.99% + Q3=Não = conflict."""
    responses = {"Q10": "99.99%", "Q3": "Não"}
    result = evaluate_rules(responses)
    assert any(c["rule_id"] == "INFRA_002_SLA_VS_NO_SCALE" for c in result["conflicts"])


def test_soc2_sem_seguranca():
    """COMP_005: SOC 2 + Q13='Nenhum específico' = conflict."""
    responses = {"Q15": ["SOC 2"], "Q13": ["Nenhum específico"]}
    result = evaluate_rules(responses)
    assert any(c["rule_id"] == "COMP_005_SOC2_NO_AUDIT" for c in result["conflicts"])


def test_lgpd_recomenda_tls():
    """COMP_001: LGPD sem TLS = warning."""
    responses = {"Q15": ["LGPD"]}
    result = evaluate_rules(responses)
    assert any(w["rule_id"] == "COMP_001_LGPD_NO_TLS" for w in result["warnings"])


def test_lgpd_gdpr_double_info():
    """COMP_006: LGPD+GDPR = info (não é conflito)."""
    responses = {"Q15": ["LGPD", "GDPR"]}
    result = evaluate_rules(responses)
    assert any(i["rule_id"] == "COMP_006_LGPD_GDPR_DOUBLE" for i in result["info"])


def test_dw_para_oltp_conflict():
    """NOSQL_005: Data warehouse + escala agressiva = conflict (OLAP vs OLTP)."""
    responses = {"Q4": "Data warehouse", "Q3": "Sim, agressivo"}
    result = evaluate_rules(responses)
    assert any(c["rule_id"] == "NOSQL_005_DW_OLTP" for c in result["conflicts"])


def test_rust_prazo_curto_warning():
    responses = {"Q5": ["Rust"], "Q2": "Curto (2-4 semanas)"}
    result = evaluate_rules(responses)
    assert any(w["rule_id"] == "STACK_005_RUST_PROTOTYPE" for w in result["warnings"])


def test_payment_gateway_pci_info():
    """COMP_003: PCI-DSS + Payment Gateway = info (boa prática)."""
    responses = {"Q13": ["PCI-DSS"], "Q11": ["Payment Gateway"]}
    result = evaluate_rules(responses)
    assert any(i["rule_id"] == "COMP_003_PCIDSS_NO_TOKEN" for i in result["info"])


def test_short_deadline_warning():
    responses = {"Q1": "Novo sistema", "Q2": "Curto (2-4 semanas)"}
    result = evaluate_rules(responses)
    assert any(w["rule_id"] == "INFRA_008_SHORT_DEADLINE_NEW_SYSTEM" for w in result["warnings"])


# =============================================================================
# NFR — latência (Gate 2 A-S2: p95 ≤ 50ms)
# =============================================================================


def test_latencia_abaixo_de_50ms():
    """30 regras × responses completas < 50ms."""
    responses = {
        "Q1": "Novo sistema",
        "Q2": "Curto (2-4 semanas)",
        "Q3": "Sim, agressivo",
        "Q4": "NoSQL (MongoDB, DynamoDB)",
        "Q5": ["Python/FastAPI", "Go"],
        "Q6": ["React", "Next.js"],
        "Q9": "Sim, Kafka",
        "Q10": "99.99%",
        "Q11": ["Payment Gateway"],
        "Q12": "GraphQL",
        "Q13": ["OAuth 2.0", "JWT", "PCI-DSS"],
        "Q14": "<100ms",
        "Q15": ["LGPD", "GDPR"],
    }
    result = evaluate_rules(responses)
    assert result["evaluated_at_ms"] < 50
    assert result["rules_evaluated"] == 30


# =============================================================================
# Idempotência
# =============================================================================


def test_evaluator_idempotente():
    """Mesma entrada = mesma saída (sem state)."""
    responses = {"Q5": ["PHP/Laravel"], "Q14": "<100ms"}
    r1 = evaluate_rules(responses)
    r2 = evaluate_rules(responses)
    assert {w["rule_id"] for w in r1["warnings"]} == {w["rule_id"] for w in r2["warnings"]}
    assert r1["rules_evaluated"] == r2["rules_evaluated"]
