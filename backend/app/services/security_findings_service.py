"""MVP 20 Fase 20.2 — Service de Security Findings + recálculo de P7.

Orquestra fetch dos scanners configurados, upsert idempotente em
`security_findings`, e recálculo determinístico do pilar P7 do OCG.

Decisão binária #7 do MVP 20: P7 consome findings reais quando scanner
configurado; sem config, heurística pré-20 preservada.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import SecurityFinding
from app.services.ports.security_scanner_port import (
    CanonicalSeverity,
    FindingPayload,
    ScannerConfig,
    ScannerConfigError,
    get_scanner,
    register_scanner,
    registered_scanners,
)


logger = structlog.get_logger(__name__)


def register_builtin_scanners() -> None:
    """Registra adapters built-in. Chamado no startup do app."""
    from app.services.adapters.gitleaks_adapter import GitleaksAdapter
    from app.services.adapters.snyk_adapter import SnykAdapter
    from app.services.adapters.sonar_adapter import SonarAdapter

    register_scanner(SonarAdapter())
    register_scanner(SnykAdapter())
    register_scanner(GitleaksAdapter())
    logger.info("security.scanners_registered",
                 scanners=registered_scanners())


# ─── CRUD canônico ────────────────────────────────────────────────────


async def list_findings(
    db: AsyncSession,
    project_id: UUID,
    *,
    status: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[SecurityFinding]:
    q = select(SecurityFinding).where(SecurityFinding.project_id == project_id)
    if status:
        q = q.where(SecurityFinding.status == status)
    if severity:
        q = q.where(SecurityFinding.severity == severity)
    q = q.order_by(SecurityFinding.last_seen_at.desc())
    return list((await db.execute(q)).scalars().all())


async def _upsert_finding(
    db: AsyncSession,
    project_id: UUID,
    source_scanner: str,
    payload: FindingPayload,
) -> SecurityFinding:
    existing = (await db.execute(
        select(SecurityFinding).where(and_(
            SecurityFinding.project_id == project_id,
            SecurityFinding.source_scanner == source_scanner,
            SecurityFinding.external_id == payload.external_id,
        ))
    )).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing is not None:
        # Re-sync: atualiza last_seen_at + campos mutáveis. Status NÃO é
        # sobrescrito pelo scanner quando GP já marcou accepted_risk.
        existing.severity = payload.severity
        existing.title = payload.title
        existing.description = payload.description
        existing.file_path = payload.file_path
        existing.line_start = payload.line_start
        existing.line_end = payload.line_end
        existing.cwe_id = payload.cwe_id
        existing.rule_id = payload.rule_id
        existing.url = payload.url
        existing.last_seen_at = now

        # Scanner diz que foi resolvido e GP não marcou accepted_risk:
        # transiciona open → fixed com fixed_at.
        if payload.status_hint == "fixed" and existing.status == "open":
            existing.status = "fixed"
            existing.fixed_at = now

        await db.flush()
        return existing

    fresh = SecurityFinding(
        project_id=project_id,
        source_scanner=source_scanner,
        external_id=payload.external_id,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        file_path=payload.file_path,
        line_start=payload.line_start,
        line_end=payload.line_end,
        cwe_id=payload.cwe_id,
        rule_id=payload.rule_id,
        url=payload.url,
        status="fixed" if payload.status_hint == "fixed" else "open",
        first_seen_at=now,
        last_seen_at=now,
        fixed_at=now if payload.status_hint == "fixed" else None,
    )
    db.add(fresh)
    await db.flush()
    return fresh


async def sync_scanner(
    db: AsyncSession,
    project_id: UUID,
    scanner: str,
    config: ScannerConfig,
) -> dict:
    """Busca findings do scanner e faz upsert idempotente.

    Retorna sumário: {scanner, total_fetched, inserted, updated}.
    """
    if scanner not in registered_scanners():
        raise ScannerConfigError(f"Scanner '{scanner}' não registrado.")
    adapter = get_scanner(scanner)
    findings = await adapter.fetch_findings(config)

    inserted = 0
    updated = 0
    for payload in findings:
        existing = (await db.execute(
            select(SecurityFinding.id).where(and_(
                SecurityFinding.project_id == project_id,
                SecurityFinding.source_scanner == scanner,
                SecurityFinding.external_id == payload.external_id,
            ))
        )).scalar_one_or_none()
        await _upsert_finding(db, project_id, scanner, payload)
        if existing is None:
            inserted += 1
        else:
            updated += 1

    return {
        "scanner": scanner,
        "total_fetched": len(findings),
        "inserted": inserted,
        "updated": updated,
    }


# ─── Risk acceptance ─────────────────────────────────────────────────


async def accept_risk(
    db: AsyncSession,
    finding_id: UUID,
    *,
    project_id: UUID,
    gp_user_id: UUID,
    justification: str,
) -> SecurityFinding:
    """GP marca finding como accepted_risk com justificativa.

    Admin co-assina depois via `admin_cosign_accepted_risk`. Em V1
    a dupla assinatura é sequencial: GP primeiro, Admin depois.
    """
    if not justification or len(justification.strip()) < 10:
        raise ValueError("Justificativa obrigatória (mínimo 10 chars).")

    finding = (await db.execute(
        select(SecurityFinding).where(and_(
            SecurityFinding.id == finding_id,
            SecurityFinding.project_id == project_id,
        ))
    )).scalar_one_or_none()
    if finding is None:
        raise ValueError(f"Finding {finding_id} não pertence ao projeto {project_id}")

    finding.status = "accepted_risk"
    finding.accepted_risk_justification = justification.strip()
    finding.accepted_by = gp_user_id
    finding.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    return finding


# ─── P7 recalculation ─────────────────────────────────────────────────


_SEVERITY_WEIGHT: dict[CanonicalSeverity, int] = {
    "critical": 25,
    "high": 10,
    "medium": 3,
    "low": 1,
    "info": 0,
}


async def compute_p7_score_from_findings(
    db: AsyncSession,
    project_id: UUID,
) -> Optional[int]:
    """Calcula score canônico de P7 com base em findings abertos.

    Fórmula determinística (sem LLM):
        score = 100 - Σ (count_severity × weight_severity), clamp 0..100

    Retorna None quando não há findings ALGUM (scanner não configurado OR
    projeto sem histórico). Caller decide: None → heurística pré-20.
    """
    counts = await count_open_findings_by_severity(db, project_id)
    if sum(counts.values()) == 0:
        return None
    penalty = sum(counts[sev] * _SEVERITY_WEIGHT[sev] for sev in counts)
    score = max(0, min(100, 100 - penalty))
    return score


async def count_open_findings_by_severity(
    db: AsyncSession,
    project_id: UUID,
) -> dict[CanonicalSeverity, int]:
    """Conta findings com status='open' agrupados por severity."""
    from sqlalchemy import func
    result = await db.execute(
        select(
            SecurityFinding.severity,
            func.count(SecurityFinding.id),
        )
        .where(SecurityFinding.project_id == project_id)
        .where(SecurityFinding.status == "open")
        .group_by(SecurityFinding.severity)
    )
    counts: dict[CanonicalSeverity, int] = {
        "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
    }
    for severity, n in result.all():
        if severity in counts:
            counts[severity] = n
    return counts
