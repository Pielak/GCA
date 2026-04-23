"""MVP 23 Fase 23.4 — Validação estática pós-scaffold contra RNF_CONTRACTS.

Decisão canônica #3 do MVP 23: validação é **determinística, sem LLM no caminho
crítico**. Roda grep estruturado (regex) sobre os arquivos gerados pelo codegen
e verifica se os middlewares/decorators/patterns declarados no contrato RNF
do OCG aparecem no código.

Contrato:
  - entrada: `RnfContracts` (view canônica) + lista de arquivos `[{path, content}]`
  - saída: `ValidationReport` com violações por arquivo e severidade
  - blocker violation → caller deve rebaixar `status="todo"` no arquivo e
    emitir audit `CODEGEN_RNF_VIOLATION`

Padrões negativos (prefixo `!`): se o padrão aparecer no código, é violação.
Ex: ``!logger\\.info.*password`` — se ``logger.info`` com "password" casar, falha.

Padrões positivos: se **nenhum** padrão de uma lista aparecer no arquivo, é
violação. Ex: rate_limit_middleware com `[slowapi|Limiter|express-rate-limit]`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.rnf_contracts import RnfContracts, extract_static_checks


@dataclass(frozen=True)
class RnfViolation:
    check_id: str
    label: str
    severity: str  # "blocker" | "warning"
    file_path: str
    reason: str


@dataclass(frozen=True)
class RnfValidationReport:
    violations: tuple[RnfViolation, ...] = ()
    checks_evaluated: int = 0
    files_scanned: int = 0

    @property
    def has_blocker(self) -> bool:
        return any(v.severity == "blocker" for v in self.violations)

    @property
    def blocker_files(self) -> set[str]:
        return {v.file_path for v in self.violations if v.severity == "blocker"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": [
                {
                    "check_id": v.check_id,
                    "label": v.label,
                    "severity": v.severity,
                    "file_path": v.file_path,
                    "reason": v.reason,
                }
                for v in self.violations
            ],
            "checks_evaluated": self.checks_evaluated,
            "files_scanned": self.files_scanned,
            "has_blocker": self.has_blocker,
            "blocker_files": sorted(self.blocker_files),
        }


#: Extensões canônicas que o validador considera "código" (ignora .md/.json/.yml
#: porque a regra se aplica a middlewares declarados no runtime).
_CODE_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".rb",
    ".go", ".rs", ".cs", ".php", ".cpp", ".h", ".hpp",
)


def validate_files(
    rnf: RnfContracts,
    files: Iterable[dict[str, Any]],
) -> RnfValidationReport:
    """Valida lista de arquivos contra contrato RNF.

    `files`: iterável de dicts com ao menos `path` (str) e `content` (str).
    Arquivos sem extensão canônica de código são ignorados (contrato não
    se aplica a docs/config).

    Sem contrato (rnf.is_empty) ou sem checks aplicáveis → report vazio.
    """
    if rnf.is_empty:
        return RnfValidationReport()

    checks = extract_static_checks(rnf)
    if not checks:
        return RnfValidationReport()

    # Normaliza arquivos em memória (path, content, is_code)
    normalized: list[tuple[str, str]] = []
    for f in files:
        path = f.get("path") or f.get("file_path") or ""
        content = f.get("content") or ""
        if not path or not content:
            continue
        if not path.lower().endswith(_CODE_EXTENSIONS):
            continue
        normalized.append((path, content))

    violations: list[RnfViolation] = []

    for check in checks:
        scope = check.get("scope", "per_file")
        if scope == "per_file":
            for path, content in normalized:
                v = _evaluate_check_on_file(check, path, content)
                if v:
                    violations.append(v)
        elif scope == "any_file_in_module":
            v = _evaluate_check_on_module(check, normalized)
            if v:
                violations.append(v)

    return RnfValidationReport(
        violations=tuple(violations),
        checks_evaluated=len(checks),
        files_scanned=len(normalized),
    )


def _evaluate_check_on_file(
    check: dict[str, Any], path: str, content: str,
) -> RnfViolation | None:
    """Aplica check `per_file`: patterns positivos/negativos no arquivo único.

    Convenção canônica:
      - pattern com prefixo `!` → NEGATIVO (se match encontrado, é violação)
      - caso contrário → POSITIVO (pelo menos um tem que casar)

    Se todos os patterns são negativos e nenhum casou → arquivo ok.
    Se algum padrão negativo casou → violação imediata.
    Se tem padrões positivos e nenhum casou → violação por ausência.
    """
    patterns: list[str] = list(check.get("patterns") or [])
    if not patterns:
        return None

    negatives = [p[1:] for p in patterns if p.startswith("!")]
    positives = [p for p in patterns if not p.startswith("!")]

    # Negativos: match = falha
    for neg in negatives:
        try:
            if re.search(neg, content):
                return RnfViolation(
                    check_id=check["id"],
                    label=check["label"],
                    severity=check.get("severity", "blocker"),
                    file_path=path,
                    reason=f"padrão proibido encontrado: /{neg}/",
                )
        except re.error:
            continue

    # Positivos: precisa pelo menos um match
    if positives:
        matched_any = False
        for pos in positives:
            try:
                if re.search(pos, content):
                    matched_any = True
                    break
            except re.error:
                continue
        if not matched_any:
            return RnfViolation(
                check_id=check["id"],
                label=check["label"],
                severity=check.get("severity", "blocker"),
                file_path=path,
                reason=(
                    f"nenhum padrão canônico encontrado "
                    f"(esperado um de: {positives})"
                ),
            )

    return None


def _evaluate_check_on_module(
    check: dict[str, Any], files: list[tuple[str, str]],
) -> RnfViolation | None:
    """Aplica check `any_file_in_module`: basta um arquivo do módulo satisfazer.

    Usado por checks como `rate_limit_middleware` — não precisa estar em todos
    os endpoints; basta o decorator/middleware aparecer em algum arquivo do
    scaffold. Se nenhum arquivo cobre → violação sintética com file_path="*".
    """
    patterns: list[str] = [p for p in (check.get("patterns") or []) if not p.startswith("!")]
    if not patterns or not files:
        return None

    for _path, content in files:
        for pat in patterns:
            try:
                if re.search(pat, content):
                    return None  # satisfeito
            except re.error:
                continue

    return RnfViolation(
        check_id=check["id"],
        label=check["label"],
        severity=check.get("severity", "blocker"),
        file_path="*",
        reason=(
            f"nenhum arquivo do módulo contém padrão canônico "
            f"(esperado um de: {patterns})"
        ),
    )
