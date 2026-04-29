"""
OCG Override Router — Permite user resolver manualmente conflitos no OCG Global

Endpoints para override de campos divergentes escolhendo valor específico
entre as opções das 7 personas.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone
from typing import Any
import structlog

from app.db.database import get_db
from app.models.base import OCGGlobal
from app.middleware.auth import get_current_user_from_token
from pydantic import BaseModel

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ocg-override"])


class OverrideRequest(BaseModel):
    """Requisição para override de campo conflitante"""
    field: str
    chosen_value: Any
    reason: str | None = None  # Motivo do override


class OverrideResponse(BaseModel):
    """Resposta de override"""
    field: str
    chosen_value: Any
    overridden_at: str
    overridden_by: str


@router.post("/projects/{project_id}/ingestion/{document_id}/ocg-global/override")
async def override_conflicting_field(
    project_id: UUID,
    document_id: UUID,
    override: OverrideRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Override um campo divergente no OCG Global com escolha manual.

    User seleciona qual valor usar entre as opções das 7 personas.
    Registra override no parecimento consolidado com rastreamento.
    """
    # 1. Buscar OCG Global
    ocg_global = await db.scalar(
        select(OCGGlobal).where(OCGGlobal.document_id == document_id)
    )

    if not ocg_global:
        raise HTTPException(status_code=404, detail="OCG Global não encontrado")

    # Verificar se campo está em conflito
    if override.field not in ocg_global.conflicting_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Campo '{override.field}' não está em conflito ou não existe",
        )

    # 2. Aplicar override
    consolidated = ocg_global.parecer_consolidated or {}

    # Registrar metadados de override
    if "_overrides" not in consolidated:
        consolidated["_overrides"] = []

    consolidated["_overrides"].append({
        "field": override.field,
        "chosen_value": override.chosen_value,
        "reason": override.reason,
        "overridden_by": str(current_user_id),
        "overridden_at": datetime.now(timezone.utc).isoformat(),
    })

    # Atualizar valor consolidado
    consolidated[f"{override.field}_consolidated"] = override.chosen_value
    consolidated[f"{override.field}_overridden"] = True

    # 3. Atualizar banco de dados
    ocg_global.parecer_consolidated = consolidated
    db.add(ocg_global)
    await db.commit()
    await db.refresh(ocg_global)

    logger.info(
        "ocg_override.field_overridden",
        project_id=str(project_id),
        document_id=str(document_id),
        field=override.field,
        overridden_by=str(current_user_id),
        reason=override.reason,
    )

    return OverrideResponse(
        field=override.field,
        chosen_value=override.chosen_value,
        overridden_at=datetime.now(timezone.utc).isoformat(),
        overridden_by=str(current_user_id),
    )


@router.get("/projects/{project_id}/ingestion/{document_id}/ocg-global/overrides")
async def get_overrides(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna histórico de overrides realizados no OCG Global"""
    ocg_global = await db.scalar(
        select(OCGGlobal).where(OCGGlobal.document_id == document_id)
    )

    if not ocg_global:
        raise HTTPException(status_code=404, detail="OCG Global não encontrado")

    overrides = ocg_global.parecer_consolidated.get("_overrides", []) if ocg_global.parecer_consolidated else []

    return {
        "ocg_global_id": str(ocg_global.id),
        "overrides": overrides,
        "total_overrides": len(overrides),
    }


@router.post("/projects/{project_id}/ingestion/{document_id}/ocg-global/revert-override")
async def revert_override(
    project_id: UUID,
    document_id: UUID,
    field: str,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Reverte um override específico voltando para votação automática"""
    ocg_global = await db.scalar(
        select(OCGGlobal).where(OCGGlobal.document_id == document_id)
    )

    if not ocg_global:
        raise HTTPException(status_code=404, detail="OCG Global não encontrado")

    consolidated = ocg_global.parecer_consolidated or {}

    # Verificar se há override para este campo
    overrides = consolidated.get("_overrides", [])
    override_found = any(o["field"] == field for o in overrides)

    if not override_found:
        raise HTTPException(status_code=400, detail=f"Nenhum override encontrado para '{field}'")

    # Remover flags de override
    consolidated.pop(f"{field}_overridden", None)

    # Voltar para valor mais votado (ou deixar com _consolidated)
    if field in ocg_global.voting_results:
        votes = ocg_global.voting_results[field]
        most_voted_json = max(votes, key=votes.get)
        try:
            most_voted = __import__("json").loads(most_voted_json)
        except:
            most_voted = most_voted_json
        consolidated[f"{field}_consolidated"] = most_voted

    # Registrar revert
    consolidated["_overrides"] = [
        o for o in overrides if o["field"] != field
    ]

    ocg_global.parecer_consolidated = consolidated
    db.add(ocg_global)
    await db.commit()

    logger.info(
        "ocg_override.reverted",
        project_id=str(project_id),
        document_id=str(document_id),
        field=field,
        reverted_by=str(current_user_id),
    )

    return {
        "field": field,
        "reverted_at": datetime.now(timezone.utc).isoformat(),
        "reverted_by": str(current_user_id),
    }
