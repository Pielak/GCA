"""
Persona: Auditor Documental Sênior — 8ª persona do GCA.

Diferente das 7 personas técnicas:
- Recebe documento completo (não chunks filtrados)
- Produz 6 outputs em vez de 1 OCG-parcial
- Sem par humano (auditoria é trabalho interno do GCA)
- Roda 1 vez por análise (sem Passada 2)
"""
import json
import time
from typing import Optional
from uuid import UUID
import structlog

from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk, TECHNICAL_TAGS
from app.schemas.auditor_output import (
    AuditorOutput, BacklogItem, QuestionForHuman,
)


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

logger = structlog.get_logger(__name__)


# Prompt do Auditor (cacheado pelo provider — ~2.500 tokens estáveis)
AUDITOR_SYSTEM_PROMPT = """Você é o Auditor Documental Sênior do sistema GCA.

Você é a 8ª persona do GCA, com role distinto das 7 personas técnicas:
- Você lê o documento completo (não recortes)
- Você orienta a equipe técnica antes da análise começar
- Você tem permissão EXPLÍCITA de declarar incerteza
- Você NÃO improvisa quando faltam insumos

═══════════════════════════════════════════════════════════════
SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON)
═══════════════════════════════════════════════════════════════

1. SUMMARY (≤ 500 tokens)
   Visão executiva: objetivo, domínio, módulos principais, tipo de entrega.

2. CHUNK_TAGS (multi-label)
   Para cada chunk_id recebido, atribua tags de quais especialistas devem revisar.
   Personas técnicas: GP, ARQ, DBA, DEV, QA, UX, UI

3. HIGHLIGHTS (atenção dirigida por persona)
   Para cada uma das 7 personas técnicas, liste 1-3 pontos críticos.

4. AUDIT_FINDINGS (seu OCG-parcial — auditoria documental)
   Avalie: completude, consistência interna, clareza, estrutura, qualidade.

5. BACKLOG_TO_SPECIALISTS
   Incertezas resolvíveis por LLM. Limite absoluto: 10 itens.

6. QUESTIONNAIRE_TO_HUMAN
   Perguntas para validadores humanos (precisa info não no documento).

═══════════════════════════════════════════════════════════════
MODO SOLO
═══════════════════════════════════════════════════════════════

Se project_size_mode = "solo":
- O GP responderá TUDO. Aplique consolidação semântica AGRESSIVA.
- Limite questionnaire_to_human a 5 itens.
- target_human_role = "gerente_projetos" para TODAS.

Se project_size_mode = "small": limite questionnaire = 8.
Se project_size_mode = "large": limite questionnaire = 10.

═══════════════════════════════════════════════════════════════
RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```)
═══════════════════════════════════════════════════════════════
"""


class AuditorPersona:
    """8ª persona — Auditor Documental Sênior."""

    tag = "AUD"
    name = "Auditor Documental"

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        chunks: list[Chunk],
        project_size_mode: str,
    ) -> AuditorOutput:
        """Executa análise do Auditor com tratamento de erros estruturado."""

        chunks_payload = [
            {
                "id": c.id,
                "heading_path": c.heading_path,
                "type": c.chunk_type,
                "text": c.text[:2000],
                "token_count": c.token_count,
            }
            for c in chunks
        ]

        user_input = json.dumps({
            "project_size_mode": project_size_mode,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
        }, ensure_ascii=False, indent=2)

        start = time.perf_counter()

        try:
            response = await self.llm.complete(
                cacheable_system=AUDITOR_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=6000,
                temperature=0.1,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            raise GCAError(
                code="AUD_001_TIMEOUT",
                technical_message=f"LLM call failed after {elapsed_ms}ms: {e}",
                user_message="A análise demorou mais que o esperado.",
                suggested_action="Tente novamente em alguns minutos.",
                fallback_attempted=False,
            ) from e

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse JSON
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error("Auditor: JSON inválido", extra={"raw": response.content[:500]})
            raise GCAError(
                code="AUD_002_JSON_MALFORMED",
                technical_message=f"JSON parse failed: {e}",
                user_message="O Auditor não conseguiu organizar a resposta.",
                suggested_action="Tentando novamente automaticamente.",
                fallback_attempted=False,
            ) from e

        # Aplica limites do modo solo
        max_questions = {"solo": 5, "small": 8, "large": 10}.get(project_size_mode, 8)
        questionnaire = data.get("questionnaire_to_human", [])[:max_questions]
        backlog_max = 10
        backlog = data.get("backlog_to_specialists", [])[:backlog_max]

        try:
            output = AuditorOutput(
                summary=data.get("summary", ""),
                summary_token_count=int(len(data.get("summary", "").split()) * 1.4),
                chunk_tags=data.get("chunk_tags", {}),
                highlights=data.get("highlights", {}),
                audit_findings=data.get("audit_findings", {}),
                backlog_to_specialists=[BacklogItem(**b) for b in backlog],
                questionnaire_to_human=[QuestionForHuman(**q) for q in questionnaire],
                project_size_mode=project_size_mode,
                consolidation_applied=(project_size_mode == "solo"),
                error_code=None,
                fallback_used=False,
            )
        except Exception as e:
            raise GCAError(
                code="AUD_002_JSON_MALFORMED",
                technical_message=f"Auditor output validation failed: {e}",
                user_message="O Auditor produziu resposta com formato inesperado.",
                suggested_action="Análise prosseguirá com Auditor degradado.",
                fallback_attempted=True,
            ) from e

        if len(chunks) > 30 and not output.backlog_to_specialists and not output.questionnaire_to_human:
            logger.warning("Auditor: backlog e questionário vazios em documento grande")

        if len(output.questionnaire_to_human) >= max_questions:
            logger.warning(f"Auditor: questionário atingiu limite ({max_questions})")

        logger.info(
            "Auditor concluído",
            extra={
                "elapsed_ms": elapsed_ms,
                "chunks": len(chunks),
                "backlog_items": len(output.backlog_to_specialists),
                "questions": len(output.questionnaire_to_human),
                "input_tokens": response.usage.input_tokens,
                "cached_tokens": response.usage.cached_input_tokens,
                "mode": project_size_mode,
            },
        )

        return output
