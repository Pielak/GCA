"""Avaliador determinístico de pilares bloqueantes (Camada base F3).

Aplica os thresholds configurados no Admin Settings sobre os scores dos
pilares de um OCG, retornando quais pilares estão bloqueando o projeto e
o status agregado (READY / NEEDS_REVIEW / AT_RISK / BLOCKED).

Sem LLM, sem rede — pure function. Usado por Gatekeeper para decisão
explícita (vs deixar o LLM marcar is_blocking arbitrariamente).
"""
from __future__ import annotations

from typing import Any, Dict, List


# Mapeamento de prefixo do score key (no JSON do OCG) → número do pilar.
# Ex: "P3_Scope_Management" → 3.
def _pillar_num_from_key(key: str) -> int | None:
    if not key or len(key) < 2 or key[0] != "P":
        return None
    try:
        return int(key[1:].split("_", 1)[0])
    except (ValueError, IndexError):
        return None


def evaluate_blocking_pillars(
    pillar_scores: Dict[str, float],
    thresholds: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Lista pilares cujo score < threshold individual configurado.

    Args:
        pillar_scores: dict como ``{"P1_Business_Case": 25.0, "P3_Scope_Management": 60.0, ...}``
            ou ``{"P1": 25.0, ...}``. Aceita qualquer formato com prefixo Pn.
        thresholds: dict do Admin Settings com chaves ``pN_blocking_threshold``
            (1≤N≤7). Threshold = 0 significa "não bloqueia individualmente".

    Returns:
        Lista de dicts ``{"pillar": "P3", "score": 60.0, "threshold": 65, "deficit": 5.0}``,
        ordenada por deficit decrescente (mais bloqueante primeiro). Vazia se
        nenhum pilar viola seu threshold.
    """
    blocking: List[Dict[str, Any]] = []
    for key, raw_score in pillar_scores.items():
        num = _pillar_num_from_key(key)
        if num is None or num < 1 or num > 7:
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        threshold_key = f"p{num}_blocking_threshold"
        threshold = thresholds.get(threshold_key, 0)
        if threshold and score < threshold:
            blocking.append({
                "pillar": f"P{num}",
                "score": score,
                "threshold": threshold,
                "deficit": threshold - score,
            })
    blocking.sort(key=lambda b: b["deficit"], reverse=True)
    return blocking


def derive_project_status(
    overall_score: float,
    blocking_pillars: List[Dict[str, Any]],
    thresholds: Dict[str, Any],
) -> str:
    """Status do projeto considerando blocking pillars + bandas de composite.

    Hierarquia (mais restritiva ganha):
        - BLOCKED: qualquer pilar bloqueante.
        - READY: overall >= ready_threshold.
        - NEEDS_REVIEW: overall >= needs_review_threshold.
        - AT_RISK: overall >= at_risk_threshold.
        - BLOCKED: caso contrário (overall abaixo do mínimo).
    """
    if blocking_pillars:
        return "BLOCKED"

    ready = thresholds.get("ready_threshold", 90)
    needs_review = thresholds.get("needs_review_threshold", 70)
    at_risk = thresholds.get("at_risk_threshold", 50)

    if overall_score >= ready:
        return "READY"
    if overall_score >= needs_review:
        return "NEEDS_REVIEW"
    if overall_score >= at_risk:
        return "AT_RISK"
    return "BLOCKED"
