"""
External Repos Router — Repositórios externos vinculados ao projeto.
GP cadastra repos read-only, GCA analisa via n8n + DeepSeek e injeta documentação.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import structlog

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectExternalRepo

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["external-repos"])


class AddRepoRequest(BaseModel):
    repo_url: str
    provider: str = "github"
    branch: str = "main"
    access_token: Optional[str] = None


class CallbackRequest(BaseModel):
    status: str
    files_total: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    error_message: Optional[str] = None


@router.get("/projects/{project_id}/external-repos")
async def list_external_repos(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Listar repositórios externos cadastrados no projeto."""
    result = await db.execute(
        select(ProjectExternalRepo)
        .where(ProjectExternalRepo.project_id == project_id)
        .order_by(ProjectExternalRepo.created_at.desc())
    )
    repos = result.scalars().all()

    return {
        "repos": [
            {
                "id": str(r.id),
                "repo_url": r.repo_url,
                "provider": r.provider,
                "branch": r.branch,
                "status": r.status,
                "last_read_at": r.last_read_at.isoformat() if r.last_read_at else None,
                "files_total": r.files_total,
                "files_processed": r.files_processed,
                "files_skipped": r.files_skipped,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in repos
        ]
    }


@router.post("/projects/{project_id}/external-repos")
async def add_external_repo(
    project_id: UUID,
    req: AddRepoRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Cadastrar novo repositório externo (GP apenas)."""
    if req.provider not in ("github", "gitlab", "bitbucket"):
        raise HTTPException(status_code=400, detail="Provider deve ser github, gitlab ou bitbucket")

    # Verificar duplicata
    existing = await db.execute(
        select(ProjectExternalRepo).where(
            (ProjectExternalRepo.project_id == project_id) &
            (ProjectExternalRepo.repo_url == req.repo_url)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Repositório já cadastrado neste projeto")

    # Criptografar token se fornecido
    encrypted_token = None
    if req.access_token:
        from app.services.vault_service import VaultService
        vault = VaultService()
        await vault.store_secret(db, project_id, "repo_token", req.repo_url, req.access_token, current_user_id)
        encrypted_token = "stored_in_vault"

    repo = ProjectExternalRepo(
        project_id=project_id,
        repo_url=req.repo_url,
        provider=req.provider,
        branch=req.branch,
        access_token_encrypted=encrypted_token,
        added_by=current_user_id,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    logger.info("external_repo.added",
                project_id=str(project_id),
                repo_url=req.repo_url,
                provider=req.provider)

    return {"id": str(repo.id), "message": "Repositório cadastrado com sucesso"}


@router.delete("/projects/{project_id}/external-repos/{repo_id}")
async def remove_external_repo(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Remover repositório externo."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    await db.delete(repo)
    await db.commit()

    logger.info("external_repo.removed", repo_id=str(repo_id), repo_url=repo.repo_url)
    return {"message": "Repositório removido"}


@router.post("/projects/{project_id}/external-repos/{repo_id}/read")
async def trigger_read(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Disparar leitura do repositório via n8n webhook."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    if repo.status == "reading":
        raise HTTPException(status_code=409, detail="Leitura já em andamento")

    # Recuperar token do vault
    access_token = None
    if repo.access_token_encrypted:
        from app.services.vault_service import VaultService
        vault = VaultService()
        access_token = await vault.get_secret(db, project_id, "repo_token", repo.repo_url)

    # Atualizar status
    repo.status = "reading"
    repo.files_total = 0
    repo.files_processed = 0
    repo.error_message = None
    await db.commit()

    # Disparar n8n webhook
    try:
        import httpx
        from app.core.config import settings

        n8n_url = getattr(settings, 'N8N_WEBHOOK_URL', None) or "http://n8n:5678/webhook/read-external-repo"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(n8n_url, json={
                "project_id": str(project_id),
                "repo_id": str(repo_id),
                "repo_url": repo.repo_url,
                "provider": repo.provider,
                "branch": repo.branch,
                "access_token": access_token,
                "callback_url": f"{settings.API_PREFIX}/projects/{project_id}/external-repos/{repo_id}/callback",
            })

        if resp.status_code not in (200, 201):
            logger.warning("external_repo.n8n_trigger_failed", status=resp.status_code, body=resp.text[:200])
            # Não bloquear — n8n pode não estar configurado ainda
            repo.status = "error"
            repo.error_message = f"n8n webhook retornou {resp.status_code}. Verifique se o workflow está ativo."
            await db.commit()

    except Exception as e:
        logger.warning("external_repo.n8n_trigger_error", error=str(e))
        repo.status = "error"
        repo.error_message = f"Não foi possível conectar ao n8n: {str(e)[:200]}"
        await db.commit()

    logger.info("external_repo.read_triggered",
                repo_id=str(repo_id),
                repo_url=repo.repo_url)

    return {"message": "Leitura iniciada", "status": repo.status}


@router.get("/projects/{project_id}/external-repos/{repo_id}/status")
async def get_repo_status(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Status da leitura do repositório."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    return {
        "status": repo.status,
        "files_total": repo.files_total,
        "files_processed": repo.files_processed,
        "files_skipped": repo.files_skipped,
        "error_message": repo.error_message,
        "last_read_at": repo.last_read_at.isoformat() if repo.last_read_at else None,
    }


@router.post("/projects/{project_id}/external-repos/{repo_id}/callback")
async def repo_read_callback(
    project_id: UUID,
    repo_id: UUID,
    req: CallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Callback do n8n para atualizar status da leitura."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    repo.status = req.status
    repo.files_total = req.files_total
    repo.files_processed = req.files_processed
    repo.files_skipped = req.files_skipped
    repo.error_message = req.error_message
    if req.status in ("completed", "partial"):
        repo.last_read_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info("external_repo.callback",
                repo_id=str(repo_id),
                status=req.status,
                files_processed=req.files_processed)

    return {"message": "Status atualizado"}
