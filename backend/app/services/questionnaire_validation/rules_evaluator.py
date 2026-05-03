"""MVP 35 — RulesEvaluator: engine determinístico stateless.

Avalia o catálogo de regras contra o payload de respostas do questionário.
Operadores DSL canônicos:

  - "Qx": "valor"           → eq scalar
  - "Qx_contains": "valor"  → inclusão em lista (multiselect)
  - "when_any": [{...},{...}] → OR (futuro, não usado nas 30 regras seed)

Uso típico:
    result = evaluate_rules(responses)
    # result = {
    #     "conflicts": [{"rule_id", "field", ...}],
    #     "warnings": [...],
    #     "evaluated_at_ms": 12,
    # }
"""
from __future__ import annotations

import time
from typing import Any, TypedDict

from .rules_catalog import RULES_CATALOG


class RuleHit(TypedDict):
    """Match de uma regra contra responses."""
    rule_id: str
    theme: str
    severity: str  # info | warning | error
    message: str
    suggestions: list[str]
    affected_fields: list[str]


class EvaluationResult(TypedDict):
    """Resultado canônico do evaluator."""
    conflicts: list[RuleHit]   # severity=error
    warnings: list[RuleHit]    # severity=warning
    info: list[RuleHit]        # severity=info (verdict=ok mas com nota)
    evaluated_at_ms: int       # latência da avaliação
    rules_evaluated: int       # cobertura


def _check_when_clause(when: dict[str, Any], responses: dict[str, Any]) -> bool:
    """Avalia bloco `when` (AND implícito entre keys).

    Operadores:
      - "Qx" simples → igualdade scalar (str==str)
      - "Qx_contains" → valor está na lista da resposta
    """
    for key, expected in when.items():
        if key.endswith("_contains"):
            field = key[:-len("_contains")]
            actual = responses.get(field)
            if not isinstance(actual, list):
                return False
            if expected not in actual:
                return False
        else:
            actual = responses.get(key)
            if actual != expected:
                return False
    return True


def evaluate_rules(
    responses: dict[str, Any],
    rules: list[dict[str, Any]] | None = None,
) -> EvaluationResult:
    """Roda catálogo de regras contra responses. Stateless, determinístico.

    Args:
        responses: dict {Q1: valor, Q2: valor, ...} do TechnicalQuestionnaire.
        rules: catálogo customizado (default = RULES_CATALOG completo).
               Útil para testes isolados.

    Returns:
        EvaluationResult com conflicts (error) + warnings (warning) + info (ok).
        Latência típica < 1ms para 30 regras.
    """
    rules = rules if rules is not None else RULES_CATALOG
    t0 = time.perf_counter()

    conflicts: list[RuleHit] = []
    warnings: list[RuleHit] = []
    info: list[RuleHit] = []

    for rule in rules:
        when = rule.get("when", {})
        if not _check_when_clause(when, responses):
            continue

        hit: RuleHit = {
            "rule_id": rule["id"],
            "theme": rule["theme"],
            "severity": rule["severity"],
            "message": rule["message"],
            "suggestions": rule.get("suggestions", []),
            "affected_fields": rule.get("affected_fields", []),
        }

        if rule["severity"] == "error":
            conflicts.append(hit)
        elif rule["severity"] == "warning":
            warnings.append(hit)
        else:  # info
            info.append(hit)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "conflicts": conflicts,
        "warnings": warnings,
        "info": info,
        "evaluated_at_ms": elapsed_ms,
        "rules_evaluated": len(rules),
    }


def is_blocking(result: EvaluationResult) -> bool:
    """True se há conflicts (severity=error). Bloqueia submit."""
    return len(result["conflicts"]) > 0
