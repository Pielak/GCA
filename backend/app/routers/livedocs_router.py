"""
LiveDocs Router — Endpoints de documentação viva.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
import json as _json
import structlog

from app.db.database import get_db
from app.services.livedocs_service import LiveDocsService
from app.dependencies.require_action import require_action
from app.services.live_doc_generator_service import (
    generate_module_live_doc,
    generate_consolidated_live_doc,
    regenerate_all_module_docs,
    regenerate_all_consolidated_docs,
    PREMIUM_DOC_TYPES,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["livedocs"])

# DT-044 — RBAC em LiveDocs (MVP 4 §7):
#  - project:view para leitura (todo membro + admin_viewer)
#  - docs:edit para refresh (GP, Dev — quem edita docs per contrato)


@router.get("/projects/{project_id}/docs")
async def get_doc_index(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Índice de todas as seções de documentação do projeto."""
    service = LiveDocsService(db)
    sections = await service.get_doc_index(project_id)
    return {"sections": sections, "total": len(sections)}


@router.get("/projects/{project_id}/docs/content")
async def get_doc_content(
    project_id: UUID,
    path: str = Query(..., description="Caminho da seção (ex: docs/README.md)"),
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Conteúdo de uma seção específica de documentação."""
    service = LiveDocsService(db)
    content = await service.get_doc_section(project_id, path)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seção não encontrada: {path}",
        )
    return {"path": path, "content": content}


@router.get("/projects/{project_id}/docs/ocg/history")
async def get_ocg_history(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de versões do OCG e suas alterações na documentação."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog
    result = await db.execute(
        select(OCGDeltaLog)
        .where(OCGDeltaLog.project_id == project_id)
        .order_by(OCGDeltaLog.created_at.desc())
    )
    deltas = result.scalars().all()
    return {
        "history": [
            {
                "id": str(d.id),
                "version_from": d.ocg_version_from,
                "version_to": d.ocg_version_to,
                "change_summary": d.change_summary,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deltas
        ],
        "total": len(deltas),
    }


@router.post("/projects/{project_id}/docs/refresh")
async def refresh_documentation(
    project_id: UUID,
    _perm: dict = Depends(require_action("docs:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Regenera toda a documentação a partir do OCG atual (GP/Dev)."""
    service = LiveDocsService(db)
    result = await service.refresh_ocg_documentation(project_id)
    if not result.get("refreshed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("reason", "Falha ao atualizar documentação"),
        )
    return result


@router.get("/projects/{project_id}/docs/changelog")
async def get_changelog(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Changelog do projeto — eventos de documentação, ingestão e geração."""
    # Buscar eventos recentes de diversas fontes
    from sqlalchemy import select, union_all
    from app.models.base import IngestedDocument, GeneratedModule

    changelog = []

    # Documentos ingeridos
    result = await db.execute(
        select(IngestedDocument)
        .where(IngestedDocument.project_id == project_id)
        .order_by(IngestedDocument.created_at.desc())
        .limit(50)
    )
    docs = result.scalars().all()
    for doc in docs:
        entry = LiveDocsService.generate_changelog_entry(
            "document_ingested",
            {"summary": f"Documento '{doc.original_filename}' ingerido", "document_id": str(doc.id)},
        )
        changelog.append(entry)

    # Módulos gerados
    result = await db.execute(
        select(GeneratedModule)
        .where(GeneratedModule.project_id == project_id)
        .order_by(GeneratedModule.created_at.desc())
        .limit(50)
    )
    modules = result.scalars().all()
    for mod in modules:
        entry = LiveDocsService.generate_changelog_entry(
            "module_generated",
            {"summary": f"Módulo '{mod.name}' gerado ({mod.status})", "module_id": str(mod.id)},
        )
        changelog.append(entry)

    # Ordenar por timestamp
    changelog.sort(key=lambda x: x["timestamp"], reverse=True)

    return {"changelog": changelog[:100], "total": len(changelog)}


# ============================================================================
# MVP 10 Fase 10.7 — LiveDocs reais (module_doc Ollama, index/architecture Premium)
# ============================================================================

@router.get("/projects/{project_id}/live-docs")
async def list_live_docs(
    project_id: UUID,
    doc_type: Optional[str] = Query(None, description="module_doc|index|architecture"),
    module_id: Optional[UUID] = Query(None, description="filtra por módulo"),
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Lista LiveDocs do projeto com filtros opcionais.

    Cada item vem com `is_stale` + `stale_reason` computados on-the-fly
    comparando `ocg_version_at_generation` com a versão atual do OCG.
    """
    from sqlalchemy import select as _select
    from app.models.base import LiveDoc
    from app.services.stale_detection_service import evaluate_live_doc_staleness

    query = _select(LiveDoc).where(LiveDoc.project_id == project_id)
    if doc_type:
        query = query.where(LiveDoc.doc_type == doc_type)
    if module_id is not None:
        query = query.where(LiveDoc.module_id == module_id)

    rows = await db.execute(query)
    items = rows.scalars().all()

    staleness = await evaluate_live_doc_staleness(db, project_id)

    return [
        {
            "id": str(d.id),
            "project_id": str(d.project_id),
            "module_id": str(d.module_id) if d.module_id else None,
            "doc_type": d.doc_type,
            "content_preview": (d.content or "")[:200],
            "content_chars": len(d.content or ""),
            "ocg_version_at_generation": d.ocg_version_at_generation,
            "generated_at": d.generated_at.isoformat() if d.generated_at else None,
            "generator_provider": d.generator_provider,
            "generator_model": d.generator_model,
            "is_stale": staleness.get(d.id).is_stale if d.id in staleness else False,
            "stale_reason": (
                staleness.get(d.id).reason if d.id in staleness and staleness[d.id].reason else None
            ),
        }
        for d in items
    ]


@router.get("/projects/{project_id}/live-docs/{doc_id}")
async def get_live_doc(
    project_id: UUID,
    doc_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna conteúdo completo do LiveDoc + provenance (modal UI)."""
    from app.models.base import LiveDoc
    from app.services.stale_detection_service import evaluate_live_doc_staleness

    doc = await db.get(LiveDoc, doc_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="LiveDoc não encontrado")

    provenance = None
    if doc.provenance_json:
        try:
            provenance = _json.loads(doc.provenance_json)
        except (ValueError, TypeError):
            provenance = None

    staleness_map = await evaluate_live_doc_staleness(db, project_id)
    stale_info = staleness_map.get(doc.id)

    return {
        "id": str(doc.id),
        "project_id": str(doc.project_id),
        "module_id": str(doc.module_id) if doc.module_id else None,
        "doc_type": doc.doc_type,
        "content": doc.content or "",
        "provenance": provenance,
        "ocg_version_at_generation": doc.ocg_version_at_generation,
        "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
        "generator_provider": doc.generator_provider,
        "generator_model": doc.generator_model,
        "is_stale": stale_info.is_stale if stale_info else False,
        "stale_reason": stale_info.reason if stale_info else None,
        "current_ocg_version": stale_info.current_ocg_version if stale_info else None,
    }


@router.post("/projects/{project_id}/modules/{module_id}/live-docs/generate")
async def generate_module_doc(
    project_id: UUID,
    module_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.7 — Gera module_doc via Ollama (baixa criticidade §6.2).

    503 se Ollama não configurado no projeto.
    """
    try:
        doc = await generate_module_live_doc(db, project_id, module_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "live_doc.generate_unexpected_error",
            project_id=str(project_id), module_id=str(module_id),
            error_type=type(exc).__name__, error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar doc ({type(exc).__name__}): {exc!r}",
        )

    return {
        "id": str(doc.id),
        "doc_type": doc.doc_type,
        "content_chars": len(doc.content or ""),
        "generator_provider": doc.generator_provider,
        "generator_model": doc.generator_model,
        "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
    }


@router.post("/projects/{project_id}/live-docs/generate-consolidated")
async def generate_consolidated_doc(
    project_id: UUID,
    doc_type: str = Query(..., description="index|architecture"),
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.7 — Gera doc consolidada (index|architecture) via Premium.

    Alta criticidade §6.3 — Ollama é explicitamente ignorado. 503 se
    Premium não configurado.
    """
    if doc_type not in PREMIUM_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type deve ser um de {PREMIUM_DOC_TYPES}. Recebido: {doc_type}",
        )

    try:
        doc = await generate_consolidated_live_doc(db, project_id, doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "live_doc.consolidated_unexpected_error",
            project_id=str(project_id), doc_type=doc_type,
            error_type=type(exc).__name__, error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar doc consolidada ({type(exc).__name__}): {exc!r}",
        )

    return {
        "id": str(doc.id),
        "doc_type": doc.doc_type,
        "content_chars": len(doc.content or ""),
        "generator_provider": doc.generator_provider,
        "generator_model": doc.generator_model,
        "generated_at": doc.generated_at.isoformat() if doc.generated_at else None,
    }


@router.post("/projects/{project_id}/live-docs/regenerate")
async def bulk_regenerate_module_docs(
    project_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.7 — Regenera module_doc pra TODOS os módulos (Ollama).

    Tolera falha individual (acumula em `errors`).
    """
    try:
        return await regenerate_all_module_docs(db, project_id)
    except Exception as exc:
        import traceback
        logger.error(
            "live_doc.bulk_regenerate_failed",
            project_id=str(project_id), error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"Erro no bulk module_doc: {exc!r}")


@router.post("/projects/{project_id}/live-docs/regenerate-consolidated")
async def bulk_regenerate_consolidated_docs(
    project_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 10 Fase 10.7 — Regenera index + architecture (Premium)."""
    try:
        return await regenerate_all_consolidated_docs(db, project_id)
    except Exception as exc:
        import traceback
        logger.error(
            "live_doc.bulk_consolidated_failed",
            project_id=str(project_id), error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500, detail=f"Erro no bulk consolidado: {exc!r}"
        )
