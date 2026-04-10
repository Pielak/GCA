"""
Orquestracao do Pipeline via n8n (spec v2.0 secao 7).

Endpoint webhook que recebe trigger do n8n ou do frontend para executar
o pipeline completo de um item do backlog: CodeGen → TestGen → CI →
Security → Compliance → QA notification.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import BacklogItem, ProjectSettings
from app.services.pipeline_audit_service import PipelineAuditService
from app.core.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Pipeline Orchestration"])


class PipelineRunRequest(BaseModel):
    """Request para executar pipeline completo de um item."""
    backlog_item_id: UUID
    auto_advance: bool = True  # Avancar automaticamente entre etapas


@router.post("/projects/{project_id}/pipeline/run")
async def run_pipeline(
    project_id: UUID,
    request: PipelineRunRequest,
    permissions: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """
    Executa pipeline completo para um item do backlog.

    Fluxo: CodeGen → TestGen → (CI via GitHub Actions) → Security → Compliance
    QA Approval fica pendente para acao humana.
    """
    item = await db.get(BacklogItem, request.backlog_item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Item nao encontrado")

    if item.status not in ("ready", "pending"):
        raise HTTPException(status_code=400, detail=f"Item com status '{item.status}' nao pode iniciar pipeline")

    user_id = permissions["user_id"]
    roles = permissions.get("roles", [])
    audit = PipelineAuditService(db)

    results = {"item_id": str(item.id), "phases": []}

    # Tentar disparar n8n webhook se configurado
    n8n_triggered = await _try_n8n_trigger(db, project_id, item, user_id)
    if n8n_triggered:
        # NAO mudar status aqui — o endpoint generate-code faz isso
        await audit.log_phase(
            project_id=project_id, backlog_item_id=item.id,
            user_id=user_id, role_used=roles[0] if roles else "unknown",
            phase="pipeline_start", status="COMPLETED",
            context={"orchestrator": "n8n", "auto_advance": request.auto_advance},
        )
        await db.commit()
        return {
            **results,
            "orchestrator": "n8n",
            "message": "Pipeline disparado via n8n. Acompanhe o progresso no backlog.",
        }

    # Fallback: disparar sequencialmente via API interna
    await audit.log_phase(
        project_id=project_id, backlog_item_id=item.id,
        user_id=user_id, role_used=roles[0] if roles else "unknown",
        phase="pipeline_start", status="COMPLETED",
        context={"orchestrator": "internal", "auto_advance": request.auto_advance},
    )
    await db.commit()

    return {
        **results,
        "orchestrator": "internal",
        "status": "generating",
        "message": "Pipeline iniciado. Execute as etapas manualmente ou configure n8n para automacao.",
        "next_steps": [
            f"POST /projects/{project_id}/backlog/{item.id}/generate-code",
            f"POST /projects/{project_id}/backlog/{item.id}/generate-tests",
            f"POST /projects/{project_id}/backlog/{item.id}/run-tests",
            f"POST /projects/{project_id}/backlog/{item.id}/security-scan",
            f"POST /projects/{project_id}/backlog/{item.id}/compliance-check",
            f"POST /projects/{project_id}/backlog/{item.id}/qa-approve",
        ],
    }


async def _try_n8n_trigger(
    db: AsyncSession, project_id: UUID, item: BacklogItem, user_id: UUID
) -> bool:
    """Tenta disparar workflow n8n se configurado."""
    from app.core.security import create_access_token

    # Buscar config n8n do projeto
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "n8n",
        )
    )
    n8n_settings = result.scalar_one_or_none()
    if not n8n_settings:
        return False

    config = json.loads(n8n_settings.settings_json)
    webhook_url = config.get("webhook_url")
    if not webhook_url:
        return False

    # Gerar JWT para n8n usar nas chamadas ao backend
    token = create_access_token(data={"sub": str(user_id)})

    payload = {
        "project_id": str(project_id),
        "backlog_item_id": str(item.id),
        "item_title": item.title,
        "module_type": item.module_type,
        "user_id": str(user_id),
        "token": token,
        "callback_base": f"{settings.API_PREFIX}/projects/{project_id}",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code in (200, 201):
                logger.info("n8n.pipeline_triggered", project_id=str(project_id), item_id=str(item.id))
                return True
    except Exception as e:
        logger.warning("n8n.trigger_failed", error=str(e))

    return False


@router.get("/projects/{project_id}/pipeline/{item_id}/status")
async def get_pipeline_status(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna status atual do pipeline de um item com todas as fases."""
    item = await db.get(BacklogItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Item nao encontrado")

    audit = PipelineAuditService(db)
    phases = await audit.get_item_audit(item_id)

    return {
        "item_id": str(item.id),
        "title": item.title,
        "current_status": item.status,
        "branch": item.branch_name,
        "commit_sha": item.commit_sha,
        "phases": phases,
        "phases_completed": len(phases),
    }
