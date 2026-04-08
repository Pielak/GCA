"""
LiveDocs Router — Endpoints de documentação viva.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
import structlog

from app.db.database import get_db
from app.services.livedocs_service import LiveDocsService
from app.middleware.auth import get_current_user_from_token

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["livedocs"])


@router.get("/projects/{project_id}/docs")
async def get_doc_index(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
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
    current_user_id: UUID = Depends(get_current_user_from_token),
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
    current_user_id: UUID = Depends(get_current_user_from_token),
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
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Regenera toda a documentação a partir do OCG atual."""
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
    current_user_id: UUID = Depends(get_current_user_from_token),
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
