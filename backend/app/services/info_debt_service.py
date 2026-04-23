"""MVP 24 Fase 24.3 — Dívida informacional persistente.

Contrato canônico:
  - `GatekeeperItem.item_data.offers_count` = quantas vezes apareceu no PDF.
  - `GatekeeperItem.item_data.skip_count` = quantas vezes foi oferecido mas ignorado.
  - `skip_count >= INFO_DEBT_THRESHOLD` → cria/mantém `BacklogItem`
    `category="info_debt"`, `priority="critical"`, `source="arguider"`.

Regra binária (sem ambiguidade):
  - skip < threshold → não há item de backlog.
  - skip == threshold → cria item (first time).
  - skip > threshold → item já existe; atualiza `description` com contador atual.
  - item respondido depois → GatekeeperItem vira resolved; backlog item
    **permanece** como rastro histórico (pode ser fechado manualmente pelo GP).
    Não removemos automaticamente — auditoria precisa do passado.
"""
from __future__ import annotations

import json
from typing import Iterable
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BacklogItem, GatekeeperItem

logger = structlog.get_logger(__name__)


#: Threshold canônico — ≥ 2 rounds ignorados = dívida informacional.
INFO_DEBT_THRESHOLD = 2

#: Prefixo que identifica items de dívida informacional no backlog
#: (busca + idempotência sem precisar de tabela nova).
INFO_DEBT_TITLE_PREFIX = "[info_debt] "


async def bump_skipped(
    db: AsyncSession,
    project_id: UUID,
    skipped_item_ids: Iterable[str],
) -> list[UUID]:
    """Incrementa `skip_count` em cada item pulado e promove para backlog
    quando cruza o threshold.

    Retorna a lista de UUIDs de itens que viraram (ou já eram) dívida
    informacional nesta chamada.
    """
    promoted: list[UUID] = []
    for raw in skipped_item_ids:
        try:
            uid = UUID(str(raw))
        except (ValueError, TypeError):
            continue
        item = await db.get(GatekeeperItem, uid)
        if item is None or item.project_id != project_id:
            continue
        if item.status != "pending":
            # Item já foi resolvido — ignora o "skip".
            continue

        try:
            data = json.loads(item.item_data) if item.item_data else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}

        new_skip = int(data.get("skip_count") or 0) + 1
        data["skip_count"] = new_skip
        item.item_data = json.dumps(data, ensure_ascii=False)
        db.add(item)

        if new_skip >= INFO_DEBT_THRESHOLD:
            await _ensure_info_debt_backlog(db, project_id, item, data, new_skip)
            promoted.append(uid)

    await db.flush()
    logger.info(
        "info_debt.bump_skipped",
        project_id=str(project_id),
        total=len(list(skipped_item_ids)) if isinstance(skipped_item_ids, (list, tuple)) else None,
        promoted=len(promoted),
    )
    return promoted


async def _ensure_info_debt_backlog(
    db: AsyncSession,
    project_id: UUID,
    item: GatekeeperItem,
    data: dict,
    skip_count: int,
) -> None:
    """Cria o BacklogItem de info_debt se não existir; atualiza descrição
    em updates subsequentes.

    Idempotência por título: `[info_debt] <item_code>` é único por projeto.
    """
    code = item.item_id_in_analysis or str(item.id)
    title = f"{INFO_DEBT_TITLE_PREFIX}{code}"

    existing_q = await db.execute(
        select(BacklogItem).where(
            BacklogItem.project_id == project_id,
            BacklogItem.title == title,
        )
    )
    existing = existing_q.scalar_one_or_none()

    question = ""
    for k in ("question", "text", "description", "title"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            question = v.strip()
            break

    description = (
        f"Pergunta ignorada pelo GP em {skip_count} rounds consecutivos "
        f"do questionário técnico retroativo.\n\n"
        f"Pergunta original: {question or '(sem texto)'}\n\n"
        f"GatekeeperItem: {str(item.id)} ({code})"
    )

    if existing:
        existing.description = description
        existing.priority = "critical"
        db.add(existing)
    else:
        db.add(BacklogItem(
            project_id=project_id,
            category="info_debt",
            title=title,
            description=description,
            priority="critical",
            status="pending",
            source="arguider",
        ))
