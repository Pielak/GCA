"""ChunkAuditorService — Auditoria de chunks em paralelo com batch processing."""
import json
import asyncio
import time
from uuid import UUID
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.services.llm_client import LLMClient, LLMResponse
from app.services.agent_service import AgentService
from app.schemas.chunk_audit import ChunkAuditOutput, ChunkAuditResult, ChunkErrorForReview
from app.schemas.chunk import Chunk
from app.utils.retry import gca_retry

logger = structlog.get_logger(__name__)


class ChunkAuditorService:
    """Audita chunks individualmente em batches com retry + repair + quarentena."""

    AUDITOR_SYSTEM_PROMPT = """Você é o Auditor AUD do GCA.

Sua tarefa é analisar APENAS o chunk recebido.
Você não deve analisar o documento inteiro.
Você não deve inferir requisitos que não estejam no texto.
Você deve devolver SOMENTE JSON válido.
A resposta deve começar com { e terminar com }.
Não use Markdown.
Não explique fora do JSON.

JSON esperado:
{
  "documentId": "uuid",
  "chunkId": "chunk_001",
  "chunkPosition": 1,
  "status": "ok",
  "summary": "Resumo de uma frase do chunk",
  "detectedTopics": ["requisito", "risco"],
  "personas": {
    "AUD": {"relevant": true, "reason": "Sempre relevante", "briefing": "Resumo da classificação"},
    "GP": {"relevant": false, "reason": "Sem menção a escopo", "briefing": ""},
    "ARQ": {"relevant": false, "reason": "", "briefing": ""},
    "DBA": {"relevant": false, "reason": "", "briefing": ""},
    "DEV": {"relevant": false, "reason": "", "briefing": ""},
    "QA": {"relevant": false, "reason": "", "briefing": ""},
    "UX": {"relevant": false, "reason": "", "briefing": ""},
    "UI": {"relevant": false, "reason": "", "briefing": ""}
  },
  "requirementsFound": [],
  "risks": [],
  "gaps": []
}"""

    def __init__(self, db: AsyncSession, llm_client: LLMClient):
        self.db = db
        self.llm = llm_client
        self.agent_service = AgentService(db)

    async def audit_chunks(
        self,
        document_id: UUID,
        project_id: UUID,
        chunks: list[Chunk],
        batch_size: int = 20,
    ) -> tuple[list[ChunkAuditResult], list[ChunkErrorForReview]]:
        """
        Audita chunks em batches paralelos.

        Args:
            document_id: ID do documento
            project_id: ID do projeto
            chunks: Lista de chunks para auditar
            batch_size: Máximo de chunks a auditar em paralelo

        Returns:
            (successful_audits, failed_audits)
        """
        successful = []
        failed = []

        logger.info(
            "chunk_audit.batch_started",
            document_id=str(document_id),
            total_chunks=len(chunks),
            batch_size=batch_size,
        )

        start_time = time.perf_counter()

        # Processar chunks em batches
        for batch_idx in range(0, len(chunks), batch_size):
            batch = chunks[batch_idx : batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1

            logger.info(
                "chunk_audit.batch_processing",
                document_id=str(document_id),
                batch_num=batch_num,
                batch_size=len(batch),
            )

            # Auditar chunks em paralelo dentro do batch
            batch_tasks = [
                self._audit_single_chunk(
                    chunk=chunk,
                    document_id=document_id,
                    project_id=project_id,
                )
                for chunk in batch
            ]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Processar resultados do batch
            for i, result in enumerate(batch_results):
                if isinstance(result, ChunkAuditResult):
                    successful.append(result)
                elif isinstance(result, ChunkErrorForReview):
                    failed.append(result)
                elif isinstance(result, Exception):
                    # Exceção não capturada — quarentena
                    failed.append(
                        ChunkErrorForReview(
                            chunk_id=batch[i].id,
                            document_id=document_id,
                            error_type="unknown",
                            retry_count=3,
                            last_error_message=str(result),
                            recovery_attempted=True,
                        )
                    )

        elapsed_sec = time.perf_counter() - start_time

        logger.info(
            "chunk_audit.batch_completed",
            document_id=str(document_id),
            successful=len(successful),
            failed=len(failed),
            elapsed_sec=f"{elapsed_sec:.1f}",
        )

        return successful, failed

    @gca_retry()
    async def _audit_single_chunk(
        self,
        chunk: Chunk,
        document_id: UUID,
        project_id: UUID,
    ) -> ChunkAuditResult | ChunkErrorForReview:
        """Audita um chunk individual com retry automático."""

        chunk_start = time.perf_counter()

        try:
            # Construir prompt para o chunk
            # Truncar texto do chunk para caber no contexto (DeepSeek V4: 1M contexto)
            # mas manter o suficiente para análise de qualidade
            chunk_text = chunk.text[:6000] if len(chunk.text) > 6000 else chunk.text
            user_input = json.dumps(
                {
                    "documentId": str(document_id),
                    "chunkId": chunk.id,
                    "chunkPosition": chunk.position,
                    "chunkText": chunk_text,
                },
                ensure_ascii=False,
                indent=2,
            )

            logger.info(
                "chunk.audit_started",
                chunk_id=chunk.id,
                document_id=str(document_id),
                position=chunk.position,
                text_length=len(chunk.text),
            )

            # Chamar LLM
            response = await self.llm.complete(
                cacheable_system=self.AUDITOR_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4096,
                temperature=0.1,
            )

            elapsed_ms = int((time.perf_counter() - chunk_start) * 1000)

            # Validar resposta
            if not response.content or response.content.strip() == "":
                raise ValueError("LLM retornou resposta vazia")

            # Tentar parse direto
            try:
                data = json.loads(response.content)
            except json.JSONDecodeError as e:
                logger.warning(
                    "chunk.audit_json_invalid",
                    chunk_id=chunk.id,
                    error=str(e),
                    raw=response.content[:200],
                )

                # Aplicar repair
                logger.info(
                    "chunk.audit_repair_started",
                    chunk_id=chunk.id,
                )
                data = self.agent_service._extract_json(response.content)
                if not data:
                    raise ValueError(f"JSON repair falhou: {e}")

            # Validar schema
            try:
                audit_output = ChunkAuditOutput(**data)
            except ValidationError as e:
                logger.warning(
                    "chunk.audit_schema_invalid",
                    chunk_id=chunk.id,
                    error=str(e),
                )
                raise ValueError(f"Schema validation falhou: {e}")

            logger.info(
                "chunk.audit_json_valid",
                chunk_id=chunk.id,
                status=audit_output.status,
                topics=len(audit_output.detectedTopics),
            )

            return ChunkAuditResult(
                chunk_id=chunk.id,
                output=audit_output,
                extraction_time_ms=elapsed_ms,
                retry_count=0,
                repair_applied=False,
                error_code=None,
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - chunk_start) * 1000)

            logger.error(
                "chunk.audit_failed",
                chunk_id=chunk.id,
                document_id=str(document_id),
                error=str(e),
                elapsed_ms=elapsed_ms,
            )

            # Retornar erro para quarentena
            return ChunkErrorForReview(
                chunk_id=chunk.id,
                document_id=document_id,
                error_type="json_invalid" if "JSON" in str(e) else "unknown",
                retry_count=3,  # @gca_retry já tentou 3 vezes
                last_error_message=str(e)[:2000],
                recovery_attempted=True,
            )
