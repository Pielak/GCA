"""Backup-4 — Scheduler do backup diário.

APScheduler embutido no FastAPI lifespan. Sem sudo, sem cron externo.

Comportamento:
- Job diário às 12:00 (BRT) — itera projetos ativos, dispara backup
- Catch-up no startup — se algum projeto não teve backup nas últimas
  24h, dispara imediatamente (mas escalonado pra não sobrecarregar)
- Notificações — registra `user_notifications` no início e fim de cada
  backup pra GP/admin do projeto verem na próxima sessão
- Banner global — `GET /api/v1/backups/active` lista backups com
  status='running' (frontend mostra banner enquanto durar)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID, uuid4

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.models.base import Project, ProjectBackup, User, UserNotification
from app.services import project_backup_service as svc

logger = structlog.get_logger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def _notify_project(
    db: AsyncSession,
    project_id: UUID,
    title: str,
    message: str,
    severity: str = "info",
    link: Optional[str] = None,
    event_type: str = "backup.event",
) -> None:
    """Cria UserNotification pro responsible_admin + GP do projeto."""
    project = (await db.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        return

    recipients: List[UUID] = []
    if project.responsible_admin_id:
        recipients.append(project.responsible_admin_id)
    # GP do projeto (papel canônico)
    from app.models.base import ProjectMember
    members = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "gp",
        )
    )).scalars().all()
    for m in members:
        if m.accepted_at and m.user_id not in recipients:
            recipients.append(m.user_id)

    for uid in recipients:
        notif = UserNotification(
            id=uuid4(),
            user_id=uid,
            project_id=project_id,
            event_type=event_type,
            title=title,
            message=message,
            severity=severity,
            link=link or f"/projects/{project_id}/backups",
            created_at=datetime.now(timezone.utc),
        )
        db.add(notif)
    await db.flush()


async def _run_backup_for_project(project_id: UUID, trigger_source: str) -> None:
    """Executa backup + notifica início/fim. Em sessão própria pra não
    interferir com outras transações em andamento."""
    async with AsyncSessionLocal() as db:
        try:
            await _notify_project(
                db, project_id,
                title="Backup iniciado",
                message=f"Backup automático ({trigger_source}) começou agora.",
                severity="info",
            )
            await db.commit()

            await svc.create_backup(db, project_id, actor_id=None, trigger_source=trigger_source)

            await _notify_project(
                db, project_id,
                title="Backup concluído",
                message="Backup automático concluído com sucesso. Disponível em Configurações > Backups.",
                severity="success",
            )
            await db.commit()
        except Exception as e:
            logger.error("scheduler.backup_failed", project_id=str(project_id), error=str(e)[:300])
            try:
                await _notify_project(
                    db, project_id,
                    title="Backup falhou",
                    message=f"O backup automático falhou: {str(e)[:200]}. Verifique logs ou dispare manualmente.",
                    severity="error",
                )
                await db.commit()
            except Exception:
                pass


async def daily_backup_job() -> None:
    """Job principal: itera projetos ativos e dispara backup pra cada."""
    logger.info("scheduler.daily_backup_starting")
    async with AsyncSessionLocal() as db:
        projects = (await db.execute(
            select(Project).where(Project.status == "active")
        )).scalars().all()
        project_ids = [p.id for p in projects]

    # Escalona com 30s entre cada pra não saturar DB/CPU
    for pid in project_ids:
        try:
            await _run_backup_for_project(pid, "scheduled")
        except Exception as e:
            logger.error("scheduler.project_backup_error", project_id=str(pid), error=str(e)[:200])
        await asyncio.sleep(30)

    logger.info("scheduler.daily_backup_completed", projects_processed=len(project_ids))


async def startup_catchup_job() -> None:
    """No startup: pra cada projeto ativo, se last_backup_at < now-24h,
    dispara backup imediato (catch-up de janelas perdidas com servidor down)."""
    logger.info("scheduler.startup_catchup_starting")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        projects = (await db.execute(
            select(Project).where(Project.status == "active")
        )).scalars().all()
        # Filtra projetos que precisam de catch-up (sem backup ou >24h)
        needs = [p for p in projects if p.last_backup_at is None or p.last_backup_at < cutoff]
        ids = [p.id for p in needs]

    if not ids:
        logger.info("scheduler.startup_catchup_skipped", reason="all_projects_recent")
        return

    logger.info("scheduler.startup_catchup_dispatching", projects=len(ids))
    for pid in ids:
        try:
            await _run_backup_for_project(pid, "startup_catchup")
        except Exception as e:
            logger.error("scheduler.catchup_error", project_id=str(pid), error=str(e)[:200])
        await asyncio.sleep(15)


def start_scheduler() -> None:
    """Inicia o APScheduler — chamado no lifespan do FastAPI startup."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("scheduler.already_started")
        return

    # Timezone hardcoded BRT — clientes BR. Configurável via env futura.
    sched = AsyncIOScheduler(timezone="America/Sao_Paulo")
    sched.add_job(
        daily_backup_job,
        CronTrigger(hour=12, minute=0),
        id="daily_backup",
        misfire_grace_time=3600,  # 1h de tolerância antes de pular
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    _scheduler = sched
    logger.info("scheduler.started", job_id="daily_backup", cron="0 12 * * *", tz="America/Sao_Paulo")

    # Catch-up no startup, em background
    asyncio.create_task(startup_catchup_job())


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler.stopped")


def is_scheduler_running() -> bool:
    return _scheduler is not None and _scheduler.running
