"""
Dashboard Router
REST endpoints para monitoramento e visualização de métricas
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID

from app.db.database import get_db
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# ============================================================================
# Pydantic Models
# ============================================================================

class ProjectMetricsResponse(BaseModel):
    """Project-level metrics"""
    project_id: str
    project_name: Optional[str] = None
    project_slug: Optional[str] = None
    status: Optional[str] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    evaluations: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    approved_at: Optional[str] = None


class ProviderCostInfo(BaseModel):
    """Provider cost and performance info"""
    cost_per_1k_tokens: Dict[str, float]
    estimated_latency_ms: Dict[str, float]
    recommended_for: str


class ProviderStatisticsResponse(BaseModel):
    """Provider statistics"""
    timestamp: str
    providers: Dict[str, ProviderCostInfo]
    recommendation: str


class ProjectSummary(BaseModel):
    """Project summary for dashboard"""
    total: int
    approved: int
    pending: int


class ArtifactSummary(BaseModel):
    """Artifact summary"""
    total: int
    evaluated: int


class EvaluationSummary(BaseModel):
    """Evaluation summary"""
    total: int
    average_score: float
    p7_blocked: int
    ready_for_codegen: int


class SystemHealth(BaseModel):
    """System health status"""
    status: str
    last_update: str


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary response"""
    timestamp: str
    projects: ProjectSummary
    artifacts: ArtifactSummary
    evaluations: EvaluationSummary
    system_health: SystemHealth


class TimelineEntry(BaseModel):
    """Timeline entry"""
    date: str
    count: int


class GenerationTimelineResponse(BaseModel):
    """Generation timeline"""
    period_days: int
    start_date: str
    end_date: str
    timeline: Dict[str, int]
    total_in_period: int


class PillarScores(BaseModel):
    """Pillar score breakdown"""
    P1_Business: float
    P2_Rules: float
    P3_Functional: float
    P4_NonFunctional: float
    P5_Architecture: float
    P6_Data: float
    P7_Security: float


class QualityMetricsResponse(BaseModel):
    """Quality metrics"""
    timestamp: str
    evaluation_status: Dict[str, int]
    pillar_averages: PillarScores
    quality_assessment: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    summary="Get dashboard summary",
    description="Get overall system metrics and health status"
)
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """
    Get comprehensive dashboard summary

    Returns:
    - Projects: total, approved, pending
    - Artifacts: total count, evaluated count
    - Evaluations: total, average score, P7 blocked
    - System Health: status and last update
    """

    try:
        service = MonitoringService(db)
        summary = await service.get_dashboard_summary()
        return DashboardSummaryResponse(**summary)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard summary: {str(e)}"
        )


@router.get(
    "/project/{project_id}",
    response_model=ProjectMetricsResponse,
    summary="Get project metrics",
    description="Get detailed metrics for a specific project"
)
async def get_project_metrics(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get project-level metrics

    - **project_id**: Project ID to get metrics for
    - Returns: Artifacts count, evaluation stats, project status
    """

    try:
        service = MonitoringService(db)
        metrics = await service.get_project_metrics(project_id)

        if metrics.get("status") == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found"
            )

        return ProjectMetricsResponse(**metrics)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project metrics: {str(e)}"
        )


@router.get(
    "/providers",
    response_model=ProviderStatisticsResponse,
    summary="Get LLM provider statistics",
    description="Get cost and performance metrics for all LLM providers"
)
async def get_provider_statistics(db: AsyncSession = Depends(get_db)):
    """
    Get LLM provider statistics

    Returns:
    - Cost per 1K tokens (input/output)
    - Estimated latency (min/avg/max)
    - Recommendation for each provider
    """

    try:
        service = MonitoringService(db)
        stats = await service.get_provider_statistics()
        return ProviderStatisticsResponse(**stats)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider statistics: {str(e)}"
        )


@router.get(
    "/timeline",
    response_model=GenerationTimelineResponse,
    summary="Get generation timeline",
    description="Get code generation activity over time"
)
async def get_generation_timeline(
    days: int = 7,
    db: AsyncSession = Depends(get_db)
):
    """
    Get generation timeline

    - **days**: Number of days to look back (default: 7)
    - Returns: Daily breakdown of artifact creation
    """

    if days < 1 or days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Days must be between 1 and 365"
        )

    try:
        service = MonitoringService(db)
        timeline = await service.get_generation_timeline(days)
        return GenerationTimelineResponse(**timeline)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get generation timeline: {str(e)}"
        )


@router.get(
    "/quality",
    response_model=QualityMetricsResponse,
    summary="Get quality metrics",
    description="Get artifact and evaluation quality metrics"
)
async def get_quality_metrics(db: AsyncSession = Depends(get_db)):
    """
    Get quality metrics

    Returns:
    - Evaluation status breakdown (approved, blocked, needs_review)
    - Average scores for each of the 7 pillars
    - Overall quality assessment
    """

    try:
        service = MonitoringService(db)
        metrics = await service.get_quality_metrics()
        return QualityMetricsResponse(**metrics)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get quality metrics: {str(e)}"
        )


@router.get(
    "/health",
    summary="Get system health",
    description="Quick health check endpoint"
)
async def get_system_health(db: AsyncSession = Depends(get_db)):
    """
    Get system health status

    Returns:
    - Status (healthy/initializing/degraded)
    - Last update timestamp
    - Basic counts
    """

    try:
        service = MonitoringService(db)
        summary = await service.get_dashboard_summary()

        projects = summary["projects"]["total"]
        evaluations = summary["evaluations"]["total"]
        status_value = summary["system_health"]["status"]

        return {
            "status": status_value,
            "timestamp": summary["timestamp"],
            "projects": projects,
            "evaluations": evaluations,
            "message": f"System {status_value}" + (
                f" with {projects} projects and {evaluations} evaluations"
                if projects > 0 else " (initializing)"
            )
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


@router.get(
    "/export/summary",
    summary="Export dashboard summary",
    description="Export summary metrics as JSON"
)
async def export_summary(db: AsyncSession = Depends(get_db)):
    """
    Export dashboard summary for external tools

    Returns JSON with complete metrics for integration with BI tools
    """

    try:
        service = MonitoringService(db)
        summary = await service.get_dashboard_summary()
        quality = await service.get_quality_metrics()
        providers = await service.get_provider_statistics()

        return {
            "export_timestamp": summary["timestamp"],
            "dashboard_summary": summary,
            "quality_metrics": quality,
            "provider_statistics": providers
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )
