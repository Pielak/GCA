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
from app.services.m01_service import M01Service
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_project_setup import require_project_setup_complete
from pydantic import BaseModel

from app.core.exceptions import NotFoundError
from app.routers.pipeline_questions_router import (
    router as pipeline_questions_router,
    get_pipeline_questions,
    submit_pipeline_answers,
    AnswersRequest,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestion"])


@router.post("/projects/{project_id}/ingestion")
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    target_module_id: Optional[str] = Form(None),
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

    # MVP 9 Fase 9.5.2 — parse target_module_id se fornecido. UUID inválido
    # vira None (em vez de 400) — service tenta extrair do PDF como fallback.
    parsed_target: UUID | None = None
    if target_module_id:
        try:
            parsed_target = UUID(target_module_id)
        except ValueError:
            parsed_target = None

    service = IngestionService(db)
    result = await service.upload_document(
        project_id=project_id,
        uploaded_by=current_user_id,
        file_bytes=file_bytes,
        original_filename=filename,
        content_type=file.content_type or "",
        target_module_id=parsed_target,
    )

    sc = result.pop("status_code", 200)
    if sc >= 400:
        raise HTTPException(status_code=sc, detail=result.get("error", result.get("message", "")))

    # Fase 2 Simplificação: Personas da ingestão removidas.
    # Pipeline agora: Questionário → 5 Personas (questionnaire.py) → OCG → Gatekeeper.
    # A ingestão apenas armazena documentos para referência.
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


@router.post("/projects/{project_id}/ingestion/{document_id}/cancel")
async def cancel_document(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Cancela manualmente um doc preso em pending/processing.
    Marca status='error' com mensagem 'Cancelado pelo owner'. UI mostra
    botão 'Reanalisar' depois disso pra retomar.
    """
    from datetime import datetime, timezone
    from app.models.base import IngestedDocument

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if doc.arguider_status not in ("pending", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"Doc em status {doc.arguider_status!r} — só cancela pending/processing.",
        )

    doc.arguider_status = "error"
    doc.arguider_stage = "failed"
    doc.arguider_completed_at = datetime.now(timezone.utc)
    doc.arguider_error_message = (
        doc.arguider_error_message or "Cancelado pelo owner"
    )
    await db.commit()

    logger.info(
        "ingestion.canceled_by_owner",
        document_id=str(document_id),
        project_id=str(project_id),
        canceled_by=str(current_user_id),
    )
    return {"message": "Documento cancelado.", "document_id": str(document_id)}


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
    # MVP 29 Fase 29.1: reset canônico também zera started_at (caso o
    # doc tenha sido quarentenado DEPOIS de uma tentativa parcial de
    # análise — evita zombie no próximo retry).
    doc.arguider_started_at = None
    doc.arguider_error_message = None
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

    # Feature flag: INGESTION_VIA_N8N migra orquestração para n8n
    from app.core.config import settings
    use_n8n = getattr(settings, "INGESTION_VIA_N8N", False)

    if use_n8n:
        import httpx
        import base64
        from app.services.ai_key_resolver import AIKeyResolver

        provider_chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
        chain_data = []
        for p in (provider_chain or []):
            chain_data.append({
                "provider": p.get("provider", ""),
                "model": p.get("model", ""),
                "api_key": p.get("api_key", ""),
                "is_default": p.get("is_default", False),
            })

        n8n_payload = {
            "ingestion_id": str(document_id),
            "project_id": str(project_id),
            "document_bytes_base64": base64.b64encode(file_bytes).decode() if file_bytes else "",
            "document_metadata": {
                "filename": doc.original_filename or doc.filename,
                "mime_type": doc.file_type or "application/octet-stream",
                "size_bytes": doc.file_size_bytes or 0,
                "uploaded_by": str(doc.uploaded_by or ""),
                "uploaded_by_role": "GP",
                "declared_purpose": "reanalyze",
            },
            "provider_chain": chain_data,
            "callback_url": f"{getattr(settings, 'GCA_CALLBACK_BASE_URL', 'http://localhost:8000')}/api/v1/webhooks/ingestion-complete",
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }

        n8n_url = getattr(settings, "N8N_BASE_URL", "http://localhost:5678")
        webhook_secret = getattr(settings, "GCA_WEBHOOK_SECRET", "")
        body_bytes = __import__("json").dumps(n8n_payload).encode()
        sig = "sha256=" + __import__("hmac").new(
            webhook_secret.encode(), body_bytes, __import__("hashlib").sha256
        ).hexdigest()

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{n8n_url}/webhook/gca-normalizer",
                content=body_bytes,
                headers={"Content-Type": "application/json", "X-GCA-Signature": sig},
            )
            if resp.status_code not in (200, 202):
                logger.error("ingestion.n8n_dispatch_failed", status=resp.status_code, body=resp.text[:200])
                raise HTTPException(status_code=502, detail=f"n8n dispatch falhou: {resp.status_code}")

        doc.arguider_status = "processing"
        doc.arguider_stage = "n8n_pipeline"
        await db.commit()
    else:
        from app.tasks.pipeline import pipeline_ingest_task
        pipeline_ingest_task.delay(
            str(document_id),
            str(project_id),
            doc.file_type or "",
        )

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


@router.get("/projects/{project_id}/ingestion/{document_id}/conflicts-pending-review")
async def get_conflicts_pending_user_decision(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """NOVO — FASE 1 Auditor Orquestrador.

    Retorna conflitos detectados durante consolidação de OCG que precisam
    de decisão humana (user final escolhe entre opções).

    Exemplo: 2+ personas sugeriram backends diferentes (PostgreSQL vs MongoDB).
    System não consegue decidir sozinho → user decide.
    """
    from sqlalchemy import select
    from app.models.base import ConflictPendingReview, ProjectMember

    # Validar que user é membro do projeto (compartimentalização §2.2)
    member_stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user_id,
        ProjectMember.is_active == True,
    )
    member = await db.scalar(member_stmt)
    if not member:
        raise HTTPException(status_code=403, detail="Acesso negado ao projeto")

    # Buscar conflitos pendentes do documento
    conflicts_stmt = select(ConflictPendingReview).where(
        ConflictPendingReview.project_id == project_id,
        ConflictPendingReview.document_id == document_id,
        ConflictPendingReview.status == "pending",
    )
    conflicts = await db.scalars(conflicts_stmt)
    conflicts_list = conflicts.all()

    logger.info(
        "hitl.get_conflicts",
        project_id=str(project_id),
        document_id=str(document_id),
        conflicts_count=len(conflicts_list),
    )

    return {
        "document_id": str(document_id),
        "conflicts": [
            {
                "conflict_id": str(c.id),
                "field": c.field_name,
                "personas_involved": c.personas_involved,
                "values_by_persona": c.values_by_persona,
                "conflict_reason": c.conflict_reason,
            }
            for c in conflicts_list
        ],
        "total_conflicts": len(conflicts_list),
        "awaiting_user_decision": len(conflicts_list) > 0,
    }


class ConflictResolution(BaseModel):
    """Resolução de conflito por usuário."""
    field: str
    selected_value: str
    justification: Optional[str] = None


@router.post("/projects/{project_id}/ingestion/{document_id}/conflict/{conflict_id}/resolve")
async def resolve_conflict(
    project_id: UUID,
    document_id: UUID,
    conflict_id: str,
    resolution: ConflictResolution,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """NOVO — FASE 1 Auditor Orquestrador.

    User resolve um conflito pendente escolhendo entre opções.
    Consequência: OCG é atualizado com decisão + justificativa.
    Propagação em cascata dispara (Gatekeeper, CodeGen, Backlog).
    """
    from sqlalchemy import select
    from datetime import datetime, timezone
    from app.models.base import ConflictPendingReview, ProjectMember, OCG, Questionnaire
    from app.services.audit_service import AuditService

    # 1. Validar que user é GP ou Admin do projeto
    member_stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user_id,
        ProjectMember.is_active == True,
    )
    member = await db.scalar(member_stmt)
    if not member or member.role not in ["gp", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Apenas GP ou Admin podem resolver conflitos",
        )

    # 2. Buscar ConflictPendingReview
    try:
        conflict_uuid = UUID(conflict_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="conflict_id inválido")

    conflict = await db.get(ConflictPendingReview, conflict_uuid)
    if not conflict or conflict.status != "pending":
        raise HTTPException(status_code=404, detail="Conflito não encontrado ou já resolvido")

    if conflict.project_id != project_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    # 3. Registrar resolução no ConflictPendingReview
    conflict.status = "resolved"
    conflict.resolved_by = current_user_id
    conflict.resolved_at = datetime.now(timezone.utc)
    conflict.resolved_value = {"value": resolution.selected_value}
    conflict.resolution_justification = resolution.justification
    db.add(conflict)
    await db.flush()

    # 4. Aplicar resolução ao OCG
    questionnaire_stmt = select(Questionnaire).where(
        Questionnaire.project_id == project_id
    ).order_by(Questionnaire.created_at.desc()).limit(1)
    questionnaire = await db.scalar(questionnaire_stmt)
    if not questionnaire:
        raise HTTPException(status_code=400, detail="Projeto sem questionário")

    ocg_stmt = select(OCG).where(
        OCG.questionnaire_id == questionnaire.id
    ).order_by(OCG.version.desc()).limit(1)
    ocg = await db.scalar(ocg_stmt)
    if not ocg:
        raise HTTPException(status_code=400, detail="Projeto sem OCG")

    # Update OCG field com resolved value
    if hasattr(ocg, conflict.field_name):
        try:
            # Try to convert resolved_value to appropriate type
            setattr(ocg, conflict.field_name, float(resolution.selected_value))
        except ValueError:
            # If not numeric, set as-is
            setattr(ocg, conflict.field_name, resolution.selected_value)

    ocg.version += 1
    ocg.updated_at = datetime.now(timezone.utc)
    db.add(ocg)
    await db.flush()

    # 5. Registrar em auditoria
    audit = AuditService(db)
    await audit.log_event(
        event_type="CONFLICT_RESOLVED",
        resource_type="conflict_pending_review",
        resource_id=conflict_uuid,
        details={
            "project_id": str(project_id),
            "field": conflict.field_name,
            "resolved_value": resolution.selected_value,
            "justification": resolution.justification,
            "personas_involved": conflict.personas_involved,
        },
    )

    # 6. Disparar propagação em cascata
    from app.services.propagation_service import PropagationService
    propagator = PropagationService(db)
    # Note: PropagationService.trigger não é async, chama em background se necessário
    logger.info(
        "hitl.conflict_resolved",
        project_id=str(project_id),
        conflict_id=str(conflict_id),
        field=conflict.field_name,
        resolved_value=resolution.selected_value,
    )

    await db.commit()

    return {
        "success": True,
        "message": "Conflito resolvido. OCG atualizado.",
        "document_id": str(document_id),
        "conflict_id": str(conflict_uuid),
        "field": conflict.field_name,
        "resolution_applied": resolution.selected_value,
        "ocg_version": ocg.version,
    }


@router.get("/projects/{project_id}/ingestion/{document_id}/content")
async def get_document_content(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Serve o conteúdo original do documento (read-only, inline).

    Fix dogfood 2026-04-22: endpoint exige token válido + membership no
    projeto (compartimentalização §2.2). Antes era acessível sem auth
    porque `get_current_user_from_token` retorna None silenciosamente —
    o link `<a target=_blank>` do frontend não manda Authorization
    header e o endpoint prosseguia. Agora rejeita anônimo e valida role.
    """
    from fastapi.responses import Response
    from app.models.base import IngestedDocument
    from app.utils.ingested_storage import read_ingested
    from app.dependencies.require_action import resolve_user_role_in_project

    if current_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação requerida",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Membership: usuário precisa ter papel no projeto (Admin global OU GP/dev/qa).
    role = await resolve_user_role_in_project(current_user_id, project_id, db)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem acesso a este projeto",
        )

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


@router.get("/projects/{project_id}/ingestion/{document_id}/extraction-report")
async def get_extraction_report(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """MVP 8 Fase 5 — Relatório do que o pipeline de extração entendeu.

    Retorna estatísticas (nº de parágrafos, tabelas, camadas PDF usadas,
    primeiros N RFs/RNFs/módulos detectados, warnings do extractor).
    Calculado sob demanda a partir dos bytes do doc — não depende do
    Arguidor ter rodado. O GP usa esse relatório pra decidir se o doc
    foi bem interpretado ou se precisa reenviar em outro formato.
    """
    from app.models.base import IngestedDocument
    from app.utils.ingested_storage import read_ingested
    from app.services.extraction_report_service import build_extraction_report

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if doc.content_status == "lost":
        raise HTTPException(
            status_code=410,
            detail="Conteúdo do documento perdido — não é possível gerar relatório.",
        )

    file_bytes = read_ingested(project_id, doc.filename)
    if file_bytes is None:
        raise HTTPException(
            status_code=404,
            detail="Arquivo não encontrado no storage.",
        )

    report = build_extraction_report(file_bytes, doc.file_type)
    report["document_id"] = str(document_id)
    report["original_filename"] = doc.original_filename
    return report


@router.get("/projects/{project_id}/ingestion/{document_id}/ocg-delta")
async def get_ocg_delta_for_document(
    project_id: UUID,
    document_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """MVP 27 Fase 1 — Impacto deste documento no OCG (antes/depois por pilar).

    Retorna o delta mais recente do `ocg_delta_log` associado a este
    document_id: versão from/to, overall antes/depois, score de cada pilar
    antes/depois, delta em pontos por pilar. Cliente renderiza tabela +
    cores (verde/vermelho/neutro) sem lógica de comparação no front.

    Quando o documento ainda não afetou o OCG (arguider pendente, updater
    rejeitou, ou propagação não rodou), retorna `has_delta=false` com
    mensagem explicativa. Nunca 404 por ausência de delta — só 404 se o
    doc não existe ou não pertence ao projeto.
    """
    from app.models.base import IngestedDocument, OCGDeltaLog
    from sqlalchemy import select as _select
    import json as _json
    import re as _re

    doc = await db.get(IngestedDocument, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Delta mais recente atribuído a este doc
    delta = (await db.execute(
        _select(OCGDeltaLog)
        .where(
            OCGDeltaLog.project_id == project_id,
            OCGDeltaLog.document_id == document_id,
        )
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if delta is None:
        return {
            "document_id": str(document_id),
            "original_filename": doc.original_filename,
            "has_delta": False,
            "message": (
                "O OCG ainda não foi atualizado com base neste documento. "
                "Pode estar em fila de análise, ter sido rejeitado por conflito, "
                "ou o updater não rodou (ex: lock ocupado por outra operação)."
            ),
        }

    def _extract_pillars(snap_obj) -> dict:
        """Extrai {n: {key, score}} das chaves PILLAR_SCORES.Pn_* ou Pn."""
        if not isinstance(snap_obj, dict):
            return {}
        pillars = snap_obj.get("PILLAR_SCORES") or {}
        out = {}
        for key, val in pillars.items():
            if not isinstance(val, dict) or not isinstance(key, str):
                continue
            match = _re.match(r"P(\d+)(?:_|$)", key, flags=_re.IGNORECASE)
            if not match:
                continue
            n = int(match.group(1))
            score = val.get("score")
            if score is None:
                continue
            try:
                out[n] = {"key": key, "score": float(score)}
            except (TypeError, ValueError):
                continue
        return out

    def _extract_overall(snap_obj) -> float | None:
        if not isinstance(snap_obj, dict):
            return None
        comp = snap_obj.get("COMPOSITE_SCORE")
        if isinstance(comp, dict):
            v = comp.get("value")
            if v is None:
                v = comp.get("overall")
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
        # Fallback: overall_score top-level (legado)
        legacy = snap_obj.get("overall_score")
        if legacy is not None:
            try:
                return float(legacy)
            except (TypeError, ValueError):
                return None
        return None

    snap_after = _json.loads(delta.ocg_snapshot) if delta.ocg_snapshot else {}

    # Snapshot ANTES = delta cuja ocg_version_to == delta atual.ocg_version_from
    prev_delta = (await db.execute(
        _select(OCGDeltaLog)
        .where(
            OCGDeltaLog.project_id == project_id,
            OCGDeltaLog.ocg_version_to == delta.ocg_version_from,
        )
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    snap_before = _json.loads(prev_delta.ocg_snapshot) if prev_delta and prev_delta.ocg_snapshot else {}

    pillars_before = _extract_pillars(snap_before)
    pillars_after = _extract_pillars(snap_after)
    overall_before = _extract_overall(snap_before)
    overall_after = _extract_overall(snap_after)

    pillars_compare = []
    for n in range(1, 8):
        b = pillars_before.get(n, {})
        a = pillars_after.get(n, {})
        s_before = b.get("score")
        s_after = a.get("score")
        d = None
        if s_before is not None and s_after is not None:
            d = round(s_after - s_before, 2)
        pillars_compare.append({
            "pillar": n,
            "key": a.get("key") or b.get("key") or f"P{n}",
            "score_before": s_before,
            "score_after": s_after,
            "delta": d,
        })

    overall_delta = None
    if overall_before is not None and overall_after is not None:
        overall_delta = round(overall_after - overall_before, 2)

    return {
        "document_id": str(document_id),
        "original_filename": doc.original_filename,
        "has_delta": True,
        "version_from": delta.ocg_version_from,
        "version_to": delta.ocg_version_to,
        "trigger_source": delta.trigger_source,
        "overall_before": overall_before,
        "overall_after": overall_after,
        "overall_delta": overall_delta,
        "pillars": pillars_compare,
        "created_at": delta.created_at.isoformat() if delta.created_at else None,
    }


# ============================================================================
# M01 QUESTIONNAIRE GENERATION
# ============================================================================

class M01GenerateRequest(BaseModel):
    """Request: Gerar questionnaire dinâmico via M01"""
    document_id: UUID
    domain: str = "software"  # software, juridico, financeiro, etc
    doc_type: str = "requisitos"  # requisitos, RFP, spec, proposal, etc


class M01GenerateResponse(BaseModel):
    """Response: Questionnaire gerado por M01"""
    iteration_id: str
    count: int  # 30-50
    questions: list
    extracted_concepts: list
    gaps_identified: list


@router.post("/projects/{project_id}/m01/generate-questionnaire", response_model=M01GenerateResponse)
async def generate_m01_questionnaire(
    project_id: UUID,
    req: M01GenerateRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Gera questionnaire dinâmico (30-50 perguntas) baseado em documento de requisitos.
    
    Fluxo:
    1. Busca documento ingerido pelo ID
    2. Extrai texto completo
    3. Chama M01Service para gerar questões dinâmicas
    4. Retorna questionnaire com iteration_id único
    """
    service = IngestionService(db)
    doc_result = await service.get_document_detail(project_id, req.document_id)
    
    if not doc_result:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    
    # Extrair texto do documento (assumindo que está no campo 'extracted_text')
    document_text = doc_result.get("extracted_text") or doc_result.get("content", "")
    
    if not document_text or len(document_text.strip()) < 200:
        raise HTTPException(
            status_code=400,
            detail="Documento deve ter pelo menos 200 caracteres de texto para gerar questionnaire"
        )
    
    try:
        # Gerar questionnaire via M01
        m01_service = M01Service()
        questionnaire = m01_service.generate_questionnaire(
            document_text=document_text,
            domain=req.domain,
            doc_type=req.doc_type
        )
        
        # Converter Question objects para dicts
        questions_list = [
            {
                "id": q.id,
                "text": q.text,
                "tipo": q.tipo,
                "opcoes": q.opcoes,
                "obrigatoria": q.obrigatoria,
                "dica": q.dica
            }
            for q in questionnaire.questions
        ]
        
        return M01GenerateResponse(
            iteration_id=questionnaire.iteration_id,
            count=questionnaire.count,
            questions=questions_list,
            extracted_concepts=questionnaire.extracted_concepts,
            gaps_identified=questionnaire.gaps_identified
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar M01 questionnaire: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar questionnaire: {str(e)}")


# ─── Follow-up Questions (Legacy) ───
# MVP-XX: Pontes para os novos endpoints pipeline-questions.
# O componente FollowUpQuestionnaire.tsx chama estas rotas.
# Redirecionam a lógica para o pipeline_questions_router.


@router.get(
    "/projects/{project_id}/ingestion/{document_id}/follow-up-questions",
)
async def legacy_follow_up_questions(
    project_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_from_token),
):
    """Legacy: retorna perguntas de follow-up para um documento.

    Redireciona para o endpoint pipeline-questions filtrando pelo
    documento. Mantido para compatibilidade com FollowUpQuestionnaire.tsx.
    """
    result = await get_pipeline_questions(project_id, db, current_user)
    # Filtrar pelo document_id específico
    pending = [
        q for q in result.pending_questions
        if q.document_id == str(document_id)
    ]
    answered = [
        q for q in result.answered_questions
        if q.document_id == str(document_id)
    ]
    return {"pending_questions": pending, "answered_questions": answered, "document_id": str(document_id)}


@router.post(
    "/projects/{project_id}/ingestion/{document_id}/follow-up-answers",
)
async def legacy_follow_up_answers(
    project_id: UUID,
    document_id: UUID,
    req: AnswersRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_from_token),
):
    """Legacy: submete respostas de follow-up para um documento.

    Redireciona para o novo endpoint pipeline-questions/answers.
    Mantido para compatibilidade com FollowUpQuestionnaire.tsx.
    """
    result = await submit_pipeline_answers(project_id, req, db, current_user)
    return {"document_id": str(document_id), "stored": result.stored, "reprocessed": result.documents_reprocessed}
