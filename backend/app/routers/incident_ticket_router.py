"""MVP 6 — router de tickets de incidente.

3 sub-routers:
  - router           → /projects/{project_id}/incidents (per-project)
  - ticket_router    → /incidents/{ticket_id} (operações sobre ticket: comment, status)
  - admin_router     → /admin/incidents (admin agregado cross-projeto)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import IncidentTicket, IncidentTicketComment, Project, User
from app.services import incident_ticket_service as svc

router = APIRouter(prefix="/projects/{project_id}/incidents", tags=["incident-tickets"])
ticket_router = APIRouter(prefix="/incidents", tags=["incident-tickets"])
admin_router = APIRouter(prefix="/admin/incidents", tags=["admin-incidents"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class TicketCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    category: str
    priority: str


class TicketStatusRequest(BaseModel):
    status: str


class CommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1)


class TicketItem(BaseModel):
    id: UUID
    project_id: UUID
    project_name: Optional[str] = None
    author_id: UUID
    author_name: Optional[str] = None
    target_scope: str
    category: str
    priority: str
    status: str
    title: str
    description: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    resolved_at: Optional[datetime]
    resolved_by: Optional[UUID]


class CommentItem(BaseModel):
    id: UUID
    ticket_id: UUID
    author_id: UUID
    author_name: Optional[str] = None
    body: str
    created_at: Optional[datetime]


class TicketListResponse(BaseModel):
    items: list[TicketItem]


class TicketDetailResponse(BaseModel):
    ticket: TicketItem
    comments: list[CommentItem]


# ─── Helpers ───────────────────────────────────────────────────────────────

def _ticket_to_item(
    t: IncidentTicket,
    *,
    project_name: Optional[str] = None,
    author_name: Optional[str] = None,
) -> TicketItem:
    return TicketItem(
        id=t.id,
        project_id=t.project_id,
        project_name=project_name,
        author_id=t.author_id,
        author_name=author_name,
        target_scope=t.target_scope,
        category=t.category,
        priority=t.priority,
        status=t.status,
        title=t.title,
        description=t.description,
        created_at=t.created_at,
        updated_at=t.updated_at,
        resolved_at=t.resolved_at,
        resolved_by=t.resolved_by,
    )


async def _hydrate_names(
    db: AsyncSession, tickets: list[IncidentTicket]
) -> tuple[dict[UUID, str], dict[UUID, str]]:
    """Busca em 2 queries (batched) os nomes de projeto e autor."""
    if not tickets:
        return {}, {}
    project_ids = {t.project_id for t in tickets}
    author_ids = {t.author_id for t in tickets}
    projects = {
        p.id: p.name
        for p in (await db.execute(
            select(Project.id, Project.name).where(Project.id.in_(project_ids))
        )).all()
    }
    authors = {
        u.id: (u.full_name or u.email or "")
        for u in (await db.execute(
            select(User.id, User.full_name, User.email).where(User.id.in_(author_ids))
        )).all()
    }
    return projects, authors


async def _require_admin(
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active or not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a Admin.")
    return user_id


# ─── Per-project endpoints ─────────────────────────────────────────────────

@router.get("", response_model=TicketListResponse)
async def list_project_tickets(
    project_id: UUID,
    status: Optional[str] = Query(None),
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista tickets visíveis ao requester no projeto. RBAC:
      - Admin           → todos
      - GP do projeto   → todos
      - Dev/Tester/QA   → só os próprios
      - Sem vínculo     → vazio
    """
    tickets = await svc.list_for_project(
        db, project_id=project_id, requester_id=user_id, status_filter=status,
    )
    projects, authors = await _hydrate_names(db, tickets)
    return TicketListResponse(items=[
        _ticket_to_item(t, project_name=projects.get(t.project_id), author_name=authors.get(t.author_id))
        for t in tickets
    ])


@router.post("", response_model=TicketItem, status_code=201)
async def create_project_ticket(
    project_id: UUID,
    payload: TicketCreateRequest,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Abre ticket no projeto. Roteamento por papel é automático no service."""
    try:
        t = await svc.create_ticket(
            db,
            project_id=project_id,
            author_id=user_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            priority=payload.priority,
        )
    except ValueError as e:
        msg = str(e)
        if "não é membro" in msg or "Autor inválido" in msg:
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    projects, authors = await _hydrate_names(db, [t])
    return _ticket_to_item(t, project_name=projects.get(t.project_id), author_name=authors.get(t.author_id))


# ─── Ticket-level endpoints ────────────────────────────────────────────────

@ticket_router.get("/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket_detail(
    ticket_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        ticket, comments = await svc.get_ticket(db, ticket_id=ticket_id, requester_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    projects, authors = await _hydrate_names(db, [ticket])
    # comentários: hydrate author names
    comment_author_ids = {c.author_id for c in comments}
    comment_authors = {
        u.id: (u.full_name or u.email or "")
        for u in (await db.execute(
            select(User.id, User.full_name, User.email).where(User.id.in_(comment_author_ids))
        )).all()
    } if comment_author_ids else {}

    return TicketDetailResponse(
        ticket=_ticket_to_item(
            ticket,
            project_name=projects.get(ticket.project_id),
            author_name=authors.get(ticket.author_id),
        ),
        comments=[
            CommentItem(
                id=c.id,
                ticket_id=c.ticket_id,
                author_id=c.author_id,
                author_name=comment_authors.get(c.author_id),
                body=c.body,
                created_at=c.created_at,
            )
            for c in comments
        ],
    )


@ticket_router.post("/{ticket_id}/comments", response_model=CommentItem, status_code=201)
async def add_ticket_comment(
    ticket_id: UUID,
    payload: CommentCreateRequest,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    # Autorização: mesma regra do get_ticket (se pode ver, pode comentar).
    try:
        await svc.get_ticket(db, ticket_id=ticket_id, requester_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        c = await svc.add_comment(db, ticket_id=ticket_id, author_id=user_id, body=payload.body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    author_name = (user.full_name or user.email) if user else None
    return CommentItem(
        id=c.id,
        ticket_id=c.ticket_id,
        author_id=c.author_id,
        author_name=author_name,
        body=c.body,
        created_at=c.created_at,
    )


@ticket_router.patch("/{ticket_id}/status", response_model=TicketItem)
async def update_ticket_status(
    ticket_id: UUID,
    payload: TicketStatusRequest,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza status do ticket. Autorização:
      - Admin                             → qualquer ticket
      - GP do projeto                     → tickets do seu projeto
      - Autor (qualquer papel)            → pode fechar o próprio ticket
    """
    try:
        ticket, _ = await svc.get_ticket(db, ticket_id=ticket_id, requester_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    is_author = ticket.author_id == user_id
    is_admin = bool(user and user.is_admin)

    # GP check: se não é admin e não é autor, só pode se for GP do projeto.
    if not is_admin and not is_author:
        # svc.get_ticket já exigiu autorização ampla (admin OR author OR gp do projeto).
        # Aqui refina: GP é ok, outros não passam desse ponto pq get_ticket teria barrado.
        pass

    try:
        updated = await svc.update_status(
            db, ticket_id=ticket_id, actor_id=user_id, new_status=payload.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    projects, authors = await _hydrate_names(db, [updated])
    return _ticket_to_item(
        updated,
        project_name=projects.get(updated.project_id),
        author_name=authors.get(updated.author_id),
    )


# ─── Admin aggregated ──────────────────────────────────────────────────────

@admin_router.get("", response_model=TicketListResponse)
async def list_admin_tickets(
    status: Optional[str] = Query(None),
    project_id: Optional[UUID] = Query(None),
    _admin: UUID = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Visão cross-projeto dos tickets escalados a Admin (target_scope='admin')."""
    tickets = await svc.list_for_admin(db, status_filter=status, project_id=project_id)
    projects, authors = await _hydrate_names(db, tickets)
    return TicketListResponse(items=[
        _ticket_to_item(t, project_name=projects.get(t.project_id), author_name=authors.get(t.author_id))
        for t in tickets
    ])
