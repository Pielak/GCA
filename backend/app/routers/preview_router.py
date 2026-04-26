"""G4 (2026-04-25) — Endpoints de preview do app gerado.

Estratégia híbrida (sem docker.sock no gca-backend):
  1. Owner clica "Preparar Ambiente Local".
  2. Backend valida que o projeto tem scaffold applied + git config OK,
     aloca porta dinâmica, monta comando shell pronto pra colar e
     persiste sessão.
  3. Owner cola o comando no terminal local. Comando faz git clone +
     docker compose up + abre URL.
  4. Owner pode reportar "running" ou "stopped" via endpoints dedicados.

Não tenta executar docker do backend — questão de segurança (sock dá
poder de root no host) e simplicidade. Quando GCA virar produto
instalável, opção docker-in-docker é parametrizável.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import (
    AppPreviewSession,
    Project,
    ProjectGitConfig,
    ScaffoldRun,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["preview"])

# Range de portas alocadas. Evita conflitos com gca (8000, 5432, 5173,
# 5555, 5678, 6379, 11434) e portas baixas privilegiadas.
PORT_RANGE_START = 9100
PORT_RANGE_END = 9999


class PreviewSessionDTO(BaseModel):
    id: UUID
    project_id: UUID
    scaffold_run_id: UUID | None
    port: int | None
    status: str
    setup_command: str | None
    preview_url: str | None
    repository_url: str | None
    notes: str | None
    created_at: str
    stopped_at: str | None


def _serialize(s: AppPreviewSession) -> PreviewSessionDTO:
    return PreviewSessionDTO(
        id=s.id,
        project_id=s.project_id,
        scaffold_run_id=s.scaffold_run_id,
        port=s.port,
        status=s.status,
        setup_command=s.setup_command,
        preview_url=s.preview_url,
        repository_url=s.repository_url,
        notes=s.notes,
        created_at=s.created_at.isoformat() if s.created_at else "",
        stopped_at=s.stopped_at.isoformat() if s.stopped_at else None,
    )


async def _allocate_port(db: AsyncSession, project_id: UUID) -> int:
    """Aloca menor porta livre no range pra este projeto. Reusa porta
    da última sessão `prepared`/`running` do mesmo projeto se existir."""
    res = await db.execute(
        select(AppPreviewSession.port)
        .where(
            AppPreviewSession.project_id == project_id,
            AppPreviewSession.status.in_(("prepared", "running")),
            AppPreviewSession.port.isnot(None),
        )
        .order_by(AppPreviewSession.created_at.desc())
        .limit(1)
    )
    last_port = res.scalar_one_or_none()
    if last_port and PORT_RANGE_START <= last_port <= PORT_RANGE_END:
        return last_port

    # Aloca porta livre: pega max porta usada no range, soma 1; se overflow,
    # volta pro start. Conservador — não verifica disponibilidade real no
    # host do owner (impossível daqui).
    res = await db.execute(
        select(AppPreviewSession.port)
        .where(AppPreviewSession.port.isnot(None))
    )
    used = {row[0] for row in res.all() if row[0]}
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port not in used:
            return port
    # Se range esgotou, recicla menor — owner é responsável por garantir
    # que não conflite no host.
    return PORT_RANGE_START


def _build_setup_command(
    project_slug: str,
    repo_url: str,
    port: int,
    workdir_root: str = "~/gca-previews",
) -> str:
    """Comando shell pronto pra colar.

    Faz: criar dir → clone (ou pull se já clonado) → exporta GCA_PREVIEW_PORT
    pro compose mapear → docker compose up -d → mostra URL.

    Owner é responsável por:
      - Ter docker + git instalados.
      - Garantir que a porta está livre.
      - O docker-compose.yml gerado pelo scaffold respeitar
        ${GCA_PREVIEW_PORT} no mapping da porta do app principal (ou
        editar manualmente).
    """
    safe_slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in project_slug)
    return (
        f"mkdir -p {workdir_root} && cd {workdir_root} && "
        f"(test -d {safe_slug} || git clone {repo_url} {safe_slug}) && "
        f"cd {safe_slug} && git pull --ff-only && "
        f"GCA_PREVIEW_PORT={port} docker compose up -d && "
        f"echo 'Preview rodando em http://localhost:{port}'"
    )


@router.post(
    "/projects/{project_id}/preview/prepare",
    response_model=PreviewSessionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Prepara sessão de preview do app gerado (G4)",
    description=(
        "Aloca porta dinâmica, monta comando shell pronto pra colar e "
        "persiste sessão. Owner roda o comando local pra subir o app. "
        "Requer scaffold applied + git config configurado no projeto."
    ),
)
async def prepare_preview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_from_token),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Busca git_config pra obter URL do remoto
    git_q = await db.execute(
        select(ProjectGitConfig).where(ProjectGitConfig.project_id == project_id)
    )
    git_cfg = git_q.scalar_one_or_none()
    if git_cfg is None or not git_cfg.repository_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Git config ausente. Configure repositório do projeto antes de preparar preview.",
        )

    # Busca última run aplicada (status='applied')
    run_q = await db.execute(
        select(ScaffoldRun)
        .where(
            ScaffoldRun.project_id == project_id,
            ScaffoldRun.status == "applied",
        )
        .order_by(ScaffoldRun.applied_at.desc())
        .limit(1)
    )
    last_run = run_q.scalar_one_or_none()
    if last_run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nenhum scaffold aplicado ainda. Execute Aplicar no Git pra gerar arquivos no remoto antes do preview.",
        )

    port = await _allocate_port(db, project_id)
    repo_url = git_cfg.repository_url
    setup = _build_setup_command(
        project_slug=project.slug or str(project_id)[:8],
        repo_url=repo_url,
        port=port,
    )
    preview_url = f"http://localhost:{port}"

    session_row = AppPreviewSession(
        project_id=project_id,
        scaffold_run_id=last_run.id,
        port=port,
        status="prepared",
        setup_command=setup,
        preview_url=preview_url,
        repository_url=repo_url,
        created_by=current_user_id,
    )
    db.add(session_row)
    await db.commit()
    await db.refresh(session_row)

    logger.info(
        "preview.prepared",
        project_id=str(project_id),
        run_id=str(last_run.id),
        port=port,
        session_id=str(session_row.id),
    )
    return _serialize(session_row)


@router.get(
    "/projects/{project_id}/preview",
    response_model=list[PreviewSessionDTO],
    summary="Lista sessões de preview do projeto (mais recentes primeiro)",
)
async def list_previews(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_from_token),
):
    res = await db.execute(
        select(AppPreviewSession)
        .where(AppPreviewSession.project_id == project_id)
        .order_by(AppPreviewSession.created_at.desc())
        .limit(50)
    )
    return [_serialize(s) for s in res.scalars().all()]


class PreviewStatusUpdate(BaseModel):
    status: str  # 'running' | 'stopped' | 'error'
    notes: str | None = None


@router.patch(
    "/preview/{session_id}/status",
    response_model=PreviewSessionDTO,
    summary="Owner reporta status do preview (running/stopped/error)",
)
async def update_preview_status(
    session_id: UUID,
    payload: PreviewStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_from_token),
):
    if payload.status not in ("running", "stopped", "error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status deve ser 'running', 'stopped' ou 'error'.",
        )
    session_row = await db.get(AppPreviewSession, session_id)
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    session_row.status = payload.status
    if payload.notes is not None:
        session_row.notes = payload.notes
    if payload.status == "stopped":
        session_row.stopped_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session_row)
    return _serialize(session_row)
