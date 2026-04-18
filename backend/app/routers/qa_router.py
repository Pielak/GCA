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
from app.dependencies.require_action import require_action
from app.services.tester_review_service import TesterReviewService
from app.services.qa_service import QAService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["qa"])

# DT-044 — mapeamento binário de ações por endpoint (contrato §4.1 + §7 MVP 4):
#  - project:view    → GPs, Devs, Testers, QAs, admin_viewer (read access)
#  - pipeline:execute → Dev + Tester (editam/executam testes; QA/GP bloqueados)
#  - qa:approve      → GP + QA (aprovam/rejeitam testes; Dev/Tester bloqueados)
#  - audit:view      → GP, Dev, Tester, QA (qualquer membro vê logs)
#  - audit:export    → GP + Tester (exportam evidências; QA só revisa, não exporta)


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
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Listar artefatos de teste com filtros opcionais."""
    svc = TesterReviewService(db)
    return await svc.list_tests(project_id, test_type=test_type, status=status)


@router.get("/projects/{project_id}/tests/{test_id}")
async def get_test(
    project_id: UUID,
    test_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
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
    perm: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """Editar artefato de teste (contrato §4.1: Tester edita, Dev também;
    GP/QA bloqueados por não terem `pipeline:execute`)."""
    svc = TesterReviewService(db)
    result = await svc.update_test(
        test_id, perm["user_id"],
        content=req.content, title=req.title, description=req.description,
    )
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.post("/projects/{project_id}/tests/{test_id}/approve")
async def approve_test(
    project_id: UUID,
    test_id: UUID,
    perm: dict = Depends(require_action("qa:approve")),
    db: AsyncSession = Depends(get_db),
):
    """Aprovar artefato de teste (contrato §4.1: QA aprova, GP também;
    Dev/Tester bloqueados)."""
    svc = TesterReviewService(db)
    result = await svc.approve_test(test_id, perm["user_id"])
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.post("/projects/{project_id}/tests/{test_id}/reject")
async def reject_test(
    project_id: UUID,
    test_id: UUID,
    req: TestRejectRequest,
    perm: dict = Depends(require_action("qa:approve")),
    db: AsyncSession = Depends(get_db),
):
    """Rejeitar artefato de teste com justificativa (mesmo gate do approve)."""
    svc = TesterReviewService(db)
    result = await svc.reject_test(test_id, perm["user_id"], req.reason)
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
    perm: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """Disparar plano de testes por categoria (Dev/Tester)."""
    svc = QAService(db)
    return await svc.execute_test_plan(project_id, perm["user_id"], test_types=req.test_types)


@router.post("/projects/{project_id}/qa/execute/{test_id}")
async def execute_single_test(
    project_id: UUID,
    test_id: UUID,
    perm: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """Executar um teste individual (Dev/Tester)."""
    svc = QAService(db)
    result = await svc.execute_single_test(test_id, perm["user_id"])
    if "error" in result:
        raise HTTPException(status_code=result.get("status_code", 400), detail=result["error"])
    return result


@router.get("/projects/{project_id}/qa/results")
async def get_results(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Resultados consolidados das execuções."""
    svc = QAService(db)
    return await svc.get_execution_results(project_id)


@router.get("/projects/{project_id}/qa/coverage")
async def get_coverage(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
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
    _perm: dict = Depends(require_action("audit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Logs de execução paginados (todos membros têm audit:view)."""
    svc = QAService(db)
    return await svc.get_logs(project_id, limit=limit, offset=offset)


@router.get("/projects/{project_id}/qa/logs/export")
async def export_logs(
    project_id: UUID,
    _perm: dict = Depends(require_action("audit:export")),
    db: AsyncSession = Depends(get_db),
):
    """Exportar todos os logs como evidência (GP + Tester).

    IMPORTANTE: rota `/export` DEVE vir antes de `/{test_id}` senão o
    FastAPI captura "export" como UUID e devolve 422 (bug descoberto em
    DT-044 2026-04-18).
    """
    svc = QAService(db)
    return await svc.get_logs(project_id, limit=10000, offset=0)


@router.get("/projects/{project_id}/qa/logs/{test_id}")
async def get_test_logs(
    project_id: UUID,
    test_id: UUID,
    _perm: dict = Depends(require_action("audit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Logs de execução de um teste específico."""
    svc = TesterReviewService(db)
    return await svc.get_execution_logs(test_id)
