"""GP Persona — Gerente de Projetos (Technical Gate 1)."""
import json
import time
import structlog
from typing import Optional

from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


GP_SYSTEM_PROMPT = """Você é o Gerente de Projetos (GP) — primeira persona técnica do Gatekeeper.

Seu papel é validar:
1. **Escopo**: Requisitos funcionais estão completos e testáveis?
2. **Viabilidade**: É possível entregar com recursos e timeline planejados?
3. **Stakeholders**: Estão todos identificados? Há consenso?
4. **ROI**: O projeto agrega valor? Há riscos de negócio documentados?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - escopo: clareza e completude de requisitos
   - stack: alinhamento com capacidade da equipe
   - dados: modelo de dados faz sentido para os fluxos?
   - implementacao: timeline é realista?
   - testes: estratégia de aceite definida?

2. APPROVED (bool)
   - true se pode proceder (escopo claro, stakeholders alinhados)
   - false se há blocker de negócio

3. ISSUES (array)
   - Ambiguidades no escopo
   - Requisitos conflitantes
   - Stakeholders faltando
   - Timeline não realista
   - Riscos não documentados

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta humana para proceder
   - Exemplos: "Qual o volume de usuários simultâneos?", "Existe budget aprovado?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class GPPersona(Persona):
    """Gerente de Projetos — Gate 1 do Gatekeeper."""

    tag = "gp"
    name = "Gerente de Projetos"

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
        """GP analysis: scope, viability, stakeholders, ROI."""

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
            "auditor_highlights": highlights.get("GP", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=GP_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.error(f"GP LLM call failed: {e}")
            # Fallback
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"GP: JSON parse failed: {str(e)[:200]}")
            return self._fallback_output(passada=passada)

        # Extract fields
        scores = PersonaScore(
            escopo=data.get("scores", {}).get("escopo", 0),
            stack=data.get("scores", {}).get("stack", 0),
            dados=data.get("scores", {}).get("dados", 0),
            implementacao=data.get("scores", {}).get("implementacao", 0),
            testes=data.get("scores", {}).get("testes", 0),
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
                id=q.get("id", f"GP-{idx}"),
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
            scores=PersonaScore(escopo=50, stack=50, dados=50, implementacao=50, testes=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="GP analysis indisponível (LLM fallback)",
                    suggested_action="Revisar documento manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="GP-FALLBACK-1",
                    question_text="Qual o escopo exato do projeto?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de GP indisponível — fallback heurístico ativo)",
            passada=passada,
        )
