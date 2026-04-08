"""
Agents Router
Rotas para análise de questionário via sistema de 8 agentes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any
import structlog

from app.db.database import get_db
from app.schemas.ocg import (
    AnalyzerRequest,
    AnalyzerResponse,
    PillarAgentRequest,
    PillarAgentResponse,
    ConsolidatorRequest,
    OCGResponse,
)
from app.services.agent_service import AgentService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["agents"])


# ========== ANALYZER ENDPOINT (Agent 0) ==========

@router.post("/agents/analyze", response_model=AnalyzerResponse)
async def analyze_questionnaire(
    req: AnalyzerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Agent 0: Questionnaire Analyzer

    Classifies survey responses by pillar and extracts project metadata.
    Returns classification mapping and identified anomalies.

    Args:
        req: AnalyzerRequest with questionnaire_id, answers, metadata

    Returns:
        AnalyzerResponse with pillar classification and extracted info
    """
    try:
        logger.info(
            "agents.analyzer_request",
            questionnaire_id=str(req.questionnaire_id),
            num_answers=len(req.answers),
        )

        service = AgentService(db)
        response = await service.analyze_questionnaire(req)

        logger.info(
            "agents.analyzer_success",
            questionnaire_id=str(req.questionnaire_id),
        )

        return response

    except ValueError as e:
        logger.error("agents.analyzer_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("agents.analyzer_unexpected_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao analisar questionário",
        )


# ========== PILLAR SPECIALIST ENDPOINTS (Agents 1-7) ==========

@router.post("/agents/pillar/{pillar_id}", response_model=PillarAgentResponse)
async def analyze_pillar(
    pillar_id: int,
    req: PillarAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Agents 1-7: Pillar Specialists

    Analyzes questionnaire responses specific to one pillar.
    Returns score, findings, and stack implications for that pillar.

    Args:
        pillar_id: 1-7 (P1-P7)
        req: PillarAgentRequest with questions, responses, metadata

    Returns:
        PillarAgentResponse with score, findings, and recommendations
    """
    if pillar_id < 1 or pillar_id > 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pillar_id deve estar entre 1 e 7",
        )

    try:
        logger.info(
            "agents.pillar_request",
            pillar_id=pillar_id,
            questionnaire_id=str(req.questionnaire_id),
        )

        service = AgentService(db)
        response = await service.analyze_pillar(pillar_id, req)

        logger.info(
            "agents.pillar_success",
            pillar_id=pillar_id,
            questionnaire_id=str(req.questionnaire_id),
            score=response.score,
        )

        return response

    except ValueError as e:
        logger.error("agents.pillar_validation_error", pillar_id=pillar_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("agents.pillar_unexpected_error", pillar_id=pillar_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao analisar pilar {pillar_id}",
        )


# ========== CONSOLIDATOR ENDPOINT (Agent 8) ==========

@router.post("/agents/consolidate", response_model=OCGResponse)
async def consolidate_ocg(
    req: ConsolidatorRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Agent 8: OCG Consolidator

    Consolidates pillar analysis results into final OCG.
    Balances trade-offs, produces stack recommendations, and saves to database.

    Args:
        req: ConsolidatorRequest with analyzer output and all pillar results

    Returns:
        OCGResponse with complete OCG data
    """
    try:
        logger.info(
            "agents.consolidator_request",
            questionnaire_id=str(req.questionnaire_id),
            num_pillars=len(req.pillar_results),
        )

        service = AgentService(db)
        response = await service.consolidate_ocg(req)

        logger.info(
            "agents.consolidator_success",
            questionnaire_id=str(req.questionnaire_id),
            ocg_id=str(response.ocg_id),
        )

        return response

    except ValueError as e:
        logger.error("agents.consolidator_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("agents.consolidator_unexpected_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao consolidar OCG",
        )


# ========== OCG RETRIEVAL ENDPOINT ==========

@router.get("/ocg/{ocg_id}", response_model=OCGResponse)
async def get_ocg(
    ocg_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a previously generated OCG by ID.

    Args:
        ocg_id: UUID of the OCG to retrieve

    Returns:
        OCGResponse with complete OCG data
    """
    try:
        logger.info("agents.ocg_retrieve", ocg_id=str(ocg_id))

        from sqlalchemy import select
        from app.models.base import OCG
        import json

        stmt = select(OCG).where(OCG.id == ocg_id)
        result = await db.execute(stmt)
        ocg = result.scalar_one_or_none()

        if not ocg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="OCG não encontrado",
            )

        # Parse OCG data
        ocg_data = json.loads(ocg.ocg_data)

        # Return OCGResponse
        return OCGResponse(**ocg_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("agents.ocg_retrieve_error", ocg_id=str(ocg_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao recuperar OCG",
        )
