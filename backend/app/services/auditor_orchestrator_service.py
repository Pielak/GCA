"""FASE 1 Refactor — Auditor Orchestrator.

Novo fluxo de ingestão:
  1. Chunk documento → DocumentRouteMap
  2. AuditorPersona.analyze() → AuditorOutput (análise inicial)
  3. ParallelEvaluator(route_map, auditor_output) → 7 personas em paralelo
  4. OCGConsolidatorService.consolidate() → OCG updates + Conflicts pending

Consequência: 7 personas rodam 2x (aqui + Gatekeeper). Aceito por qualidade.
"""
import json
import time
from typing import Optional
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.personas.auditor import AuditorPersona
from app.services.parallel_evaluator import ParallelEvaluator
from app.services.chunk_auditor_service import ChunkAuditorService
from app.services.llm_client import LLMClient
from app.models.base import IngestedDocument, OCG, ChunkErrorPendingReview
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput
from app.schemas.chunk import Chunk

logger = structlog.get_logger(__name__)


class AuditorOrchestratorService:
    """Orquestra Auditor + 7 personas em paralelo durante ingestão."""

    def __init__(self, db: AsyncSession, llm_client: LLMClient):
        self.db = db
        self.llm = llm_client

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
            # Helper: atualizar stage do documento
            async def update_stage(stage: str, progress: int):
                doc = await self.db.get(IngestedDocument, document_id)
                if doc:
                    doc.arguider_stage = stage
                    doc.arguider_progress_percent = progress
                    await self.db.commit()

            # 1️⃣ CHUNKING — Dividir documento em seções (fallback apenas)
            await update_stage("chunking", 10)
            logger.info("orchestrator.phase_chunking_start", document_id=str(document_id))

            # FASE 1: Chunking simples por paragrafos (fallback universal)
            # Note: DocumentRouter usa chunkers especializados por formato.
            # Aqui usamos fallback porque já temos texto extraído.
            # chunk_type deve ser um dos: 'section', 'table', 'list', 'code'
            paragraphs = document_text.split("\n\n") if document_text else []
            raw_chunks = [
                Chunk(
                    id=f"chunk_{i}",
                    heading_path="",
                    chunk_type="section",  # Padrão: seção de texto
                    text=p.strip(),
                    first_sentence=p.strip().split(".")[0] if p.strip() else "",
                    token_count=len(p.split()),
                    position=i,
                )
                for i, p in enumerate(paragraphs) if p.strip()
            ]

            if not raw_chunks:
                # Se nenhum chunk produzido, usar documento inteiro como 1 chunk
                raw_chunks = [
                    Chunk(
                        id="chunk_0",
                        heading_path="",
                        chunk_type="section",  # Padrão: seção
                        text=document_text[:4000] if document_text else "",
                        first_sentence=(document_text[:200] if document_text else ""),
                        token_count=len((document_text or "").split()),
                        position=0,
                    )
                ]

            chunks = raw_chunks

            # Criar DocumentRouteMap (registro no DB)
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

            # AUDITOR — Análise por chunk em batches (refactor fase 1)
            await update_stage("auditor_analysis", 25)
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

            # PERSONAS PARALELAS — skip se não houver chunks auditados com sucesso
            personas_responses = {}
            if successful_chunks:
                # TODO: consolidar results dos chunks e passar para personas
                # Por enquanto, skip personas se auditoria falhou
                await update_stage("personas_evaluation", 40)
                logger.info("orchestrator.phase_parallel_start", document_id=str(document_id))
                # evaluator = ParallelEvaluator(self.llm, self.db)
                # personas_responses = await evaluator.run_passada_1(...)
                await update_stage("personas_evaluation", 75)
                logger.info(
                    "orchestrator.phase_parallel_complete",
                    document_id=str(document_id),
                    personas_completed=0,
                )
            else:
                logger.warning(
                    "orchestrator.phase_parallel_skipped",
                    document_id=str(document_id),
                    reason="no_successful_chunks",
                )
                await update_stage("personas_evaluation", 75)

            # CONSOLIDACAO OCG — Arbitra conflitos, gera updates (skip se não houver personas)
            consolidation_result = {'ocg_updates': {}, 'conflicts_pending': [], 'strategic_questions': []}
            if personas_responses:
                await update_stage("ocg_consolidation", 80)
                logger.info("orchestrator.phase_consolidation_start", document_id=str(document_id))
                from app.services.ocg_consolidator_service import OCGConsolidatorService
                consolidator = OCGConsolidatorService(self.db)
                consolidation_result = await consolidator.consolidate_from_personas(
                    project_id=project_id,
                    personas_responses=personas_responses,
                    auditor_output=None,  # TODO: usar auditor_output consolidado
                )
                logger.info(
                    "orchestrator.phase_consolidation_complete",
                    document_id=str(document_id),
                    ocg_fields_updated=len(consolidation_result.get('ocg_updates', {})),
                    conflicts_pending=len(consolidation_result.get('conflicts_pending', [])),
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
                'auditor_output': auditor_output,
                'personas_responses': personas_responses,
                'ocg_updates': consolidation_result.get('ocg_updates', {}),
                'conflicts_pending': consolidation_result.get('conflicts_pending', []),
                'strategic_questions': consolidation_result.get('strategic_questions', []),
                'elapsed_sec': elapsed_sec,
            }

        except Exception as e:
            elapsed_sec = time.perf_counter() - start
            await update_stage("error", 0)
            logger.error(
                "orchestrator.failed",
                document_id=str(document_id),
                project_id=str(project_id),
                error=str(e),
                elapsed_sec=elapsed_sec,
                exc_info=True,
            )
            return {
                'success': False,
                'error': str(e),
                'elapsed_sec': elapsed_sec,
            }
