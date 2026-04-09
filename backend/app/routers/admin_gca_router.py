"""
Admin GCA Router — Parametrização de pilares, thresholds e configuração de agentes.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, validator
from typing import Dict, Optional
import structlog

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token, require_admin
from uuid import UUID

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["admin-gca"])


# Valores padrão de configuração
DEFAULT_PILLAR_WEIGHTS = {
    "P1": 10, "P2": 15, "P3": 20, "P4": 20, "P5": 15, "P6": 10, "P7": 10,
}
DEFAULT_THRESHOLDS = {
    "p7_blocking_threshold": 70,
    "ready_threshold": 90,
    "needs_review_threshold": 70,
    "at_risk_threshold": 50,
}
DEFAULT_AGENT_CONFIG = {
    "model": "claude-opus-4-0-20250514",
    "max_tokens": 4096,
    "temperature": 0.3,
}

# Estado em memória (em produção, usar tabela pillar_configuration)
_current_settings = {
    "pillar_weights": dict(DEFAULT_PILLAR_WEIGHTS),
    "score_thresholds": dict(DEFAULT_THRESHOLDS),
    "agent_config": dict(DEFAULT_AGENT_CONFIG),
}


class PillarWeightsRequest(BaseModel):
    P1: int
    P2: int
    P3: int
    P4: int
    P5: int
    P6: int
    P7: int

    @validator("P7")
    def validate_sum(cls, v, values):
        total = sum(values.get(f"P{i}", 0) for i in range(1, 7)) + v
        if total != 100:
            raise ValueError(f"Soma dos pesos deve ser exatamente 100, recebido: {total}")
        return v


class ThresholdsRequest(BaseModel):
    p7_blocking_threshold: int = 70
    ready_threshold: int = 90
    needs_review_threshold: int = 70
    at_risk_threshold: int = 50


@router.get("/admin/gca/settings")
async def get_gca_settings(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Configurações atuais do GCA: pesos dos pilares, thresholds, agentes."""
    return _current_settings


@router.put("/admin/gca/settings/pillar-weights")
async def update_pillar_weights(
    req: PillarWeightsRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza pesos dos pilares. Soma deve ser exatamente 100."""
    _current_settings["pillar_weights"] = {
        "P1": req.P1, "P2": req.P2, "P3": req.P3, "P4": req.P4,
        "P5": req.P5, "P6": req.P6, "P7": req.P7,
    }
    logger.info(
        "admin_gca.pesos_atualizados",
        actor=str(current_user_id),
        weights=_current_settings["pillar_weights"],
    )
    return {"success": True, "pillar_weights": _current_settings["pillar_weights"]}


@router.put("/admin/gca/settings/thresholds")
async def update_thresholds(
    req: ThresholdsRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza thresholds de score."""
    _current_settings["score_thresholds"] = {
        "p7_blocking_threshold": req.p7_blocking_threshold,
        "ready_threshold": req.ready_threshold,
        "needs_review_threshold": req.needs_review_threshold,
        "at_risk_threshold": req.at_risk_threshold,
    }
    logger.info(
        "admin_gca.thresholds_atualizados",
        actor=str(current_user_id),
        thresholds=_current_settings["score_thresholds"],
    )
    return {"success": True, "score_thresholds": _current_settings["score_thresholds"]}
