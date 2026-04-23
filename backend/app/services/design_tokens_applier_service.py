"""MVP 25 Fase 25.3 — Aplicador de design tokens no OCG.

Responsabilidades:
  - `apply_tokens_to_ocg`: escreve `STACK_RECOMMENDATION.frontend.design_tokens`
    no OCG mais recente do projeto, bumpa versão, emite audit `OCG_UPDATED`.
  - `seed_design_tokens_gap_if_needed`: cria GatekeeperItem pedindo paleta/
    tipografia quando mock visual (PNG/PDF) foi ingerido mas nenhum CSS
    alimentou tokens no OCG. Idempotente por `item_id_in_analysis`.

Decisão binária #2 do MVP 25: aplicar é **idempotente** — se o dict
normalizado não difere do atual, não bumpa (evita inflar histórico).

Canônico do bump: mesmo padrão de `rnf_arguider_service.apply_rnf_answer`
(MVP 23 Fase 23.2) — cadeia de responsabilidade: leitura → merge →
persist → audit → flush.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ArguiderAnalysis, GatekeeperItem, OCG

logger = structlog.get_logger(__name__)


#: Código canônico do gap "mock visual sem design tokens".
#: Precisa caber em VARCHAR(10) da coluna item_id_in_analysis.
DESIGN_GAP_CODE = "DT-DSGN001"


async def apply_tokens_to_ocg(
    db: AsyncSession,
    project_id: UUID,
    tokens_payload: dict,
    *,
    actor_id: Optional[UUID] = None,
    source_document_id: Optional[UUID] = None,
) -> dict:
    """Escreve `STACK_RECOMMENDATION.frontend.design_tokens` no OCG.

    Retorna dict com:
      {applied: bool, ocg_version_to: int | None, reason: str}

    `applied=False` e `reason="no_ocg"` se não houver OCG ainda; caller
    pode logar. `applied=False` e `reason="noop"` se payload idêntico ao
    atual (idempotente).
    """
    if not isinstance(tokens_payload, dict) or not tokens_payload:
        return {"applied": False, "ocg_version_to": None, "reason": "empty_payload"}

    ocg = await _load_current_ocg(db, project_id)
    if ocg is None:
        return {"applied": False, "ocg_version_to": None, "reason": "no_ocg"}

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}
    if not isinstance(ocg_data, dict):
        ocg_data = {}

    stack = ocg_data.get("STACK_RECOMMENDATION")
    if not isinstance(stack, dict):
        stack = {}
    frontend = stack.get("frontend")
    if not isinstance(frontend, dict):
        frontend = {}

    previous = frontend.get("design_tokens") if isinstance(frontend.get("design_tokens"), dict) else None

    # Idempotência: compara payload ignorando generated_at (só timestamp novo
    # não é razão pra bumpar versão).
    if previous and _same_except_timestamp(previous, tokens_payload):
        return {"applied": False, "ocg_version_to": ocg.version, "reason": "noop"}

    frontend["design_tokens"] = tokens_payload
    stack["frontend"] = frontend
    ocg_data["STACK_RECOMMENDATION"] = stack

    new_version = (ocg.version or 0) + 1
    ocg.ocg_data = json.dumps(ocg_data, ensure_ascii=False)
    ocg.version = new_version
    ocg.updated_at = datetime.now(timezone.utc)
    db.add(ocg)

    # Audit canônico — mesmo evento usado por RNF_CONTRACTS (OCG_UPDATED).
    from app.services.audit_service import AuditEvents, AuditService
    await AuditService(db).log_event(
        event_type=AuditEvents.OCG_UPDATED,
        resource_type="ocg",
        actor_id=actor_id,
        resource_id=ocg.id,
        details={
            "project_id": str(project_id),
            "version_from": new_version - 1,
            "version_to": new_version,
            "source": "design_tokens_ingestion",
            "source_document_id": str(source_document_id) if source_document_id else None,
            "tokens_source": tokens_payload.get("source"),
        },
    )
    await db.flush()

    logger.info(
        "design_tokens.applied",
        project_id=str(project_id),
        version_from=new_version - 1,
        version_to=new_version,
        source=tokens_payload.get("source"),
    )
    return {"applied": True, "ocg_version_to": new_version, "reason": "updated"}


async def seed_design_tokens_gap_if_needed(
    db: AsyncSession,
    project_id: UUID,
    *,
    triggered_by_document_id: Optional[UUID] = None,
) -> dict:
    """Cria gap no Arguidor pedindo paleta/tipografia/breakpoints.

    Disparado quando mock visual (PNG/PDF) chega mas o OCG não tem
    `design_tokens`. Idempotente: se já existe GatekeeperItem com o
    código canônico, não duplica.

    Retorna dict {created: bool, item_id: str | None, reason: str}.
    """
    # 1. Já tem design_tokens no OCG? Se sim, não cria gap.
    ocg = await _load_current_ocg(db, project_id)
    if ocg:
        try:
            ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
        except (TypeError, ValueError):
            ocg_data = {}
        frontend = (ocg_data.get("STACK_RECOMMENDATION") or {}).get("frontend") or {}
        tokens = frontend.get("design_tokens")
        if isinstance(tokens, dict) and (
            (tokens.get("palette") or {}).get("by_role")
            or (tokens.get("palette") or {}).get("top")
        ):
            return {"created": False, "item_id": None, "reason": "tokens_present"}

    # 2. Já existe gap canônico pendente?
    existing = (await db.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project_id,
            GatekeeperItem.item_id_in_analysis == DESIGN_GAP_CODE,
            GatekeeperItem.status == "pending",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"created": False, "item_id": str(existing.id), "reason": "already_seeded"}

    # 3. GatekeeperItem requer arguider_analysis_id; anexa à análise mais
    # recente do projeto. Se não houver (caso raro), abstém — o hook
    # subsequente vai criar análise e recair aqui no próximo evento.
    analysis = (await db.execute(
        select(ArguiderAnalysis).where(
            ArguiderAnalysis.project_id == project_id,
        ).order_by(ArguiderAnalysis.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if analysis is None:
        return {"created": False, "item_id": None, "reason": "no_analysis"}

    # 4. Cria o gap canônico.
    item_data = {
        "question": (
            "O projeto recebeu mocks visuais (PNG/PDF) mas ainda não há "
            "design tokens declarados. Informe a paleta de cores canônica "
            "(primary, secondary, accent), famílias tipográficas e escala "
            "de tamanhos/breakpoints — ou envie um arquivo CSS/SCSS pela "
            "Ingestão para extração automática."
        ),
        "pillar": "P5",
        "severity": "warning",
        "category": "design_tokens",
        "suggestions": [
            "Envie um .css/.scss via Ingestão — extração é automática.",
            "Preencha manualmente em `/projects/:id/ocg` → Design Tokens.",
        ],
        "source": "design_tokens_auto_seed",
        "triggered_by_document_id": (
            str(triggered_by_document_id) if triggered_by_document_id else None
        ),
    }

    item = GatekeeperItem(
        id=uuid4(),
        project_id=project_id,
        arguider_analysis_id=analysis.id,
        item_type="gap",
        item_id_in_analysis=DESIGN_GAP_CODE,
        item_data=json.dumps(item_data, ensure_ascii=False),
        status="pending",
    )
    db.add(item)
    await db.flush()

    logger.info(
        "design_tokens.gap_seeded",
        project_id=str(project_id),
        item_id=str(item.id),
        document_id=str(triggered_by_document_id) if triggered_by_document_id else None,
    )
    return {"created": True, "item_id": str(item.id), "reason": "seeded"}


# ─── Internals ────────────────────────────────────────────────────────


async def _load_current_ocg(db: AsyncSession, project_id: UUID) -> Optional[OCG]:
    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc()).limit(1)
    )
    return row.scalar_one_or_none()


def _same_except_timestamp(a: dict, b: dict) -> bool:
    """Idempotência: compara dois payloads ignorando `generated_at`."""
    def strip(d: Any) -> Any:
        if not isinstance(d, dict):
            return d
        out = {k: v for k, v in d.items() if k != "generated_at"}
        return out
    return strip(a) == strip(b)
