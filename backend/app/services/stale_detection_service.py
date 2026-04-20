"""MVP 10 Fase 10.4 — Stale detection pra TestSpecs e LiveDocs.

Contrato §7 MVP 10: detecção de desatualização é **marcação**, não
regeneração automática. GP dispara Regenerar manual quando quiser.

Heurística de staleness:
  1. Item sem `ocg_version_at_generation` → is_stale=True
     (nasceu sem contexto; nunca foi alinhado com OCG).
  2. OCG atual > versão registrada → is_stale=True, reason lista
     quantas mudanças de OCG houve desde então (via `ocg_delta_log`).
  3. OCG atual == registrado → is_stale=False.
  4. Projeto sem OCG → is_stale=False (nada pra comparar).

Funções puras: recebem a lista de specs/docs + versão atual do OCG +
lista de deltas relevantes; retornam payload enriquecido. Zero mutação
no DB. Endpoint GET usa pra anexar `is_stale` + `stale_reason` no
retorno sem precisar UPDATE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import LiveDoc, OCG, OCGDeltaLog, TestSpec

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StaleInfo:
    """Resultado da avaliação de staleness de um item."""
    is_stale: bool
    reason: Optional[str]
    current_ocg_version: Optional[int]
    generated_ocg_version: Optional[int]
    deltas_since_generation: int


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def evaluate_test_spec_staleness(
    db: AsyncSession, project_id: UUID,
) -> dict[UUID, StaleInfo]:
    """Avalia staleness pra todas as test_specs do projeto.

    Retorna `{spec_id: StaleInfo}`. Caller usa pra decorar payload sem
    precisar persistir o resultado no DB.
    """
    current_version = await _current_ocg_version(db, project_id)
    rows = await db.execute(
        select(TestSpec.id, TestSpec.ocg_version_at_generation)
        .where(TestSpec.project_id == project_id)
    )
    items = rows.all()

    max_generated = max(
        (v for _, v in items if v is not None),
        default=None,
    )
    delta_counts = await _count_deltas_grouped_by_from_version(
        db, project_id,
        current_version=current_version,
        min_generated=_min_not_none([v for _, v in items]),
    )

    out: dict[UUID, StaleInfo] = {}
    for spec_id, generated in items:
        out[spec_id] = _compute_stale(
            current_version=current_version,
            generated_version=generated,
            delta_counts=delta_counts,
        )
    return out


async def evaluate_live_doc_staleness(
    db: AsyncSession, project_id: UUID,
) -> dict[UUID, StaleInfo]:
    """Mesma lógica, pra live_docs. Compartilha helpers com test_specs."""
    current_version = await _current_ocg_version(db, project_id)
    rows = await db.execute(
        select(LiveDoc.id, LiveDoc.ocg_version_at_generation)
        .where(LiveDoc.project_id == project_id)
    )
    items = rows.all()

    delta_counts = await _count_deltas_grouped_by_from_version(
        db, project_id,
        current_version=current_version,
        min_generated=_min_not_none([v for _, v in items]),
    )

    out: dict[UUID, StaleInfo] = {}
    for doc_id, generated in items:
        out[doc_id] = _compute_stale(
            current_version=current_version,
            generated_version=generated,
            delta_counts=delta_counts,
        )
    return out


async def build_stale_summary(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any]:
    """Retorna resumo agregado pra UI Fase 10.5:

        {
          "current_ocg_version": 10,
          "test_specs": {
            "total": 40,
            "stale": 12,
            "by_type": {"unit": {"total": 15, "stale": 5}, ...},
          },
          "live_docs": {"total": 0, "stale": 0, "by_type": {}},
          "needs_regeneration": bool,
        }
    """
    current_version = await _current_ocg_version(db, project_id)

    spec_rows = await db.execute(
        select(TestSpec.spec_type, TestSpec.ocg_version_at_generation)
        .where(TestSpec.project_id == project_id)
    )
    specs = spec_rows.all()

    doc_rows = await db.execute(
        select(LiveDoc.doc_type, LiveDoc.ocg_version_at_generation)
        .where(LiveDoc.project_id == project_id)
    )
    docs = doc_rows.all()

    spec_summary = _group_summary(specs, current_version)
    doc_summary = _group_summary(docs, current_version)

    return {
        "current_ocg_version": current_version,
        "test_specs": spec_summary,
        "live_docs": doc_summary,
        "needs_regeneration": bool(
            spec_summary["stale"] > 0 or doc_summary["stale"] > 0,
        ),
    }


# ---------------------------------------------------------------------------
# Core logic (pura)
# ---------------------------------------------------------------------------

def _compute_stale(
    *, current_version: Optional[int], generated_version: Optional[int],
    delta_counts: dict[int, int],
) -> StaleInfo:
    """Decide is_stale com base nas versões e no mapa de deltas.

    `delta_counts[v]` = quantos deltas entre `v` e `current_version` há.
    Calculado 1x no caller e reusado pra cada spec/doc.
    """
    # Projeto sem OCG — nada pra avaliar
    if current_version is None:
        return StaleInfo(
            is_stale=False, reason=None,
            current_ocg_version=None,
            generated_ocg_version=generated_version,
            deltas_since_generation=0,
        )

    # Item sem registro de OCG na geração — considera stale por ser
    # legado sem contexto (nunca foi alinhado com OCG).
    if generated_version is None:
        return StaleInfo(
            is_stale=True,
            reason="Item gerado antes da Fase 10.4 (sem rastro de versão do OCG) — regenere pra alinhar.",
            current_ocg_version=current_version,
            generated_ocg_version=None,
            deltas_since_generation=0,
        )

    if generated_version >= current_version:
        # Mesma versão ou (raro) versão futura — considera alinhado
        return StaleInfo(
            is_stale=False, reason=None,
            current_ocg_version=current_version,
            generated_ocg_version=generated_version,
            deltas_since_generation=0,
        )

    deltas = delta_counts.get(generated_version, current_version - generated_version)
    reason = _format_reason(generated_version, current_version, deltas)
    return StaleInfo(
        is_stale=True,
        reason=reason,
        current_ocg_version=current_version,
        generated_ocg_version=generated_version,
        deltas_since_generation=deltas,
    )


def _format_reason(generated: int, current: int, deltas: int) -> str:
    if deltas <= 1:
        return f"OCG avançou v{generated} → v{current} (1 mudança desde a geração)."
    return f"OCG avançou v{generated} → v{current} ({deltas} mudanças desde a geração)."


def _group_summary(
    rows: Sequence[Any], current_version: Optional[int],
) -> dict[str, Any]:
    """Recebe lista de (type, ocg_version_at_generation) e agrupa.

    Compatível com TestSpec.spec_type e LiveDoc.doc_type — ambos são
    VARCHAR na posição [0] e Integer nullable na [1].
    """
    by_type: dict[str, dict[str, int]] = {}
    total = 0
    stale_total = 0
    for kind, generated in rows:
        bucket = by_type.setdefault(str(kind), {"total": 0, "stale": 0})
        bucket["total"] += 1
        total += 1
        is_stale = _is_stale_simple(current_version, generated)
        if is_stale:
            bucket["stale"] += 1
            stale_total += 1
    return {"total": total, "stale": stale_total, "by_type": by_type}


def _is_stale_simple(current: Optional[int], generated: Optional[int]) -> bool:
    """Heurística leve pra o summary (sem contar deltas)."""
    if current is None:
        return False
    if generated is None:
        return True
    return generated < current


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _current_ocg_version(db: AsyncSession, project_id: UUID) -> Optional[int]:
    row = await db.execute(
        select(func.max(OCG.version)).where(OCG.project_id == project_id)
    )
    return row.scalar()


async def _count_deltas_grouped_by_from_version(
    db: AsyncSession, project_id: UUID,
    *, current_version: Optional[int], min_generated: Optional[int],
) -> dict[int, int]:
    """Pra cada `version_from` distinto entre `min_generated` e
    `current_version`, conta quantas transições `ocg_delta_log` tem
    daquela versão pra frente.

    Resultado: dict `{version_x: count_of_deltas_from_x_to_current}`.
    """
    if current_version is None or min_generated is None:
        return {}
    if min_generated >= current_version:
        return {}

    rows = await db.execute(
        select(OCGDeltaLog.ocg_version_from, func.count())
        .where(
            OCGDeltaLog.project_id == project_id,
            OCGDeltaLog.ocg_version_from >= min_generated,
            OCGDeltaLog.ocg_version_to <= current_version,
        )
        .group_by(OCGDeltaLog.ocg_version_from)
    )
    counts_by_from = {v: c for v, c in rows.all()}

    # Agregação cumulativa: counts[x] = nº de deltas com
    # version_from >= x (deltas QUE AFETAM itens gerados em v<x).
    cumulative: dict[int, int] = {}
    running = 0
    # Iterar de current pra trás: sort desc por from_version
    for v in sorted(counts_by_from.keys(), reverse=True):
        running += counts_by_from[v]
        cumulative[v] = running
    return cumulative


def _min_not_none(values: list[Optional[int]]) -> Optional[int]:
    filtered = [v for v in values if v is not None]
    return min(filtered) if filtered else None
