"""
Arguider Service — Agent 9: Análise de documentos ingeridos.
Classifica, identifica gaps, show-stoppers, má-definição,
sugere módulos e atualiza OCG evolutivamente.
"""
import json
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.retry import gca_retry
from uuid import uuid4, UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from anthropic import AsyncAnthropic
import structlog

from app.core.config import settings
from app.models.base import (
    IngestedDocument, ArguiderAnalysis, ModuleCandidate,
    OCG,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Document Extractor
# ============================================================================

class DocumentExtractor:
    """Extrai texto de diferentes tipos de arquivo."""

    def __init__(self, client=None):
        self.client = client

    async def extract_text(self, file_bytes: bytes, file_type: str) -> str:
        if file_type in ("markdown", "md", "txt", "code"):
            return file_bytes.decode("utf-8", errors="replace")

        if file_type == "pdf":
            return self._extract_pdf(file_bytes)

        if file_type in ("docx", "doc"):
            return self._extract_docx(file_bytes)

        if file_type in ("xlsx", "xls", "csv", "spreadsheet"):
            return self._extract_spreadsheet(file_bytes, file_type)

        if file_type in ("image", "wireframe", "png", "jpg", "jpeg", "gif", "webp"):
            return await self._extract_image_description(file_bytes)

        # Tentar como texto
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return "{arquivo binário não extraível}"

    def _extract_pdf(self, file_bytes: bytes) -> str:
        try:
            import io
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    return "\n\n".join(page.extract_text() or "" for page in pdf.pages)
            except ImportError:
                from PyPDF2 import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.warning("extractor.pdf_error", error=str(e))
            return f"[Erro ao extrair PDF: {str(e)}]"

    def _extract_docx(self, file_bytes: bytes) -> str:
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return "[python-docx não instalado — extrair DOCX não disponível]"
        except Exception as e:
            logger.warning("extractor.docx_error", error=str(e))
            return f"[Erro ao extrair DOCX: {str(e)}]"

    def _extract_spreadsheet(self, file_bytes: bytes, file_type: str) -> str:
        if file_type == "csv":
            return file_bytes.decode("utf-8", errors="replace")
        try:
            import io
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            rows = []
            for ws in wb.worksheets[:5]:
                rows.append(f"=== Aba: {ws.title} ===")
                for row in ws.iter_rows(max_row=200, values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if any(cells):
                        rows.append(" | ".join(cells))
            return "\n".join(rows)
        except ImportError:
            return "[openpyxl não instalado]"
        except Exception as e:
            return f"[Erro ao extrair planilha: {str(e)}]"

    async def _extract_image_description(self, image_bytes: bytes) -> str:
        """Usa Claude Vision para descrever imagem/wireframe."""
        try:
            import base64
            client = self.client  # Reutiliza client com chave do projeto
            b64 = base64.b64encode(image_bytes).decode("ascii")
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": b64},
                        },
                        {
                            "type": "text",
                            "text": "Descreva detalhadamente este wireframe/imagem de interface ou diagrama. "
                                    "Identifique: elementos visuais, fluxos, componentes, textos visíveis e funcionalidades implícitas.",
                        },
                    ],
                }],
            )
            return response.content[0].text
        except Exception as e:
            logger.warning("extractor.vision_error", error=str(e))
            return f"[Erro ao analisar imagem via IA: {str(e)}]"


# ============================================================================
# Arguider Service (Agent 9)
# ============================================================================

ARGUIDER_SYSTEM_PROMPT = """
Você é o Arguidor do GCA (Gestão de Codificação Assistida).
Seu papel é analisar documentos ingeridos em projetos de software e:

1. Classificar o tipo e categoria do documento
2. Identificar GAPS em relação ao OCG (Objeto Contexto Global) do projeto
3. Identificar SHOW-STOPPERS: contradições graves que impedem implementação
4. Identificar MÁ DEFINIÇÃO: ambiguidades que precisam ser esclarecidas
5. Sugerir MELHORIAS de forma objetiva e acionável
6. Identificar MÓDULOS CANDIDATOS: funcionalidades implementáveis

Para cada módulo candidato, decida se é:
- 'feature': funcionalidade completa de negócio
- 'component': componente técnico reutilizável

IMPORTANTE:
- Seja específico. Cada item com ID único (G001, SS001, PD001, IS001).
- Módulo só é ready_for_codegen=true se o documento fornece TODAS as informações.
- Ao atualizar OCG, sugira apenas campos diretamente impactados.
- Responda SOMENTE com JSON válido.
"""


class ArguiderService:
    """Agent 9: Arguidor — analisa documentos e atualiza OCG.
    CAMADA PROJETO — usa chave de IA configurada pelo GP do projeto.
    Se não configurada, tenta chave GCA como fallback temporário.
    """

    def __init__(self, db: AsyncSession, project_api_key: str = None):
        self.db = db
        # Preferência: chave do projeto (vault) > chave global (fallback)
        api_key = project_api_key or settings.ANTHROPIC_API_KEY
        self.client = AsyncAnthropic(api_key=api_key)
        self.extractor = DocumentExtractor(client=self.client)

    @gca_retry()
    async def analyze_document(
        self,
        document_id: UUID,
        project_id: UUID,
        document_text: str,
        current_ocg: dict,
        previous_analyses: list[dict] | None = None,
    ) -> dict:
        """Executa análise completa do Arguidor para um documento."""
        try:
            # Atualizar status
            doc = await self.db.execute(
                select(IngestedDocument).where(IngestedDocument.id == document_id)
            )
            document = doc.scalar_one_or_none()
            if document:
                document.arguider_status = "processing"
                document.arguider_started_at = datetime.now(timezone.utc)
                await self.db.commit()

            # Construir prompt
            user_prompt = self._build_prompt(document_text, current_ocg, previous_analyses or [])

            # Chamar Claude
            start_time = datetime.now(timezone.utc)
            response = await self.client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                temperature=0.2,
                system=ARGUIDER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            # Parsear JSON
            result_json = self._extract_json(response.content[0].text)

            # Salvar análise
            analysis = ArguiderAnalysis(
                document_id=document_id,
                project_id=project_id,
                document_classification=json.dumps(result_json.get("document_classification", {}), ensure_ascii=False),
                gaps=json.dumps(result_json.get("gaps", []), ensure_ascii=False),
                show_stoppers=json.dumps(result_json.get("show_stoppers", []), ensure_ascii=False),
                poor_definitions=json.dumps(result_json.get("poor_definitions", []), ensure_ascii=False),
                improvement_suggestions=json.dumps(result_json.get("improvement_suggestions", []), ensure_ascii=False),
                module_candidates=json.dumps(result_json.get("module_candidates", []), ensure_ascii=False),
                ocg_fields_to_update=json.dumps(result_json.get("ocg_fields_to_update", []), ensure_ascii=False),
                llm_model=settings.ANTHROPIC_MODEL,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )
            self.db.add(analysis)
            await self.db.commit()

            # Promover module_candidates
            for mc in result_json.get("module_candidates", []):
                candidate = ModuleCandidate(
                    project_id=project_id,
                    arguider_analysis_id=analysis.id,
                    name=mc.get("name", "Unnamed"),
                    description=mc.get("description", ""),
                    module_type=mc.get("module_type", "feature"),
                    priority=mc.get("priority", "medium"),
                    dependencies=json.dumps(mc.get("dependencies", []), ensure_ascii=False),
                    source_document_ids=json.dumps([str(document_id)], ensure_ascii=False),
                    pillar_impact=json.dumps(
                        {f"p{i}": f"P{i}" in mc.get("pillar_impact", []) for i in range(1, 8)},
                        ensure_ascii=False,
                    ),
                    ready_for_codegen=mc.get("ready_for_codegen", False),
                )
                self.db.add(candidate)

            # OCG é atualizado em seguida pelo OCGUpdaterService (chamado por
            # ingestion_service). Aqui só sinalizamos a intenção do Arguidor de
            # atualizar — o flag final ocg_updated reflete proposta, não persistência.
            ocg_fields = result_json.get("ocg_fields_to_update", [])
            ocg_updated = bool(ocg_fields)

            # Atualizar categoria do documento
            classification = result_json.get("document_classification", {})
            if document:
                document.document_category = classification.get("category", "other")
                document.arguider_status = "completed"
                document.arguider_completed_at = datetime.now(timezone.utc)
                document.ocg_updated = ocg_updated

            await self.db.commit()

            logger.info(
                "arguider.analysis_complete",
                document_id=str(document_id),
                category=classification.get("category"),
                gaps=len(result_json.get("gaps", [])),
                show_stoppers=len(result_json.get("show_stoppers", [])),
                modules=len(result_json.get("module_candidates", [])),
                ocg_updated=ocg_updated,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return result_json

        except Exception as e:
            logger.error("arguider.analysis_error", document_id=str(document_id), error=str(e))
            # Marcar como erro
            doc = await self.db.execute(
                select(IngestedDocument).where(IngestedDocument.id == document_id)
            )
            document = doc.scalar_one_or_none()
            if document:
                document.arguider_status = "error"
                document.arguider_error_message = str(e)[:500]
                await self.db.commit()
            raise

    def _build_prompt(self, doc_text: str, ocg: dict, prev: list) -> str:
        prev_summary = "Nenhuma análise anterior."
        if prev:
            prev_summary = "\n".join(
                f"- Doc {i+1}: {a.get('document_classification', {}).get('category', '?')} "
                f"({len(a.get('gaps', []))} gaps, {len(a.get('module_candidates', []))} módulos)"
                for i, a in enumerate(prev)
            )

        # Truncar texto muito longo
        max_chars = 15000
        if len(doc_text) > max_chars:
            doc_text = doc_text[:max_chars] + f"\n\n[... documento truncado, {len(doc_text)} chars total]"

        return f"""=== DOCUMENTO A ANALISAR ===
{doc_text}

=== OCG ATUAL DO PROJETO ===
{json.dumps(ocg, ensure_ascii=False, indent=2)[:5000]}

=== ANÁLISES ANTERIORES (RESUMO) ===
{prev_summary}

=== INSTRUÇÕES ===
Analise o documento acima em relação ao OCG do projeto.
Retorne SOMENTE JSON válido com as chaves: document_classification, gaps, show_stoppers,
poor_definitions, improvement_suggestions, module_candidates, ocg_fields_to_update."""

    @staticmethod
    def _extract_json(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("arguider.json_parse_failed", text_preview=text[:200])
        return {}
