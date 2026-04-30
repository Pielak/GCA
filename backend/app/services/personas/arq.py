"""ARQ Persona — Arquiteto de Projetos (Technical Gate 2)."""
import json
import time
import structlog
from typing import Optional

from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


ARQ_SYSTEM_PROMPT = """Você é o Arquiteto de Projetos (ARQ) — segunda persona técnica do Gatekeeper.

Seu papel é validar:
1. **Stack**: Tecnologias escolhidas são apropriadas para o escopo?
2. **Integração**: Qual é a superfície de integração com sistemas legados?
3. **Padrões**: Arquitetura segue padrões consolidados (MVC, DDD, event-driven, etc)?
4. **Acoplamento**: Módulos estão desacoplados? Há dependências cíclicas?
5. **Escalabilidade**: Sistema é escalável horizontal e vertical?
6. **NFRs**: Atende requisitos não-funcionais (segurança, compliance, performance)?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - stack: adequação das tecnologias ao escopo
   - integracao: clareza da superfície de integração
   - acoplamento: modularidade e independência
   - escalabilidade: capacidade de crescimento
   - nfr: cobertura de requisitos não-funcionais

2. APPROVED (bool)
   - true se a arquitetura é viável
   - false se há problema estrutural bloqueante

3. ISSUES (array)
   - Tecnologias inadequadas
   - Acoplamento alto
   - Falta de modularidade
   - Escalabilidade em dúvida
   - Compliance ou segurança não cobertos

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para proceder
   - Exemplos: "Qual SLA esperado?", "Qual taxa de crescimento prevista?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class ArchitectPersona(Persona):
    """Arquiteto de Projetos — Gate 2 do Gatekeeper."""

    tag = "arq"
    name = "Arquiteto de Projetos"

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
        """ARQ analysis: stack, integration, patterns, coupling, scalability, NFRs."""

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
            "auditor_highlights": highlights.get("ARQ", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=ARQ_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.error(f"ARQ LLM call failed: {e}")
            # Fallback
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"ARQ: JSON parse failed: {str(e)[:200]}")
            return self._fallback_output(passada=passada)

        # Extract fields - map ARQ's 5 dimensions to PersonaScore's available fields
        scores = PersonaScore(
            stack=data.get("scores", {}).get("stack", 0),        # Tecnologias apropriadas
            dados=data.get("scores", {}).get("integracao", 0),   # Integração com legado
            implementacao=data.get("scores", {}).get("acoplamento", 0),  # Modularidade
            testes=data.get("scores", {}).get("escalabilidade", 0),   # Escalabilidade
            escopo=data.get("scores", {}).get("nfr", 0),         # NFRs (compliance, segurança)
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
                id=q.get("id", f"ARQ-{idx}"),
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
            scores=PersonaScore(stack=50, dados=50, implementacao=50, testes=50, escopo=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise arquitetural indisponível (LLM fallback)",
                    suggested_action="Revisar arquitetura manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="ARQ-FALLBACK-1",
                    question_text="Qual é a arquitetura proposta (monolito, microsserviços, etc)?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de ARQ indisponível — fallback heurístico ativo)",
            passada=passada,
        )
