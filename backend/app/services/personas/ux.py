"""UX Persona — UX Designer (Technical Gate 6 / Phase C)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


UX_SYSTEM_PROMPT = """Você é o UX Designer (UX) — sexta persona técnica do Gatekeeper.

Seu papel é validar:
1. **Jornada de Usuário**: Fluxos principais estão mapeados e lógicos?
2. **Acessibilidade**: WCAG AA é atendido? Navegação funcional?
3. **Usabilidade**: Interface é intuitiva para o público-alvo?
4. **Performance Perceptual**: Feedback visual é claro e imediato?
5. **Múltiplos Contextos**: Responsivo, offline, múltiplos dispositivos?
6. **Inclusão**: Suporta diferentes capacidades (visual, auditivo, motor)?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - jornada: clareza de fluxos de usuário
   - acessibilidade: conformidade WCAG AA
   - usabilidade: intuitividade da interface
   - performance: feedback visual e responsividade
   - contextos: suporte a múltiplos contextos
   - inclusao: suporte a capacidades diversas

2. APPROVED (bool)
   - true se UX é aceitável para lançamento
   - false se há problema crítico na jornada

3. ISSUES (array)
   - Fluxos não claros
   - Acessibilidade não atende WCAG AA
   - Interface não intuitiva
   - Performance perceptual ruim
   - Falta suporte responsivo/offline
   - Não inclui usuários com diferentes capacidades

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para proceder
   - Exemplos: "Qual é o público-alvo principal?", "Há restrições de rede esperadas?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class UXPersona(Persona):
    """UX Designer — Gate 6 do Gatekeeper (Phase C)."""

    tag = "ux"
    name = "UX Designer"

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client)

    async def analyze(
        self,
        chunks: list[Chunk],
        summary: str,
        highlights: dict,
        backlog: list,
        passada: int = 1,
        human_answers: Optional[dict] = None,
    ) -> PersonaOutput:
        """UX analysis: user journeys, accessibility, usability, performance, contexts, inclusion."""

        # Build payload
        chunks_payload = [
            {
                "id": c.id,
                "heading_path": c.heading_path,
                "type": c.chunk_type,
                "text": c.text[:1000],  # First 1k chars
                "tags": c.tags,
                "token_count": c.token_count,
            }
            for c in chunks
        ]

        user_input = json.dumps({
            "passada": passada,
            "summary": summary,
            "auditor_highlights": highlights.get("UX", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=UX_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("ux.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("ux.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("ux.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields
        scores = PersonaScore(
            ux=data.get("scores", {}).get("jornada", 0),
            ui=data.get("scores", {}).get("acessibilidade", 0),
            dados=data.get("scores", {}).get("usabilidade", 0),
            testes=data.get("scores", {}).get("performance", 0),
            stack=data.get("scores", {}).get("contextos", 0),
            escopo=data.get("scores", {}).get("inclusao", 0),
        )

        approved = data.get("approved", False)
        issues = [
            PersonaIssue(
                chunk_id=i.get("chunk_id", ""),
                category=i.get("category", "missing"),
                severity=i.get("severity", "warning"),
                description=i.get("description", ""),
                suggested_action=i.get("suggested_action"),
            )
            for i in data.get("issues", [])
        ]

        questions = [
            PersonaQuestion(
                id=q.get("id", f"UX-{idx}"),
                question_text=q.get("question_text", ""),
                rationale=q.get("rationale", ""),
                answer_type=q.get("answer_type", "free_text"),
                severity=q.get("severity", "important"),
                chunk_refs=q.get("chunk_refs", []),
            )
            for idx, q in enumerate(data.get("questions", []))
        ]

        return self._create_output(
            scores=scores,
            approved=approved,
            issues=issues,
            questions=questions,
            justification=data.get("justification", ""),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cached_tokens=response.usage.cached_input_tokens,
            elapsed_ms=elapsed_ms,
            passada=passada,
        )

    def _fallback_output(self, passada: int = 1) -> PersonaOutput:
        """Fallback quando LLM falha."""
        return self._create_output(
            scores=PersonaScore(ux=50, ui=50, dados=50, testes=50, stack=50, escopo=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de UX indisponível (LLM fallback)",
                    suggested_action="Revisar jornada de usuário manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="UX-FALLBACK-1",
                    question_text="Quem é o público-alvo principal?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de UX indisponível — fallback heurístico ativo)",
            passada=passada,
        )
