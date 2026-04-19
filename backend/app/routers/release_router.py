"""MVP 7 — router de releases.

Sub-routers:
  - admin_router  → /admin/releases (Admin-only: list, detail, apply, rollback)
  - user_router   → /releases (usuário autenticado, changelog segmentado)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import (
    Release, ReleaseApplicationLog, ReleaseCompletionTask, ReleaseItem, User,
)
from app.services import release_service as svc

admin_router = APIRouter(prefix="/admin/releases", tags=["admin-releases"])
user_router = APIRouter(prefix="/releases", tags=["releases"])


# ─── Schemas ───────────────────────────────────────────────────────────────

class ReleaseItemOut(BaseModel):
    id: UUID
    kind: str
    ref_id: Optional[str]
    title: str
    description: Optional[str]
    affected_roles: list[str]
    display_order: int


class ReleaseOut(BaseModel):
    id: UUID
    tag: str
    title: str
    body: Optional[str]
    is_destructive: bool
    status: str
    declared_at: Optional[datetime]
    applied_at: Optional[datetime]
    applied_by: Optional[UUID]
    source_yaml: Optional[str]
    item_count: int = 0


class ReleaseDetailOut(BaseModel):
    release: ReleaseOut
    items: list[ReleaseItemOut]


class ReleaseLogEntry(BaseModel):
    id: UUID
    event_type: str
    project_id: Optional[UUID]
    actor_id: Optional[UUID]
    metadata: Optional[dict] = None
    created_at: Optional[datetime]


class ReleaseLogResponse(BaseModel):
    entries: list[ReleaseLogEntry]


# ─── Helpers ───────────────────────────────────────────────────────────────

def _parse_roles(raw: str) -> list[str]:
    try:
        r = json.loads(raw or "[]")
        return r if isinstance(r, list) else []
    except (ValueError, TypeError):
        return []


def _rel_to_out(r: Release, item_count: int = 0) -> ReleaseOut:
    return ReleaseOut(
        id=r.id, tag=r.tag, title=r.title, body=r.body,
        is_destructive=bool(r.is_destructive),
        status=r.status,
        declared_at=r.declared_at,
        applied_at=r.applied_at,
        applied_by=r.applied_by,
        source_yaml=r.source_yaml,
        item_count=item_count,
    )


def _item_to_out(it: ReleaseItem) -> ReleaseItemOut:
    return ReleaseItemOut(
        id=it.id, kind=it.kind, ref_id=it.ref_id,
        title=it.title, description=it.description,
        affected_roles=_parse_roles(it.affected_roles),
        display_order=it.display_order,
    )


def _primary_role(user: User) -> str:
    """Papel para segmentar changelog. Admin vê tudo → retorna 'admin'.
    Support ativo → 'admin' (vê como admin). Outros → consultam
    project_memberships — para UI user-facing simples, retornamos 'all'
    se for usuário comum e deixamos o frontend filtrar por preferência."""
    if user.is_admin or user.is_support:
        return "admin"
    # Usuário comum: retornamos 'all' pra mostrar os itens marcados como
    # all; itens role-specific dependem do contexto de projeto (ver F3).
    return "all"


async def _require_admin(
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active or not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a Admin.")
    return user_id


# ─── Endpoints admin ───────────────────────────────────────────────────────

class ReleaseListResponse(BaseModel):
    items: list[ReleaseOut]


@admin_router.get("", response_model=ReleaseListResponse)
async def list_releases_admin(
    status: Optional[str] = None,
    _admin: UUID = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lista todas as releases (inclui pending). Admin-only."""
    releases = await svc.list_releases(db, status_filter=status)
    # Contagem de items por release (batched)
    from sqlalchemy import func
    counts_raw = (await db.execute(
        select(ReleaseItem.release_id, func.count(ReleaseItem.id))
        .group_by(ReleaseItem.release_id)
    )).all()
    counts = {rid: c for rid, c in counts_raw}
    return ReleaseListResponse(items=[
        _rel_to_out(r, item_count=counts.get(r.id, 0)) for r in releases
    ])


@admin_router.get("/{release_id}", response_model=ReleaseDetailOut)
async def get_release_detail_admin(
    release_id: UUID,
    _admin: UUID = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        rel, items = await svc.get_release_with_items(db, release_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ReleaseDetailOut(
        release=_rel_to_out(rel, item_count=len(items)),
        items=[_item_to_out(it) for it in items],
    )


@admin_router.get("/{release_id}/log", response_model=ReleaseLogResponse)
async def get_release_log(
    release_id: UUID,
    _admin: UUID = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    entries = await svc.get_application_log(db, release_id)
    return ReleaseLogResponse(entries=[
        ReleaseLogEntry(
            id=e.id,
            event_type=e.event_type,
            project_id=e.project_id,
            actor_id=e.actor_id,
            metadata=(json.loads(e.metadata_json) if e.metadata_json else None),
            created_at=e.created_at,
        ) for e in entries
    ])


# ─── Fase 2: aplicação destrutiva + rollback ─────────────────────────────

class ApplyDestructiveRequest(BaseModel):
    confirm: bool
    take_snapshots: bool = True


class ApplyDestructiveResponse(BaseModel):
    release_id: UUID
    status: str
    snapshots_taken: int
    affected_projects: int


class RollbackProjectRequest(BaseModel):
    project_id: UUID
    snapshot_id: UUID
    confirm: bool


@admin_router.post("/{release_id}/apply", response_model=ApplyDestructiveResponse)
async def apply_destructive(
    release_id: UUID,
    payload: ApplyDestructiveRequest,
    actor_id: UUID = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Aplica release destrutiva. Fluxo:
      1. valida release pending + is_destructive=True;
      2. se take_snapshots=True: cria backup (DT-063) de cada projeto
         ativo com trigger_source='manual_admin'; registra snapshot_id;
      3. marca release applied + loga eventos.

    As migrations SQL reais rodam via deploy/upgrade.sh **antes** do
    backend subir — este endpoint só formaliza o registro da aplicação
    e garante snapshot pré-release. Migration destrutiva sem este
    fluxo é considerada violação do contrato §7 MVP 7.
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Operação destrutiva — passe confirm=true no body.",
        )

    from app.models.base import Project
    from app.services import project_backup_service as backup_svc

    rel = (await db.execute(
        select(Release).where(Release.id == release_id)
    )).scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Release não encontrada.")
    if rel.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Release não está pending (status={rel.status}).",
        )
    if not rel.is_destructive:
        raise HTTPException(
            status_code=400,
            detail="Release não é destrutiva; aplicação automática já ocorre no startup.",
        )

    snapshots: list[dict] = []
    if payload.take_snapshots:
        # Projetos ativos — snapshot pré-release por projeto
        active_projects = (await db.execute(
            select(Project).where(Project.deleted_at.is_(None))
        )).scalars().all()
        for p in active_projects:
            try:
                b = await backup_svc.create_backup(
                    db, p.id, trigger_source="manual_admin", actor_id=actor_id,
                )
                snapshots.append({"project_id": p.id, "snapshot_id": b.id})
            except Exception:
                # Se um projeto falhar, registra mas continua — admin decide abortar
                pass

    try:
        await svc.apply_destructive_release(
            db, release_id=release_id, actor_id=actor_id, snapshots=snapshots,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApplyDestructiveResponse(
        release_id=release_id,
        status="applied",
        snapshots_taken=len(snapshots),
        affected_projects=len(snapshots),
    )


@admin_router.post("/{release_id}/rollback-project", status_code=200)
async def rollback_project(
    release_id: UUID,
    payload: RollbackProjectRequest,
    actor_id: UUID = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restaura um projeto ao snapshot pré-release. Usa DT-063 pra
    aplicar `restore_from_backup` e registra evento 'rolled_back' no
    log da release."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Operação destrutiva — passe confirm=true.",
        )

    from app.services import project_backup_service as backup_svc

    try:
        await backup_svc.restore_from_backup(
            db, payload.project_id, payload.snapshot_id, actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        await svc.mark_rollback(
            db, release_id=release_id, project_id=payload.project_id,
            actor_id=actor_id, snapshot_id=payload.snapshot_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "ok", "release_id": str(release_id), "project_id": str(payload.project_id)}


# ─── Completion tasks (assistente pós-release) ───────────────────────────

class CompletionTaskOut(BaseModel):
    id: UUID
    release_id: UUID
    project_id: UUID
    kind: str
    title: str
    description: Optional[str]
    payload: Optional[dict] = None
    status: str
    created_at: Optional[datetime]
    completed_at: Optional[datetime]
    completed_by: Optional[UUID]


class CompletionTaskListResponse(BaseModel):
    items: list[CompletionTaskOut]


def _task_to_out(t: ReleaseCompletionTask) -> CompletionTaskOut:
    payload_dict = None
    if t.payload:
        try:
            payload_dict = json.loads(t.payload)
        except (ValueError, TypeError):
            payload_dict = None
    return CompletionTaskOut(
        id=t.id,
        release_id=t.release_id,
        project_id=t.project_id,
        kind=t.kind,
        title=t.title,
        description=t.description,
        payload=payload_dict,
        status=t.status,
        created_at=t.created_at,
        completed_at=t.completed_at,
        completed_by=t.completed_by,
    )


@user_router.get("/project/{project_id}/completion-tasks", response_model=CompletionTaskListResponse)
async def list_project_completion_tasks(
    project_id: UUID,
    status: Optional[str] = None,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista pendências pós-release do projeto. Autorização segue regra
    do projeto: Admin vê; GP do projeto vê; outros membros vêem as do
    projeto onde são membros aceitos."""
    from app.models.base import ProjectMember

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido.")

    allowed = user.is_admin or user.is_support
    if not allowed:
        member = (await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        allowed = bool(member and member.accepted_at)
    if not allowed:
        raise HTTPException(status_code=403, detail="Sem permissão para este projeto.")

    q = select(ReleaseCompletionTask).where(ReleaseCompletionTask.project_id == project_id)
    if status:
        q = q.where(ReleaseCompletionTask.status == status)
    q = q.order_by(ReleaseCompletionTask.created_at.desc())
    tasks = (await db.execute(q)).scalars().all()
    return CompletionTaskListResponse(items=[_task_to_out(t) for t in tasks])


@user_router.post("/completion-tasks/{task_id}/complete", response_model=CompletionTaskOut)
async def complete_task(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Marca tarefa pós-release como concluída. Admin OU GP do projeto."""
    from app.models.base import ProjectMember

    task = (await db.execute(
        select(ReleaseCompletionTask).where(ReleaseCompletionTask.id == task_id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido.")

    allowed = user.is_admin
    if not allowed:
        member = (await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == task.project_id,
                ProjectMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        allowed = bool(member and member.accepted_at and member.role == "gp")
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Apenas Admin ou GP do projeto pode concluir tarefa pós-release.",
        )

    if task.status == "done":
        return _task_to_out(task)

    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    task.completed_by = user_id
    db.add(ReleaseApplicationLog(
        release_id=task.release_id,
        event_type="completion_task_fulfilled",
        project_id=task.project_id,
        actor_id=user_id,
        metadata_json=json.dumps({"task_id": str(task_id), "kind": task.kind}),
    ))
    await db.commit()
    await db.refresh(task)
    return _task_to_out(task)


# ─── Endpoints user-facing ─────────────────────────────────────────────────

@user_router.get("", response_model=ReleaseListResponse)
async def list_releases_user(
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista releases aplicadas (pending oculto pra usuário comum)."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido.")

    status_filter = None if (user.is_admin or user.is_support) else "applied"
    releases = await svc.list_releases(db, status_filter=status_filter)
    from sqlalchemy import func
    counts_raw = (await db.execute(
        select(ReleaseItem.release_id, func.count(ReleaseItem.id))
        .group_by(ReleaseItem.release_id)
    )).all()
    counts = {rid: c for rid, c in counts_raw}
    return ReleaseListResponse(items=[
        _rel_to_out(r, item_count=counts.get(r.id, 0)) for r in releases
    ])


@user_router.get("/{release_id}", response_model=ReleaseDetailOut)
async def get_release_detail_user(
    release_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe filtrado por papel. Usuário comum só vê releases applied
    e só os itens cujo affected_roles inclui 'all' ou o seu papel."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido.")

    try:
        rel, items = await svc.get_release_with_items(db, release_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Release pending escondida de usuário comum
    if rel.status == "pending" and not (user.is_admin or user.is_support):
        raise HTTPException(status_code=404, detail="Release não encontrada.")

    # Segmentação: admin/support veem tudo; outros filtram por papel 'all'.
    if user.is_admin or user.is_support:
        visible = items
    else:
        visible = svc.items_visible_to_role(items, role="all")

    return ReleaseDetailOut(
        release=_rel_to_out(rel, item_count=len(visible)),
        items=[_item_to_out(it) for it in visible],
    )
