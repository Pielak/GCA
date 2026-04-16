"""Testes do classificador de OCG.DELIVERABLES → (kind, category).

Tabela com strings reais que apareceram nos OCGs do FinanceHub Pro
e variações comuns. Garante que padrões cobrem o vocabulário em PT-BR
sem falsos-positivos óbvios.
"""
import pytest

from app.services.deliverable_classifier import (
    classify_deliverable,
    is_auto_verifiable,
    normalize_name,
)


# ────────────────────────── normalização ─────────────────────────────

def test_normalize_lowers_and_strips_accents():
    assert normalize_name("Documento de Caso de Negócio") == "documento de caso de negocio"
    assert normalize_name("  ESPAÇOS  EXTRAS  ") == "espacos extras"
    assert normalize_name("") == ""
    assert normalize_name(None) == ""  # type: ignore[arg-type]


# ────────────────────────── matches conhecidos ───────────────────────

@pytest.mark.parametrize("text,expected_kind,expected_cat", [
    # Code
    ("Repositório de Código Fonte com Pipeline CI/CD configurado", "ci_pipeline", "code"),
    ("Ambiente de Desenvolvimento Containerizado", "dockerfile", "code"),
    ("Imagem Docker do backend", "dockerfile", "code"),
    ("SBOM (Software Bill of Materials) inicial do projeto", "sbom", "code"),
    ("Manifestos de Dependências Versionadas (pyproject.toml, package.json)", "manifests", "code"),
    ("Projeto de Banco de Dados (DDL inicial)", "database_design", "code"),

    # Docs API
    ("Documentação da API (OpenAPI/Swagger)", "openapi", "doc"),
    ("ADR (Architecture Decision Record) para estrutura de diretórios", "adr", "doc"),
    ("Documento de Arquitetura de Solução", "architecture_doc", "doc"),

    # Negócio
    ("Documento de Caso de Negócio e ROI", "business_case", "doc"),
    ("Justification Record para ingestão de repositórios externos", "justification_record", "process"),
    ("Política de Gestão de Dependências e Supply Chain Security", "dependency_policy", "process"),

    # Compliance
    ("Políticas de Compliance (LGPD, Backup, Retenção)", "compliance_doc", "process"),
    ("Checklist LGPD", "compliance_doc", "process"),

    # Test
    ("Plano de Testes (Unitário, Integração, Carga, Segurança)", "test_plan", "test"),

    # Backlog
    ("Especificação de MVP e Backlog Priorizado", "backlog", "process"),

    # Observability
    ("Dashboard de Observabilidade (Grafana)", "observability_dashboard", "code"),
])
def test_classifies_known_deliverables(text, expected_kind, expected_cat):
    kind, category = classify_deliverable(text)
    assert kind == expected_kind, f"texto={text!r} → kind={kind} (esperado {expected_kind})"
    assert category == expected_cat


# ────────────────────────── unmatched → manual ───────────────────────

def test_unknown_text_falls_to_manual():
    kind, cat = classify_deliverable("Algum entregável muito específico que não tem padrão")
    assert kind == "other_manual"
    assert cat == "other"


def test_empty_or_invalid_input_is_manual():
    assert classify_deliverable("") == ("other_manual", "other")
    assert classify_deliverable(None) == ("other_manual", "other")  # type: ignore[arg-type]
    assert classify_deliverable(123) == ("other_manual", "other")  # type: ignore[arg-type]


# ────────────────────────── case-insensitivity ───────────────────────

def test_classification_is_case_and_accent_insensitive():
    a, _ = classify_deliverable("DOCUMENTO DE CASO DE NEGOCIO E ROI")
    b, _ = classify_deliverable("documento de caso de negócio e roi")
    c, _ = classify_deliverable("Documento de Caso de Negócio e ROI")
    assert a == b == c == "business_case"


# ────────────────────────── auto-verifiable flag ─────────────────────

def test_auto_verifiable_for_known_kinds():
    assert is_auto_verifiable("dockerfile") is True
    assert is_auto_verifiable("openapi") is True
    assert is_auto_verifiable("sbom") is True
    assert is_auto_verifiable("backlog") is True


def test_auto_verifiable_false_for_business_case_and_manual():
    """business_case e other_manual exigem atestação humana — sem checker auto."""
    assert is_auto_verifiable("business_case") is False
    assert is_auto_verifiable("other_manual") is False


# ────────────────────────── precedência de padrões ───────────────────

def test_first_match_wins_when_multiple_patterns_apply():
    """ 'Pipeline CI/CD configurado em Docker' poderia matchar tanto
    ci_pipeline quanto dockerfile — mas ci_pipeline vem antes na lista,
    então ganha (dependência consciente da ordem em _PATTERNS)."""
    kind, _ = classify_deliverable("Pipeline CI/CD configurado em Docker")
    assert kind == "ci_pipeline"
