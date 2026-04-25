"""Aging de gaps recorrentes pra evitar punição infinita do score (2026-04-25).

Reforma Arguidor #1: GCA é construtor, não auditor. Gap que aparece em
muitas ingestões sem o owner agir não pode continuar punindo eternamente.
Aqui a lógica:

  1. Cada gap reportado pelo Arguidor é normalizado em um `gap_signature`
     (hash determinístico de pilar + texto). Gaps "iguais" entre ingestões
     batem na mesma signature.
  2. A cada análise nova, o serviço incrementa `sightings_count`.
  3. Quando `sightings_count >= DEFER_THRESHOLD` (default 5) E o projeto
     está em modo solo_owner, o gap é marcado `deferred_at = now()`.
  4. Gaps deferred ficam OCULTOS do M01 (Questões em Aberto) e NÃO contam
     no cálculo de score do OCG.
  5. Owner pode ressuscitar manualmente via endpoint dedicado (futuro).

Funciona como wrapper consultivo: o Arguidor segue gerando gaps
livremente, este serviço só decide quais entram no fluxo a jusante.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable, Set
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import DeferredGap, Project

logger = structlog.get_logger(__name__)

DEFER_THRESHOLD = 5


def _normalize_text(text: str) -> str:
    """Normaliza texto pra agrupar gaps levemente diferentes em sightings.

    Lowercase + remove diacríticos (NFKD) + colapsa whitespace + remove
    pontuação. "Não" e "nao" viram "nao". Conservador — não tenta
    lematizar nem similaridade semântica.
    """
    if not text:
        return ""
    t = text.lower().strip()
    # Diacríticos: 'não' → 'nao', 'série' → 'serie'
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:500]


def gap_signature(pillar: str | None, text: str | None) -> str:
    """sha256(pilar normalizado + texto normalizado), trunca em 64 chars."""
    payload = f"{(pillar or '').lower()}::{_normalize_text(text or '')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def update_sightings_for_gaps(
    db: AsyncSession,
    project_id: UUID,
    gaps: list[dict],
) -> dict:
    """Registra novas sightings dos gaps de uma análise. Aplica defer
    automático quando atinge o threshold em modo solo_owner.

    Retorna estatística: {total_processed, new_signatures, defer_triggered}.
    """
    if not gaps:
        return {"total_processed": 0, "new_signatures": 0, "defer_triggered": 0}

    gov_mode = "solo_owner"
    proj_row = await db.execute(
        select(Project.governance_mode).where(Project.id == project_id)
    )
    gov_mode = proj_row.scalar() or "solo_owner"

    new_count = 0
    defer_count = 0
    now = datetime.now(timezone.utc)

    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        pillar = gap.get("pillar") or gap.get("affected_pillar")
        text = gap.get("text") or gap.get("description") or gap.get("name")
        if not text:
            continue
        sig = gap_signature(pillar, text)

        existing = (await db.execute(
            select(DeferredGap)
            .where(DeferredGap.project_id == project_id, DeferredGap.gap_signature == sig)
        )).scalar_one_or_none()

        if existing is None:
            db.add(DeferredGap(
                project_id=project_id,
                gap_signature=sig,
                pillar=str(pillar)[:40] if pillar else None,
                sample_text=str(text)[:1000],
                sightings_count=1,
                first_seen_at=now,
                last_seen_at=now,
            ))
            new_count += 1
        else:
            existing.sightings_count += 1
            existing.last_seen_at = now
            if (
                gov_mode == "solo_owner"
                and existing.deferred_at is None
                and existing.revived_at is None
                and existing.sightings_count >= DEFER_THRESHOLD
            ):
                existing.deferred_at = now
                defer_count += 1
                logger.info(
                    "gap_aging.deferred",
                    project_id=str(project_id),
                    signature=sig[:12],
                    pillar=existing.pillar,
                    sightings=existing.sightings_count,
                )

    await db.flush()
    return {
        "total_processed": len(gaps),
        "new_signatures": new_count,
        "defer_triggered": defer_count,
    }


async def get_deferred_signatures(db: AsyncSession, project_id: UUID) -> Set[str]:
    """Retorna o set de gap_signatures que estão owner-deferred no projeto."""
    rows = await db.execute(
        select(DeferredGap.gap_signature)
        .where(
            DeferredGap.project_id == project_id,
            DeferredGap.deferred_at.is_not(None),
            DeferredGap.revived_at.is_(None),
        )
    )
    return {r[0] for r in rows.all()}


async def filter_out_deferred(
    db: AsyncSession,
    project_id: UUID,
    gaps: Iterable[dict],
) -> list[dict]:
    """Remove gaps deferred da lista. Usado pelo M01 antes de gerar perguntas
    e pelo ocg_updater antes de aplicar deltas que mencionem o gap."""
    deferred = await get_deferred_signatures(db, project_id)
    if not deferred:
        return list(gaps or [])
    out = []
    for gap in gaps or []:
        if not isinstance(gap, dict):
            out.append(gap)
            continue
        pillar = gap.get("pillar") or gap.get("affected_pillar")
        text = gap.get("text") or gap.get("description") or gap.get("name")
        sig = gap_signature(pillar, text)
        if sig in deferred:
            continue
        out.append(gap)
    return out
