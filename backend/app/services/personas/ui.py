"""UI Persona — UI Designer (Technical Gate 7 / Phase C)."""
import json
import time
import structlog
from typing import Optional

from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


UI_SYSTEM_PROMPT = """Você é o UI Designer (UI) — sétima persona técnica do Gatekeeper.

Seu papel é validar:
1. **Design System**: Existe e está bem documentado? Reutilizável?
2. **Consistência Visual**: Tipografia, cores, espaçamento são consistentes?
3. **Interações**: Feedback visual é claro? Animações fazem sentido?
4. **Contrast**: Contraste atende WCAG AAA (7:1)?
5. **Tipografia**: Legibilidade é ótima em todos os tamanhos?
6. **Components**: Componentes estão bem definidos e parametrizados?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - design_system: maturidade do design system
   - consistencia: consistência visual global
   - interacoes: clareza de feedback visual
   - contrast: conformidade WCAG AAA
   - tipografia: legibilidade e hierarquia
   - components: qualidade dos componentes

2. APPROVED (bool)
   - true se UI é consistente e bem documentada
   - false se há problema crítico visual

3. ISSUES (array)
   - Design system não documentado
   - Inconsistência visual
   - Feedback de interação não claro
   - Contraste insuficiente
   - Tipografia não otimizada
   - Componentes mal definidos

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para proceder
   - Exemplos: "Quais são as brand colors?", "Qual é a typeface principal?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class UIPersona(Persona):
    """UI Designer — Gate 7 do Gatekeeper (Phase C)."""

    tag = "ui"
    name = "UI Designer"

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
        """UI analysis: design system, consistency, interactions, contrast, typography, components."""

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
            "auditor_highlights": highlights.get("UI", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=UI_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.error(f"UI LLM call failed: {e}")
            # Fallback
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"UI: JSON parse failed: {str(e)[:200]}")
            return self._fallback_output(passada=passada)

        # Extract fields
        scores = PersonaScore(
            ui=data.get("scores", {}).get("design_system", 0),
            dados=data.get("scores", {}).get("consistencia", 0),
            testes=data.get("scores", {}).get("interacoes", 0),
            stack=data.get("scores", {}).get("contrast", 0),
            escopo=data.get("scores", {}).get("tipografia", 0),
            ux=data.get("scores", {}).get("components", 0),
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
                id=q.get("id", f"UI-{idx}"),
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
            scores=PersonaScore(ui=50, dados=50, testes=50, stack=50, escopo=50, ux=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de UI indisponível (LLM fallback)",
                    suggested_action="Revisar design system manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="UI-FALLBACK-1",
                    question_text="Qual é a brand identity (cores, tipografia, ton)?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de UI indisponível — fallback heurístico ativo)",
            passada=passada,
        )
