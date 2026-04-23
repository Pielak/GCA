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

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, update

from app.celery_app import celery_app
from app.tasks.pipeline import _run_coro_isolated

logger = structlog.get_logger(__name__)


# MVP 29 Fase 29.2 — Helper canônico de claim atômico. UPDATE condicional
# funciona como uma "reserva" do slot: se o rowcount volta 1, esta execução
# é a dona do efeito. Se volta 0, outra execução já claimou antes —
# redistribuição de worker morto ou retry duplo. Skip silencioso canônico.


async def _try_claim_questionnaire_flag(db, questionnaire_id: UUID, flag: str) -> bool:
    """UPDATE atomic. True = slot reservado, prossiga. False = skip.

    Compatível com qualquer coluna `TIMESTAMP WITH TIME ZONE NULL` do
    `Questionnaire`. Faz commit próprio — chamador não precisa gerenciar.
    """
    from app.models.base import Questionnaire
    if not hasattr(Questionnaire, flag):
        raise ValueError(f"flag '{flag}' não existe no Questionnaire")
    column = getattr(Questionnaire, flag)
    now = datetime.now(timezone.utc)
    r = await db.execute(
        update(Questionnaire)
        .where(Questionnaire.id == questionnaire_id, column.is_(None))
        .values({flag: now})
    )
    await db.commit()
    claimed = (r.rowcount or 0) > 0
    if not claimed:
        logger.info(
            "questionnaire.flag_already_claimed",
            questionnaire_id=str(questionnaire_id),
            flag=flag,
        )
    return claimed


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
    from app.db.database import AsyncSessionLocal
    from app.services.questionnaire_service import QuestionnaireService

    qid = UUID(questionnaire_id) if isinstance(questionnaire_id, str) else questionnaire_id
    async with AsyncSessionLocal() as db:
        claimed = await _try_claim_questionnaire_flag(db, qid, "admins_notified_at")
        if not claimed:
            return  # skip silencioso: email já foi enviado

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
    from app.db.database import AsyncSessionLocal
    from app.services.questionnaire_service import QuestionnaireService

    qid = UUID(questionnaire_id) if isinstance(questionnaire_id, str) else questionnaire_id
    async with AsyncSessionLocal() as db:
        claimed = await _try_claim_questionnaire_flag(db, qid, "analysis_email_sent_at")
        if not claimed:
            return  # skip silencioso

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
    # MVP 29 Fase 29.2 — guard canônico: se já existe OCG para esse
    # questionnaire_id, skip silencioso. Uma nova redistribuição de task
    # não pode gerar v1 + v2 duplicado do mesmo OCG inicial.
    from app.db.database import AsyncSessionLocal
    from app.models.base import OCG
    from app.services.questionnaire_service import QuestionnaireService

    qid = UUID(questionnaire_id)
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(OCG.id).where(OCG.questionnaire_id == qid).limit(1)
        )).scalar_one_or_none()
        if existing is not None:
            logger.info(
                "generate_ocg_task.skip_already_exists",
                questionnaire_id=str(qid),
                ocg_id=str(existing),
            )
            return

    await QuestionnaireService._generate_ocg(
        questionnaire_id=qid,
        project_id=UUID(project_id),
        gp_email=gp_email,
    )
