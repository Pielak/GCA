"""MVP 6 — service de tickets de incidente.

Roteamento por papel do autor:
  Dev/Tester/QA  → target_scope='gp'    (GPs do projeto são notificados)
  GP             → target_scope='admin' (Admins + Sustentação recebem)
  Admin          → target_scope='admin' (demais Admins + Sustentação recebem)

Compartimentalização: todo predicado inclui project_id. Ticket de projeto
A nunca é lido por não-admin fora do projeto A. Admin+Sustentação vêem
cross-projeto via target_scope='admin'.

Emenda 2026-04-19:
- Destinatários admin = (is_admin=True OR is_support=True) — Admin herda.
- Support (is_admin=False, is_support=True) pode ler/comentar/mudar status
  mas não é Admin.
- Anexos: upload_attachment/list/read/delete (até 5/10MB/tipos restritos).
- Campos section_reference + flow_description obrigatórios em novas criações.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IncidentTicket,
    IncidentTicketAttachment,
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

# MVP 6 Emenda — anexos
ATTACHMENT_STORAGE_ROOT = "/tmp/gca-storage/incidents"
ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB por arquivo
ATTACHMENT_MAX_PER_TICKET = 5
ATTACHMENT_ALLOWED_MIME: tuple[str, ...] = (
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "text/plain", "application/json", "application/pdf",
    "application/octet-stream",  # .log às vezes é inferido como octet-stream
)
ATTACHMENT_ALLOWED_EXT: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".txt", ".log", ".json", ".pdf",
)


def _has_admin_scope(user: User) -> bool:
    """Admin HERDA Support. Regra dura (contrato §7 MVP 6 emenda).

    Retorna True para is_admin OR is_support — ambos enxergam tickets
    com target_scope='admin'.
    """
    return bool(user.is_admin or user.is_support)


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

    # admin → Admin + Sustentação (is_admin OR is_support). Emenda 2026-04-19.
    rows = (await db.execute(
        select(User.id).where(
            or_(User.is_admin.is_(True), User.is_support.is_(True)),
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
    flow_description: str,
    section_reference: Optional[str] = None,
) -> IncidentTicket:
    """Cria ticket, resolve target_scope automaticamente, notifica
    destinatários. commit ocorre dentro.

    Emenda 2026-04-19: flow_description é obrigatório; section_reference
    é opcional (o frontend autopreenche com a rota atual).
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Categoria inválida: {category}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Prioridade inválida: {priority}")
    title = (title or "").strip()
    description = (description or "").strip()
    flow_description = (flow_description or "").strip()
    if not title or not description:
        raise ValueError("Título e descrição são obrigatórios.")
    if len(title) > 200:
        raise ValueError("Título excede 200 caracteres.")
    if not flow_description:
        raise ValueError("Fluxo do incidente (flow_description) é obrigatório.")

    section_reference = (section_reference or "").strip() or None
    if section_reference and len(section_reference) > 300:
        section_reference = section_reference[:300]

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
        section_reference=section_reference,
        flow_description=flow_description,
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

    if _has_admin_scope(user):
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
    if _has_admin_scope(user):
        # Admin ou Support (Sustentação) vê tickets target=admin
        # diretamente + pode ver target=gp de qualquer projeto.
        # Regra dura: Admin herda Support; Support compartilha visão
        # cross-projeto dos tickets (contrato §7 MVP 6 emenda).
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


# ─── Anexos (Emenda 2026-04-19) ────────────────────────────────────────────

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str) -> str:
    """Normaliza nome de arquivo para armazenamento seguro no volume.

    Remove acentos, substitui caracteres fora de [A-Za-z0-9._-] por `_`,
    limita a 120 chars. Mantém extensão se houver.
    """
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    name = name.strip().replace(" ", "_")
    name = _SAFE_FILENAME_RE.sub("_", name)
    name = re.sub(r"_+", "_", name).strip("._") or "arquivo"
    return name[:120]


def _validate_attachment(filename: str, mime: str, content: bytes) -> None:
    """Valida tamanho, mime e extensão do anexo. Levanta ValueError."""
    if not content:
        raise ValueError("Arquivo vazio.")
    if len(content) > ATTACHMENT_MAX_BYTES:
        raise ValueError(
            f"Arquivo excede o limite de {ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB."
        )
    if mime not in ATTACHMENT_ALLOWED_MIME:
        raise ValueError(f"MIME type não permitido: {mime}")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ATTACHMENT_ALLOWED_EXT:
        raise ValueError(f"Extensão não permitida: {ext}")


async def upload_attachment(
    db: AsyncSession,
    *,
    ticket_id: UUID,
    uploader_id: UUID,
    filename: str,
    mime: str,
    content: bytes,
) -> IncidentTicketAttachment:
    """Adiciona anexo ao ticket. Validação de tamanho/tipo, contagem
    máxima (5 por ticket), sanitização do nome, sha256 pra integridade.

    Autorização: uploader precisa poder ver o ticket (get_ticket já
    valida Admin/Support/autor/GP). Enforcement no router que chama
    get_ticket antes.
    """
    _validate_attachment(filename, mime, content)

    ticket = (await db.execute(
        select(IncidentTicket).where(IncidentTicket.id == ticket_id)
    )).scalar_one_or_none()
    if not ticket:
        raise ValueError("Ticket não encontrado.")

    from sqlalchemy import func
    current_count = int((await db.execute(
        select(func.count(IncidentTicketAttachment.id)).where(
            IncidentTicketAttachment.ticket_id == ticket_id
        )
    )).scalar() or 0)
    if current_count >= ATTACHMENT_MAX_PER_TICKET:
        raise ValueError(
            f"Ticket já tem o máximo de {ATTACHMENT_MAX_PER_TICKET} anexos."
        )

    sha = hashlib.sha256(content).hexdigest()
    safe_name = _sanitize_filename(filename)

    dir_path = Path(ATTACHMENT_STORAGE_ROOT) / str(ticket_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{sha[:12]}_{safe_name}"
    file_path.write_bytes(content)

    rel_path = str(file_path.relative_to(ATTACHMENT_STORAGE_ROOT))

    att = IncidentTicketAttachment(
        ticket_id=ticket_id,
        uploader_id=uploader_id,
        filename=safe_name,
        mime=mime,
        size_bytes=len(content),
        sha256=sha,
        storage_path=rel_path,
    )
    db.add(att)
    ticket.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(att)
    return att


async def list_attachments(
    db: AsyncSession, *, ticket_id: UUID
) -> list[IncidentTicketAttachment]:
    """Lista anexos ordenados por created_at ASC. Autorização é feita
    pelo caller (router chama get_ticket antes)."""
    return list((await db.execute(
        select(IncidentTicketAttachment)
        .where(IncidentTicketAttachment.ticket_id == ticket_id)
        .order_by(IncidentTicketAttachment.created_at.asc())
    )).scalars().all())


def read_attachment_bytes(attachment: IncidentTicketAttachment) -> bytes:
    """Lê bytes do anexo do volume + revalida sha256 (integridade)."""
    full = Path(ATTACHMENT_STORAGE_ROOT) / attachment.storage_path
    if not full.exists():
        raise ValueError("Arquivo não encontrado no volume.")
    data = full.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != attachment.sha256:
        raise ValueError(
            f"SHA256 divergente (gravado={attachment.sha256[:12]} atual={actual[:12]})"
        )
    return data


async def delete_attachment(
    db: AsyncSession,
    *,
    attachment_id: UUID,
    actor_id: UUID,
) -> None:
    """Remove anexo do DB + do volume. Autor do anexo OU Admin pode excluir.
    Support pode excluir anexos próprios mas não de outros (não é Admin)."""
    att = (await db.execute(
        select(IncidentTicketAttachment).where(IncidentTicketAttachment.id == attachment_id)
    )).scalar_one_or_none()
    if not att:
        raise ValueError("Anexo não encontrado.")

    actor = (await db.execute(
        select(User).where(User.id == actor_id)
    )).scalar_one_or_none()
    if not actor or not actor.is_active:
        raise PermissionError("Usuário inválido ou inativo.")

    is_admin = bool(actor.is_admin)  # Admin puro. Support NÃO pode deletar anexo de outros.
    is_uploader = att.uploader_id == actor_id
    if not (is_admin or is_uploader):
        raise PermissionError("Apenas o autor do anexo ou um Admin pode excluir.")

    full = Path(ATTACHMENT_STORAGE_ROOT) / att.storage_path
    try:
        if full.exists():
            full.unlink()
    except OSError:
        # best-effort; registro do DB é a fonte de verdade pra auditoria
        pass
    await db.delete(att)
    await db.commit()


# ─── Gestão da Equipe Sustentação ─────────────────────────────────────────

async def set_support_flag(
    db: AsyncSession,
    *,
    target_user_id: UUID,
    new_value: bool,
    actor_id: UUID,
) -> User:
    """Promove/rebaixa is_support de um usuário. Apenas Admin pode.

    Regra dura (contrato §7 MVP 6 emenda): Admin pode ativar is_support
    em si mesmo (acumula Sustentação). UI de "Equipe Sustentação" nunca
    promove Support a Admin — isso é gestão de usuários canônica.
    """
    actor = (await db.execute(
        select(User).where(User.id == actor_id)
    )).scalar_one_or_none()
    if not actor or not actor.is_active or not actor.is_admin:
        raise PermissionError("Apenas Admin pode gerenciar a Equipe Sustentação.")

    target = (await db.execute(
        select(User).where(User.id == target_user_id)
    )).scalar_one_or_none()
    if not target:
        raise ValueError("Usuário alvo não encontrado.")
    if not target.is_active:
        raise ValueError("Usuário alvo inativo.")

    target.is_support = bool(new_value)
    await db.commit()
    await db.refresh(target)
    return target


async def list_support_team(db: AsyncSession) -> list[User]:
    """Lista usuários com is_support=True OU is_admin=True (ambos fazem
    parte do conjunto de destinatários de target='admin'). Ordenação
    apresenta Admins primeiro, depois Support puros."""
    rows = (await db.execute(
        select(User).where(
            or_(User.is_admin.is_(True), User.is_support.is_(True)),
            User.is_active.is_(True),
        ).order_by(User.is_admin.desc(), User.full_name.asc())
    )).scalars().all()
    return list(rows)
