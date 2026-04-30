"""
Celery tasks para Pilares Vivos — regeneração e notificações
"""
import asyncio
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.database import engine as async_engine
from app.models.base import ProjectMember
from app.services.notification_inapp_service import InAppNotificationService
from app.services.pilares_vivos_service import PilaresVivosService

logger = structlog.get_logger(__name__)


@shared_task(bind=True, max_retries=3)
def regenerar_pilares_apos_analise(
    self,
    project_id: str,
    user_id: str,
    trigger: str = "ingestao",
):
    """Regenera Pilares Vivos após análise de documento ou mudança de questionnaire.

    Args:
        project_id: UUID do projeto
        user_id: UUID do usuário que disparou
        trigger: "ingestao" | "questionnaire" | "manual"

    Executado após:
    - Todas as 7 personas terminarem análise de ingestão
    - Questionário técnico ser submetido
    - User clicar "Regenerar Análise" manualmente
    """
    try:
        project_uuid = UUID(project_id)
        user_uuid = UUID(user_id)

        asyncio.run(
            _regenerar_pilares_async(
                project_uuid,
                user_uuid,
                trigger,
                async_engine,
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
        # Retry com backoff
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _regenerar_pilares_async(
    project_id: UUID,
    user_id: UUID,
    trigger: str,
    async_engine,
) -> dict:
    """Executa regeneração dentro de sessão assíncrona."""
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
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

        return result


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
