"""Validação de Requisitos (2026-04-25): visão agregada por documento
do que o Arguidor #1 já identificou (gaps, show_stoppers, poor_definitions).

Sem LLM call nova, sem tabela nova — só agrega `arguider_analyses` por doc
e devolve status canônico:
  - clean: análise completa + 0 issues
  - has_issues: análise completa + N issues
  - processing: ainda rodando
  - error: análise falhou
  - pending: ainda na fila

UI minimalista lista os docs com ✅ / ⏳ pra owner ver de relance se tem
documento com requisito faltante ou contradição antes de gerar código.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import ArguiderAnalysis, IngestedDocument

router = APIRouter(tags=["consistency"])


def _safe_json_len(raw: Any) -> int:
    """Conta items de uma coluna JSON (text). Tolera None/'[]'/lista nativa."""
    if raw is None:
        return 0
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return len(parsed) if isinstance(parsed, list) else 0
        except json.JSONDecodeError:
            return 0
    return 0


@router.get("/projects/{project_id}/consistency")
async def get_consistency_status(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os documentos do projeto + status de consistência.

    Status canônico:
      - clean: arguider completou e não achou gap/show_stopper/poor_definition
      - has_issues: arguider completou e há ≥1 item identificado
      - processing: arguider ainda rodando
      - error: arguider quebrou
      - pending: ainda enfileirado
    """
    docs = (await db.execute(
        select(IngestedDocument)
        .where(IngestedDocument.project_id == project_id)
        .order_by(IngestedDocument.created_at.desc())
    )).scalars().all()

    analyses_q = await db.execute(
        select(ArguiderAnalysis)
        .where(ArguiderAnalysis.document_id.in_([d.id for d in docs]) if docs else False)
    )
    analyses_by_doc: dict[UUID, ArguiderAnalysis] = {}
    for a in analyses_q.scalars().all():
        # Pega a análise mais recente por doc se houver múltiplas
        cur = analyses_by_doc.get(a.document_id)
        if cur is None or (a.created_at and (cur.created_at is None or a.created_at > cur.created_at)):
            analyses_by_doc[a.document_id] = a

    items = []
    counts = {"clean": 0, "has_issues": 0, "processing": 0, "error": 0, "pending": 0}

    for d in docs:
        analysis = analyses_by_doc.get(d.id)
        gaps_n = _safe_json_len(analysis.gaps) if analysis else 0
        ss_n = _safe_json_len(analysis.show_stoppers) if analysis else 0
        pd_n = _safe_json_len(analysis.poor_definitions) if analysis else 0
        modules_n = _safe_json_len(analysis.module_candidates) if analysis else 0
        total_issues = gaps_n + ss_n + pd_n

        if d.arguider_status == "error":
            status = "error"
        elif d.arguider_status == "processing":
            status = "processing"
        elif d.arguider_status == "pending":
            status = "pending"
        elif d.arguider_status == "completed":
            status = "has_issues" if total_issues > 0 else "clean"
        else:
            status = d.arguider_status or "pending"

        counts[status] = counts.get(status, 0) + 1

        items.append({
            "document_id": str(d.id),
            "original_filename": d.original_filename,
            "file_type": d.file_type,
            "is_canonical_decision": bool(getattr(d, "is_canonical_decision", False)),
            "category": d.document_category,
            "status": status,
            "gaps_count": gaps_n,
            "show_stoppers_count": ss_n,
            "poor_definitions_count": pd_n,
            "modules_count": modules_n,
            "total_issues": total_issues,
            "uploaded_at": d.created_at.isoformat() if d.created_at else None,
            "checked_at": (
                analysis.created_at.isoformat()
                if analysis and analysis.created_at
                else None
            ),
        })

    return {
        "project_id": str(project_id),
        "total_documents": len(items),
        "counts": counts,
        "all_clean": counts["has_issues"] == 0 and counts["error"] == 0 and len(items) > 0,
        "items": items,
    }


@router.get("/projects/{project_id}/consistency/{document_id}/issues")
async def get_document_issues(
    project_id: UUID,
    document_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe das issues de um documento específico — usado pra expandir card."""
    analysis = (await db.execute(
        select(ArguiderAnalysis)
        .where(ArguiderAnalysis.document_id == document_id)
        .order_by(ArguiderAnalysis.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if analysis is None:
        return {"document_id": str(document_id), "gaps": [], "show_stoppers": [], "poor_definitions": []}

    def _parse(raw):
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw) if isinstance(raw, str) else []
        except json.JSONDecodeError:
            return []

    return {
        "document_id": str(document_id),
        "gaps": _parse(analysis.gaps),
        "show_stoppers": _parse(analysis.show_stoppers),
        "poor_definitions": _parse(analysis.poor_definitions),
        "checked_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }
