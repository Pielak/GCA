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
    Criticidade (contrato §6.2): **ALTA** (análise que alimenta o OCG e dispara
    módulos candidatos e achados). Sem fallback silencioso para chave global
    do admin — se o projeto não tem chave, levanta `RuntimeError` claro.
    """

    def __init__(
        self,
        db: AsyncSession,
        project_api_key: str = None,
        provider: str = None,
        model: str = None,
    ):
        """Arguidor multi-provider (DT-032).

        Aceita:
          - `project_api_key`: chave do projeto (obrigatória).
          - `provider`: "anthropic"|"openai"|"deepseek"|"grok"|"gemini".
            Default `"anthropic"` para retrocompat com callers antigos.
          - `model`: modelo específico. Se None, usa default do provider.

        Contrato §6.4: nenhum fallback para chave global do admin.
        """
        self.db = db
        if not project_api_key:
            raise RuntimeError(
                "Arguidor não pode operar sem chave IA do projeto. "
                "GP deve configurar provedor e chave em Settings > LLM. "
                "Arguidor é tarefa de ALTA criticidade (contrato §6.2) e "
                "não aceita fallback para chave global do admin."
            )
        self.api_key = project_api_key
        self.provider = (provider or "anthropic").lower()
        # Model default por provider (match com o que `/settings/llm/validate`
        # testa em settings_router.py).
        _default_models = {
            "anthropic": "claude-haiku-4-5-20251001",
            "openai": "gpt-4o-mini",
            "deepseek": "deepseek-chat",
            "grok": "grok-2",
            "gemini": "gemini-2.0-flash",
        }
        self.model = model or _default_models.get(self.provider, "deepseek-chat")
        # Client Anthropic só quando for o provider — para o resto, httpx.
        self.client = AsyncAnthropic(api_key=project_api_key) if self.provider == "anthropic" else None
        # DocumentExtractor ainda recebe o client Anthropic por compatibilidade
        # com o pipeline de extração de texto. Quando provider é outro, passa
        # None — extração fallback usa pypdf local sem LLM.
        self.extractor = DocumentExtractor(client=self.client)

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> tuple[str, int]:
        """Chamada unificada ao LLM do projeto (DT-032).

        Replica o padrão de `agent_service._call_llm` + `ocg_updater_service`:
          - Anthropic: SDK nativo AsyncAnthropic.
          - OpenAI/DeepSeek/Grok: httpx POST em `/v1/chat/completions`
            (endpoint OpenAI-compatible).
          - Gemini: escopo futuro (requer formato próprio, fora da DT-032
            que mira o caminho já usado pelo user dogfood).

        Retorna `(text, tokens_used)`.
        """
        if self.provider == "anthropic" and self.client:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0.2,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens
            return text, tokens

        import httpx
        provider_urls = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "deepseek": "https://api.deepseek.com/chat/completions",
            "grok": "https://api.x.ai/v1/chat/completions",
        }
        url = provider_urls.get(self.provider)
        if not url:
            raise ValueError(
                f"Provider '{self.provider}' ainda não suportado pelo Arguidor. "
                f"Suportados hoje: anthropic, openai, deepseek, grok."
            )
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
        if resp.status_code not in (200, 201):
            raise ValueError(
                f"LLM API error ({resp.status_code}) no provider {self.provider}: "
                f"{resp.text[:300]}"
            )
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        return text, tokens

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

            # Chamar LLM do projeto (multi-provider, DT-032)
            start_time = datetime.now(timezone.utc)
            response_text, tokens_used = await self._call_llm(
                system_prompt=ARGUIDER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Parsear JSON
            result_json = self._extract_json(response_text)

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
                # DT-032: label reflete o modelo real usado, não mais hardcoded
                # ANTHROPIC_MODEL. Ex: "deepseek-chat", "claude-haiku-4-5-*".
                llm_model=f"{self.provider}:{self.model}",
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
