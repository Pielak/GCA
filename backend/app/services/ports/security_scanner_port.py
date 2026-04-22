"""MVP 20 Fase 20.2 — Porta canônica de Security Scanner.

Decisão binária #3 do MVP 20: GCA consome findings de scanners commodity
(Sonar, Snyk, gitleaks) e mapeia pro OCG P7. GCA NÃO gera finding próprio
em V1.

Segue o mesmo Adapter-Port pattern da Fase 20.1 (`IssueTrackerPort`).
Ver memória `feedback_adapter_port_pattern.md`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


CanonicalSeverity = Literal["critical", "high", "medium", "low", "info"]
Scanner = Literal["sonar", "snyk", "gitleaks"]


@dataclass
class ScannerConfig:
    """Config opaca por projeto — adapter interpreta conforme seu schema.

    Campos canônicos:
      - `credentials`: dict com chaves do vault.
      - `base_url`: endpoint do scanner (on-prem ou cloud).
      - `project_key`: identificador do projeto no scanner (SonarQube project
        key, Snyk org_id/project_id, etc).
      - `extra`: campos específicos (repo path pro gitleaks, branch, etc).
    """

    credentials: dict[str, str]
    base_url: str
    project_key: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FindingPayload:
    """Payload canônico retornado pelo adapter.

    `external_id` é a chave natural do scanner (Sonar issue key, Snyk
    issue id, gitleaks fingerprint). Junto com `source_scanner` e
    `project_id` forma a UNIQUE canônica da migration 036.
    """

    external_id: str
    severity: CanonicalSeverity
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    cwe_id: Optional[str] = None
    rule_id: Optional[str] = None
    url: Optional[str] = None
    status_hint: Optional[Literal["open", "fixed"]] = None
    # `status_hint` é a dica do scanner — nem todos reportam "resolved"; quando
    # não disponível, caller trata como "open".


class SecurityScannerPort(ABC):
    """Interface mínima que todo adapter de scanner deve implementar.

    Operações canônicas V1:
      - fetch_findings : retorna lista de FindingPayload do scanner
      - normalize_severity : mapeia severity raw do scanner → canônico

    Scanners que rodam localmente (gitleaks) podem ignorar `base_url` e
    receber o path do repo via `config.extra['repo_path']`.
    """

    scanner: Scanner

    @abstractmethod
    async def fetch_findings(
        self,
        config: ScannerConfig,
    ) -> list[FindingPayload]:
        """Consulta o scanner e retorna findings normalizados.

        Erros esperados: `ScannerAuthError`, `ScannerAPIError`,
        `ScannerRateLimitError`, `ScannerConfigError`.
        """
        raise NotImplementedError

    @abstractmethod
    def normalize_severity(self, raw: str) -> CanonicalSeverity:
        """Mapeia severity raw (SonarQube BLOCKER, Snyk critical, etc) para
        canônico. Fallback para 'low' quando desconhecido."""
        raise NotImplementedError


# ─── Exceções canônicas ────────────────────────────────────────────────


class ScannerError(Exception):
    """Base — todos os erros de adapter de scanner herdam daqui."""


class ScannerAuthError(ScannerError):
    pass


class ScannerAPIError(ScannerError):
    pass


class ScannerRateLimitError(ScannerError):
    pass


class ScannerConfigError(ScannerError):
    pass


# ─── Registry canônico ─────────────────────────────────────────────────

_REGISTRY: dict[str, SecurityScannerPort] = {}


def register_scanner(adapter: SecurityScannerPort) -> None:
    """Registra adapter no registry canônico. Idempotente."""
    if not getattr(adapter, "scanner", None):
        raise ScannerConfigError(
            f"Adapter {type(adapter).__name__} não definiu atributo `scanner`"
        )
    _REGISTRY[adapter.scanner] = adapter


def get_scanner(scanner: str) -> SecurityScannerPort:
    adapter = _REGISTRY.get(scanner)
    if adapter is None:
        raise ScannerConfigError(
            f"Scanner '{scanner}' não tem adapter registrado. "
            f"Disponíveis: {list(_REGISTRY.keys()) or '[nenhum]'}"
        )
    return adapter


def registered_scanners() -> list[str]:
    return sorted(_REGISTRY.keys())


def _clear_scanner_registry_for_tests() -> None:
    _REGISTRY.clear()
