"""MVP 14 Fase 14.1 — Celery tasks pro pipeline de questionário.

Substitui os 4 `asyncio.create_task` em `QuestionnaireService.submit_questionnaire`
(linhas 135, 231, 242, 254 pré-14.1) por tasks Celery com retry bounded +
ACK late, seguindo o padrão já estabelecido em `app/tasks/pipeline.py`
(MVP 13 Fase 13.3).

Escopo:
- `notify_admins_submitted_task`: email para admins após submit.
- `send_analysis_email_task`: email pro GP com resultado da análise.
- `trigger_n8n_analysis_task`: webhook externo n8n (retry mais
  conservador — falha de rede é comum).
- `generate_ocg_task`: pipeline de 8 agentes IA (retry 60s — LLM
  pesado; idempotente via flag no DB).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from app.celery_app import celery_app
from app.tasks.pipeline import _run_coro_isolated

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.tasks.questionnaire.notify_admins_submitted_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def notify_admins_submitted_task(
    self,
    gp_email: str,
    project_name: str,
    questionnaire_id: str,
    project_id: str | None = None,
) -> dict:
    """Notifica admins que o questionário foi submetido."""
    try:
        _run_coro_isolated(_run_notify_admins(gp_email, project_name, questionnaire_id, project_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("notify_admins_submitted_task.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "questionnaire_id": questionnaire_id}


async def _run_notify_admins(gp_email, project_name, questionnaire_id, project_id):
    from app.services.questionnaire_service import QuestionnaireService
    pid: Any = UUID(project_id) if project_id else None
    await QuestionnaireService._notify_admins_questionnaire_submitted(
        gp_email=gp_email,
        project_name=project_name,
        questionnaire_id=questionnaire_id,
        project_id=pid,
    )


@celery_app.task(
    name="app.tasks.questionnaire.send_analysis_email_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def send_analysis_email_task(
    self,
    gp_email: str,
    project_id: str,
    questionnaire_id: str,
    notification_type: str,
    analysis_result: dict,
) -> dict:
    """Envia email pro GP com resultado da análise do questionário."""
    try:
        _run_coro_isolated(
            _run_send_analysis_email(
                gp_email, project_id, questionnaire_id, notification_type, analysis_result
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("send_analysis_email_task.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=30 + 30 * self.request.retries)
    return {"status": "ok", "questionnaire_id": questionnaire_id}


async def _run_send_analysis_email(gp_email, project_id, questionnaire_id, notification_type, analysis_result):
    from app.services.questionnaire_service import QuestionnaireService
    await QuestionnaireService._send_analysis_email(
        gp_email=gp_email,
        project_id=project_id,
        questionnaire_id=questionnaire_id,
        notification_type=notification_type,
        analysis_result=analysis_result,
    )


@celery_app.task(
    name="app.tasks.questionnaire.trigger_n8n_analysis_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def trigger_n8n_analysis_task(
    self,
    questionnaire_id: str,
    project_id: str,
    gp_email: str,
    responses: dict,
) -> dict:
    """Dispara webhook n8n para análise complementar."""
    try:
        _run_coro_isolated(
            _run_trigger_n8n(questionnaire_id, project_id, gp_email, responses)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("trigger_n8n_analysis_task.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 + 60 * self.request.retries)
    return {"status": "ok", "questionnaire_id": questionnaire_id}


async def _run_trigger_n8n(questionnaire_id, project_id, gp_email, responses):
    from app.services.questionnaire_service import QuestionnaireService
    await QuestionnaireService._trigger_n8n_analysis(
        questionnaire_id=questionnaire_id,
        project_id=project_id,
        gp_email=gp_email,
        responses=responses,
    )


@celery_app.task(
    name="app.tasks.questionnaire.generate_ocg_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def generate_ocg_task(
    self,
    questionnaire_id: str,
    project_id: str,
    gp_email: str,
) -> dict:
    """Dispara pipeline de 8 agentes IA para geração do OCG.

    Retry mais conservador (60s, exponencial) — LLM calls são caras
    e transitório vale esperar. Idempotência via flag no DB do
    questionnaire (já aprovado = no-op).
    """
    try:
        _run_coro_isolated(_run_generate_ocg(questionnaire_id, project_id, gp_email))
    except Exception as exc:  # noqa: BLE001
        logger.error("generate_ocg_task.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 + 60 * self.request.retries)
    return {"status": "ok", "questionnaire_id": questionnaire_id}


async def _run_generate_ocg(questionnaire_id, project_id, gp_email):
    from app.services.questionnaire_service import QuestionnaireService
    await QuestionnaireService._generate_ocg(
        questionnaire_id=UUID(questionnaire_id),
        project_id=UUID(project_id),
        gp_email=gp_email,
    )
