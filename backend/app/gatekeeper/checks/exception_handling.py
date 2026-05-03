"""Check AST para o pilar Conformidade do Gatekeeper.

Detecta violações da convenção docs/conventions/exception-handling.md
em código Python (escrito ou gerado pelo CodeGen).
"""
from __future__ import annotations
import ast
from typing import TypedDict


class Issue(TypedDict):
    line: int
    code: str
    message: str
    severity: str


def _has_raise(node: ast.ExceptHandler) -> bool:
    """True se o except contém um `raise` (re-lançamento ou novo)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Raise):
            return True
    return False


def _is_only_pass(node: ast.ExceptHandler) -> bool:
    return len(node.body) == 1 and isinstance(node.body[0], ast.Pass)


def _is_only_return_none(node: ast.ExceptHandler) -> bool:
    if len(node.body) != 1:
        return False
    stmt = node.body[0]
    if not isinstance(stmt, ast.Return):
        return False
    return stmt.value is None or (
        isinstance(stmt.value, ast.Constant) and stmt.value.value is None
    )


def check_source(source: str, filename: str = "<string>") -> list[Issue]:
    """Analisa código-fonte Python e retorna lista de violações."""
    issues: list[Issue] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [{
            "line": e.lineno or 0,
            "code": "EH000",
            "message": f"syntax error: {e.msg}",
            "severity": "error",
        }]

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        # EH001 — bare except
        if node.type is None:
            issues.append({
                "line": node.lineno,
                "code": "EH001",
                "message": "bare `except:` é proibido — capture exceção específica",
                "severity": "error",
            })
            continue

        # EH002 — except Exception sem raise
        is_blind = (
            isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")
        )
        if is_blind and not _has_raise(node):
            issues.append({
                "line": node.lineno,
                "code": "EH002",
                "message": "`except Exception` sem re-raise — re-lance via `raise ... from e`",
                "severity": "error",
            })

        # EH003 — pass silencioso
        if _is_only_pass(node):
            issues.append({
                "line": node.lineno,
                "code": "EH003",
                "message": "`except: pass` mascara erro — logue e re-lance",
                "severity": "error",
            })

        # EH004 — return None silencioso
        if _is_only_return_none(node):
            issues.append({
                "line": node.lineno,
                "code": "EH004",
                "message": "`return None` silencioso em except — logue e re-lance",
                "severity": "error",
            })

    return issues


def check_file(path: str) -> list[Issue]:
    with open(path, encoding="utf-8") as f:
        return check_source(f.read(), filename=path)
