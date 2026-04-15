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
import asyncio
import json
import structlog

from app.db.database import get_db, AsyncSessionLocal
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectExternalRepo, RepoAnalysisResult, RepoIntegrationRoadmap, IngestedDocument

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

    # Disparar n8n webhook com fallback para análise direta
    try:
        import httpx
        from app.core.config import settings

        n8n_base = getattr(settings, 'N8N_WEBHOOK_URL', None) or "http://n8n:5678/webhook"
        n8n_url = f"{n8n_base}/gca-external-repo-reader/webhook/read-external-repo"
        analyze_url = f"{settings.API_PREFIX}/projects/{project_id}/external-repos/{repo_id}/analyze"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(n8n_url, json={
                "project_id": str(project_id),
                "repo_id": str(repo_id),
                "repo_url": repo.repo_url,
                "provider": repo.provider,
                "branch": repo.branch,
                "access_token": access_token,
                "callback_url": f"{settings.API_PREFIX}/projects/{project_id}/external-repos/{repo_id}/callback",
                "analyze_url": analyze_url,
            })

        if resp.status_code not in (200, 201):
            logger.warning("external_repo.n8n_trigger_failed", status=resp.status_code, body=resp.text[:200])
            # Fallback: rodar análise diretamente sem n8n
            logger.info("external_repo.fallback_direct_analysis", repo_id=str(repo_id))
            asyncio.create_task(_run_analysis_fallback(project_id, repo_id))

    except Exception as e:
        logger.warning("external_repo.n8n_trigger_error", error=str(e))
        # Fallback: rodar análise diretamente sem n8n
        logger.info("external_repo.fallback_direct_analysis", repo_id=str(repo_id))
        asyncio.create_task(_run_analysis_fallback(project_id, repo_id))

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


async def _run_analysis_fallback(project_id: UUID, repo_id: UUID):
    """Executa análise direta quando n8n não está disponível."""
    try:
        from app.services.repo_analysis_service import RepoAnalysisService
        async with AsyncSessionLocal() as db:
            service = RepoAnalysisService(db)
            await service.analyze_repository(project_id, repo_id)
            logger.info("external_repo.fallback_analysis_complete", repo_id=str(repo_id))
    except Exception as e:
        logger.error("external_repo.fallback_analysis_error", repo_id=str(repo_id), error=str(e))
        try:
            async with AsyncSessionLocal() as db:
                repo = await db.get(ProjectExternalRepo, repo_id)
                if repo:
                    repo.status = "error"
                    repo.error_message = f"Análise direta falhou: {str(e)[:200]}"
                    await db.commit()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────
# Endpoints de Análise
# ──────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/external-repos/{repo_id}/analyze")
async def analyze_repo(
    project_id: UUID,
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Executa análise completa do repositório (chamado pelo n8n ou diretamente)."""
    from app.services.repo_analysis_service import RepoAnalysisService
    service = RepoAnalysisService(db)
    result = await service.analyze_repository(project_id, repo_id)
    return result


@router.get("/projects/{project_id}/external-repos/{repo_id}/analysis")
async def get_analysis_results(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna resultados da análise para o frontend."""
    # Buscar todos os resultados da análise (um por categoria)
    result = await db.execute(
        select(RepoAnalysisResult)
        .where(
            (RepoAnalysisResult.repo_id == repo_id) &
            (RepoAnalysisResult.project_id == project_id)
        )
        .order_by(RepoAnalysisResult.category)
    )
    all_results = result.scalars().all()
    if not all_results:
        raise HTTPException(status_code=404, detail="Análise não encontrada para este repositório")

    # Usar o primeiro resultado para dados compartilhados (stack, compat, etc.)
    analysis = all_results[0]

    # Buscar roadmap de integração
    roadmap_result = await db.execute(
        select(RepoIntegrationRoadmap)
        .where(
            (RepoIntegrationRoadmap.repo_id == repo_id) &
            (RepoIntegrationRoadmap.project_id == project_id)
        )
        .order_by(RepoIntegrationRoadmap.step_number)
    )
    roadmap_items = roadmap_result.scalars().all()

    # Buscar documentos injetados
    docs_result = await db.execute(
        select(IngestedDocument)
        .where(
            (IngestedDocument.project_id == project_id) &
            (IngestedDocument.source_repo_id == repo_id)
        )
        .order_by(IngestedDocument.created_at.desc())
    )
    injected_docs = docs_result.scalars().all()

    # Parse JSON fields com fallback seguro
    def safe_json(val):
        if not val:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    return {
        "stack": safe_json(analysis.stack_json) or {
            "language": {"primary": analysis.primary_language},
            "repository": {"files_total": 0},
            "frameworks": [{"name": analysis.framework_name, "version": analysis.framework_version}] if analysis.framework_name else [],
            "has_dockerfile": analysis.has_docker,
            "has_cicd": analysis.has_cicd,
            "has_tests": analysis.has_tests,
        },
        "vulnerabilities": safe_json(analysis.vulnerabilities_json) or {
            "security_summary": {
                "total_vulnerabilities": analysis.vulnerabilities_count,
                "critical": analysis.critical_vulnerabilities,
                "risk_level": analysis.risk_level,
            },
            "vulnerabilities": [],
        },
        "compatibility": safe_json(analysis.compatibility_matrix) or {
            "compatibility_assessment": {
                "overall_status": analysis.gca_overall_status,
                "effort_estimate_days": analysis.gca_integration_effort_days,
            },
            "gca_backend_compatibility": {"status": "compatível" if analysis.gca_backend_compatible else "incompatível", "reason": ""},
            "gca_frontend_compatibility": {"status": "compatível" if analysis.gca_frontend_compatible else "incompatível", "reason": ""},
            "gca_database_compatibility": {"status": "compatível" if analysis.gca_database_compatible else "incompatível", "reason": ""},
        },
        "gca_overall_status": analysis.gca_overall_status,
        "risk_level": analysis.risk_level,
        "categories": [
            {
                "category": r.category,
                "summary": r.summary,
                "files_analyzed": r.files_analyzed,
                "ai_provider": r.ai_provider_used,
                "metrics": safe_json(r.metrics) if r.metrics else {},
            }
            for r in all_results
        ],
        "roadmap": [
            {
                "id": str(r.id),
                "step_number": r.step_number,
                "title": r.title,
                "description": r.description,
                "effort_hours": r.effort_hours,
                "status": r.status,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in roadmap_items
        ],
        "injected_documents": [
            {
                "id": str(d.id),
                "filename": d.original_filename,
                "file_type": d.file_type,
                "source_url": d.source_url,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in injected_docs
        ],
        "analyzed_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }


@router.post("/projects/{project_id}/external-repos/{repo_id}/approve-integration")
async def approve_integration(
    project_id: UUID,
    repo_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """GP aprova integração de repos que requerem adaptação."""
    repo = await db.get(ProjectExternalRepo, repo_id)
    if not repo or repo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Repositório não encontrado")

    # Verificar se existe análise com status requer_adaptação
    result = await db.execute(
        select(RepoAnalysisResult)
        .where(
            (RepoAnalysisResult.repo_id == repo_id) &
            (RepoAnalysisResult.project_id == project_id)
        )
        .order_by(RepoAnalysisResult.created_at.desc())
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=400, detail="Repositório ainda não foi analisado")

    if analysis.gca_overall_status not in ("requer_adaptacao", "requer_adaptação"):
        raise HTTPException(
            status_code=400,
            detail=f"Repositório com status '{analysis.gca_overall_status}' não requer aprovação manual"
        )

    # Aprovar integração
    repo.is_approved_for_integration = True
    await db.commit()

    # Disparar injeção dos documentos já analisados
    try:
        from app.services.repo_analysis_service import RepoAnalysisService
        service = RepoAnalysisService(db)
        await service.analyze_repository(project_id, repo_id)
        logger.info("external_repo.integration_approved_and_injected",
                     repo_id=str(repo_id), approved_by=str(current_user_id))
    except Exception as e:
        logger.warning("external_repo.injection_after_approval_failed",
                       repo_id=str(repo_id), error=str(e))

    return {
        "message": "Integração aprovada com sucesso",
        "repo_id": str(repo_id),
        "is_approved_for_integration": True,
    }
