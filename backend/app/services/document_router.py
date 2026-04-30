"""
DocumentRouter — orquestra Camada 0 (parser) + Camada 1 (Auditor).

Detecção automática de project_size_mode:
- solo  : 1 humano declarado no projeto
- small : 2-4 humanos
- large : 5+ humanos
"""
from pathlib import Path
from uuid import UUID
import logging
import time
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.base import IngestedDocument
from app.models.document_route_map import DocumentRouteMap
from app.models.auditor_output import AuditorOutput as AuditorOutputModel
from app.schemas.chunk import Chunk
from app.schemas.auditor_output import AuditorOutput
from app.services.chunkers.base import Chunker
from app.services.chunkers.docx_chunker import DocxChunker
from app.services.chunkers.markdown_chunker import MarkdownChunker
from app.services.chunkers.pdf_chunker import PdfChunker
from app.services.personas.auditor import AuditorPersona
from app.services.llm_client import LLMClient
class GCAError(Exception):
    """GCA error with structured fields."""
    def __init__(self, code: str, technical_message: str, user_message: str,
                 suggested_action: str, fallback_attempted: bool = False):
        self.code = code
        self.technical_message = technical_message
        self.user_message = user_message
        self.suggested_action = suggested_action
        self.fallback_attempted = fallback_attempted
        super().__init__(user_message)

logger = logging.getLogger(__name__)


CHUNKER_REGISTRY: dict[str, type[Chunker]] = {
    '.docx': DocxChunker,
    '.md':   MarkdownChunker,
    '.pdf':  PdfChunker,
}


class DocumentRouter:
    """Orquestra parsing + Auditor."""

    def __init__(self, llm_client: LLMClient, db: Session):
        self.llm = llm_client
        self.db = db

    async def route(
        self, document: IngestedDocument, user_id: UUID | None = None
    ) -> tuple[DocumentRouteMap, AuditorOutputModel]:
        """Retorna (route_map, auditor_output) ambos persistidos."""
        file_path = Path(settings.STORAGE_PATH) / document.filename
        if not file_path.exists():
            raise GCAError(
                code="DOC_001_FILE_NOT_FOUND",
                technical_message=f"Document {document.id} arquivo não encontrado em {file_path}",
                user_message="Arquivo do documento não encontrado.",
                suggested_action="Verifique se o upload foi concluído.",
            )

        # === Camada 0: parser estrutural ===
        ext = file_path.suffix.lower()
        chunker_cls = CHUNKER_REGISTRY.get(ext)
        if not chunker_cls:
            raise GCAError(
                code="DOC_002_UNSUPPORTED_FORMAT",
                technical_message=f"Extensão não suportada: {ext}",
                user_message=f"Formato {ext} não é suportado.",
                suggested_action="Use .docx, .md ou .pdf.",
            )

        t0 = time.perf_counter()
        raw_chunks = chunker_cls().chunk(str(file_path))
        chunking_ms = int((time.perf_counter() - t0) * 1000)

        if not raw_chunks:
            raise GCAError(
                code="DOC_003_EMPTY",
                technical_message="Chunker produziu 0 chunks",
                user_message="O documento parece estar vazio.",
                suggested_action="Verifique o arquivo.",
            )

        logger.info(f"Chunker: {len(raw_chunks)} chunks em {chunking_ms}ms")

        # Persistir route_map
        next_version = self._next_version(document.id)
        route_map = DocumentRouteMap(
            document_id=document.id,
            version=next_version,
            llm_provider=self.llm.provider_name,
            llm_model=self.llm.model_name,
            chunks=[
                {
                    "id": rc.id,
                    "heading_path": rc.heading_path,
                    "chunk_type": rc.chunk_type,
                    "text": rc.text,
                    "first_sentence": rc.first_sentence,
                    "token_count": rc.token_count,
                    "position": rc.position,
                    "tags": [],
                }
                for rc in raw_chunks
            ],
            total_chunks=len(raw_chunks),
            chunking_time_ms=chunking_ms,
            created_by=user_id,
        )
        self.db.add(route_map)
        self.db.commit()
        self.db.refresh(route_map)

        # === Camada 1: Auditor ===
        project_size_mode = self._detect_project_size(document.project_id)
        chunks_for_auditor = [Chunk(**c) for c in route_map.chunks]

        auditor = AuditorPersona(self.llm)
        try:
            auditor_output = await auditor.analyze(
                chunks=chunks_for_auditor,
                project_size_mode=project_size_mode,
            )
        except GCAError as e:
            logger.error(f"Auditor falhou: {e.code}; aplicando fallback")
            auditor_output = self._fallback_heuristic_output(chunks_for_auditor)

        # Atualiza route_map.chunks com tags do Auditor
        for chunk in route_map.chunks:
            chunk_id = chunk["id"]
            chunk["tags"] = auditor_output.chunk_tags.get(chunk_id, ["DEV"])

        self.db.add(route_map)

        # Persiste auditor_output
        ao_model = AuditorOutputModel(
            route_map_id=route_map.id,
            summary=auditor_output.summary,
            summary_token_count=auditor_output.summary_token_count,
            chunk_tags=auditor_output.chunk_tags,
            highlights=auditor_output.highlights,
            audit_findings=auditor_output.audit_findings,
            backlog_to_specialists=[b.model_dump() for b in auditor_output.backlog_to_specialists],
            questionnaire_to_human=[q.model_dump() for q in auditor_output.questionnaire_to_human],
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
        self.db.commit()
        self.db.refresh(ao_model)

        return route_map, ao_model

    def _next_version(self, document_id: UUID) -> int:
        last = (
            self.db.query(DocumentRouteMap)
            .filter(DocumentRouteMap.document_id == document_id)
            .order_by(DocumentRouteMap.version.desc())
            .first()
        )
        return (last.version + 1) if last else 1

    def _detect_project_size(self, project_id: UUID) -> str:
        """solo / small / large baseado em humanos declarados."""
        from app.models.project_member import ProjectMember
        members_count = (
            self.db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.is_human == True,
                ProjectMember.is_active == True,
            )
            .count()
        )
        if members_count <= 1:
            return "solo"
        elif members_count <= 4:
            return "small"
        return "large"

    def _fallback_heuristic_output(self, chunks: list[Chunk]) -> AuditorOutput:
        """Fallback quando o Auditor LLM falha."""
        keywords = {
            "GP":  ["objetivo", "escopo", "stakeholder", "roi", "timeline"],
            "ARQ": ["arquitetura", "stack", "api", "integração"],
            "DBA": ["dados", "schema", "banco", "retenção"],
            "DEV": ["implementação", "feature", "dependência"],
            "QA":  ["teste", "aceite", "cobertura"],
            "UX":  ["jornada", "fluxo", "acessibilidade"],
            "UI":  ["tela", "componente", "design"],
        }

        chunk_tags = {}
        for c in chunks:
            heading_lower = c.heading_path.lower()
            tags = [
                tag for tag, kws in keywords.items()
                if any(kw in heading_lower for kw in kws)
            ]
            chunk_tags[c.id] = tags or ["DEV"]

        return AuditorOutput(
            summary="(Auditor LLM indisponível — análise heurística)",
            summary_token_count=0,
            chunk_tags=chunk_tags,
            highlights={},
            audit_findings={"warning": "Fallback heurístico ativo"},
            backlog_to_specialists=[],
            questionnaire_to_human=[],
            project_size_mode="small",
            consolidation_applied=False,
            error_code="AUD-005-FALLBACK",
            fallback_used=True,
        )
