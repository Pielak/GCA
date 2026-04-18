"""
Git Router — Conexão e operações com repositórios Git por projeto
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
import structlog

from app.db.database import get_db
from app.services.git_service import GitService
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_action import require_action

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["git"])


class GitConnectRequest(BaseModel):
    provider: str  # github, gitlab, bitbucket, azure_devops, other
    repository_url: str
    pat: str
    default_branch: str = "main"


class GitConnectResponse(BaseModel):
    success: bool
    message: str
    provider: str | None = None
    branch: str | None = None


class GitStatusResponse(BaseModel):
    connected: bool
    provider: str | None = None
    repository_url: str | None = None
    branch: str | None = None
    last_verified: str | None = None
    last_commit_at: str | None = None
    # Outros projetos que apontam para o mesmo repositório. Vazio = ok.
    # Presença aqui = violação de compartimentalização (contrato §2.2).
    shared_with: list[str] = []


@router.post(
    "/projects/{project_id}/git/connect",
    response_model=GitConnectResponse,
)
async def connect_git_repository(
    project_id: UUID,
    req: GitConnectRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Conecta um repositório Git ao projeto.
    Valida o PAT fazendo chamada de teste ao provider.
    """
    git_service = GitService(db)
    result = await git_service.connect_repository(
        project_id=project_id,
        provider=req.provider,
        repository_url=req.repository_url,
        pat=req.pat,
        default_branch=req.default_branch,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"],
        )

    return GitConnectResponse(**result)


@router.get(
    "/projects/{project_id}/git/status",
    response_model=GitStatusResponse,
)
async def get_git_status(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Status da conexão Git do projeto."""
    git_service = GitService(db)
    result = await git_service.verify_connection(project_id)
    return GitStatusResponse(**result)


@router.get("/projects/{project_id}/git/tree")
async def get_git_tree(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Árvore completa do repositório Git conectado (paths recursivos)."""
    git_service = GitService(db)
    tree = await git_service.list_tree(project_id)
    return {"tree": tree}


@router.get("/projects/{project_id}/git/file")
async def get_git_file(
    project_id: UUID,
    path: str,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o conteúdo de um arquivo no repo Git conectado."""
    from fastapi import HTTPException
    git_service = GitService(db)
    content = await git_service.get_file_content(project_id, path)
    if content is None:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no repositório")
    return {"path": path, "content": content}


@router.post(
    "/projects/{project_id}/git/verify",
    response_model=GitConnectResponse,
)
async def verify_git_connection(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Testa a conexão atual com o repositório."""
    git_service = GitService(db)
    result = await git_service.verify_connection(project_id)
    return GitConnectResponse(
        success=result["connected"],
        message="Conexão verificada" if result["connected"] else "Falha na conexão",
        provider=result.get("provider"),
        branch=result.get("branch"),
    )


@router.delete(
    "/projects/{project_id}/git/disconnect",
)
async def disconnect_git_repository(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Remove configuração Git do projeto. Apenas Admin global."""
    git_service = GitService(db)
    success = await git_service.disconnect(project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuração Git não encontrada",
        )
    return {"success": True}


class GitCommitRequest(BaseModel):
    file_path: str
    content: str
    message: str
    backlog_item_id: Optional[str] = None


@router.post("/projects/{project_id}/git/commit")
async def commit_file(
    project_id: UUID,
    request: GitCommitRequest,
    permissions: dict = Depends(require_action("git:commit")),
    db: AsyncSession = Depends(get_db),
):
    """Commit arquivo ao repositorio com audit log."""
    user_id = permissions["user_id"]
    roles = permissions.get("roles", [permissions.get("role", "unknown")])

    git_service = GitService(db)
    result = await git_service.commit_file(
        project_id=project_id,
        file_path=request.file_path,
        content=request.content,
        commit_message=request.message,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Erro ao commitar"))

    # Atualizar backlog item se fornecido
    if request.backlog_item_id:
        from app.models.base import BacklogItem
        item = await db.get(BacklogItem, request.backlog_item_id)
        if item:
            item.commit_sha = result.get("commit_sha")
            item.status = "committed"
            await db.commit()

    logger.info(
        "git.commit",
        project_id=str(project_id),
        user_id=str(user_id),
        roles=roles,
        file_path=request.file_path,
        commit_sha=result.get("commit_sha"),
    )

    return result
