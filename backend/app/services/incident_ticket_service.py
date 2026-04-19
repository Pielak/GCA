"""MVP 6 — service de tickets de incidente.

Roteamento por papel do autor:
  Dev/Tester/QA  → target_scope='gp'    (GPs do projeto são notificados)
  GP             → target_scope='admin' (Admins da instância são notificados)
  Admin          → target_scope='admin' (demais Admins são notificados)

Compartimentalização: todo predicado inclui project_id. Ticket de projeto
A nunca é lido por não-admin fora do projeto A. Admin vê cross-projeto
via target_scope='admin'.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IncidentTicket,
    IncidentTicketComment,
    Project,
    ProjectMember,
    User,
)
from app.services.notification_inapp_service import InAppNotificationService


TargetScope = Literal["gp", "admin"]
Category = Literal["bug", "duvida", "pedido_feature", "incidente_pipeline"]
Priority = Literal["baixa", "media", "alta", "critica"]
Status = Literal["open", "in_progress", "resolved", "closed"]

VALID_CATEGORIES: tuple[str, ...] = ("bug", "duvida", "pedido_feature", "incidente_pipeline")
VALID_PRIORITIES: tuple[str, ...] = ("baixa", "media", "alta", "critica")
VALID_STATUS: tuple[str, ...] = ("open", "in_progress", "resolved", "closed")


# ─── Resolução de papel/destinatários ──────────────────────────────────────

async def _resolve_target_scope(
    db: AsyncSession, project_id: UUID, author_id: UUID
) -> TargetScope:
    """Determina para onde o ticket vai, com base no papel do autor no
    projeto (ou em is_admin global).

    Regra binária (contrato §7 MVP 6):
      - autor Admin global    → 'admin'
      - autor GP do projeto   → 'admin'
      - autor Dev/Tester/QA   → 'gp'

    Se o autor não tem vínculo aceito com o projeto e não é admin, levanta
    ValueError — caller (router) traduz pra 403.
    """
    user = (await db.execute(
        select(User).where(User.id == author_id)
    )).scalar_one_or_none()
    if not user or not user.is_active:
        raise ValueError("Autor inválido ou inativo.")

    if user.is_admin:
        return "admin"

    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == author_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at:
        raise ValueError("Autor não é membro aceito do projeto.")

    if member.role == "gp":
        return "admin"
    return "gp"


async def _list_recipients(
    db: AsyncSession, project_id: UUID, target_scope: TargetScope, author_id: UUID
) -> list[UUID]:
    """Destinatários da notificação. Exclui o autor (não se auto-notifica)."""
    if target_scope == "gp":
        rows = (await db.execute(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "gp",
                ProjectMember.accepted_at.isnot(None),
            )
        )).scalars().all()
        return [uid for uid in rows if uid != author_id]

    # admin
    rows = (await db.execute(
        select(User.id).where(
            User.is_admin.is_(True),
            User.is_active.is_(True),
        )
    )).scalars().all()
    return [uid for uid in rows if uid != author_id]


# ─── CRUD + ações ──────────────────────────────────────────────────────────

async def create_ticket(
    db: AsyncSession,
    *,
    project_id: UUID,
    author_id: UUID,
    title: str,
    description: str,
    category: Category,
    priority: Priority,
) -> IncidentTicket:
    """Cria ticket, resolve target_scope automaticamente, notifica
    destinatários. commit ocorre dentro."""
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Categoria inválida: {category}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Prioridade inválida: {priority}")
    title = (title or "").strip()
    description = (description or "").strip()
    if not title or not description:
        raise ValueError("Título e descrição são obrigatórios.")
    if len(title) > 200:
        raise ValueError("Título excede 200 caracteres.")

    # Confirma projeto existe (evita FK violation mais adiante).
    project = (await db.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        raise ValueError("Projeto não encontrado.")

    target_scope = await _resolve_target_scope(db, project_id, author_id)

    ticket = IncidentTicket(
        project_id=project_id,
        author_id=author_id,
        target_scope=target_scope,
        category=category,
        priority=priority,
        status="open",
        title=title,
        description=description,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    await _notify_recipients(
        db, ticket, event_suffix="opened",
        title_tpl="Novo ticket: {title}",
        message=f"[{priority.upper()}] {title}",
    )
    return ticket


async def add_comment(
    db: AsyncSession,
    *,
    ticket_id: UUID,
    author_id: UUID,
    body: str,
) -> IncidentTicketComment:
    """Adiciona comentário. Notifica o autor do ticket + destinatários
    originais (exceto o próprio comentador)."""
    body = (body or "").strip()
    if not body:
        raise ValueError("Comentário vazio.")

    ticket = (await db.execute(
        select(IncidentTicket).where(IncidentTicket.id == ticket_id)
    )).scalar_one_or_none()
    if not ticket:
        raise ValueError("Ticket não encontrado.")

    comment = IncidentTicketComment(
        ticket_id=ticket_id,
        author_id=author_id,
        body=body,
    )
    db.add(comment)
    # touch updated_at do ticket
    ticket.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(comment)

    # Notificar: autor original + destinatários do scope (exceto o comentador)
    recipients = await _list_recipients(db, ticket.project_id, ticket.target_scope, author_id)
    if ticket.author_id != author_id and ticket.author_id not in recipients:
        recipients.append(ticket.author_id)

    notif = InAppNotificationService(db)
    for uid in recipients:
        await notif.notify(
            user_id=uid,
            event_type="incident_ticket.commented",
            title=f"Novo comentário em: {ticket.title}",
            message=body[:140],
            project_id=ticket.project_id,
            resource_type="incident_ticket",
            resource_id=ticket.id,
            link=_link_for(ticket),
            severity="info",
        )
    return comment


async def update_status(
    db: AsyncSession,
    *,
    ticket_id: UUID,
    actor_id: UUID,
    new_status: Status,
) -> IncidentTicket:
    """Atualiza status do ticket. resolved/closed preenchem resolved_at."""
    if new_status not in VALID_STATUS:
        raise ValueError(f"Status inválido: {new_status}")

    ticket = (await db.execute(
        select(IncidentTicket).where(IncidentTicket.id == ticket_id)
    )).scalar_one_or_none()
    if not ticket:
        raise ValueError("Ticket não encontrado.")

    prev = ticket.status
    if prev == new_status:
        return ticket

    now = datetime.now(timezone.utc)
    ticket.status = new_status
    ticket.updated_at = now
    if new_status in ("resolved", "closed"):
        ticket.resolved_at = ticket.resolved_at or now
        ticket.resolved_by = ticket.resolved_by or actor_id
    elif new_status in ("open", "in_progress"):
        ticket.resolved_at = None
        ticket.resolved_by = None
    await db.commit()
    await db.refresh(ticket)

    await _notify_recipients(
        db, ticket,
        event_suffix=f"status_{new_status}",
        title_tpl=f"Ticket {new_status}: {{title}}",
        message=f"Status: {prev} → {new_status}",
        actor_id=actor_id,
        include_author=True,
    )
    return ticket


# ─── Leitura ───────────────────────────────────────────────────────────────

async def list_for_project(
    db: AsyncSession,
    *,
    project_id: UUID,
    requester_id: UUID,
    status_filter: Optional[str] = None,
) -> list[IncidentTicket]:
    """Lista tickets do projeto aplicando RBAC:
      - Admin             → todos do projeto
      - GP do projeto     → todos do projeto
      - Dev/Tester/QA     → apenas os próprios (author_id=self)
      - Sem vínculo       → nada (lista vazia)
    """
    user = (await db.execute(
        select(User).where(User.id == requester_id)
    )).scalar_one_or_none()
    if not user or not user.is_active:
        return []

    q = select(IncidentTicket).where(IncidentTicket.project_id == project_id)
    if status_filter and status_filter in VALID_STATUS:
        q = q.where(IncidentTicket.status == status_filter)
    q = q.order_by(IncidentTicket.created_at.desc())

    if user.is_admin:
        return list((await db.execute(q)).scalars().all())

    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == requester_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at:
        return []

    if member.role != "gp":
        # Dev/Tester/QA: só os próprios
        q = q.where(IncidentTicket.author_id == requester_id)
    return list((await db.execute(q)).scalars().all())


async def list_for_admin(
    db: AsyncSession,
    *,
    status_filter: Optional[str] = None,
    project_id: Optional[UUID] = None,
) -> list[IncidentTicket]:
    """Lista agregada cross-projeto dos tickets escalados a Admin.
    Assume caller é Admin (enforcement no router)."""
    q = select(IncidentTicket).where(IncidentTicket.target_scope == "admin")
    if status_filter and status_filter in VALID_STATUS:
        q = q.where(IncidentTicket.status == status_filter)
    if project_id:
        q = q.where(IncidentTicket.project_id == project_id)
    q = q.order_by(IncidentTicket.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_ticket(
    db: AsyncSession,
    *,
    ticket_id: UUID,
    requester_id: UUID,
) -> tuple[IncidentTicket, list[IncidentTicketComment]]:
    """Retorna ticket + comentários se o requester puder ver. Senão
    levanta ValueError(404)/PermissionError(403)."""
    ticket = (await db.execute(
        select(IncidentTicket).where(IncidentTicket.id == ticket_id)
    )).scalar_one_or_none()
    if not ticket:
        raise ValueError("Ticket não encontrado.")

    user = (await db.execute(
        select(User).where(User.id == requester_id)
    )).scalar_one_or_none()
    if not user or not user.is_active:
        raise PermissionError("Usuário inválido ou inativo.")

    allowed = False
    if user.is_admin:
        # Admin vê tickets target=admin diretamente + pode ver target=gp
        # de qualquer projeto (admin tem visão global).
        allowed = True
    elif ticket.author_id == requester_id:
        allowed = True
    else:
        member = (await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == ticket.project_id,
                ProjectMember.user_id == requester_id,
            )
        )).scalar_one_or_none()
        if member and member.accepted_at and member.role == "gp":
            allowed = True

    if not allowed:
        raise PermissionError("Sem permissão para ver este ticket.")

    comments = list((await db.execute(
        select(IncidentTicketComment)
        .where(IncidentTicketComment.ticket_id == ticket_id)
        .order_by(IncidentTicketComment.created_at.asc())
    )).scalars().all())
    return ticket, comments


# ─── Notificação interna ──────────────────────────────────────────────────

def _link_for(ticket: IncidentTicket) -> str:
    if ticket.target_scope == "admin":
        return f"/admin/incidents/{ticket.id}"
    return f"/projects/{ticket.project_id}/incidents/{ticket.id}"


async def _notify_recipients(
    db: AsyncSession,
    ticket: IncidentTicket,
    *,
    event_suffix: str,
    title_tpl: str,
    message: str,
    actor_id: Optional[UUID] = None,
    include_author: bool = False,
) -> None:
    """Envia UserNotification para os destinatários do ticket."""
    skip = actor_id or ticket.author_id
    recipients = await _list_recipients(db, ticket.project_id, ticket.target_scope, skip)
    if include_author and ticket.author_id != skip and ticket.author_id not in recipients:
        recipients.append(ticket.author_id)

    notif = InAppNotificationService(db)
    severity_map = {"critica": "error", "alta": "warning"}
    severity = severity_map.get(ticket.priority, "info")

    for uid in recipients:
        await notif.notify(
            user_id=uid,
            event_type=f"incident_ticket.{event_suffix}",
            title=title_tpl.format(title=ticket.title),
            message=message,
            project_id=ticket.project_id,
            resource_type="incident_ticket",
            resource_id=ticket.id,
            link=_link_for(ticket),
            severity=severity,
        )
