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


# ============================================================================
# MVP 10 Fase 10.2 — Planos de teste gerados por LLM
# ============================================================================

@router.get("/projects/{project_id}/test-specs")
async def list_test_specs(
    project_id: UUID,
    spec_type: Optional[str] = Query(None, description="unit|integration|security|compliance|e2e"),
    module_id: Optional[UUID] = Query(None, description="filtra por módulo"),
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista TestSpecs do projeto com filtros opcionais.

    MVP 10 Fase 10.4 — cada item vem com `is_stale` + `stale_reason`
    computados on-the-fly comparando `ocg_version_at_generation` com
    OCG atual. Zero mutação no DB.
    """
    from sqlalchemy import select as _select
    from app.models.base import TestSpec
    from app.services.stale_detection_service import evaluate_test_spec_staleness

    query = _select(TestSpec).where(TestSpec.project_id == project_id)
    if spec_type:
        query = query.where(TestSpec.spec_type == spec_type)
    if module_id is not None:
        query = query.where(TestSpec.module_id == module_id)

    rows = await db.execute(query)
    items = rows.scalars().all()

    staleness = await evaluate_test_spec_staleness(db, project_id)

    return [
        {
            "id": str(s.id),
            "project_id": str(s.project_id),
            "module_id": str(s.module_id) if s.module_id else None,
            "spec_type": s.spec_type,
            "status": s.status,
            "content_preview": (s.content or "")[:200],
            "content_chars": len(s.content or ""),
            "ocg_version_at_generation": s.ocg_version_at_generation,
            "generated_at": s.generated_at.isoformat() if s.generated_at else None,
            "generator_provider": s.generator_provider,
            "generator_model": s.generator_model,
            "approved_by": str(s.approved_by) if s.approved_by else None,
            "approved_at": s.approved_at.isoformat() if s.approved_at else None,
            # MVP 10 Fase 10.4
            "is_stale": staleness.get(s.id).is_stale if s.id in staleness else False,
            "stale_reason": (
                staleness.get(s.id).reason if s.id in staleness and staleness[s.id].reason else None
            ),
        }
        for s in items
    ]


@router.get("/projects/{project_id}/test-specs/stale-summary")
async def get_stale_summary(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.4 — Agregado de staleness pra banner da aba Testes.

    Retorna counts por tipo (test_specs + live_docs) + flag
    `needs_regeneration`. Zero mutação — só leitura.
    """
    from app.services.stale_detection_service import build_stale_summary
    return await build_stale_summary(db, project_id)


@router.get("/projects/{project_id}/test-specs/{spec_id}")
async def get_test_spec(
    project_id: UUID,
    spec_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna conteúdo completo do spec + provenance pro modal da UI."""
    from app.models.base import TestSpec
    import json as _json

    spec = await db.get(TestSpec, spec_id)
    if not spec or spec.project_id != project_id:
        raise HTTPException(status_code=404, detail="Spec não encontrado")

    provenance = None
    if spec.provenance_json:
        try:
            provenance = _json.loads(spec.provenance_json)
        except (ValueError, TypeError):
            provenance = None

    # MVP 10 Fase 10.4 — stale on-the-fly pra este spec
    from app.services.stale_detection_service import evaluate_test_spec_staleness
    staleness_map = await evaluate_test_spec_staleness(db, project_id)
    stale_info = staleness_map.get(spec.id)

    return {
        "id": str(spec.id),
        "project_id": str(spec.project_id),
        "module_id": str(spec.module_id) if spec.module_id else None,
        "spec_type": spec.spec_type,
        "status": spec.status,
        "content": spec.content or "",
        "provenance": provenance,
        "ocg_version_at_generation": spec.ocg_version_at_generation,
        "generated_at": spec.generated_at.isoformat() if spec.generated_at else None,
        "generator_provider": spec.generator_provider,
        "generator_model": spec.generator_model,
        "rejection_reason": spec.rejection_reason,
        "is_stale": stale_info.is_stale if stale_info else False,
        "stale_reason": stale_info.reason if stale_info else None,
        "current_ocg_version": stale_info.current_ocg_version if stale_info else None,
    }


@router.post("/projects/{project_id}/modules/{module_id}/test-specs/generate")
async def generate_single_test_spec(
    project_id: UUID,
    module_id: UUID,
    spec_type: str = Query(..., description="unit|integration|e2e"),
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.2 — Gera (ou regera) TestSpec de 1 módulo + tipo.

    Rebaixa status pra 'draft' se existia approved/rejected — regeneração
    exige re-revisão (regra dura §7 MVP 10).

    503 se Ollama não configurado.
    """
    try:
        spec = await generate_module_spec(db, project_id, module_id, spec_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "test_spec.generate_unexpected_error",
            project_id=str(project_id), module_id=str(module_id),
            error_type=type(exc).__name__, error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar spec ({type(exc).__name__}): {exc!r}",
        )

    return {
        "id": str(spec.id),
        "spec_type": spec.spec_type,
        "status": spec.status,
        "content_chars": len(spec.content or ""),
        "generated_at": spec.generated_at.isoformat() if spec.generated_at else None,
    }


@router.post("/projects/{project_id}/test-specs/generate-global")
async def generate_global_test_spec(
    project_id: UUID,
    spec_type: str = Query(..., description="security|compliance"),
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.3 — Gera (ou regera) TestSpec GLOBAL via Premium.

    Specs globais (module_id=NULL) consolidam OCG inteiro. Só aceita
    security e compliance — alta criticidade §6.3 exige Premium.

    503 se Premium não configurado (Ollama é explicitamente ignorado).
    """
    from app.services.global_spec_generator_service import generate_global_spec

    try:
        spec = await generate_global_spec(db, project_id, spec_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "global_spec.generate_unexpected_error",
            project_id=str(project_id), spec_type=spec_type,
            error_type=type(exc).__name__, error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar spec global ({type(exc).__name__}): {exc!r}",
        )

    return {
        "id": str(spec.id),
        "spec_type": spec.spec_type,
        "status": spec.status,
        "content_chars": len(spec.content or ""),
        "generator_provider": spec.generator_provider,
        "generator_model": spec.generator_model,
        "generated_at": spec.generated_at.isoformat() if spec.generated_at else None,
    }


@router.post("/projects/{project_id}/test-specs/regenerate-global")
async def bulk_regenerate_global_specs(
    project_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.3 — Regenera security + compliance em bulk.

    Tolera falha individual (acumula em `errors`). Útil pro botão
    'Regenerar Security+Compliance' da Fase 10.8.
    """
    from app.services.global_spec_generator_service import regenerate_all_global_specs
    try:
        return await regenerate_all_global_specs(db, project_id)
    except Exception as exc:
        import traceback
        logger.error(
            "global_spec.bulk_regenerate_failed",
            project_id=str(project_id), error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"Erro no bulk global: {exc!r}")


@router.post("/projects/{project_id}/test-specs/regenerate")
async def bulk_regenerate_test_specs(
    project_id: UUID,
    spec_types: str = Query("unit,integration", description="CSV de tipos"),
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.2 — Regenera specs em bulk pra todos os módulos.

    Itera módulos canônicos do Roadmap × tipos solicitados. Tolera
    falhas individuais (acumula em `errors`). Útil pra o botão
    'Regenerar Tudo' da Fase 10.5.
    """
    types_tuple = tuple(
        t.strip() for t in spec_types.split(",")
        if t.strip() in SUPPORTED_TYPES_LOCAL
    )
    if not types_tuple:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum spec_type válido em '{spec_types}'. "
                   f"Aceitos: {SUPPORTED_TYPES_LOCAL}",
        )

    try:
        report = await regenerate_project_specs(db, project_id, spec_types=types_tuple)
    except Exception as exc:
        import traceback
        logger.error(
            "test_spec.bulk_regenerate_failed",
            project_id=str(project_id), error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"Erro no bulk: {exc!r}")

    return report
