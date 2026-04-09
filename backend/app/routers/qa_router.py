"""
QA Router — Tester Review + Execução de Testes + Logs de Auditoria.

13 endpoints cobrindo CRUD de artefatos de teste, execução isolada,
resultados consolidados e exportação de logs.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
import structlog

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.services.tester_review_service import TesterReviewService
from app.services.qa_service import QAService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["qa"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TestUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None


class TestRejectRequest(BaseModel):
    reason: str


class ExecutePlanRequest(BaseModel):
    test_types: Optional[List[str]] = None


# ============================================================================
# Tester Review — CRUD de artefatos de teste
# ============================================================================

@router.get("/projects/{project_id}/tests")
async def list_tests(
    project_id: UUID,
    test_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Listar artefatos de teste com filtros opcionais."""
    svc = TesterReviewService(db)
    return await svc.list_tests(project_id, test_type=test_type, status=status)


@router.get("/projects/{project_id}/tests/{test_id}")
async def get_test(
    project_id: UUID,
    test_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe de um artefato de teste."""
    svc = TesterReviewService(db)
    result = await svc.get_test(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Teste não encontrado")
    return result


@router.put("/projects/{project_id}/tests/{test_id}")
async def update_test(
    project_id: UUID,
    test_id: UUID,
    req: TestUpdateRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Editar artefato de teste (RBAC: tester/admin)."""
    svc = TesterReviewService(db)
    result = await svc.update_test(
        test_id, current_user_id,
        content=req.content, title=req.title, description=req.description,
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.post("/projects/{project_id}/tests/{test_id}/approve")
async def approve_test(
    project_id: UUID,
    test_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Aprovar artefato de teste (RBAC: tester/gestor/admin/qa)."""
    svc = TesterReviewService(db)
    result = await svc.approve_test(test_id, current_user_id)
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.post("/projects/{project_id}/tests/{test_id}/reject")
async def reject_test(
    project_id: UUID,
    test_id: UUID,
    req: TestRejectRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Rejeitar artefato de teste com justificativa."""
    svc = TesterReviewService(db)
    result = await svc.reject_test(test_id, current_user_id, req.reason)
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


# ============================================================================
# Execução de testes
# ============================================================================

@router.post("/projects/{project_id}/qa/execute")
async def execute_test_plan(
    project_id: UUID,
    req: ExecutePlanRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Disparar plano de testes por categoria."""
    svc = QAService(db)
    return await svc.execute_test_plan(project_id, current_user_id, test_types=req.test_types)


@router.post("/projects/{project_id}/qa/execute/{test_id}")
async def execute_single_test(
    project_id: UUID,
    test_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Executar um teste individual."""
    svc = QAService(db)
    result = await svc.execute_single_test(test_id, current_user_id)
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.get("/projects/{project_id}/qa/results")
async def get_results(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Resultados consolidados das execuções."""
    svc = QAService(db)
    return await svc.get_execution_results(project_id)


@router.get("/projects/{project_id}/qa/coverage")
async def get_coverage(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Cobertura por categoria de teste."""
    svc = QAService(db)
    return await svc.get_coverage_by_type(project_id)


# ============================================================================
# Logs de auditoria
# ============================================================================

@router.get("/projects/{project_id}/qa/logs")
async def get_logs(
    project_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Logs de execução paginados."""
    svc = QAService(db)
    return await svc.get_logs(project_id, limit=limit, offset=offset)


@router.get("/projects/{project_id}/qa/logs/{test_id}")
async def get_test_logs(
    project_id: UUID,
    test_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Logs de execução de um teste específico."""
    svc = TesterReviewService(db)
    return await svc.get_execution_logs(test_id)


@router.get("/projects/{project_id}/qa/logs/export")
async def export_logs(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Exportar todos os logs de execução como lista JSON."""
    svc = QAService(db)
    return await svc.get_logs(project_id, limit=10000, offset=0)
