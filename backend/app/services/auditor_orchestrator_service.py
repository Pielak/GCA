"""FASE 1 Refactor — Auditor Orchestrator.

Novo fluxo de ingestão:
  1. Chunk documento (chunkers especializados por formato) → DocumentRouteMap
  2. AuditorPersona.analyze() → AuditorOutput (análise inicial)
  3. ChunkAuditorService (per-chunk batch audit) → enriquecimento
  4. ParallelEvaluator(route_map, auditor_output) → 7 personas em paralelo
  5. OCGConsolidatorService.consolidate() → OCG updates + Conflicts pending

Consequência: 7 personas rodam 2x (aqui + Gatekeeper). Aceito por qualidade.
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Optional
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.personas.auditor import AuditorPersona
from app.services.parallel_evaluator import ParallelEvaluator
from app.services.chunk_auditor_service import ChunkAuditorService
from app.services.chunkers.base import Chunker
from app.services.chunkers.docx_chunker import DocxChunker
from app.services.chunkers.markdown_chunker import MarkdownChunker
from app.services.chunkers.pdf_chunker import PdfChunker
from app.services.llm_client import LLMClient
from app.models.base import IngestedDocument, OCG, ChunkErrorPendingReview
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.schemas.chunk import Chunk
from app.utils.ingested_storage import ingested_path

logger = structlog.get_logger(__name__)

CHUNKER_REGISTRY: dict[str, type[Chunker]] = {
    '.docx': DocxChunker,
    '.md':   MarkdownChunker,
    '.pdf':  PdfChunker,
}

EXT_MAP = {
    'docx': '.docx', 'md': '.md', 'pdf': '.pdf',
    'markdown': '.md',
}


class AuditorOrchestratorService:
    """Orquestra Auditor + 7 personas em paralelo durante ingestão."""

    def __init__(self, db: AsyncSession, llm_client: LLMClient):
        self.db = db
        self.llm = llm_client

    @staticmethod
    def _fallback_chunking(document_text: str) -> list:
        """Chunking por parágrafo quando arquivo não está em storage."""
        from app.services.chunkers.base import RawChunk
        paragraphs = document_text.split("\n\n") if document_text else [document_text or ""]
        result = []
        for i, p in enumerate(paragraphs):
            text = p.strip()
            if not text:
                continue
            result.append(RawChunk(
                id=f"chunk_{i}",
                heading_path="",
                chunk_type="section",
                text=text[:4000],
                first_sentence=text.split(".")[0][:200] if "." in text else text[:200],
                token_count=Chunker.estimate_tokens(text),
                position=i,
            ))
        return result

    @staticmethod
    def _fallback_auditor_output(chunks: list[Chunk]):
        """Fallback heurístico quando Auditor LLM falha."""
        from app.schemas.auditor_output import AuditorOutput as AudOut, BacklogItem, QuestionForHuman
        keywords = {
            "GP":  ["objetivo", "escopo", "stakeholder", "roi", "timeline"],
            "ARQ": ["arquitetura", "stack", "api", "integração", "endpoint"],
            "DBA": ["dados", "schema", "banco", "retenção", "lgpd"],
            "DEV": ["implementação", "feature", "dependência", "código"],
            "QA":  ["teste", "aceite", "cobertura", "qualidade"],
            "UX":  ["jornada", "fluxo", "acessibilidade", "usuário"],
            "UI":  ["tela", "componente", "design", "layout"],
        }
        chunk_tags = {}
        for c in chunks:
            heading_lower = (c.heading_path + " " + c.text[:200]).lower()
            tags = [
                tag for tag, kws in keywords.items()
                if any(kw in heading_lower for kw in kws)
            ]
            chunk_tags[c.id] = tags or ["DEV"]
        return AudOut(
            summary="(Auditor LLM indisponível — análise heurística)",
            summary_token_count=0,
            chunk_tags=chunk_tags,
            highlights={},
            audit_findings={"warning": "Fallback heurístico ativo — Auditor LLM falhou"},
            backlog_to_specialists=[],
            questionnaire_to_human=[],
            project_size_mode="small",
            consolidation_applied=False,
            error_code="AUD-005-FALLBACK",
            fallback_used=True,
        )

    async def _detect_project_size_async(self, project_id: UUID) -> str:
        """solo / small / large via AsyncSession."""
        from app.models.base import ProjectMember
        from sqlalchemy import select, func
        stmt = select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.is_active == True,
            ProjectMember.joined_at.isnot(None),
        )
        result = await self.db.execute(stmt)
        members_count = result.scalar() or 0
        if members_count <= 1:
            return "solo"
        elif members_count <= 4:
            return "small"
        return "large"

    async def orchestrate(
        self,
        document_id: UUID,
        project_id: UUID,
        document_text: str,
        file_type: str,
    ) -> dict:
        """
        Orquestra análise completa: Auditor + 7 personas + Consolidação OCG.

        Retorna:
        {
            'success': bool,
            'auditor_output': AuditorOutput,
            'personas_responses': dict[str, GatekeeperPersonaResponse],
            'ocg_updates': dict,
            'conflicts_pending': list,
            'strategic_questions': list,
            'elapsed_sec': float
        }
        """
        start = time.perf_counter()
        try:
            # Helper: atualizar stage e status do documento
            async def update_stage(stage: str, progress: int, error_msg: str = None):
                doc = await self.db.get(IngestedDocument, document_id)
                if doc:
                    doc.arguider_stage = stage
                    doc.arguider_progress_percent = progress
                    if doc.arguider_status == "pending":
                        doc.arguider_status = "processing"
                    if stage == "completed":
                        doc.arguider_status = "completed"
                    if error_msg:
                        doc.arguider_error_message = error_msg
                    await self.db.commit()

            # 1️⃣ CHUNKING — Usar chunkers especializados por formato
            await update_stage("chunking", 10)
            logger.info("orchestrator.phase_chunking_start", document_id=str(document_id))

            # Buscar doc pra descobrir filename e ext
            doc = await self.db.get(IngestedDocument, document_id)
            if not doc:
                raise ValueError(f"Documento {document_id} não encontrado")

            # Determinar extensão e caminho do arquivo
            ext = Path(doc.filename).suffix.lower() if doc.filename else ""
            if not ext and file_type:
                ext = EXT_MAP.get((file_type or "").lower(), "")
            if not ext:
                ext = ".md"  # fallback: trata como markdown

            file_path = ingested_path(project_id, doc.filename)
            if not file_path.exists():
                # Fallback: chunking por parágrafo (arquivo não está em storage)
                logger.warning(
                    "orchestrator.storage_missing_fallback",
                    document_id=str(document_id),
                    path=str(file_path),
                )
                raw_chunks = self._fallback_chunking(document_text)
            else:
                # Usar chunker especializado (executa sync em thread separado)
                chunker_cls = CHUNKER_REGISTRY.get(ext)
                if chunker_cls:
                    t0 = time.perf_counter()
                    raw_chunks = await asyncio.to_thread(
                        chunker_cls().chunk, str(file_path)
                    )
                    chunking_ms = int((time.perf_counter() - t0) * 1000)
                    logger.info(
                        "orchestrator.chunker_used",
                        ext=ext,
                        chunker=chunker_cls.__name__,
                        chunks=len(raw_chunks),
                        elapsed_ms=chunking_ms,
                    )
                else:
                    logger.warning(
                        "orchestrator.chunker_unknown_ext",
                        ext=ext,
                        file_type=file_type,
                    )
                    raw_chunks = self._fallback_chunking(document_text)

            if not raw_chunks:
                raw_chunks = self._fallback_chunking(document_text)

            # Converter RawChunks para Chunks com enriquecimento
            chunks = [
                Chunk(
                    id=rc.id,
                    heading_path=rc.heading_path,
                    chunk_type=rc.chunk_type,
                    text=rc.text,
                    first_sentence=rc.first_sentence,
                    token_count=rc.token_count,
                    position=rc.position,
                )
                for rc in raw_chunks
            ]

            # Criar DocumentRouteMap
            route_map = DocumentRouteMap(
                document_id=document_id,
                llm_provider=self.llm.provider_name,
                llm_model=self.llm.model_name,
                chunks=[
                    {
                        "id": c.id,
                        "heading_path": c.heading_path,
                        "chunk_type": c.chunk_type,
                        "text": c.text,
                        "first_sentence": c.first_sentence,
                        "token_count": c.token_count,
                        "position": c.position,
                        "tags": [],
                    }
                    for c in chunks
                ],
                total_chunks=len(chunks),
                chunking_time_ms=int((time.perf_counter() - start) * 1000),
            )
            self.db.add(route_map)
            await self.db.commit()
            logger.info(
                "orchestrator.phase_chunking_complete",
                document_id=str(document_id),
                total_chunks=len(chunks),
            )

            # 2️⃣ AUDITOR — Análise big-picture do documento (summary, chunk_tags, highlights, backlog)
            await update_stage("auditor_analysis", 20)
            logger.info("orchestrator.phase_auditor_bigpicture_start", document_id=str(document_id))

            auditor = AuditorPersona(self.llm)
            project_size_mode = await self._detect_project_size_async(project_id)
            try:
                auditor_output = await auditor.analyze(
                    chunks=chunks,
                    project_size_mode=project_size_mode,
                )
                logger.info(
                    "orchestrator.phase_auditor_bigpicture_complete",
                    document_id=str(document_id),
                    summary_tokens=auditor_output.summary_token_count,
                    tags_populated=len(auditor_output.chunk_tags),
                    highlights_personas=len(auditor_output.highlights),
                    backlog_items=len(auditor_output.backlog_to_specialists),
                    questions=len(auditor_output.questionnaire_to_human),
                    error_code=auditor_output.error_code,
                    fallback=auditor_output.fallback_used,
                )
            except Exception as e:
                logger.error(
                    "orchestrator.auditor_bigpicture_failed",
                    document_id=str(document_id),
                    error=str(e),
                )
                auditor_output = self._fallback_auditor_output(chunks)

            # Popula tags nos chunks a partir do auditor_output
            for chunk in chunks:
                chunk.tags = auditor_output.chunk_tags.get(chunk.id, ["DEV"])

            # Atualiza route_map.chunks com tags
            for chunk_dict in route_map.chunks:
                chunk_dict["tags"] = auditor_output.chunk_tags.get(chunk_dict["id"], ["DEV"])
            self.db.add(route_map)
            await self.db.commit()

            # Persistir AuditorOutput no DB para rastreabilidade
            from app.models.auditor_output import AuditorOutput as AuditorOutputModel
            ao_model = AuditorOutputModel(
                route_map_id=route_map.id,
                summary=auditor_output.summary,
                summary_token_count=auditor_output.summary_token_count,
                chunk_tags=auditor_output.chunk_tags,
                highlights=auditor_output.highlights,
                audit_findings=auditor_output.audit_findings,
                backlog_to_specialists=[
                    b.model_dump() if hasattr(b, 'model_dump') else b
                    for b in auditor_output.backlog_to_specialists
                ],
                questionnaire_to_human=[
                    q.model_dump() if hasattr(q, 'model_dump') else q
                    for q in auditor_output.questionnaire_to_human
                ],
                llm_provider=self.llm.provider_name,
                llm_model=self.llm.model_name,
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                elapsed_ms=0,
                error_code=auditor_output.error_code,
                fallback_used=auditor_output.fallback_used,
            )
            self.db.add(ao_model)
            await self.db.commit()
            await self.db.refresh(ao_model)

            # 3️⃣ CHUNK AUDITOR — Análise por chunk em batches (enriquecimento)
            await update_stage("auditor_analysis", 30)
            logger.info("orchestrator.phase_auditor_start", document_id=str(document_id))

            chunk_auditor = ChunkAuditorService(self.db, self.llm)
            successful_chunks, failed_chunks = await chunk_auditor.audit_chunks(
                document_id=document_id,
                project_id=project_id,
                chunks=chunks,
                batch_size=20,
            )

            logger.info(
                "orchestrator.phase_auditor_complete",
                document_id=str(document_id),
                successful_chunks=len(successful_chunks),
                failed_chunks=len(failed_chunks),
            )

            # Registrar chunks falhados em quarentena
            if failed_chunks:
                for failed_chunk in failed_chunks:
                    chunk_error = ChunkErrorPendingReview(
                        project_id=project_id,
                        document_id=document_id,
                        chunk_id=failed_chunk.chunk_id,
                        error_type=failed_chunk.error_type,
                        error_message=failed_chunk.last_error_message,
                        retry_count=failed_chunk.retry_count,
                        recovery_attempted=failed_chunk.recovery_attempted,
                        suggested_fallback=failed_chunk.suggested_fallback,
                        status="pending",
                    )
                    self.db.add(chunk_error)
                await self.db.commit()

            # 4️⃣ PERSONAS PARALELAS — 7 especialistas em Passada 1
            personas_responses = {}
            if successful_chunks:
                await update_stage("personas_evaluation", 40)
                logger.info("orchestrator.phase_parallel_start", document_id=str(document_id))
                try:
                    evaluator = ParallelEvaluator(self.llm, self.db)
                    personas_responses = await evaluator.run_passada_1(
                        route_map=route_map,
                        auditor_output=ao_model,
                    )
                    logger.info(
                        "orchestrator.phase_parallel_complete",
                        document_id=str(document_id),
                        personas_completed=len(personas_responses),
                        persona_tags=list(personas_responses.keys()),
                    )
                except Exception as e:
                    import traceback
                    logger.error(
                        "orchestrator.phase_parallel_failed",
                        document_id=str(document_id),
                        error=str(e),
                        traceback=traceback.format_exc(),
                    )
                    personas_responses = {}
                    await update_stage("personas_evaluation", 75,
                                      error_msg=f"Falha na avaliação das personas: {str(e)[:500]}")
                await update_stage("personas_evaluation", 75)
            else:
                logger.warning(
                    "orchestrator.phase_parallel_skipped",
                    document_id=str(document_id),
                    reason="no_successful_chunks",
                )
                # Se 0 chunks passaram e todos falharam, marcar erro
                if failed_chunks:
                    sample_errors = [f"{fc.chunk_id}: {fc.last_error_message[:100]}" for fc in failed_chunks[:3]]
                    error_summary = f"Todos os {len(failed_chunks)} chunks falharam na auditoria. Exemplos: {'; '.join(sample_errors)}"
                    await update_stage("personas_evaluation", 75, error_msg=error_summary)
                else:
                    await update_stage("personas_evaluation", 75,
                                      error_msg="Nenhum chunk produzido pelo parser. Documento pode estar vazio ou em formato não suportado.")

            # 5️⃣ CONSOLIDACAO OCG — Arbitra conflitos, gera updates
            consolidation_result = {'ocg_updates': {}, 'conflicts_pending': [], 'strategic_questions': []}
            if personas_responses:
                await update_stage("ocg_consolidation", 80)
                logger.info("orchestrator.phase_consolidation_start", document_id=str(document_id))
                try:
                    from app.services.ocg_consolidator_service import OCGConsolidatorService
                    consolidator = OCGConsolidatorService(self.db)
                    consolidation_result = await consolidator.consolidate_from_personas(
                        project_id=project_id,
                        personas_responses=personas_responses,
                        auditor_output=ao_model,
                    )
                    logger.info(
                        "orchestrator.phase_consolidation_complete",
                        document_id=str(document_id),
                        ocg_fields_updated=len(consolidation_result.get('ocg_updates', {})),
                        conflicts_pending=len(consolidation_result.get('conflicts_pending', [])),
                    )
                except Exception as e:
                    logger.error(
                        "orchestrator.phase_consolidation_failed",
                        document_id=str(document_id),
                        error=str(e),
                    )
            else:
                await update_stage("ocg_consolidation", 80)
                logger.warning(
                    "orchestrator.phase_consolidation_skipped",
                    document_id=str(document_id),
                    reason="no_personas_responses",
                )

            elapsed_sec = time.perf_counter() - start
            await update_stage("completed", 100)

            return {
                'success': True,
                'auditor_output': ao_model,
                'personas_responses': personas_responses,
                'ocg_updates': consolidation_result.get('ocg_updates', {}),
                'conflicts_pending': consolidation_result.get('conflicts_pending', []),
                'strategic_questions': consolidation_result.get('strategic_questions', []),
                'elapsed_sec': elapsed_sec,
            }

        except Exception as e:
            elapsed_sec = time.perf_counter() - start
            error_msg = f"Falha crítica na orquestração: {str(e)[:500]}"
            logger.error(
                "orchestrator.failed",
                document_id=str(document_id),
                project_id=str(project_id),
                error=str(e),
                elapsed_sec=elapsed_sec,
                exc_info=True,
            )
            # Marcar documento como erro para visibilidade imediata na UI
            try:
                doc = await self.db.get(IngestedDocument, document_id)
                if doc:
                    doc.arguider_status = "error"
                    doc.arguider_stage = "failed"
                    doc.arguider_error_message = error_msg
                    await self.db.commit()
            except Exception:
                pass
            return {
                'success': False,
                'error': str(e),
                'elapsed_sec': elapsed_sec,
            }
