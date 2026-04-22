"""MVP 20 Fase 20.2 — GitleaksAdapter.

Duas modalidades canônicas:

  Modo 1 — "consume report" (recomendado): cliente já roda gitleaks no
  CI e posta o JSON via endpoint de upload. GCA só consome o relatório
  passado em `config.extra['report_json']` (string JSON ou dict).

  Modo 2 — "run local" (V1 simplificado): se `config.extra['repo_path']`
  existe e é diretório legível pelo backend, executa
  `gitleaks detect --source <path> --report-format json --report-path -`
  e parseia o stdout. Requer gitleaks instalado no container.

V1 prioriza Modo 1 — mais seguro, mais auditável, alinha com filosofia
"GCA consome, não executa segurança do cliente".

Severity: gitleaks não reporta severity nativa de cada finding. Canônico:
secrets vazados são SEMPRE `high` (a menos que regra específica diga
critical). Finding individual vem classificado pela regra.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Optional

import structlog

from app.services.ports.security_scanner_port import (
    CanonicalSeverity,
    FindingPayload,
    ScannerAPIError,
    ScannerConfig,
    ScannerConfigError,
    SecurityScannerPort,
)


logger = structlog.get_logger(__name__)


# Regras específicas conhecidas do gitleaks → severity canônica.
# Fallback: high (secret vazado é default high).
_RULE_SEVERITY_OVERRIDES: dict[str, CanonicalSeverity] = {
    "private-key": "critical",
    "aws-access-token": "critical",
    "aws-secret-key": "critical",
    "gcp-api-key": "critical",
    "gcp-service-account": "critical",
    "stripe-access-token": "critical",
    "github-pat": "critical",
    "slack-bot-token": "high",
    "generic-api-key": "high",
}


class GitleaksAdapter(SecurityScannerPort):
    scanner = "gitleaks"

    def normalize_severity(self, raw: str) -> CanonicalSeverity:
        # Gitleaks não reporta severity; a escolha vem da regra.
        key = (raw or "").lower()
        return _RULE_SEVERITY_OVERRIDES.get(key, "high")

    async def fetch_findings(self, config: ScannerConfig) -> list[FindingPayload]:
        report = config.extra.get("report_json")
        if report is not None:
            return self._parse_report(report)

        repo_path = config.extra.get("repo_path")
        if repo_path:
            return self._run_local(repo_path)

        raise ScannerConfigError(
            "Gitleaks exige config.extra['report_json'] (modo consume) "
            "OR config.extra['repo_path'] (modo local). Nenhum encontrado."
        )

    def _parse_report(self, report: Any) -> list[FindingPayload]:
        if isinstance(report, str):
            try:
                data = json.loads(report)
            except json.JSONDecodeError as exc:
                raise ScannerAPIError(f"Gitleaks report não é JSON válido: {exc}") from exc
        elif isinstance(report, (list, dict)):
            data = report
        else:
            raise ScannerConfigError(
                f"Gitleaks report deve ser str/list/dict, recebido {type(report).__name__}"
            )

        items = data if isinstance(data, list) else data.get("findings", []) or []
        findings: list[FindingPayload] = []
        for item in items:
            rule_id = item.get("RuleID") or item.get("rule_id") or ""
            commit = item.get("Commit") or item.get("commit") or ""
            file_path = item.get("File") or item.get("file") or ""
            line_start = item.get("StartLine") or item.get("start_line")
            line_end = item.get("EndLine") or item.get("end_line")
            fingerprint = item.get("Fingerprint") or item.get("fingerprint")

            # external_id determinístico pra idempotência.
            external_id = fingerprint or f"{commit}:{file_path}:{line_start}:{rule_id}"

            findings.append(FindingPayload(
                external_id=external_id,
                severity=self.normalize_severity(rule_id),
                title=f"Secret leak: {rule_id}" if rule_id else "Secret leak",
                description=item.get("Description") or item.get("Secret", "")[:200],
                file_path=file_path or None,
                line_start=line_start,
                line_end=line_end,
                cwe_id="CWE-798",  # Use of Hard-coded Credentials
                rule_id=rule_id,
                url=None,
                status_hint="open",
            ))
        return findings

    def _run_local(self, repo_path: str) -> list[FindingPayload]:
        """Executa gitleaks localmente — modo auxiliar, V1 conservador.

        Se gitleaks não está instalado, levanta ScannerConfigError com
        mensagem clara apontando pra modo consume_report como alternativa.
        """
        try:
            result = subprocess.run(
                ["gitleaks", "detect",
                 "--source", repo_path,
                 "--report-format", "json",
                 "--report-path", "-",
                 "--no-banner",
                 "--exit-code", "0"],
                capture_output=True, text=True, timeout=120,
            )
        except FileNotFoundError as exc:
            raise ScannerConfigError(
                "gitleaks não está instalado no container. Use modo "
                "consume com config.extra['report_json']."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ScannerAPIError("gitleaks excedeu 120s") from exc

        if result.returncode not in (0, 1):
            raise ScannerAPIError(
                f"gitleaks retornou {result.returncode}: {result.stderr[:200]}"
            )
        if not result.stdout.strip():
            return []
        return self._parse_report(result.stdout)
