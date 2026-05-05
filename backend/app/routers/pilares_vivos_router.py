"""Endpoints para Pilares Vivos — Análise viva consolidada de 7 personas"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import PilaresVivosJob
from app.services.pilares_vivos_service import PilaresVivosService
from app.tasks.pilares_vivos_task import regenerar_pilares_apos_analise

router = APIRouter(tags=["Pilares Vivos"])


@router.post("/projects/{project_id}/pilares/regenerar")
async def regenerar_pilares(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_action("project:edit")),
):
    """Inicia regeneração assíncrona de Pilares Vivos.

    Retorna job_id imediatamente (sem bloqueio). Frontend faz poll em /jobs/{job_id}.

    Fluxo:
    1. Criar PilaresVivosJob com status=queued
    2. Disparar Celery task regenerar_pilares_apos_analise
    3. Retornar job_id + status + celery_task_id
    """
    from uuid import uuid4

    user_id = user_context.get("user_id")

    job_id = uuid4()
    job = PilaresVivosJob(
        id=job_id,
        project_id=project_id,
        status="queued",
        criado_por=user_id,
    )

    db.add(job)
    await db.flush()

    message = regenerar_pilares_apos_analise.send(
        project_id=str(project_id),
        user_id=str(user_id),
        trigger="manual",
    )

    job.celery_task_id = message.message_id
    await db.commit()

    return {
        "sucesso": True,
        "job_id": str(job_id),
        "status": "queued",
        "celery_task_id": message.message_id,
    }


@router.get("/projects/{project_id}/pilares/jobs/{job_id}")
async def obter_status_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Obtém status de job de regeneração de Pilares Vivos.

    Status: queued, processing, completed, failed.
    Se completed, inclui resultado_json com documento regenerado.
    """
    result = await db.execute(
        select(PilaresVivosJob).where(
            PilaresVivosJob.id == job_id,
            PilaresVivosJob.project_id == project_id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    response = {
        "job_id": str(job.id),
        "status": job.status,
        "criado_em": job.criado_em.isoformat() if job.criado_em else None,
        "iniciado_em": job.iniciado_em.isoformat() if job.iniciado_em else None,
        "concluido_em": job.concluido_em.isoformat() if job.concluido_em else None,
        "tempo_total_segundos": float(job.tempo_total_segundos) if job.tempo_total_segundos else None,
    }

    if job.status == "completed":
        response["resultado_json"] = job.resultado_json
    elif job.status == "failed":
        response["erro_mensagem"] = job.erro_mensagem

    return response


@router.get("/projects/{project_id}/pilares")
async def obter_pilares(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Obtém documento Pilares Vivos mais recente do projeto."""
    from app.models.base import PilaresVivos
    from sqlalchemy import select

    result = await db.execute(
        select(PilaresVivos).where(PilaresVivos.project_id == project_id)
    )
    pilares = result.scalar_one_or_none()

    if not pilares:
        raise HTTPException(
            status_code=404,
            detail="Pilares Vivos não encontrado. Execute regeneração primeiro.",
        )

    return {
        "id": str(pilares.id),
        "projeto_id": str(pilares.project_id),
        "documento": pilares.documento,
        "gerado_em": pilares.gerado_em.isoformat() if pilares.gerado_em else None,
        "regenerado_em": pilares.regenerado_em.isoformat() if pilares.regenerado_em else None,
        "gerado_por": str(pilares.gerado_por),
    }


@router.get("/projects/{project_id}/pilares/historia")
async def obter_pilares_historia(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Obtém histórico de versões anteriores de Pilares Vivos."""
    from app.models.base import PilaresVivosHistory
    from sqlalchemy import select

    result = await db.execute(
        select(PilaresVivosHistory)
        .where(PilaresVivosHistory.project_id == project_id)
        .order_by(PilaresVivosHistory.archived_em.desc())
        .limit(10)
    )
    historico = result.scalars().all()

    return [
        {
            "id": str(h.id),
            "gerado_em": h.gerado_em.isoformat() if h.gerado_em else None,
            "archived_em": h.archived_em.isoformat() if h.archived_em else None,
            "personas_modificadas": h.personas_modificadas or [],
            "resumo_mudancas": h.resumo_mudancas,
        }
        for h in historico
    ]
