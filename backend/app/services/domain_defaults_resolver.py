"""M02 — resolver de defaults de domínio.

Recebe gap (dict com id/text/severity) + contexto do projeto e decide se
há default canônico aplicável via `domain_defaults_kb.find_matches`.
Quando há match, grava (ou atualiza) a decisão em `applied_defaults` e
retorna a linha. Se não há match, retorna None — gap continua sendo
tratado como pergunta pro M01.

Não chama LLM — é determinístico via substring match na KB. LLM entra
numa evolução futura (fuzzy matching). Hoje, se um gap precisa de decision
que a KB não tem, sobe pro M01 normalmente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import AppliedDefault
from app.services.domain_defaults_kb import find_matches


async def resolve_gap(
    db: AsyncSession,
    project_id: UUID,
    gap: dict[str, Any],
    project_context_tags: list[str],
) -> Optional[AppliedDefault]:
    """Resolve um gap via default de domínio público, se aplicável.

    Args:
        gap: dict com ao menos `id` (str) e `text`/`description` (str).
        project_context_tags: tags do projeto (ex: ["domain:juridico",
            "project_type:processo_civil", "integration:datajud",
            "compliance:lgpd", "stack:sqlite", "deployment:desktop"]).

    Returns:
        `AppliedDefault` gravada/atualizada, OU None se nenhum default
        canônico se aplica.
    """
    gap_text = str(gap.get("text") or gap.get("description") or "")
    gap_id = str(gap.get("id") or "")
    if not gap_text:
        return None

    matches = find_matches(gap_text, project_context_tags)
    if not matches:
        return None

    # Pega o primeiro match. Multiple matches com mesma decision_key é ambiguidade
    # da KB e deve ser resolvida lá — aqui escolhemos determinístico.
    entry = matches[0]
    decision_key = entry["key"]

    # Upsert canônico: se já existe decisão com esta key pro projeto,
    # atualiza gap_id + rationale; NÃO sobrescreve se já foi contestada.
    existing_result = await db.execute(
        select(AppliedDefault).where(
            (AppliedDefault.project_id == project_id)
            & (AppliedDefault.decision_key == decision_key)
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        if existing.contested_at is not None:
            # User já contestou — NÃO re-aplica. Devolve a linha existente.
            return existing
        existing.gap_id = gap_id
        existing.rationale = entry["rationale"]
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    row = AppliedDefault(
        project_id=project_id,
        gap_id=gap_id,
        category=entry["category"],
        decision_key=decision_key,
        decision_value=entry["value"],
        source_citation=entry["source"],
        rationale=entry["rationale"],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_applied(
    db: AsyncSession,
    project_id: UUID,
    include_contested: bool = True,
) -> list[AppliedDefault]:
    """Lista decisões aplicadas ao projeto, agrupáveis pelo caller por categoria."""
    query = select(AppliedDefault).where(AppliedDefault.project_id == project_id)
    if not include_contested:
        query = query.where(AppliedDefault.contested_at.is_(None))
    query = query.order_by(AppliedDefault.category, AppliedDefault.applied_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def contest_decision(
    db: AsyncSession,
    project_id: UUID,
    decision_id: UUID,
    contested_by: UUID,
    new_value: str,
) -> Optional[AppliedDefault]:
    """Usuário contesta um default aplicado. Marca `contested_at` + salva
    `contested_value`. CodeGen deve usar `contested_value` sobre
    `decision_value` quando presente.
    """
    result = await db.execute(
        select(AppliedDefault).where(
            (AppliedDefault.id == decision_id)
            & (AppliedDefault.project_id == project_id)
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.contested_at = datetime.now(timezone.utc)
    row.contested_by = contested_by
    row.contested_value = new_value
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


def infer_project_context_tags(ocg_data: dict[str, Any] | None) -> list[str]:
    """Gera tags de contexto do projeto a partir do OCG pra filtrar defaults.

    Hoje, inferência simples baseada em strings no STACK_RECOMMENDATION e
    PROJECT_PROFILE. Se OCG é escasso, retorna lista vazia — aí só
    defaults sem `applies_when` se aplicam (os universais).
    """
    if not isinstance(ocg_data, dict):
        return []
    tags: list[str] = []

    # Infer domain
    profile = ocg_data.get("PROJECT_PROFILE") or {}
    profile_str = str(profile).lower()
    is_juridico = any(w in profile_str for w in (
        "jurídic", "juridic", "advogad", "processo", "tribunal", "judicial", "oab",
    ))
    if is_juridico:
        tags.append("domain:juridico")
        # Default: sistema jurídico assumimos processo civil como cobertura base
        # a menos que esteja explicitamente limitado a outro ramo. Sempre ativar
        # pra aproveitar defaults de retenção cível — advogado civil é a maioria.
        tags.append("project_type:processo_civil")
        if any(w in profile_str for w in ("trabalhist", "clt", "reclamação trabalhista")):
            tags.append("project_type:processo_trabalhista")

    # Infer stack
    stack = ocg_data.get("STACK_RECOMMENDATION") or {}
    stack_str = str(stack).lower()
    if "sqlite" in stack_str:
        tags.append("stack:sqlite")
    if any(w in stack_str for w in ("tauri", "electron", "desktop")):
        tags.append("deployment:desktop")
    if "datajud" in stack_str or "datajud" in profile_str:
        tags.append("integration:datajud")
    if "jwt" in stack_str:
        tags.append("tech:jwt_auth")

    # Compliance: LGPD é assumido sempre que há:
    #  - menção explícita a LGPD, OU
    #  - dados pessoais óbvios (domínio jurídico, domínio de saúde,
    #    usuários cadastrados, PII em geral).
    # Subnotificar LGPD gera gaps regulatórios persistentes — assumir
    # aplicável é o safe default.
    lgpd_indicators = any(w in profile_str for w in (
        "lgpd", "dados pessoais", "cpf", "personal data", "pii",
    )) or any(w in stack_str for w in ("lgpd", "dados pessoais"))
    if lgpd_indicators or is_juridico:
        tags.append("compliance:lgpd")

    return tags
