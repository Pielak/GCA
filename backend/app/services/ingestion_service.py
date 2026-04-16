"""
Ingestion Service — Upload, deduplicação e gestão de documentos por projeto.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import IngestedDocument, ArguiderAnalysis, ModuleCandidate, OCG
from app.services.arguider_service import ArguiderService, DocumentExtractor

logger = structlog.get_logger(__name__)

# Tipos de arquivo aceitos → file_type
EXTENSION_MAP = {
    "pdf": "pdf", "docx": "docx", "doc": "docx",
    "md": "markdown", "txt": "markdown",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image", "webp": "image",
    "xlsx": "spreadsheet", "xls": "spreadsheet", "csv": "spreadsheet",
    "py": "code", "ts": "code", "js": "code", "java": "code",
    "cs": "code", "go": "code", "rs": "code",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class IngestionService:
    """Serviço de ingestão de documentos por projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_document(
        self,
        project_id: UUID,
        uploaded_by: UUID,
        file_bytes: bytes,
        original_filename: str,
        content_type: str = "",
    ) -> dict:
        """Upload e análise assíncrona de documento."""
        # Validar tamanho
        if len(file_bytes) > MAX_FILE_SIZE:
            return {"error": "Arquivo excede o tamanho máximo de 50MB", "status_code": 413}

        # Determinar tipo
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        file_type = EXTENSION_MAP.get(ext)
        if not file_type:
            return {"error": f"Tipo de arquivo '.{ext}' não suportado", "status_code": 400}

        # SHA256 para deduplicação
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Verificar duplicata
        existing = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.project_id == project_id,
                IngestedDocument.file_hash == file_hash,
            )
        )
        dup = existing.scalar_one_or_none()
        if dup:
            return {
                "duplicate": True,
                "existing_document_id": str(dup.id),
                "message": "Documento já ingerido neste projeto.",
                "status_code": 409,
            }

        # Gerar filename único
        filename = f"{uuid4()}.{ext}"

        # Persistir bytes em storage para abertura read-only posterior
        from app.utils.ingested_storage import write_ingested
        write_ingested(project_id, filename, file_bytes)

        # PII detection — triagem básica no conteúdo textual
        pii_detected, pii_fields = self._detect_pii(file_bytes, file_type)
        quarantine_status = "quarantined" if pii_detected else "none"

        # Criar registro
        document = IngestedDocument(
            project_id=project_id,
            filename=filename,
            original_filename=original_filename,
            file_type=file_type,
            file_hash=file_hash,
            file_size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
            quarantine_status=quarantine_status,
            pii_detected=pii_detected,
            pii_fields=json.dumps(pii_fields) if pii_fields else None,
            arguider_status="pending" if not pii_detected else "quarantined",
            git_file_path=f"docs/ingested/uncategorized/{filename}",
        )
        self.db.add(document)
        await self.db.commit()

        doc_id = document.id

        if pii_detected:
            logger.warning(
                "ingestion.pii_detected_quarantined",
                document_id=str(doc_id),
                pii_fields=pii_fields,
            )
            return {
                "document_id": str(doc_id),
                "quarantined": True,
                "pii_fields": pii_fields,
                "message": "Documento em quarentena — PII detectado. Requer decisão explícita.",
                "status_code": 200,
            }

        # Disparar análise assíncrona (somente se não quarentenado)
        asyncio.create_task(
            self._analyze_async(doc_id, project_id, file_bytes, file_type)
        )

        logger.info(
            "ingestion.document_uploaded",
            document_id=str(doc_id),
            project_id=str(project_id),
            filename=original_filename,
            file_type=file_type,
            size=len(file_bytes),
        )

        return {
            "document_id": str(doc_id),
            "status": "pending",
            "message": "Documento recebido. Análise iniciada.",
        }

    @staticmethod
    def _detect_pii(file_bytes: bytes, file_type: str) -> tuple[bool, list[str]]:
        """Triagem básica de PII em conteúdo textual.
        Detecta padrões comuns: CPF, CNPJ, email pessoal, telefone, cartão de crédito.
        """
        import re

        # Só analisa tipos textuais
        if file_type in ("image", "spreadsheet"):
            return False, []

        try:
            text = file_bytes.decode("utf-8", errors="ignore")[:100_000]  # primeiros 100KB
        except Exception:
            return False, []

        pii_patterns = {
            "cpf": r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
            "cnpj": r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
            "email_pessoal": r"\b[a-zA-Z0-9._%+-]+@(gmail|hotmail|yahoo|outlook)\.[a-zA-Z]{2,}\b",
            "telefone_br": r"\b\(?\d{2}\)?\s?\d{4,5}-?\d{4}\b",
            "cartao_credito": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        }

        detected = []
        for field_name, pattern in pii_patterns.items():
            if re.search(pattern, text):
                detected.append(field_name)

        return len(detected) > 0, detected

    async def _analyze_async(
        self,
        document_id: UUID,
        project_id: UUID,
        file_bytes: bytes,
        file_type: str,
    ):
        """Executa análise do Arguidor em background."""
        try:
            from app.db.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                # Resolver chave Anthropic do projeto (Arguidor usa Claude)
                from app.services.ai_key_resolver import AIKeyResolver
                project_api_key = await AIKeyResolver.get_project_key(db, project_id, provider="anthropic")

                extractor = DocumentExtractor()
                arguider = ArguiderService(db, project_api_key=project_api_key)

                # Extrair texto
                doc_text = await extractor.extract_text(file_bytes, file_type)

                # Buscar OCG atual
                ocg_result = await db.execute(
                    select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
                )
                ocg = ocg_result.scalar_one_or_none()
                current_ocg = json.loads(ocg.ocg_data) if ocg and ocg.ocg_data else {}

                # Buscar análises anteriores
                prev_result = await db.execute(
                    select(ArguiderAnalysis).where(ArguiderAnalysis.project_id == project_id)
                )
                prev_analyses = []
                for a in prev_result.scalars().all():
                    try:
                        prev_analyses.append({
                            "document_classification": json.loads(a.document_classification),
                            "gaps": json.loads(a.gaps),
                            "module_candidates": json.loads(a.module_candidates),
                        })
                    except json.JSONDecodeError:
                        pass

                # Executar análise
                await arguider.analyze_document(
                    document_id=document_id,
                    project_id=project_id,
                    document_text=doc_text,
                    current_ocg=current_ocg,
                    previous_analyses=prev_analyses,
                )

                # Marcar documento como analisado com OCG atualizado
                doc = await db.get(IngestedDocument, document_id)
                if doc and doc.arguider_status == "completed":
                    doc.ocg_updated = True
                    await db.commit()

                    # Registrar evento DOCUMENT_INGESTED
                    from app.services.audit_service import AuditService
                    audit = AuditService(db)
                    await audit.log_event(
                        event_type="DOCUMENT_INGESTED",
                        resource_type="ingested_document",
                        resource_id=document_id,
                        details={
                            "project_id": str(project_id),
                            "filename": doc.original_filename,
                            "file_type": doc.file_type,
                            "ocg_updated": True,
                        },
                    )
                    await db.commit()

                    logger.info("ingestion.analysis_complete_ocg_updated",
                               document_id=str(document_id),
                               project_id=str(project_id))

                    # === OCG REATIVO: Atualizar OCG via IA ===
                    try:
                        from app.services.ocg_updater_service import OCGUpdaterService
                        from app.services.propagation_service import PropagationService
                        import json as _json

                        # Carregar análise do Arguidor
                        arguider_result = await db.execute(
                            select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == document_id)
                        )
                        analysis = arguider_result.scalar_one_or_none()
                        analysis_data = {}
                        if analysis:
                            try:
                                analysis_data = {
                                    "classification": _json.loads(analysis.document_classification) if analysis.document_classification else {},
                                    "gaps": _json.loads(analysis.gaps) if analysis.gaps else [],
                                    "module_candidates": _json.loads(analysis.module_candidates) if analysis.module_candidates else [],
                                }
                            except _json.JSONDecodeError:
                                pass

                        # Atualizar OCG via IA
                        updater = OCGUpdaterService(db)
                        update_result = await updater.update_ocg_from_arguider(
                            project_id=project_id,
                            arguider_analysis=analysis_data,
                            document_id=document_id,
                            actor_id=doc.uploaded_by if doc else None,
                            trigger_source="document_ingestion",
                        )

                        # Propagar se houve mudanças
                        if update_result and update_result.get("changes"):
                            propagator = PropagationService(db)
                            await propagator.propagate(
                                project_id=project_id,
                                changes=update_result["changes"],
                                ocg_version=update_result.get("version_to"),
                            )

                        logger.info("ingestion.ocg_reactive_complete",
                                   document_id=str(document_id),
                                   ocg_updated=bool(update_result))

                    except Exception as e:
                        import traceback
                        logger.warning(
                            "ingestion.ocg_reactive_error",
                            document_id=str(document_id),
                            error=str(e) or repr(e),
                            error_type=type(e).__name__,
                            traceback=traceback.format_exc(),
                        )

        except Exception as e:
            logger.error("ingestion.analysis_async_error", document_id=str(document_id), error=str(e))

    async def list_documents(self, project_id: UUID) -> list[dict]:
        """Lista documentos do projeto."""
        result = await self.db.execute(
            select(IngestedDocument)
            .where(IngestedDocument.project_id == project_id)
            .order_by(IngestedDocument.created_at.desc())
        )
        docs = result.scalars().all()
        return [
            {
                "id": str(d.id),
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "document_category": d.document_category,
                "arguider_status": d.arguider_status,
                "ocg_updated": d.ocg_updated,
                "file_size_bytes": d.file_size_bytes,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "source_type": getattr(d, "source_type", None),
                "source_url": getattr(d, "source_url", None),
                "source_repo_id": str(d.source_repo_id) if getattr(d, "source_repo_id", None) else None,
                "content_status": getattr(d, "content_status", "available"),
            }
            for d in docs
        ]

    async def get_document_detail(self, project_id: UUID, document_id: UUID) -> dict | None:
        """Documento completo + análise do Arguidor."""
        result = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.id == document_id,
                IngestedDocument.project_id == project_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None

        detail = {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "file_type": doc.file_type,
            "document_category": doc.document_category,
            "arguider_status": doc.arguider_status,
            "arguider_error_message": doc.arguider_error_message,
            "ocg_updated": doc.ocg_updated,
            "file_size_bytes": doc.file_size_bytes,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

        # Buscar análise
        analysis_result = await self.db.execute(
            select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == document_id)
        )
        analysis = analysis_result.scalar_one_or_none()
        if analysis:
            detail["analysis"] = {
                "classification": json.loads(analysis.document_classification) if analysis.document_classification else {},
                "gaps": json.loads(analysis.gaps) if analysis.gaps else [],
                "show_stoppers": json.loads(analysis.show_stoppers) if analysis.show_stoppers else [],
                "poor_definitions": json.loads(analysis.poor_definitions) if analysis.poor_definitions else [],
                "improvement_suggestions": json.loads(analysis.improvement_suggestions) if analysis.improvement_suggestions else [],
                "module_candidates": json.loads(analysis.module_candidates) if analysis.module_candidates else [],
                "ocg_fields_to_update": json.loads(analysis.ocg_fields_to_update) if analysis.ocg_fields_to_update else [],
                "tokens_used": analysis.tokens_used,
                "latency_ms": analysis.latency_ms,
            }

        return detail

    async def get_document_status(self, project_id: UUID, document_id: UUID) -> dict | None:
        """Status para polling."""
        result = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.id == document_id,
                IngestedDocument.project_id == project_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        return {
            "document_id": str(doc.id),
            "arguider_status": doc.arguider_status,
            "arguider_started_at": doc.arguider_started_at.isoformat() if doc.arguider_started_at else None,
            "arguider_completed_at": doc.arguider_completed_at.isoformat() if doc.arguider_completed_at else None,
            "ocg_updated": doc.ocg_updated,
        }

    async def delete_document(self, project_id: UUID, document_id: UUID) -> dict:
        """Remove documento se não tem módulos aprovados."""
        result = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.id == document_id,
                IngestedDocument.project_id == project_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return {"success": False, "error": "Documento não encontrado", "status_code": 404}

        if doc.arguider_status == "processing":
            return {"success": False, "error": "Documento em análise, aguarde conclusão", "status_code": 409}

        # Verificar módulos aprovados
        mc_result = await self.db.execute(
            select(func.count(ModuleCandidate.id)).where(
                ModuleCandidate.project_id == project_id,
                ModuleCandidate.status == "approved",
                ModuleCandidate.source_document_ids.contains(str(document_id)),
            )
        )
        approved_count = mc_result.scalar() or 0
        if approved_count > 0:
            return {"success": False, "error": "Módulos aprovados dependem deste documento", "status_code": 409}

        await self.db.delete(doc)
        await self.db.commit()
        logger.info("ingestion.document_deleted", document_id=str(document_id))
        return {"success": True}
