"""MVP 20 Fase 20.2 — SonarAdapter (SonarQube / SonarCloud).

Consome `/api/issues/search` da REST API do Sonar. Auth via Basic
(`token:` com password vazio) para SonarCloud, ou token de usuário
em `Authorization: Bearer <token>` em SonarQube on-prem.

Severity mapping (Sonar → canônico):
    BLOCKER    → critical
    CRITICAL   → high
    MAJOR      → medium
    MINOR      → low
    INFO       → info

Segue Adapter-Port pattern do MVP 20.
"""
from __future__ import annotations

import base64
from typing import Optional

import httpx
import structlog

from app.services.ports.security_scanner_port import (
    CanonicalSeverity,
    FindingPayload,
    ScannerAPIError,
    ScannerAuthError,
    ScannerConfig,
    ScannerConfigError,
    ScannerRateLimitError,
    SecurityScannerPort,
)


logger = structlog.get_logger(__name__)


_SEVERITY_MAP: dict[str, CanonicalSeverity] = {
    "BLOCKER": "critical",
    "CRITICAL": "high",
    "MAJOR": "medium",
    "MINOR": "low",
    "INFO": "info",
}


class SonarAdapter(SecurityScannerPort):
    scanner = "sonar"

    _client: Optional[httpx.AsyncClient]

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None, timeout: float = 15.0):
        self._client = client
        self._timeout = timeout

    def normalize_severity(self, raw: str) -> CanonicalSeverity:
        return _SEVERITY_MAP.get((raw or "").upper(), "low")

    def _auth_header(self, config: ScannerConfig) -> dict[str, str]:
        token = config.credentials.get("token")
        if not token:
            raise ScannerConfigError(
                "Sonar exige credentials={'token': ...}"
            )
        # Sonar aceita Basic auth com "token:" (password vazio).
        raw = f"{token}:".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    async def _request(
        self,
        config: ScannerConfig,
        path: str,
        params: dict,
    ) -> dict:
        base = config.base_url.rstrip("/")
        url = f"{base}{path}"
        headers = self._auth_header(config)

        async def _do(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(url, params=params, headers=headers, timeout=self._timeout)

        try:
            if self._client is not None:
                resp = await _do(self._client)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await _do(c)
        except httpx.HTTPError as exc:
            raise ScannerAPIError(f"Sonar HTTP error: {exc}") from exc

        if resp.status_code in (401, 403):
            raise ScannerAuthError(f"Sonar auth rejected ({resp.status_code})")
        if resp.status_code == 429:
            raise ScannerRateLimitError("Sonar 429 — backoff necessário")
        if resp.status_code >= 400:
            raise ScannerAPIError(f"Sonar {resp.status_code}: {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise ScannerAPIError("Sonar returned non-JSON") from exc

    async def fetch_findings(
        self,
        config: ScannerConfig,
    ) -> list[FindingPayload]:
        if not config.project_key:
            raise ScannerConfigError(
                "Sonar exige project_key (componentKeys) no ScannerConfig"
            )

        all_findings: list[FindingPayload] = []
        page = 1
        page_size = 100
        while True:
            data = await self._request(
                config, "/api/issues/search",
                params={
                    "componentKeys": config.project_key,
                    "ps": page_size,
                    "p": page,
                    "resolved": "false",
                    "types": "VULNERABILITY,CODE_SMELL,BUG",
                },
            )
            issues = data.get("issues", []) or []
            for issue in issues:
                # Localização (textRange.startLine/endLine ou component path).
                comp = issue.get("component", "")
                # Sonar component vem como "projectKey:path/to/file".
                file_path = None
                if ":" in comp:
                    file_path = comp.split(":", 1)[1]
                text_range = issue.get("textRange") or {}
                url = None
                base = config.base_url.rstrip("/")
                if issue.get("key"):
                    url = f"{base}/project/issues?id={config.project_key}&issues={issue['key']}&open={issue['key']}"

                all_findings.append(FindingPayload(
                    external_id=issue.get("key", ""),
                    severity=self.normalize_severity(issue.get("severity", "")),
                    title=issue.get("message", "") or "(sem título)",
                    description=None,
                    file_path=file_path,
                    line_start=text_range.get("startLine"),
                    line_end=text_range.get("endLine"),
                    cwe_id=None,  # Sonar usa próprio rule_id
                    rule_id=issue.get("rule"),
                    url=url,
                    status_hint=None,
                ))
            total = data.get("total", 0)
            if page * page_size >= total or not issues:
                break
            page += 1
            if page > 20:
                # Safety cap — 2000 findings por projeto é mais que razoável.
                break

        return all_findings
