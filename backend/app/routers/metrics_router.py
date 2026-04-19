"""DT-060 — Endpoints de métricas operacionais.

3 endpoints:
- GET /api/v1/metrics/health        — sempre 200, healthcheck público
- GET /api/v1/metrics/dashboard     — JSON agregado (audit:view)
- GET /api/v1/metrics/prometheus    — texto Prometheus (audit:view)

Acesso a dashboard/prometheus exige `audit:view` (per matriz DT-044
RBAC). Healthcheck é público — usado por load balancer / k8s probe.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user_from_token
from app.db.database import get_db
from app.models.base import ProjectMember, User
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])
project_router = APIRouter(
    prefix="/projects/{project_id}/metrics", tags=["project-metrics"],
)


async def _require_admin(
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Métricas globais — restritas a admin (não há `project_id` na URL).

    DT-060: dashboard agrega dados de todos os projetos; só admin tem
    visão global por contrato §4.1 (Admin opera a instância). GP/Dev
    têm escopo de projeto, não de instância.
    """
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user or not user.is_admin or not user.is_active:
        raise HTTPException(status_code=403, detail="Apenas admins podem ver métricas globais.")
    return {"user_id": user_id, "is_admin": True}


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Healthcheck público — usado por load balancer / liveness probe.

    Não autenticado. Confirma que app respondeu e DB query trivial passou.
    """
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT 1"))
        ok = result.scalar() == 1
    except Exception:
        ok = False
    return {"status": "ok" if ok else "degraded", "db": ok}


@router.get("/dashboard")
async def metrics_dashboard(
    hours: int = Query(24, ge=1, le=720, description="Janela em horas (1-720)"),
    _admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Snapshot agregado pra UI: AI usage, audit, projects, users."""
    svc = MetricsService(db)
    return await svc.as_dashboard_dict(hours=hours)


@router.get("/prometheus", response_class=Response)
async def metrics_prometheus(
    hours: int = Query(24, ge=1, le=720),
    _admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mesma agregação do dashboard, formato texto Prometheus.

    Útil pra scrape externo (Grafana Agent, Prometheus). Exige
    `audit:view` — não exponha publicamente; clientes que querem
    expor via reverse proxy devem proxiar com auth.
    """
    svc = MetricsService(db)
    text = await svc.as_prometheus_text(hours=hours)
    return Response(content=text, media_type="text/plain; charset=utf-8")


# ─── Métricas por projeto (autorização: admin OR membro aceito) ───────────

async def _require_project_access(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Autoriza acesso a métricas do projeto.
    Admin (ou Support) sempre; caso contrário exige membership aceito."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido ou inativo.")

    if user.is_admin or user.is_support:
        return {"user_id": user_id, "scope": "admin_or_support"}

    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at:
        raise HTTPException(
            status_code=403,
            detail="Apenas Admin, Sustentação ou membro aceito do projeto pode ver estas métricas.",
        )
    return {"user_id": user_id, "scope": "member", "role": member.role}


@project_router.get("/dashboard")
async def project_metrics_dashboard(
    project_id: UUID,
    hours: int = Query(24, ge=1, le=720),
    _auth: dict = Depends(_require_project_access),
    db: AsyncSession = Depends(get_db),
):
    """Métricas operacionais do projeto: AI usage e eventos de audit
    (limitação: audit filtra por resource_id=project_id — eventos
    diretos sobre o projeto, não os recursos-filhos)."""
    svc = MetricsService(db)
    return await svc.as_dashboard_dict(hours=hours, project_id=project_id)
