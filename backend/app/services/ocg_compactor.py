"""Compactador do OCG para uso em prompts LLM (Fase 3 do refactor reativo).

Reduz o tamanho do OCG enviado ao LLM **sem perder valores estruturados**
(scores, listas, items de checklist). Apenas trima textos explicativos
verbosos (rationale, description, reasoning, etc.) que o LLM raramente
precisa modificar e que dominam o tamanho do payload em projetos grandes.

Uso típico:
    compact = compact_ocg_for_prompt(full_ocg)
    # compact tem mesmo schema; campos como 'rationale' viram '<trimmed:N chars>'.
    # O delta_applier opera no full_ocg original — paths permanecem válidos
    # porque a estrutura é preservada.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

# Threshold abaixo do qual NÃO compactamos (overhead não vale a pena).
# Em chars; ~4 chars/token, então 8000 chars ≈ 2000 tokens.
DEFAULT_MIN_SIZE_CHARS = 8000

# Marcadores de campos textuais que serão trimados, na forma "path.regex":
#  - dot-notation segments
#  - "*" matcha qualquer key/index
_TRIM_TARGETS: list[tuple[str, ...]] = [
    # Stack recommendation: cada subsetor (frontend, backend, etc.) tem rationale
    ("STACK_RECOMMENDATION", "*", "rationale"),
    # Testing: cada modalidade tem rationale
    ("TESTING_REQUIREMENTS", "*", "rationale"),
    # Architecture overview tem description longa
    ("ARCHITECTURE_OVERVIEW", "description"),
    ("ARCHITECTURE_OVERVIEW", "data_flow"),
    # Risk analysis: cada item tem impact + mitigation
    ("RISK_ANALYSIS", "high_risks", "*", "impact"),
    ("RISK_ANALYSIS", "high_risks", "*", "mitigation"),
    ("RISK_ANALYSIS", "medium_risks", "*", "impact"),
    ("RISK_ANALYSIS", "medium_risks", "*", "mitigation"),
    # Critical findings: recommendation pode ser longa
    ("CRITICAL_FINDINGS", "recommendation"),
    # Approval: reason pode crescer
    ("APPROVAL_STATUS", "reason"),
]


def _trim_string(s: str, max_chars: int = 80) -> str:
    """Reduz string para `max_chars` adicionando indicador de trimming."""
    if not isinstance(s, str) or len(s) <= max_chars:
        return s
    return f"{s[:max_chars].rstrip()}… <trimmed:{len(s)} chars>"


def _apply_trim(node: Any, target_segs: tuple[str, ...]) -> None:
    """Aplica trim recursivamente seguindo `target_segs`. Mutação in-place."""
    if not target_segs:
        return

    head, rest = target_segs[0], target_segs[1:]

    if head == "*":
        if isinstance(node, dict):
            for v in node.values():
                if isinstance(v, (dict, list)):
                    _apply_trim(v, rest) if rest else None
                elif rest == () and isinstance(v, str):
                    pass  # last segment trim acontece no nível do parent
        elif isinstance(node, list):
            for item in node:
                _apply_trim(item, rest)
        return

    if isinstance(node, dict):
        if head not in node:
            return
        if not rest:
            # Último segmento — trim direto
            if isinstance(node[head], str):
                node[head] = _trim_string(node[head])
        else:
            _apply_trim(node[head], rest)
    # arrays só fazem sentido com '*' antes; ignoramos índices literais aqui


def _trim_via_targets(ocg: Dict[str, Any]) -> None:
    """Aplica todos os _TRIM_TARGETS no OCG (in-place). Iteração simples e robusta."""
    for target in _TRIM_TARGETS:
        # Last segment é a property a trimar; navegação até parent acontece
        # nos segmentos anteriores. Então tratamos o ultimo separadamente.
        if not target:
            continue
        parent_path, leaf = target[:-1], target[-1]
        # Navegar até cada possível parent (suporta '*' em listas/dicts)
        parents = _enumerate_parents(ocg, parent_path)
        for parent in parents:
            if isinstance(parent, dict) and leaf in parent and isinstance(parent[leaf], str):
                parent[leaf] = _trim_string(parent[leaf])


def _enumerate_parents(node: Any, path: tuple[str, ...]) -> list[Any]:
    """Coleta todos os 'parents' alcançáveis seguindo `path` com suporte a '*'.

    Ex: para path=('STACK_RECOMMENDATION','*'), retorna lista com os dicts
    frontend/backend/database/etc. Cada um deles é um candidato a ter o
    `leaf` trimado.
    """
    if not path:
        return [node]

    head, rest = path[0], path[1:]

    if head == "*":
        if isinstance(node, dict):
            collected: list[Any] = []
            for v in node.values():
                collected.extend(_enumerate_parents(v, rest))
            return collected
        if isinstance(node, list):
            collected = []
            for item in node:
                collected.extend(_enumerate_parents(item, rest))
            return collected
        return []

    if isinstance(node, dict):
        if head in node:
            return _enumerate_parents(node[head], rest)
        return []

    return []


def compact_ocg_for_prompt(
    ocg: Dict[str, Any],
    min_size_chars: int = DEFAULT_MIN_SIZE_CHARS,
) -> Dict[str, Any]:
    """Devolve cópia do OCG com textos verbosos trimados, se vale a pena.

    Critérios:
        - Se serialização do OCG <= ``min_size_chars``: devolve cópia
          inalterada (overhead não compensa).
        - Caso contrário: aplica trims em campos conhecidos como verbose
          (rationale, description, mitigation, etc.). Estrutura preservada;
          paths em dot-notation continuam válidos para o delta applier.

    Importante:
        - Valores numéricos (scores), listas de strings (DELIVERABLES) e
          item-arrays (COMPLIANCE_CHECKLIST) NÃO são tocados.
        - O OCG passado como input não é mutado (deepcopy interno).
    """
    if not isinstance(ocg, dict):
        return ocg  # type: ignore[return-value]

    # Heurística de tamanho via repr
    try:
        import json
        size = len(json.dumps(ocg, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        size = 0

    if size <= min_size_chars:
        return deepcopy(ocg)

    compact = deepcopy(ocg)
    _trim_via_targets(compact)
    return compact
