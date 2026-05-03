"""QA Persona — QA/Testing Lead (Technical Gate 5)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


QA_SYSTEM_PROMPT = """Você é o QA/Testing Lead (QA) — quinta persona técnica do Gatekeeper.

Seu papel é validar:
1. **Testes Unitários**: Cobertura de código suficiente (>80%)?
2. **Testes Integração**: Fluxos ponta-a-ponta testados?
3. **Testes E2E**: Cenários críticos têm testes automatizados?
4. **Regressão**: Há estratégia de detecção de regressão?
5. **Acessibilidade**: WCAG AA está coberto nos testes?
6. **Performance**: Há testes de carga/stress?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - testes: cobertura de testes
   - integracao: testes de integração
   - e2e: testes end-to-end
   - regressao: estratégia de regressão
   - acessibilidade: cobertura de WCAG AA
   - performance: testes de carga

2. APPROVED (bool)
   - true se cobertura de testes é suficiente
   - false se há gap crítico em testes

3. ISSUES (array)
   - Cobertura insuficiente
   - Falta testes de integração
   - Falta testes E2E críticos
   - Sem proteção contra regressão
   - Acessibilidade não testada
   - Sem testes de performance

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para proceder
   - Exemplos: "Qual SLA de uptime esperado?", "Qual volume de usuários simultâneos?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class QAPersona(Persona):
    """QA/Testing Lead — Gate 5 do Gatekeeper."""

    tag = "qa"
    name = "QA/Testing Lead"

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
        """QA analysis: unit tests, integration tests, E2E tests, regression, accessibility, performance."""

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
            "auditor_highlights": highlights.get("QA", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=QA_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("qa.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("qa.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("qa.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields
        scores = PersonaScore(
            testes=data.get("scores", {}).get("testes", 0),
            dados=data.get("scores", {}).get("integracao", 0),
            implementacao=data.get("scores", {}).get("e2e", 0),
            stack=data.get("scores", {}).get("regressao", 0),
            escopo=data.get("scores", {}).get("acessibilidade", 0),
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
                id=q.get("id", f"QA-{idx}"),
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
            scores=PersonaScore(testes=50, dados=50, implementacao=50, stack=50, escopo=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de testes indisponível (LLM fallback)",
                    suggested_action="Revisar estratégia de testes manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="QA-FALLBACK-1",
                    question_text="Qual é a meta de cobertura de testes?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de QA indisponível — fallback heurístico ativo)",
            passada=passada,
        )
