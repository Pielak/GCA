"""
Celery tasks para Pilares Vivos — regeneração e notificações
"""
import asyncio
import time
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.database import engine as async_engine
from app.models.base import ProjectMember, PilaresVivosJob
from app.services.notification_inapp_service import InAppNotificationService
from app.services.pilares_vivos_service import PilaresVivosService

logger = structlog.get_logger(__name__)


@shared_task(bind=True, max_retries=3)
def regenerar_pilares_apos_analise(
    self,
    project_id: str,
    user_id: str,
    trigger: str = "ingestao",
    job_id: str = None,
):
    """Regenera Pilares Vivos após análise de documento ou mudança de questionnaire.

    Args:
        project_id: UUID do projeto
        user_id: UUID do usuário que disparou
        trigger: "ingestao" | "questionnaire" | "manual"
        job_id: UUID do PilaresVivosJob (se disparado via API assíncrona)

    Executado após:
    - Todas as 7 personas terminarem análise de ingestão
    - Questionário técnico ser submetido
    - User clicar "Regenerar Análise" manualmente
    """
    try:
        project_uuid = UUID(project_id)
        user_uuid = UUID(user_id)
        job_uuid = UUID(job_id) if job_id else None

        start_time = time.time()

        asyncio.run(
            _regenerar_pilares_async(
                project_uuid,
                user_uuid,
                trigger,
                async_engine,
                job_uuid,
                start_time,
            )
        )

    except Exception as exc:
        logger.error(
            "pilares_vivos.regeneracao_falhou",
            project_id=project_id,
            user_id=user_id,
            trigger=trigger,
            erro=str(exc),
            retry_count=self.request.retries,
        )

        if job_uuid:
            asyncio.run(_marcar_job_falhou(job_uuid, str(exc), async_engine))

        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _regenerar_pilares_async(
    project_id: UUID,
    user_id: UUID,
    trigger: str,
    async_engine,
    job_id: UUID = None,
    start_time: float = None,
) -> dict:
    """Executa regeneração dentro de sessão assíncrona e atualiza job status."""
    from datetime import datetime, timezone

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            # Marcar job como processing
            if job_id:
                await _atualizar_job_status(job_id, "processing", async_engine)

            result = await PilaresVivosService.regenerar_pilares(
                db=db,
                project_id=project_id,
                user_id=user_id,
            )

            if result["sucesso"]:
                logger.info(
                    "pilares_vivos.regeneracao_sucesso",
                    project_id=str(project_id),
                    user_id=str(user_id),
                    trigger=trigger,
                    tempo=result.get("tempo_total"),
                    pilares_id=result.get("pilares_id"),
                )

                # Atualizar job com resultado
                if job_id and start_time:
                    tempo_total = time.time() - start_time
                    await _marcar_job_completo(
                        job_id,
                        resultado=result.get("documento", {}),
                        tempo_segundos=tempo_total,
                        async_engine=async_engine,
                    )

                # Disparar notificação se houver DTs bloqueantes
                await _verificar_e_notificar_bloqueantes(
                    db=db,
                    project_id=project_id,
                    documento=result.get("documento", {}),
                )
            else:
                logger.error(
                    "pilares_vivos.regeneracao_falhou_async",
                    project_id=str(project_id),
                    trigger=trigger,
                    erro=result.get("erro"),
                )

                if job_id:
                    await _marcar_job_falhou(job_id, result.get("erro", "erro desconhecido"), async_engine)

            return result
    except Exception as exc:
        logger.error(
            "pilares_vivos.regeneracao_exception",
            project_id=str(project_id),
            user_id=str(user_id),
            trigger=trigger,
            error=str(exc),
            exc_info=True,
        )
        if job_id:
            await _marcar_job_falhou(job_id, f"Exceção: {str(exc)[:500]}", async_engine)
        raise


async def _verificar_e_notificar_bloqueantes(
    db: AsyncSession,
    project_id: UUID,
    documento: dict,
) -> None:
    """Verifica se há DTs BLOCKER e notifica GPs. Também notifica conclusão geral."""
    bloqueantes = []
    critical_count = 0

    # Verificar todas as personas
    personas_lista = PilaresVivosService.PERSONAS_ORDER

    for persona_key in personas_lista:
        parecer = documento.get(persona_key)
        if not parecer or not parecer.get("dts"):
            continue

        for dt in parecer.get("dts", []):
            dt_data = dt if isinstance(dt, dict) else {}
            if dt_data.get("impacto") == "BLOCKER":
                bloqueantes.append({
                    "persona": persona_key,
                    "dt_id": dt_data.get("id", "sem-id"),
                    "descricao": dt_data.get("descricao", "sem descrição"),
                })
            elif dt_data.get("impacto") == "CRITICAL":
                critical_count += 1

    # Buscar GPs do projeto
    result = await db.execute(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "gp",
            ProjectMember.is_active == True,
        )
    )
    gps = result.scalars().all()

    # Notificar cada GP via in-app notification
    notification_service = InAppNotificationService(db)

    if bloqueantes:
        # Notificação de bloqueantes
        logger.warning(
            "pilares_vivos.bloqueantes_detectados",
            project_id=str(project_id),
            count=len(bloqueantes),
        )

        bloqueantes_str = "\n".join([f"- {b['persona']}: {b['dt_id']}" for b in bloqueantes])

        for gp_member in gps:
            await notification_service.notify(
                user_id=gp_member.user_id,
                event_type="pilares_vivos_bloqueante",
                title="⚠️ Pilares Vivos: Discovery Tasks Bloqueantes",
                message=f"Foram detectadas {len(bloqueantes)} DTs bloqueantes que bloqueiam codegen:\n{bloqueantes_str}\n\nRevise na aba 'Pilares Vivos' e resolva antes de gerar código.",
                project_id=project_id,
                resource_type="pilares_vivos",
                link=f"/projects/{str(project_id)}/pilares-vivos",
                severity="warning",
            )

            logger.info(
                "pilares_vivos.notificacao_bloqueante_enviada",
                project_id=str(project_id),
                gp_id=str(gp_member.user_id),
                bloqueantes_count=len(bloqueantes),
            )
    else:
        # Notificação de sucesso (sem bloqueantes)
        logger.info(
            "pilares_vivos.analise_concluida_sem_bloqueantes",
            project_id=str(project_id),
            critical_count=critical_count,
        )

        for gp_member in gps:
            status_msg = "✓ Análise concluída com sucesso!"
            if critical_count > 0:
                status_msg += f"\nAviso: {critical_count} DTs CRITICAL detectados — revisão recomendada."

            await notification_service.notify(
                user_id=gp_member.user_id,
                event_type="pilares_vivos_concluido",
                title="✓ Pilares Vivos Regenerado",
                message=status_msg + "\n\nVocê pode prosseguir com CodeGen.",
                project_id=project_id,
                resource_type="pilares_vivos",
                link=f"/projects/{str(project_id)}/pilares-vivos",
                severity="info",
            )


async def _atualizar_job_status(job_id: UUID, status: str, async_engine):
    """Atualiza status do job de Pilares Vivos."""
    from datetime import datetime, timezone

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(select(PilaresVivosJob).where(PilaresVivosJob.id == job_id))
        job = result.scalar_one_or_none()

        if job:
            job.status = status
            if status == "processing":
                job.iniciado_em = datetime.now(timezone.utc)
            await db.commit()


async def _marcar_job_completo(job_id: UUID, resultado: dict, tempo_segundos: float, async_engine):
    """Marca job como completo com resultado."""
    from datetime import datetime, timezone

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(select(PilaresVivosJob).where(PilaresVivosJob.id == job_id))
        job = result.scalar_one_or_none()

        if job:
            job.status = "completed"
            job.resultado_json = resultado
            job.tempo_total_segundos = round(tempo_segundos, 2)
            job.concluido_em = datetime.now(timezone.utc)
            await db.commit()


async def _marcar_job_falhou(job_id: UUID, erro: str, async_engine):
    """Marca job como falhado com mensagem de erro."""
    from datetime import datetime, timezone

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(select(PilaresVivosJob).where(PilaresVivosJob.id == job_id))
        job = result.scalar_one_or_none()

        if job:
            job.status = "failed"
            job.erro_mensagem = erro[:500]  # Limitar tamanho
            job.concluido_em = datetime.now(timezone.utc)
            await db.commit()
