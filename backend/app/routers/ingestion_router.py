"""
Ingestion Router — Upload e gestão de documentos por projeto
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
import structlog

from app.db.database import get_db
from app.services.ingestion_service import IngestionService
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_project_setup import require_project_setup_complete

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestion"])


@router.post("/projects/{project_id}/ingestion")
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
    _setup: dict = Depends(require_project_setup_complete),
):
    """Upload de documento para análise pelo Arguidor."""
    filename = file.filename or "unnamed"

    # DT-021: detectar PDF de questionário do GCA antes de ingerir como documento
    # genérico. O PDF gerado pelo próprio sistema tem padrão de filename
    # `Questionario_GCA_<project_uuid>_editavel...pdf` e o caminho oficial de
    # submetê-lo é a aba Questionário (não Ingestão). Subir aqui joga o PDF no
    # detector de PII + Arguidor genérico — caminho errado.
    import re
    if re.match(r"(?i)^Questionario_GCA_[0-9a-f-]+.*\.pdf$", filename):
        raise HTTPException(
            status_code=409,
            detail=(
                "Este arquivo é o PDF do questionário técnico gerado pelo GCA. "
                "Ele deve ser submetido pela aba Questionário (não por Ingestão), "
                "para ser tratado como transporte de respostas e alimentar o OCG "
                "corretamente. Se este é um documento de complemento (não o "
                "questionário em si), renomeie o arquivo para algo diferente "
                "antes de subir aqui."
            ),
        )

    file_bytes = await file.read()
    service = IngestionService(db)
    result = await service.upload_document(
        project_id=project_id,
        uploaded_by=current_user_id,
        file_bytes=file_bytes,
        original_filename=filename,
        content_type=file.content_type or "",
    )

    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", result.get("message", "")))
    return result


@router.get("/projects/{project_id}/ingestion")
async def list_documents(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista documentos ingeridos do projeto."""
    service = IngestionService(db)
    return await service.list_documents(project_id)


@router.get("/projects/{project_id}/ingestion/{document_id}")
async def get_document_detail(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Documento + análise completa do Arguidor."""
    service = IngestionService(db)
    result = await service.get_document_detail(project_id, document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return result


@router.get("/projects/{project_id}/ingestion/{document_id}/status")
async def get_document_status(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Status para polling (a cada 3s)."""
    service = IngestionService(db)
    result = await service.get_document_status(project_id, document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return result


@router.delete("/projects/{project_id}/ingestion/{document_id}")
async def delete_document(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Remove documento. GP apenas."""
    service = IngestionService(db)
    result = await service.delete_document(project_id, document_id)
    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", ""))
    return result


@router.post("/projects/{project_id}/ingestion/{document_id}/release")
async def release_from_quarantine(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Liberar documento da quarentena e disparar análise + OCG update."""
    from app.models.base import IngestedDocument

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc.quarantine_status != "quarantined":
        raise HTTPException(status_code=400, detail="Documento não está em quarentena")

    doc.quarantine_status = "released"
    doc.arguider_status = "pending"
    await db.commit()

    return {"message": "Documento liberado da quarentena. Análise será iniciada.", "document_id": str(document_id)}


@router.post("/projects/{project_id}/ingestion/{document_id}/reanalyze")
async def reanalyze_document(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Re-executa o Arguidor em um documento já ingerido (DT-039).

    Casos de uso:
      - doc ficou em `error` (401, parse, timeout, etc) — quer tentar de novo
      - projeto trocou de provider (ex: DeepSeek → OpenAI) e quer re-analisar
        com o provider novo
      - prompt do Arguidor mudou (upgrade de versão) e quer re-analisar com
        novo comportamento

    Pré-requisitos:
      - `content_status='available'` (bytes do arquivo ainda no storage);
        se `lost` (ex: arquivo ingerido antes da DT-030 ser aplicada), este
        endpoint retorna 409 — user precisa reuploadar.
    """
    from app.models.base import IngestedDocument
    from app.utils.ingested_storage import read_ingested

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if doc.content_status == "lost":
        raise HTTPException(
            status_code=409,
            detail=(
                "Arquivo original foi perdido (storage ephemeral antes da DT-030). "
                "Reenvie o arquivo via aba Ingestão — não é possível reanalisar sem os bytes."
            ),
        )

    # DT-068: o path correto é /app/storage/ingested/<project_id>/<filename>
    # (ver utils/ingested_storage.py). O código antigo usava
    # os.path.join(STORAGE_PATH, filename), que resolvia pra /app/storage/<filename>
    # e falhava sempre — pior: marcava content_status='lost' em cima do
    # bug do próprio path, corrompendo o estado.
    file_bytes = read_ingested(project_id, doc.filename)
    if file_bytes is None:
        doc.content_status = "lost"
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail="Arquivo não encontrado no storage. Marcado como 'lost' — reenvie.",
        )

    # DT-071 — idempotência da reanalise. Sem limpar a análise anterior
    # e os items derivados, dois bugs acontecem:
    #  (1) DT-065 checkpoint detecta `arguider_analyses` existente pro
    #      document_id e PULA o LLM, indo direto pra updating_ocg. Ou
    #      seja, /reanalyze não reanalisa — reusa a análise velha.
    #  (2) Se forçássemos rodar de novo sem limpar, gatekeeper_items e
    #      module_candidates antigos ficam órfãos (mesmo doc, múltiplos
    #      IDs) e a UI duplica tudo.
    # Fix: DELETE gatekeeper_items → module_candidates → arguider_analyses
    # do document_id antes de disparar a task async. Ordem respeita a FK
    # arguider_analysis_id.
    from sqlalchemy import delete, select as _select
    from app.models.base import ArguiderAnalysis, GatekeeperItem, ModuleCandidate

    analysis_ids_q = await db.execute(
        _select(ArguiderAnalysis.id).where(ArguiderAnalysis.document_id == document_id)
    )
    analysis_ids = [row[0] for row in analysis_ids_q.all()]
    if analysis_ids:
        await db.execute(
            delete(GatekeeperItem).where(GatekeeperItem.arguider_analysis_id.in_(analysis_ids))
        )
        await db.execute(
            delete(ModuleCandidate).where(ModuleCandidate.arguider_analysis_id.in_(analysis_ids))
        )
        await db.execute(
            delete(ArguiderAnalysis).where(ArguiderAnalysis.id.in_(analysis_ids))
        )

    # Reset status antes do retry
    doc.arguider_status = "pending"
    doc.arguider_stage = "queued"
    doc.arguider_progress_percent = 0
    doc.arguider_error_message = None
    doc.arguider_started_at = None
    doc.arguider_completed_at = None
    doc.ocg_updated = False
    await db.commit()

    # Dispara análise em background (não bloqueia a resposta)
    import asyncio
    from app.services.ingestion_service import IngestionService
    svc = IngestionService(db)
    asyncio.create_task(svc._analyze_async(document_id, project_id, file_bytes, doc.file_type))

    logger.info(
        "ingestion.reanalyze_dispatched",
        document_id=str(document_id),
        project_id=str(project_id),
        filename=doc.original_filename,
    )

    return {
        "success": True,
        "message": "Reanálise disparada. Status será atualizado em segundo plano.",
        "document_id": str(document_id),
    }


@router.get("/projects/{project_id}/ingestion/{document_id}/content")
async def get_document_content(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Serve o conteúdo original do documento (read-only, inline)."""
    from fastapi.responses import Response
    from app.models.base import IngestedDocument
    from app.utils.ingested_storage import read_ingested

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Soft-delete: doc marcado como bytes perdidos (script de inventário).
    # 410 Gone é o status semanticamente correto — recurso existiu, foi perdido.
    if doc.content_status == "lost":
        raise HTTPException(
            status_code=410,
            detail=(
                "Conteúdo perdido permanentemente. O arquivo foi ingerido antes "
                "da feature de persistência e não é recuperável automaticamente. "
                "Re-faça o upload se ainda tiver o original."
            ),
        )

    content = read_ingested(project_id, doc.filename)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail="Conteúdo não disponível. Documento foi ingerido antes da persistência — requer re-ingestão.",
        )

    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "markdown": "text/markdown; charset=utf-8",
        "image": "image/png",
        "spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "code": "text/plain; charset=utf-8",
    }
    content_type = mime_map.get(doc.file_type, "application/octet-stream")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.original_filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )
