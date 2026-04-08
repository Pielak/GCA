"""
Evaluation Router
Rotas para avaliação de artefatos contra os 7 pilares
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
from typing import Dict, Any, List
import structlog

from app.db.database import get_db
from app.services.evaluation_service import EvaluationService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["evaluation"])


# ========== REQUEST MODELS ==========

class PillarScores(BaseModel):
    """Scores for all 7 pillars"""
    p1_score: float  # Business Alignment (0-100)
    p2_score: float  # Business Logic (0-100)
    p3_score: float  # Functional Requirements (0-100)
    p4_score: float  # Non-Functional (0-100)
    p5_score: float  # Architecture (0-100)
    p6_score: float  # Data (0-100)
    p7_score: float  # Compliance/Security/Testing (0-100)


class EvaluationDetails(BaseModel):
    """Detailed evaluation information"""
    strengths: List[str] = []
    weaknesses: List[str] = []
    recommendations: List[str] = []
    notes: str = ""


class EvaluateArtifactRequest(BaseModel):
    """Request to evaluate an artifact"""
    scores: PillarScores
    details: EvaluationDetails = None
    feedback: str = ""


class EvaluateAllRequest(BaseModel):
    """Request to evaluate all project artifacts"""
    evaluations: List[Dict[str, Any]]


# ========== EVALUATION ENDPOINTS ==========

@router.post("/projects/{project_id}/artifacts/{artifact_id}/evaluate")
async def evaluate_artifact(
    project_id: UUID,
    artifact_id: UUID,
    req: EvaluateArtifactRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Evaluate a single artifact against all 7 pillars

    Returns:
        {
            "id": UUID,
            "artifact_id": UUID,
            "scores": {...},
            "weights": {...},
            "p7_blocked": bool,
            "final_score": float,
            "final_status": "approved|needs_review|blocked",
            "code_generation_allowed": bool,
            "feedback": str
        }
    """
    try:
        service = EvaluationService(db)

        evaluation_data = {
            "p1_score": req.scores.p1_score,
            "p2_score": req.scores.p2_score,
            "p3_score": req.scores.p3_score,
            "p4_score": req.scores.p4_score,
            "p5_score": req.scores.p5_score,
            "p6_score": req.scores.p6_score,
            "p7_score": req.scores.p7_score,
            "details": req.details.dict() if req.details else {},
            "feedback": req.feedback
        }

        evaluation = await service.evaluate_artifact(
            artifact_id=artifact_id,
            evaluator_id=current_user_id,
            evaluation_data=evaluation_data
        )

        return {
            "id": str(evaluation.id),
            "artifact_id": str(evaluation.artifact_id),
            "scores": {
                "p1": evaluation.p1_business_score,
                "p2": evaluation.p2_rules_score,
                "p3": evaluation.p3_functional_score,
                "p4": evaluation.p4_nonfunctional_score,
                "p5": evaluation.p5_architecture_score,
                "p6": evaluation.p6_data_score,
                "p7": evaluation.p7_security_score,
            },
            "weights": {
                "p1": evaluation.p1_weight,
                "p2": evaluation.p2_weight,
                "p3": evaluation.p3_weight,
                "p4": evaluation.p4_weight,
                "p5": evaluation.p5_weight,
                "p6": evaluation.p6_weight,
                "p7": evaluation.p7_weight,
            },
            "p7_blocked": evaluation.p7_blocked,
            "final_score": evaluation.final_score,
            "final_status": evaluation.final_status,
            "code_generation_allowed": evaluation.code_generation_allowed,
            "feedback": evaluation.feedback,
            "evaluated_at": evaluation.evaluation_date.isoformat()
        }

    except ValueError as e:
        logger.warning("evaluation.validate_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("evaluation.error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error evaluating artifact"
        )


@router.get("/projects/{project_id}/artifacts/{artifact_id}/evaluation")
async def get_artifact_evaluation(
    project_id: UUID,
    artifact_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get latest evaluation for an artifact
    """
    try:
        service = EvaluationService(db)
        evaluation = await service.get_artifact_evaluation(artifact_id)

        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No evaluation found for artifact"
            )

        return evaluation

    except HTTPException:
        raise
    except Exception as e:
        logger.error("evaluation.get_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving evaluation"
        )


@router.get("/projects/{project_id}/evaluations")
async def get_project_evaluations(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all evaluations for a project

    Returns:
        {
            "project_id": UUID,
            "total_evaluations": int,
            "evaluations": [...],
            "summary": {
                "avg_score": float,
                "blocked_count": int,
                "can_generate_code": bool
            }
        }
    """
    try:
        service = EvaluationService(db)
        evaluations = await service.get_project_evaluations(project_id)

        # Calculate summary
        total_blocked = sum(1 for e in evaluations if "blocked" in e.get("final_status", ""))
        avg_score = sum(float(e.get("final_score", 0)) for e in evaluations) / len(evaluations) if evaluations else 0
        can_generate = not any(e.get("p7_blocked", False) for e in evaluations) if evaluations else True

        return {
            "project_id": str(project_id),
            "total_evaluations": len(evaluations),
            "evaluations": evaluations,
            "summary": {
                "avg_score": round(avg_score, 1),
                "blocked_count": total_blocked,
                "can_generate_code": can_generate
            }
        }

    except Exception as e:
        logger.error("evaluation.list_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving evaluations"
        )


@router.post("/projects/{project_id}/evaluate-all")
async def evaluate_all_artifacts(
    project_id: UUID,
    req: EvaluateAllRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Evaluate all project artifacts at once

    Returns:
        {
            "evaluations": [...],
            "summary": {
                "total_artifacts": int,
                "approved": int,
                "needs_review": int,
                "blocked": int,
                "avg_score": float,
                "can_generate_code": bool
            }
        }
    """
    try:
        service = EvaluationService(db)

        evaluations, summary = await service.evaluate_all_artifacts(
            project_id=project_id,
            evaluator_id=current_user_id,
            evaluation_results=req.evaluations
        )

        return {
            "project_id": str(project_id),
            "evaluations": [
                {
                    "id": str(e.id),
                    "artifact_id": str(e.artifact_id),
                    "final_score": e.final_score,
                    "final_status": e.final_status,
                    "p7_blocked": e.p7_blocked
                }
                for e in evaluations
            ],
            "summary": summary
        }

    except ValueError as e:
        logger.warning("evaluation.all_validate_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("evaluation.all_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error evaluating artifacts"
        )
