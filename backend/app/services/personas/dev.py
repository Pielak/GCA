"""DEV Persona — Developer Senior (Technical Gate 4)."""
import json
import time
import structlog
from typing import Optional

from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


DEV_SYSTEM_PROMPT = """Você é o Developer Senior (DEV) — quarta persona técnica do Gatekeeper.

Seu papel é validar:
1. **Viabilidade**: Requisitos são implementáveis com recursos disponíveis?
2. **Dependências**: Há dependências externas bloqueantes ou arriscadas?
3. **Timeline**: Estimativa de tempo é realista para o escopo?
4. **Debt Técnico**: Há riscos de débito técnico acumulado?
5. **Testing**: Estratégia de testes é clara e suficiente?
6. **DevOps**: CI/CD, deploy, rollback bem definidos?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - implementacao: viabilidade técnica
   - dependencias: clareza e risco de dependências
   - timeline: realismo da estimativa
   - debt: risco de débito técnico
   - devops: maturidade de CI/CD/deploy

2. APPROVED (bool)
   - true se implementação é viável
   - false se há risco crítico

3. ISSUES (array)
   - Requisitos não implementáveis
   - Dependências arriscadas
   - Timeline não realista
   - Risco de débito técnico
   - DevOps imaturo

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para proceder
   - Exemplos: "Qual plataforma de deploy?", "Qual SLA de uptime?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class DevPersona(Persona):
    """Developer Senior — Gate 4 do Gatekeeper."""

    tag = "dev"
    name = "Developer Senior"

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
        """DEV analysis: viability, dependencies, timeline, tech debt, testing, DevOps."""

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
            "auditor_highlights": highlights.get("DEV", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=DEV_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.error(f"DEV LLM call failed: {e}")
            # Fallback
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"DEV: JSON parse failed: {str(e)[:200]}")
            return self._fallback_output(passada=passada)

        # Extract fields
        scores = PersonaScore(
            implementacao=data.get("scores", {}).get("implementacao", 0),
            stack=data.get("scores", {}).get("dependencias", 0),
            escopo=data.get("scores", {}).get("timeline", 0),
            dados=data.get("scores", {}).get("debt", 0),
            testes=data.get("scores", {}).get("devops", 0),
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
                id=q.get("id", f"DEV-{idx}"),
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
            scores=PersonaScore(implementacao=50, stack=50, escopo=50, dados=50, testes=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de viabilidade indisponível (LLM fallback)",
                    suggested_action="Revisar viabilidade manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="DEV-FALLBACK-1",
                    question_text="Quais são as dependências externas críticas?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de DEV indisponível — fallback heurístico ativo)",
            passada=passada,
        )
