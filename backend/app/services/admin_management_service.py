"""Gestão da camada administrativa: promoção / rebaixamento / convite /
lifecycle de projeto.

Extensão autorizada em 2026-04-19 pelo stakeholder-soberano — até aqui só
existia `auth_service.bootstrap_admin` (primeiro admin no setup).

Regras duras:
- Apenas Admin pode promover, rebaixar ou convidar.
- **Último admin ativo não pode se auto-rebaixar** — bloqueia órfão.
- Rebaixar Admin não toca em is_support (as flags são independentes).
- Criar Admin novo via convite: gera senha temporária, email opcional
  (reusa email_service.send_admin_invitation_email). Se SMTP não
  configurado, a senha é retornada no response pra Admin comunicar
  manualmente.
- Status de projeto: active | paused | inactive.
  * active   = operacional normal
  * paused   = suspenso temporariamente; dados preservados; sem backup auto
  * inactive = encerrado sem deleção; dados preservados para consulta
  Admin é soberano para alterar entre os 3; nunca deleta hard o projeto
  por este fluxo — quando a intenção era deletar, usar 'inactive'.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.base import Project, User
from app.services.email_service import EmailService
from app.services.audit_service import AuditService, AuditEvents

logger = structlog.get_logger(__name__)


async def _require_admin_actor(db: AsyncSession, actor_id: UUID) -> User:
    actor = (await db.execute(
        select(User).where(User.id == actor_id)
    )).scalar_one_or_none()
    if not actor or not actor.is_active or not actor.is_admin:
        raise PermissionError("Apenas Admin ativo pode gerenciar a camada administrativa.")
    return actor


async def _count_active_admins(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count(User.id)).where(
            User.is_admin.is_(True),
            User.is_active.is_(True),
        )
    )).scalar() or 0)


async def guard_last_admin_on_action(db: AsyncSession, target_user: User) -> None:
    """MVP 11 Fase 11.3 — pré-check canônico de último Admin ativo.

    Usado antes de qualquer ação que removeria `target_user` do pool de
    administradores ativos (lock, delete, demote, deactivate). Se o target
    NÃO é admin ativo, a ação não afeta o pool — retorna sem erro. Se é
    admin ativo, verifica que restam outros — senão levanta
    `PermissionError` com a mensagem canônica. Pré-check antes de
    autorizar a ação (contrato §7 MVP 11 Fase 11.3), nunca recuperação
    posterior.
    """
    if not target_user.is_admin or not target_user.is_active:
        return
    count = await _count_active_admins(db)
    if count - 1 <= 0:
        raise PermissionError(
            f"Operação bloqueada: {target_user.email} é o último "
            "administrador ativo — a instância ficaria sem soberania."
        )


async def set_admin_flag(
    db: AsyncSession,
    *,
    target_user_id: UUID,
    new_value: bool,
    actor_id: UUID,
) -> User:
    """Promove ou rebaixa o papel de Admin de um usuário existente.

    Regra dura (contrato §4.1 + stakeholder 2026-04-19):
    - Apenas Admin pode tocar em is_admin de outros.
    - Último admin ativo não pode se auto-rebaixar.
    - Rebaixar não altera is_support (flags independentes).
    """
    actor = await _require_admin_actor(db, actor_id)

    target = (await db.execute(
        select(User).where(User.id == target_user_id)
    )).scalar_one_or_none()
    if not target:
        raise ValueError("Usuário alvo não encontrado.")
    if not target.is_active:
        raise ValueError("Usuário alvo inativo.")

    current = bool(target.is_admin)
    if current == new_value:
        return target  # noop

    # Rebaixando e alvo é o actor: checa se é o último admin
    if (new_value is False) and (target.id == actor.id):
        count = await _count_active_admins(db)
        if count <= 1:
            raise PermissionError(
                "Você é o último administrador ativo — não é possível se rebaixar."
            )

    # Rebaixando alvo diferente: também checa, por segurança (evita
    # cenário de race onde 2 admins se rebaixam simultaneamente).
    if new_value is False and target.id != actor.id:
        count = await _count_active_admins(db)
        if count <= 1:
            raise PermissionError(
                "A instância ficaria sem administradores ativos. Operação bloqueada."
            )

    target.is_admin = bool(new_value)
    await db.flush()

    # MVP 11 Fase 11.4 — audit canônico: promoção/rebaixamento de Admin
    # (papel de instância; project_id=None por definição)
    if new_value:
        await AuditService(db).log_role_event(
            event_type=AuditEvents.ROLE_GRANTED,
            actor_id=actor.id,
            target_user_id=target.id,
            project_id=None,
            old_role=None,
            new_role="admin",
            phase="admin_promoted",
            resource_type="user",
            resource_id=target.id,
        )
    else:
        await AuditService(db).log_role_event(
            event_type=AuditEvents.ROLE_REVOKED,
            actor_id=actor.id,
            target_user_id=target.id,
            project_id=None,
            old_role="admin",
            new_role=None,
            phase="admin_demoted",
            resource_type="user",
            resource_id=target.id,
        )

    await db.commit()
    await db.refresh(target)
    logger.info(
        "admin_flag_changed",
        target_id=str(target.id),
        new_value=new_value,
        actor_id=str(actor.id),
    )
    return target


async def invite_admin(
    db: AsyncSession,
    *,
    email: str,
    full_name: str,
    actor_id: UUID,
    activation_link: str = "",
) -> dict:
    """Cria (ou promove) usuário a Admin via convite.

    Fluxo:
    - Se email já existe: marca is_admin=True (equivalente a promote).
    - Se não existe: cria user com senha temporária, is_admin=True,
      first_access_completed=False (forçará troca na 1ª entrada).
    - Tenta enviar email com senha via EmailService.send_admin_invitation_email.
      Se SMTP não configurado / falhar, a senha é retornada no response
      pro Admin comunicar manualmente.

    Retorna: {user_id, email, created, temp_password_sent, temp_password?}
    """
    actor = await _require_admin_actor(db, actor_id)
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()
    if not email or "@" not in email:
        raise ValueError("Email inválido.")
    if not full_name:
        raise ValueError("Nome obrigatório.")

    existing = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()

    created = False
    temp_password: Optional[str] = None
    if existing:
        if not existing.is_active:
            raise ValueError("Usuário existe mas está inativo. Reative antes de promover.")
        existing.is_admin = True
        user = existing
    else:
        temp_password = secrets.token_urlsafe(12)
        user = User(
            id=uuid4(),
            email=email,
            full_name=full_name,
            password_hash=hash_password(temp_password),
            is_active=True,
            is_admin=True,
            first_access_completed=False,
        )
        db.add(user)
        created = True
    await db.flush()

    # MVP 11 Fase 11.4 — audit canônico: convite/promoção de Admin
    # (papel de instância; project_id=None)
    await AuditService(db).log_role_event(
        event_type=AuditEvents.ROLE_GRANTED,
        actor_id=actor.id,
        target_user_id=user.id,
        project_id=None,
        old_role=None if created else ("user" if not existing or not existing.is_admin else None),
        new_role="admin",
        phase="invited" if created else "admin_promoted",
        resource_type="user",
        resource_id=user.id,
    )

    await db.commit()
    await db.refresh(user)

    sent = False
    if created and temp_password:
        try:
            ok, _err = EmailService.send_admin_invitation_email(
                to_email=email,
                invited_by_name=(actor.full_name or actor.email),
                temporary_password=temp_password,
                activation_link=activation_link or "",
            )
            sent = bool(ok)
        except Exception as e:  # noqa: BLE001
            logger.warning("admin_invite_email_failed", error=str(e))
            sent = False

    logger.info(
        "admin_invited",
        user_id=str(user.id),
        email=email,
        created=created,
        email_sent=sent,
    )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "created": created,
        "email_sent": sent,
        # Só retorna a senha se: user foi criado agora AND email não
        # foi enviado (admin precisa comunicar manualmente).
        "temp_password": temp_password if (created and not sent) else None,
    }


# ─── Lifecycle de projeto ─────────────────────────────────────────────────

PROJECT_LIFECYCLE_STATES: tuple[str, ...] = ("active", "paused", "inactive")


async def set_project_status(
    db: AsyncSession,
    *,
    project_id: UUID,
    new_status: str,
    actor_id: UUID,
    reason: Optional[str] = None,
) -> Project:
    """Altera o status do projeto entre active|paused|inactive.

    Não deleta nada — dados do projeto (OCG, questionário, backlog,
    documentos, backups, tickets) permanecem intactos em qualquer estado.
    Scheduler de backup (DT-063) já filtra por status='active', então
    projetos paused/inactive param de receber snapshots automáticos mas
    os existentes continuam acessíveis.

    Apenas Admin pode. Validação do valor é dura (whitelist).
    """
    actor = await _require_admin_actor(db, actor_id)

    if new_status not in PROJECT_LIFECYCLE_STATES:
        raise ValueError(
            f"Status inválido: {new_status}. "
            f"Válidos: {', '.join(PROJECT_LIFECYCLE_STATES)}"
        )

    project = (await db.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        raise ValueError("Projeto não encontrado.")

    prev = project.status
    if prev == new_status:
        return project

    project.status = new_status
    await db.flush()

    # MVP 13 Fase 13.6 — audit canônico de mudança de lifecycle.
    await AuditService(db).log_project_event(
        event_type=AuditEvents.PROJECT_STATUS_CHANGED,
        actor_id=actor.id,
        project_id=project.id,
        action="set_status",
        old_status=prev,
        new_status=new_status,
        extra={"reason": (reason or "")[:500]} if reason else None,
    )

    await db.commit()
    await db.refresh(project)

    logger.info(
        "project_status_changed",
        project_id=str(project.id),
        slug=project.slug,
        previous=prev,
        new=new_status,
        actor_id=str(actor.id),
        reason=(reason or "")[:200],
    )
    return project
