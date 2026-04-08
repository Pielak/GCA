"""
Module Router — Endpoints de geração de código e testes por módulo.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
import structlog

from app.db.database import get_db
from app.services.module_codegen_service import ModuleCodegenService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["modules"])


class GenerateModuleRequest(BaseModel):
    module_candidate_id: UUID


@router.post("/projects/{project_id}/modules/generate")
async def generate_module(
    project_id: UUID,
    req: GenerateModuleRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Inicia geração de código para um módulo candidato aprovado."""
    service = ModuleCodegenService(db)
    module_id = await service.generate_module_from_candidate(
        project_id=project_id,
        module_candidate_id=req.module_candidate_id,
    )
    if not module_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível gerar o módulo. Verifique se o candidato existe e está aprovado.",
        )
    return {"module_id": str(module_id), "status": "generating"}


@router.get("/projects/{project_id}/modules")
async def list_modules(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os módulos gerados de um projeto."""
    service = ModuleCodegenService(db)
    modules = await service.list_modules(project_id)
    return {"modules": modules, "total": len(modules)}


@router.get("/projects/{project_id}/modules/{module_id}")
async def get_module_detail(
    project_id: UUID,
    module_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Detalhes completos de um módulo gerado."""
    service = ModuleCodegenService(db)
    module = await service.get_module(module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Módulo não encontrado.",
        )
    return {
        "id": str(module.id),
        "project_id": str(module.project_id),
        "name": module.name,
        "module_type": module.module_type,
        "status": module.status,
        "git_source_path": module.git_source_path,
        "git_unit_test_path": module.git_unit_test_path,
        "git_integration_test_path": module.git_integration_test_path,
        "git_uat_test_path": module.git_uat_test_path,
        "git_docs_path": module.git_docs_path,
        "llm_provider": module.llm_provider,
        "llm_model": module.llm_model,
        "tokens_used": module.tokens_used,
        "generation_latency_ms": module.generation_latency_ms,
        "error_message": module.error_message,
        "generated_at": module.generated_at.isoformat() if module.generated_at else None,
        "created_at": module.created_at.isoformat() if module.created_at else None,
    }


@router.get("/projects/{project_id}/modules/{module_id}/status")
async def get_module_status(
    project_id: UUID,
    module_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Status de geração de um módulo (para polling)."""
    service = ModuleCodegenService(db)
    status_info = await service.get_module_status(module_id)
    if not status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Módulo não encontrado.",
        )
    return status_info


@router.get("/projects/{project_id}/modules/{module_id}/tests")
async def get_module_tests(
    project_id: UUID,
    module_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista testes gerados para um módulo."""
    service = ModuleCodegenService(db)
    tests = await service.list_tests(project_id, module_id=module_id)
    return {"tests": tests, "total": len(tests)}
