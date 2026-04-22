"""MVP 20 Fase 20.2 — SnykAdapter (Snyk REST API).

Consome `/rest/orgs/{org_id}/issues` ou `/api/v1/org/{org_id}/project/{proj_id}/issues`
do Snyk. Auth via `Authorization: token <api_token>`.

Severity mapping (Snyk → canônico):
    critical   → critical
    high       → high
    medium     → medium
    low        → low
"""
from __future__ import annotations

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
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
}


class SnykAdapter(SecurityScannerPort):
    scanner = "snyk"

    _client: Optional[httpx.AsyncClient]

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None, timeout: float = 15.0):
        self._client = client
        self._timeout = timeout

    def normalize_severity(self, raw: str) -> CanonicalSeverity:
        return _SEVERITY_MAP.get((raw or "").lower(), "low")

    def _headers(self, config: ScannerConfig) -> dict[str, str]:
        token = config.credentials.get("api_token")
        if not token:
            raise ScannerConfigError(
                "Snyk exige credentials={'api_token': ...}"
            )
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.api+json",
        }

    async def _request(self, config: ScannerConfig, path: str, params: dict) -> dict:
        base = config.base_url.rstrip("/") or "https://api.snyk.io"
        url = f"{base}{path}"
        headers = self._headers(config)

        async def _do(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(url, params=params, headers=headers, timeout=self._timeout)

        try:
            if self._client is not None:
                resp = await _do(self._client)
            else:
                async with httpx.AsyncClient() as c:
                    resp = await _do(c)
        except httpx.HTTPError as exc:
            raise ScannerAPIError(f"Snyk HTTP error: {exc}") from exc

        if resp.status_code in (401, 403):
            raise ScannerAuthError(f"Snyk auth rejected ({resp.status_code})")
        if resp.status_code == 429:
            raise ScannerRateLimitError("Snyk 429")
        if resp.status_code >= 400:
            raise ScannerAPIError(f"Snyk {resp.status_code}: {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise ScannerAPIError("Snyk returned non-JSON") from exc

    async def fetch_findings(self, config: ScannerConfig) -> list[FindingPayload]:
        # project_key = org_id; config.extra['snyk_project_id'] opcional.
        if not config.project_key:
            raise ScannerConfigError(
                "Snyk exige project_key = org_id no ScannerConfig"
            )

        org_id = config.project_key
        snyk_project_id = config.extra.get("snyk_project_id")

        # Usa API REST v2024+: /rest/orgs/{org_id}/issues.
        params = {"version": "2024-10-15", "limit": 100}
        if snyk_project_id:
            params["scan_item.id"] = snyk_project_id
            params["scan_item.type"] = "project"

        data = await self._request(config, f"/rest/orgs/{org_id}/issues", params)

        findings: list[FindingPayload] = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {}) or {}
            classes = attrs.get("classes") or []
            cwe = None
            for c in classes:
                if c.get("source") == "CWE":
                    cwe = c.get("id")
                    break
            coordinates = attrs.get("coordinates") or []
            file_path = None
            line_start = None
            if coordinates:
                first_coord = coordinates[0]
                representations = first_coord.get("representations") or []
                for rep in representations:
                    src = rep.get("sourceLocation") or {}
                    if src.get("file"):
                        file_path = src["file"]
                        line_start = src.get("region", {}).get("start", {}).get("line")
                        break

            findings.append(FindingPayload(
                external_id=item.get("id", ""),
                severity=self.normalize_severity(attrs.get("effective_severity_level", "")),
                title=attrs.get("title", "") or "(sem título)",
                description=attrs.get("description"),
                file_path=file_path,
                line_start=line_start,
                cwe_id=cwe,
                rule_id=attrs.get("key"),
                url=None,
                status_hint="fixed" if attrs.get("status") == "resolved" else "open",
            ))

        return findings
