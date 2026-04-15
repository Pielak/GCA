"""Validação de código multi-linguagem (Tier 1).

Expõe `validate_code(code, language)` que retorna uma lista de `ValidationIssue`.
Cada issue tem linha (1-based), coluna, mensagem e severidade (error|warning).
Linguagens não suportadas retornam `supported=False` no resultado.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import io
import json
import tomllib
from typing import List, Optional


@dataclass
class ValidationIssue:
    """Uma ocorrência de problema encontrada no código."""

    line: int
    column: int
    message: str
    severity: str  # "error" | "warning"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationResult:
    """Resultado da validação de um bloco de código."""

    supported: bool
    language: str
    issues: List[ValidationIssue]

    @property
    def valid(self) -> bool:
        return self.supported and not any(i.severity == "error" for i in self.issues)

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "language": self.language,
            "valid": self.valid,
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Python — pyflakes
# ---------------------------------------------------------------------------

def _validate_python(code: str) -> List[ValidationIssue]:
    """Executa pyflakes no código e traduz reporter para ValidationIssue."""
    from pyflakes.api import check
    from pyflakes.reporter import Reporter

    warn_buf = io.StringIO()
    err_buf = io.StringIO()
    reporter = Reporter(warn_buf, err_buf)
    check(code, filename="<input>", reporter=reporter)

    issues: List[ValidationIssue] = []
    for raw in err_buf.getvalue().splitlines():
        # formato: "<input>:LINE:COL: mensagem"
        parts = raw.split(":", 3)
        if len(parts) >= 4:
            try:
                line = int(parts[1])
                col = int(parts[2])
                message = parts[3].strip()
            except ValueError:
                continue
            issues.append(ValidationIssue(line=line, column=col, message=message, severity="error"))
    for raw in warn_buf.getvalue().splitlines():
        parts = raw.split(":", 3)
        if len(parts) >= 3:
            try:
                line = int(parts[1])
                message_tail = parts[-1].strip()
            except ValueError:
                continue
            # Pyflakes só reporta problemas reais (não estilo).
            # 'unused' → warning; resto (undefined name, redefinition, etc.) → error.
            sev = "warning" if "unused" in message_tail.lower() else "error"
            issues.append(ValidationIssue(line=line, column=1, message=message_tail, severity=sev))
    return issues


# ---------------------------------------------------------------------------
# JavaScript / TypeScript — esprima
# ---------------------------------------------------------------------------

def _validate_js_like(code: str) -> List[ValidationIssue]:
    """Parse JS/TS com esprima. TS com sintaxe só-de-tipos pode não parsear."""
    import esprima

    try:
        esprima.parseScript(code, tolerant=False, loc=True)
        return []
    except esprima.Error as exc:
        line = getattr(exc, "lineNumber", 1) or 1
        col = getattr(exc, "column", 1) or 1
        msg = str(exc)
        return [ValidationIssue(line=line, column=col, message=msg, severity="error")]


# ---------------------------------------------------------------------------
# JSON / YAML / TOML
# ---------------------------------------------------------------------------

def _validate_json(code: str) -> List[ValidationIssue]:
    try:
        json.loads(code)
        return []
    except json.JSONDecodeError as exc:
        return [ValidationIssue(line=exc.lineno, column=exc.colno, message=exc.msg, severity="error")]


def _validate_yaml(code: str) -> List[ValidationIssue]:
    import yaml

    try:
        yaml.safe_load(code)
        return []
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (mark.line + 1) if mark else 1
        col = (mark.column + 1) if mark else 1
        return [ValidationIssue(line=line, column=col, message=str(exc), severity="error")]


def _validate_toml(code: str) -> List[ValidationIssue]:
    try:
        tomllib.loads(code)
        return []
    except tomllib.TOMLDecodeError as exc:
        return [ValidationIssue(line=1, column=1, message=str(exc), severity="error")]


# ---------------------------------------------------------------------------
# Roteamento
# ---------------------------------------------------------------------------

_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


def detect_language(path: Optional[str], explicit: Optional[str] = None) -> Optional[str]:
    """Retorna 'python'|'javascript'|'typescript'|'json'|'yaml'|'toml' ou None."""
    if explicit:
        return explicit.lower()
    if not path:
        return None
    for ext, lang in _LANGUAGE_BY_EXT.items():
        if path.lower().endswith(ext):
            return lang
    return None


def validate_code(code: str, language: Optional[str], path: Optional[str] = None) -> ValidationResult:
    """Valida `code`. `language` explícito sobrepõe inferência por `path`."""
    lang = detect_language(path, language)
    if not lang:
        return ValidationResult(supported=False, language="unknown", issues=[])

    if lang == "python":
        return ValidationResult(supported=True, language=lang, issues=_validate_python(code))
    if lang in ("javascript", "typescript"):
        return ValidationResult(supported=True, language=lang, issues=_validate_js_like(code))
    if lang == "json":
        return ValidationResult(supported=True, language=lang, issues=_validate_json(code))
    if lang == "yaml":
        return ValidationResult(supported=True, language=lang, issues=_validate_yaml(code))
    if lang == "toml":
        return ValidationResult(supported=True, language=lang, issues=_validate_toml(code))

    return ValidationResult(supported=False, language=lang, issues=[])
