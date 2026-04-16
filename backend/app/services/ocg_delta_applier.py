"""Aplicador determinístico de deltas no OCG (Objeto de Contexto Global).

Permite que o OCGUpdaterService peça ao LLM **apenas o delta** (~500 tokens)
em vez do OCG inteiro modificado (~5000 tokens). O delta é então aplicado
localmente, deterministicamente, com optimistic concurrency e whitelist de
campos.

Design:
    - Path em dot-notation (ex: ``PILLAR_SCORES.P3_Scope_Management``).
    - Operações suportadas: ``replace`` (set scalar/object) e ``append``
      (push em array).
    - Optimistic concurrency: ``replace`` aceita ``old_value``; se o valor
      atual no OCG diverge, o delta é rejeitado (não-fatal — vai para a
      lista de rejeitados, com motivo).
    - Whitelist de top-level keys: nada fora de ``_ALLOWED_TOP_LEVEL`` é
      tocado, evitando que o LLM injete campos arbitrários.
    - Sem rede, sem LLM — totalmente testável via tabela.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

# Top-level keys que o delta pode tocar. Qualquer outra é rejeitada com
# `top_level_not_allowed`. Adicione aqui se o schema do OCG crescer.
_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset({
    "PROJECT_PROFILE",
    "PILLAR_SCORES",
    "COMPOSITE_SCORE",
    "STACK_RECOMMENDATION",
    "CRITICAL_FINDINGS",
    "TESTING_REQUIREMENTS",
    "COMPLIANCE_CHECKLIST",
    "DELIVERABLES",
    "ARCHITECTURE_OVERVIEW",
    "RISK_ANALYSIS",
    "APPROVAL_STATUS",
})

OP_REPLACE = "replace"
OP_APPEND = "append"
SUPPORTED_OPS: frozenset[str] = frozenset({OP_REPLACE, OP_APPEND})


class DeltaError(Exception):
    """Erro estrutural num delta — formato inválido, op desconhecida, etc."""


def _split_path(path: Any) -> List[str]:
    """Divide ``"A.B.C"`` em ``["A", "B", "C"]``. Levanta DeltaError em entrada inválida."""
    if not isinstance(path, str) or not path:
        raise DeltaError(f"path inválido: {path!r}")
    parts = [p for p in path.split(".") if p]
    if not parts:
        raise DeltaError(f"path vazio após split: {path!r}")
    return parts


def _navigate_to_parent(
    obj: Dict[str, Any],
    parts: List[str],
) -> Tuple[Any, str]:
    """Navega ``obj`` seguindo ``parts[:-1]`` e retorna ``(parent, last_segment)``.

    Para arrays, segmento numérico é interpretado como índice. Levanta
    DeltaError se o caminho não existe ou tem tipo incompatível.
    """
    cur: Any = obj
    for p in parts[:-1]:
        if isinstance(cur, dict):
            if p not in cur:
                raise DeltaError(f"segmento não encontrado: {p}")
            cur = cur[p]
        elif isinstance(cur, list):
            try:
                idx = int(p)
            except ValueError as exc:
                raise DeltaError(
                    f"esperado índice numérico em lista, recebido {p!r}"
                ) from exc
            if idx < 0 or idx >= len(cur):
                raise DeltaError(f"índice fora de range: {idx}")
            cur = cur[idx]
        else:
            raise DeltaError(
                f"tipo {type(cur).__name__} não navegável em segmento {p!r}"
            )
    return cur, parts[-1]


def _apply_replace(
    ocg: Dict[str, Any],
    delta: Dict[str, Any],
) -> Tuple[bool, str]:
    """Aplica delta `replace`. Optimistic concurrency via `old_value` opcional."""
    parts = _split_path(delta.get("path"))
    parent, key = _navigate_to_parent(ocg, parts)

    if isinstance(parent, dict):
        if key not in parent:
            return False, f"chave {key!r} não existe no parent (path={delta.get('path')})"
        if "old_value" in delta and parent[key] != delta["old_value"]:
            return (
                False,
                f"old_value não confere em {delta['path']!r}: "
                f"esperado={delta['old_value']!r}, atual={parent[key]!r}",
            )
        parent[key] = delta.get("new_value")
        return True, ""

    if isinstance(parent, list):
        try:
            idx = int(key)
        except ValueError:
            return False, f"esperado índice numérico para replace em lista, recebido {key!r}"
        if idx < 0 or idx >= len(parent):
            return False, f"índice fora de range: {idx}"
        if "old_value" in delta and parent[idx] != delta["old_value"]:
            return (
                False,
                f"old_value não confere em índice {idx}: "
                f"esperado={delta['old_value']!r}, atual={parent[idx]!r}",
            )
        parent[idx] = delta.get("new_value")
        return True, ""

    return False, f"replace requer parent dict|list, encontrado {type(parent).__name__}"


def _apply_append(
    ocg: Dict[str, Any],
    delta: Dict[str, Any],
) -> Tuple[bool, str]:
    """Aplica delta `append`. Path deve apontar para uma lista existente."""
    parts = _split_path(delta.get("path"))
    cur: Any = ocg
    for p in parts:
        if not isinstance(cur, dict):
            return False, f"navegação inválida no segmento {p!r}: tipo {type(cur).__name__}"
        if p not in cur:
            return False, f"path não existe para append: {delta.get('path')!r}"
        cur = cur[p]
    if not isinstance(cur, list):
        return False, f"append requer lista, encontrado {type(cur).__name__}"
    cur.append(delta.get("value"))
    return True, ""


def _apply_one(ocg: Dict[str, Any], delta: Dict[str, Any]) -> Tuple[bool, str]:
    """Aplica um delta in-place. Retorna (applied, motivo_se_rejeitado)."""
    if not isinstance(delta, dict):
        return False, f"delta deve ser objeto, recebido {type(delta).__name__}"

    op = delta.get("op")
    if op not in SUPPORTED_OPS:
        return False, f"op não suportada: {op!r} (suportadas: {sorted(SUPPORTED_OPS)})"

    path = delta.get("path")
    try:
        parts = _split_path(path)
    except DeltaError as exc:
        return False, str(exc)

    if parts[0] not in _ALLOWED_TOP_LEVEL:
        return False, f"top-level {parts[0]!r} não está na whitelist"

    try:
        if op == OP_REPLACE:
            return _apply_replace(ocg, delta)
        if op == OP_APPEND:
            return _apply_append(ocg, delta)
    except DeltaError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, f"erro inesperado: {type(exc).__name__}: {exc}"

    return False, f"fluxo não tratado para op={op}"


def apply_deltas(
    current_ocg: Dict[str, Any],
    deltas: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Aplica lista de deltas a uma cópia profunda do OCG.

    Args:
        current_ocg: estado atual do OCG (não é mutado).
        deltas: lista de deltas no formato definido no docstring do módulo.

    Returns:
        Tupla ``(updated_ocg, applied, rejected)`` onde:
            - ``updated_ocg``: cópia do OCG com deltas aplicados.
            - ``applied``: subconjunto de ``deltas`` que foi aceito.
            - ``rejected``: deltas rejeitados, cada um com chave extra
              ``_reason`` explicando por quê (path inválido, old_value
              divergente, etc.). Não-fatal: o caller decide se loga e segue
              ou aborta.
    """
    if not isinstance(deltas, list):
        raise DeltaError(f"deltas deve ser lista, recebido {type(deltas).__name__}")

    updated = deepcopy(current_ocg)
    applied: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for delta in deltas:
        ok, reason = _apply_one(updated, delta)
        if ok:
            applied.append(delta)
        else:
            entry = dict(delta) if isinstance(delta, dict) else {"_raw": delta}
            entry["_reason"] = reason
            rejected.append(entry)

    return updated, applied, rejected
