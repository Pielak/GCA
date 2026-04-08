"""
Evaluation Service
Motor de avaliação dos 7 pilares com weighted scoring e P7 blocker
"""
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.tenant import Artifact, ArtifactEvaluation, ArtifactStatus
from app.models.pillar import PillarTemplate

logger = structlog.get_logger(__name__)


class EvaluationService:
    """Service for evaluating artifacts against 7 pillars"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate_artifact(
        self,
        artifact_id: UUID,
        evaluator_id: UUID,
        evaluation_data: Dict[str, Any]
    ) -> ArtifactEvaluation:
        """
        Evaluate an artifact against all 7 pillars

        evaluation_data: {
            "p1_score": 0-100,
            "p2_score": 0-100,
            ...
            "p7_score": 0-100,
            "details": {...},
            "feedback": "..."
        }
        """

        try:
            # 1. Get artifact
            artifact = await self.db.get(Artifact, artifact_id)
            if not artifact:
                raise ValueError("Artifact not found")

            # 2. Get pillar weights (default to 1.0)
            weights = await self._get_pillar_weights(
                project_id=artifact.id  # Assuming artifact has project context
            )

            # 3. Calculate weighted scores
            scores = self._extract_scores(evaluation_data)
            final_score, p7_blocked = self._calculate_final_score(scores, weights)

            # 4. Determine status
            status = self._determine_status(scores, p7_blocked)

            # 5. Create evaluation record
            evaluation = ArtifactEvaluation(
                artifact_id=artifact_id,
                p1_business_score=scores.get("p1", 0),
                p2_rules_score=scores.get("p2", 0),
                p3_functional_score=scores.get("p3", 0),
                p4_nonfunctional_score=scores.get("p4", 0),
                p5_architecture_score=scores.get("p5", 0),
                p6_data_score=scores.get("p6", 0),
                p7_security_score=scores.get("p7", 0),
                p1_weight=weights.get("P1", 1.0),
                p2_weight=weights.get("P2", 1.0),
                p3_weight=weights.get("P3", 1.0),
                p4_weight=weights.get("P4", 1.0),
                p5_weight=weights.get("P5", 1.0),
                p6_weight=weights.get("P6", 1.0),
                p7_weight=weights.get("P7", 1.0),
                p7_blocked=p7_blocked,
                final_score=final_score,
                final_status=status,
                code_generation_allowed=(not p7_blocked),
                evaluation_details=evaluation_data.get("details", {}),
                feedback=evaluation_data.get("feedback", ""),
                evaluated_by=evaluator_id
            )

            self.db.add(evaluation)

            # 6. Update artifact
            artifact.status = ArtifactStatus.UNDER_REVIEW
            artifact.last_evaluation_date = datetime.now(timezone.utc)
            artifact.evaluation_id = evaluation.id

            await self.db.commit()

            logger.info("artifact.evaluated",
                       artifact_id=str(artifact_id),
                       final_score=final_score,
                       p7_blocked=p7_blocked,
                       status=status)

            return evaluation

        except Exception as e:
            await self.db.rollback()
            logger.error("artifact.evaluation_failed",
                        artifact_id=str(artifact_id),
                        error=str(e))
            raise

    async def evaluate_all_artifacts(
        self,
        project_id: UUID,
        evaluator_id: UUID,
        evaluation_results: List[Dict[str, Any]]
    ) -> Tuple[List[ArtifactEvaluation], Dict[str, Any]]:
        """
        Evaluate multiple artifacts and return aggregate results

        Returns:
            (evaluations, summary)
            summary: {
                "total_artifacts": int,
                "approved": int,
                "needs_review": int,
                "blocked": int,
                "avg_score": float,
                "can_generate_code": bool
            }
        """

        evaluations = []
        summary = {
            "total_artifacts": 0,
            "approved": 0,
            "needs_review": 0,
            "blocked": 0,
            "avg_score": 0.0,
            "can_generate_code": True
        }

        try:
            total_score = 0

            for eval_data in evaluation_results:
                evaluation = await self.evaluate_artifact(
                    artifact_id=eval_data["artifact_id"],
                    evaluator_id=evaluator_id,
                    evaluation_data=eval_data
                )

                evaluations.append(evaluation)

                # Aggregate stats
                summary["total_artifacts"] += 1
                if evaluation.final_status == "approved":
                    summary["approved"] += 1
                elif evaluation.final_status == "needs_review":
                    summary["needs_review"] += 1
                elif evaluation.final_status == "blocked":
                    summary["blocked"] += 1

                # Check P7 blocker
                if evaluation.p7_blocked:
                    summary["can_generate_code"] = False

                total_score += evaluation.final_score

            # Calculate average
            if summary["total_artifacts"] > 0:
                summary["avg_score"] = total_score / summary["total_artifacts"]

            logger.info("project.evaluation_complete",
                       project_id=str(project_id),
                       total=summary["total_artifacts"],
                       approved=summary["approved"],
                       avg_score=summary["avg_score"])

            return evaluations, summary

        except Exception as e:
            logger.error("project.evaluation_failed",
                        project_id=str(project_id),
                        error=str(e))
            raise

    def _extract_scores(self, evaluation_data: Dict[str, Any]) -> Dict[str, float]:
        """Extract pillar scores from evaluation data"""

        return {
            "p1": evaluation_data.get("p1_score", 0),
            "p2": evaluation_data.get("p2_score", 0),
            "p3": evaluation_data.get("p3_score", 0),
            "p4": evaluation_data.get("p4_score", 0),
            "p5": evaluation_data.get("p5_score", 0),
            "p6": evaluation_data.get("p6_score", 0),
            "p7": evaluation_data.get("p7_score", 0),
        }

    def _calculate_final_score(
        self,
        scores: Dict[str, float],
        weights: Dict[str, float]
    ) -> Tuple[float, bool]:
        """
        Calculate final weighted score and P7 blocker status

        Scoring:
        - P1-P6: Contribute to final score with weights
        - P7: Blocker if < 70 (regardless of other scores)
        """

        # Check P7 blocker
        p7_score = scores.get("p7", 0)
        p7_blocked = p7_score < 70.0

        # Calculate weighted average (excluding P7)
        weighted_sum = 0
        total_weight = 0

        for pillar_num in range(1, 7):  # P1 to P6
            key = f"p{pillar_num}"
            score = scores.get(key, 0)
            weight = weights.get(f"P{pillar_num}", 1.0)

            weighted_sum += score * weight
            total_weight += weight

        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 0

        # Include P7 in final score if not blocked
        if not p7_blocked:
            p7_weight = weights.get("P7", 1.0)
            weighted_sum += p7_score * p7_weight
            total_weight += p7_weight
            final_score = weighted_sum / total_weight

        return round(final_score, 1), p7_blocked

    def _determine_status(
        self,
        scores: Dict[str, float],
        p7_blocked: bool
    ) -> str:
        """Determine artifact status based on scores and P7 blocker"""

        if p7_blocked:
            return "blocked"

        # Calculate average of P1-P7
        avg_score = sum(scores.values()) / len(scores) if scores else 0

        if avg_score >= 80:
            return "approved"
        elif avg_score >= 60:
            return "needs_review"
        else:
            return "blocked"

    async def _get_pillar_weights(
        self,
        project_id: UUID
    ) -> Dict[str, float]:
        """
        Get customized pillar weights for project

        Falls back to default 1.0 if not customized
        """

        try:
            # TODO: Fetch from tenant schema pillar_configuration
            # For now, return default weights
            return {
                "P1": 1.0,
                "P2": 1.0,
                "P3": 1.0,
                "P4": 1.0,
                "P5": 1.0,
                "P6": 1.0,
                "P7": 1.0,
            }

        except Exception as e:
            logger.warning("evaluation.weights_fallback",
                          project_id=str(project_id),
                          error=str(e))
            # Return default weights on error
            return {
                f"P{i}": 1.0 for i in range(1, 8)
            }

    async def get_artifact_evaluation(
        self,
        artifact_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get latest evaluation for artifact"""

        result = await self.db.execute(
            select(ArtifactEvaluation)
            .where(ArtifactEvaluation.artifact_id == artifact_id)
            .order_by(ArtifactEvaluation.evaluation_date.desc())
            .limit(1)
        )

        evaluation = result.scalar_one_or_none()

        if not evaluation:
            return None

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
            "evaluated_at": evaluation.evaluation_date.isoformat(),
            "evaluated_by": str(evaluation.evaluated_by)
        }

    async def get_project_evaluations(
        self,
        project_id: UUID
    ) -> List[Dict[str, Any]]:
        """Get all evaluations for a project"""

        # TODO: Query from tenant schema artifacts and evaluations
        # For now, return empty list

        return []
