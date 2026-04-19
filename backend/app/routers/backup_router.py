"""Backup-3 — Endpoints de backup/restore por projeto + visão admin.

RBAC:
- Listar/baixar backup do projeto: Admin OU GP/Dev/QA do projeto (project:view)
- Disparar backup manual: Admin OU GP do projeto
- Restore: Admin OU GP do projeto (operação destrutiva — requer
  confirmação dupla via flag query)
- Visão admin agregada: apenas Admin (qualquer projeto)
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.require_action import require_action
from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import User, Project
from app.services import project_backup_service as svc

router = APIRouter(prefix="/projects/{project_id}/backups", tags=["backups"])
admin_router = APIRouter(prefix="/admin/backups", tags=["admin-backups"])
status_router = APIRouter(prefix="/backups", tags=["backups"])


# ─── Pydantic responses ─────────────────────────────────────────────────────

class BackupItem(BaseModel):
    id: UUID
    project_id: UUID
    project_name: Optional[str] = None
    project_slug: Optional[str] = None
    created_at: str
    completed_at: Optional[str]
    trigger_source: str
    status: str
    size_bytes: int
    sha256: Optional[str]
    error_message: Optional[str]
    restored_at: Optional[str]
    restored_by: Optional[UUID]
    created_by: Optional[UUID]


class BackupListResponse(BaseModel):
    items: List[BackupItem]
    retention_limit: int = svc.RETENTION_PER_PROJECT


def _to_item(backup, project: Optional[Project] = None) -> BackupItem:
    return BackupItem(
        id=backup.id,
        project_id=backup.project_id,
        project_name=project.name if project else None,
        project_slug=project.slug if project else None,
        created_at=backup.created_at.isoformat() if backup.created_at else "",
        completed_at=backup.completed_at.isoformat() if backup.completed_at else None,
        trigger_source=backup.trigger_source,
        status=backup.status,
        size_bytes=backup.size_bytes or 0,
        sha256=backup.sha256,
        error_message=backup.error_message,
        restored_at=backup.restored_at.isoformat() if backup.restored_at else None,
        restored_by=backup.restored_by,
        created_by=backup.created_by,
    )


# ─── Helpers de RBAC ────────────────────────────────────────────────────────

async def _require_admin_or_gp(
    project_id: UUID,
    db: AsyncSession,
    user_id: UUID,
) -> dict:
    """Backup-3: backup/restore exigem Admin (global) OU GP do projeto.

    Não usa `require_action` direto pq aqui a regra é OR explícito entre
    "is_admin global" E "role=gp em project_members". Outros papéis
    (Dev/Tester/QA) podem listar/baixar mas não podem disparar
    backup/restore.
    """
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido ou inativo.")

    if user.is_admin:
        return {"user_id": user_id, "role": "admin", "is_admin": True}

    # Não é admin: tem que ser GP membro do projeto.
    from app.models.base import ProjectMember
    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at or member.role != "gp":
        raise HTTPException(
            status_code=403,
            detail="Apenas Admin ou GP do projeto podem operar backup/restore.",
        )
    return {"user_id": user_id, "role": "gp", "is_admin": False}


# ─── Endpoints projeto ──────────────────────────────────────────────────────

@router.get("", response_model=BackupListResponse)
async def list_project_backups(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista backups do projeto. Qualquer membro com project:view vê."""
    backups = await svc.list_backups(db, project_id)
    return BackupListResponse(items=[_to_item(b) for b in backups])


@router.post("", response_model=BackupItem, status_code=201)
async def trigger_project_backup(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Dispara backup imediato do projeto. Admin OU GP do projeto."""
    perms = await _require_admin_or_gp(project_id, db, user_id)
    trigger = "manual_admin" if perms["is_admin"] else "manual_gp"
    backup = await svc.create_backup(db, project_id, actor_id=user_id, trigger_source=trigger)
    return _to_item(backup)


@router.post("/{backup_id}/restore", response_model=BackupItem)
async def restore_project_backup(
    project_id: UUID,
    backup_id: UUID,
    confirm: bool = Query(False, description="Obrigatório true — operação destrutiva"),
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Rollback do projeto a partir do backup. Admin OU GP. Destrutivo."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Operação destrutiva — passe ?confirm=true para confirmar.",
        )
    await _require_admin_or_gp(project_id, db, user_id)
    backup = await svc.restore_from_backup(db, project_id, backup_id, user_id)
    return _to_item(backup)


@router.get("/{backup_id}/download", response_class=Response)
async def download_project_backup(
    project_id: UUID,
    backup_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Download bruto do .zip do backup (qualquer membro com project:view)."""
    backup = (await db.execute(
        select(svc.ProjectBackup).where(
            svc.ProjectBackup.id == backup_id,
            svc.ProjectBackup.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup não encontrado.")
    if backup.status != "completed":
        raise HTTPException(status_code=400, detail=f"Backup não está completo (status={backup.status}).")
    try:
        data = svc.read_backup_bytes(backup)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    filename = f"backup_{project_id}_{backup_id.hex[:8]}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Endpoint admin agregado ────────────────────────────────────────────────

async def _require_admin(
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user or not user.is_admin or not user.is_active:
        raise HTTPException(status_code=403, detail="Apenas admin.")
    return {"user_id": user_id, "is_admin": True}


@status_router.get("/active", response_model=BackupListResponse)
async def list_active_backups(
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Backup-4: lista backups com status='running' visíveis ao usuário.
    Frontend usa pra mostrar banner global enquanto algum backup está em
    andamento. Admin vê todos; outros usuários veem apenas dos projetos
    em que são membros aceitos."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido.")

    q = select(svc.ProjectBackup).where(svc.ProjectBackup.status == "running")
    if not user.is_admin:
        from app.models.base import ProjectMember
        member_pids = (await db.execute(
            select(ProjectMember.project_id).where(
                ProjectMember.user_id == user_id,
                ProjectMember.accepted_at.isnot(None),
            )
        )).scalars().all()
        if not member_pids:
            return BackupListResponse(items=[])
        q = q.where(svc.ProjectBackup.project_id.in_(member_pids))

    backups = (await db.execute(q.order_by(svc.ProjectBackup.created_at.desc()))).scalars().all()
    project_ids = list({b.project_id for b in backups})
    proj_map = {}
    if project_ids:
        projects = (await db.execute(
            select(Project).where(Project.id.in_(project_ids))
        )).scalars().all()
        proj_map = {p.id: p for p in projects}
    return BackupListResponse(items=[_to_item(b, proj_map.get(b.project_id)) for b in backups])


@admin_router.get("", response_model=BackupListResponse)
async def list_all_backups_admin(
    _admin: dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Visão admin agregada: backups de todos os projetos (últimos 200)."""
    backups = await svc.list_all_backups(db)
    # Resolve project name/slug em batch
    project_ids = list({b.project_id for b in backups})
    if project_ids:
        projects = (await db.execute(
            select(Project).where(Project.id.in_(project_ids))
        )).scalars().all()
        proj_map = {p.id: p for p in projects}
    else:
        proj_map = {}

    items = [_to_item(b, project=proj_map.get(b.project_id)) for b in backups]
    return BackupListResponse(items=items)
