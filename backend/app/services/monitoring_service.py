"""
Monitoring Service
Rastreia métricas de geração de código, performance e custos
"""
import structlog
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from enum import Enum

from app.models.tenant import Artifact, ArtifactEvaluation
from app.models.onboarding import ProjectRequest

logger = structlog.get_logger(__name__)


class LLMProviderMetrics(str, Enum):
    """LLM provider cost and latency mappings"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GROK = "grok"
    DEEPSEEK = "deepseek"


# Estimated costs per 1K tokens (in USD)
PROVIDER_COSTS = {
    "anthropic": {"input": 0.003, "output": 0.015},
    "openai": {"input": 0.005, "output": 0.015},
    "grok": {"input": 0.002, "output": 0.010},
    "deepseek": {"input": 0.0005, "output": 0.002}
}

# Estimated latency (in seconds)
PROVIDER_LATENCY = {
    "anthropic": {"min": 1.5, "avg": 3.0, "max": 10.0},
    "openai": {"min": 1.0, "avg": 2.5, "max": 8.0},
    "grok": {"min": 0.5, "avg": 1.5, "max": 5.0},
    "deepseek": {"min": 1.0, "avg": 2.0, "max": 6.0}
}


class MonitoringService:
    """Service for tracking and analyzing code generation metrics"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_generation(
        self,
        project_id: UUID,
        provider: str,
        tokens_generated: int,
        generation_time_ms: float,
        status: str = "success"
    ) -> Dict[str, Any]:
        """Track code generation event"""

        try:
            # Calculate estimated cost
            cost = self._calculate_cost(provider, tokens_generated)

            event = {
                "project_id": str(project_id),
                "provider": provider,
                "tokens_generated": tokens_generated,
                "generation_time_ms": generation_time_ms,
                "estimated_cost_usd": cost,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            logger.info("monitoring.generation_tracked",
                       project_id=str(project_id),
                       provider=provider,
                       tokens=tokens_generated,
                       time_ms=generation_time_ms,
                       cost=cost)

            return event

        except Exception as e:
            logger.error("monitoring.track_generation_failed",
                        project_id=str(project_id),
                        error=str(e))
            raise

    async def get_project_metrics(
        self,
        project_id: UUID
    ) -> Dict[str, Any]:
        """Get aggregated metrics for a project"""

        try:
            # Get project
            project = await self.db.get(ProjectRequest, project_id)
            if not project:
                return {
                    "project_id": str(project_id),
                    "status": "not_found"
                }

            # Count artifacts
            result = await self.db.execute(
                select(func.count(Artifact.id))
                .where(Artifact.created_by == project.gp_id)
            )
            artifact_count = result.scalar() or 0

            # Count evaluations
            result = await self.db.execute(
                select(func.count(ArtifactEvaluation.id))
            )
            evaluation_count = result.scalar() or 0

            # Get evaluation stats
            result = await self.db.execute(
                select(
                    func.avg(ArtifactEvaluation.final_score).label("avg_score"),
                    func.max(ArtifactEvaluation.final_score).label("max_score"),
                    func.min(ArtifactEvaluation.final_score).label("min_score")
                )
            )
            scores = result.first()

            return {
                "project_id": str(project_id),
                "project_name": project.project_name,
                "project_slug": project.project_slug,
                "status": project.status.value,
                "artifacts": {
                    "total": artifact_count
                },
                "evaluations": {
                    "total": evaluation_count,
                    "avg_score": float(scores[0]) if scores[0] else 0,
                    "max_score": float(scores[1]) if scores[1] else 0,
                    "min_score": float(scores[2]) if scores[2] else 0
                },
                "created_at": project.requested_at.isoformat(),
                "approved_at": project.approved_at.isoformat() if project.approved_at else None
            }

        except Exception as e:
            logger.error("monitoring.get_metrics_failed",
                        project_id=str(project_id),
                        error=str(e))
            raise

    async def get_provider_statistics(self) -> Dict[str, Any]:
        """Get provider usage and cost statistics"""

        providers = list(PROVIDER_COSTS.keys())

        stats = {}
        for provider in providers:
            stats[provider] = {
                "cost_per_1k_tokens": PROVIDER_COSTS[provider],
                "estimated_latency_ms": {
                    "min": PROVIDER_LATENCY[provider]["min"] * 1000,
                    "avg": PROVIDER_LATENCY[provider]["avg"] * 1000,
                    "max": PROVIDER_LATENCY[provider]["max"] * 1000
                },
                "recommended_for": self._get_provider_recommendation(provider)
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "providers": stats,
            "recommendation": "Use Anthropic Claude for best quality, DeepSeek for lowest cost"
        }

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get dashboard summary for system overview"""

        try:
            # Count total projects
            result = await self.db.execute(
                select(func.count(ProjectRequest.id))
            )
            total_projects = result.scalar() or 0

            # Count approved projects
            result = await self.db.execute(
                select(func.count(ProjectRequest.id))
                .where(ProjectRequest.status == "approved")
            )
            approved_projects = result.scalar() or 0

            # Count total artifacts
            result = await self.db.execute(
                select(func.count(Artifact.id))
            )
            total_artifacts = result.scalar() or 0

            # Count evaluated artifacts
            result = await self.db.execute(
                select(func.count(ArtifactEvaluation.id))
            )
            total_evaluations = result.scalar() or 0

            # Get average evaluation score
            result = await self.db.execute(
                select(func.avg(ArtifactEvaluation.final_score))
            )
            avg_score = result.scalar() or 0

            # Count P7 blocked evaluations
            result = await self.db.execute(
                select(func.count(ArtifactEvaluation.id))
                .where(ArtifactEvaluation.p7_blocked == True)
            )
            p7_blocked_count = result.scalar() or 0

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "projects": {
                    "total": total_projects,
                    "approved": approved_projects,
                    "pending": total_projects - approved_projects
                },
                "artifacts": {
                    "total": total_artifacts,
                    "evaluated": total_evaluations
                },
                "evaluations": {
                    "total": total_evaluations,
                    "average_score": round(float(avg_score), 1),
                    "p7_blocked": p7_blocked_count,
                    "ready_for_codegen": total_evaluations - p7_blocked_count
                },
                "system_health": {
                    "status": "healthy" if approved_projects > 0 else "initializing",
                    "last_update": datetime.now(timezone.utc).isoformat()
                }
            }

        except Exception as e:
            logger.error("monitoring.dashboard_summary_failed",
                        error=str(e))
            raise

    async def get_generation_timeline(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get code generation activity over time"""

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get artifacts created in timeframe
        result = await self.db.execute(
            select(
                func.date(Artifact.created_at).label("date"),
                func.count(Artifact.id).label("count")
            )
            .where(Artifact.created_at >= cutoff_date)
            .group_by(func.date(Artifact.created_at))
            .order_by(func.date(Artifact.created_at))
        )

        timeline = {}
        for row in result.all():
            date_str = row[0].isoformat() if row[0] else "unknown"
            timeline[date_str] = row[1]

        return {
            "period_days": days,
            "start_date": cutoff_date.isoformat(),
            "end_date": datetime.now(timezone.utc).isoformat(),
            "timeline": timeline,
            "total_in_period": sum(timeline.values())
        }

    async def get_quality_metrics(self) -> Dict[str, Any]:
        """Get code quality and evaluation metrics"""

        try:
            # Get evaluation status breakdown
            result = await self.db.execute(
                select(
                    ArtifactEvaluation.final_status,
                    func.count(ArtifactEvaluation.id).label("count")
                )
                .group_by(ArtifactEvaluation.final_status)
            )

            status_breakdown = {}
            for status, count in result.all():
                status_breakdown[status or "unknown"] = count

            # Get pillar scores distribution
            result = await self.db.execute(
                select(
                    func.avg(ArtifactEvaluation.p1_business_score),
                    func.avg(ArtifactEvaluation.p2_rules_score),
                    func.avg(ArtifactEvaluation.p3_functional_score),
                    func.avg(ArtifactEvaluation.p4_nonfunctional_score),
                    func.avg(ArtifactEvaluation.p5_architecture_score),
                    func.avg(ArtifactEvaluation.p6_data_score),
                    func.avg(ArtifactEvaluation.p7_security_score)
                )
            )

            pillars = result.first()
            pillar_scores = {
                "P1_Business": round(float(pillars[0]), 1) if pillars[0] else 0,
                "P2_Rules": round(float(pillars[1]), 1) if pillars[1] else 0,
                "P3_Functional": round(float(pillars[2]), 1) if pillars[2] else 0,
                "P4_NonFunctional": round(float(pillars[3]), 1) if pillars[3] else 0,
                "P5_Architecture": round(float(pillars[4]), 1) if pillars[4] else 0,
                "P6_Data": round(float(pillars[5]), 1) if pillars[5] else 0,
                "P7_Security": round(float(pillars[6]), 1) if pillars[6] else 0
            }

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "evaluation_status": status_breakdown,
                "pillar_averages": pillar_scores,
                "quality_assessment": self._assess_quality(pillar_scores)
            }

        except Exception as e:
            logger.error("monitoring.quality_metrics_failed",
                        error=str(e))
            raise

    def _calculate_cost(self, provider: str, tokens: int) -> float:
        """Calculate estimated cost for token generation"""

        if provider not in PROVIDER_COSTS:
            return 0.0

        # Estimate 70% input, 30% output
        input_tokens = int(tokens * 0.7)
        output_tokens = int(tokens * 0.3)

        costs = PROVIDER_COSTS[provider]
        total_cost = (input_tokens * costs["input"] / 1000) + (output_tokens * costs["output"] / 1000)

        return round(total_cost, 4)

    def _get_provider_recommendation(self, provider: str) -> str:
        """Get recommended use case for provider"""

        recommendations = {
            "anthropic": "Best for quality code generation, recommended for production",
            "openai": "Advanced reasoning, good for complex architectures",
            "grok": "Fast generation, real-time knowledge, cost-effective",
            "deepseek": "Lowest cost, specialized in coding, good for volume"
        }

        return recommendations.get(provider, "General purpose")

    def _assess_quality(self, pillar_scores: Dict[str, float]) -> str:
        """Assess overall quality based on pillar scores"""

        avg_score = sum(pillar_scores.values()) / len(pillar_scores) if pillar_scores else 0

        if avg_score >= 85:
            return "Excellent - All pillars strong"
        elif avg_score >= 75:
            return "Good - Most pillars adequate"
        elif avg_score >= 65:
            return "Acceptable - Some pillars need improvement"
        else:
            return "Needs Review - Multiple pillars below threshold"
