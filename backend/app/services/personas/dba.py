"""DBA Persona — Data Engineer (Technical Gate 3)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


DBA_SYSTEM_PROMPT = """Você é o Data Engineer (DBA) — terceira persona técnica do Gatekeeper.

Seu papel é validar:
1. **Schema**: Modelo de dados faz sentido para os fluxos?
2. **Performance**: Índices estão bem dimensionados? Há N+1 queries?
3. **Migração**: Scripts de migração são idempotentes e reversíveis?
4. **Retenção**: Política de limpeza de dados está clara?
5. **Compliance**: Conformidade com LGPD, regulamentações, backup/recovery?
6. **Escalabilidade**: Banco é escalável (sharding, replicação)?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - dados: qualidade do modelo de dados
   - performance: otimização de índices e queries
   - migracao: clareza de scripts de migração
   - compliance: conformidade com regulamentações
   - escalabilidade: capacidade de crescimento

2. APPROVED (bool)
   - true se o schema é viável
   - false se há problema crítico nos dados

3. ISSUES (array)
   - Schema inadequado para fluxos
   - Falta de índices críticos
   - Scripts de migração não reversíveis
   - Política de retenção não definida
   - Compliance ou backup não cobertos

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para proceder
   - Exemplos: "Qual SLA de RPO/RTO?", "Quais dados são PII?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class DBAPersona(Persona):
    """Data Engineer — Gate 3 do Gatekeeper."""

    tag = "dba"
    name = "Data Engineer"

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
        """DBA analysis: schema, performance, migration, retention, compliance, scalability."""

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
            "auditor_highlights": highlights.get("DBA", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=DBA_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("dba.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("dba.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("dba.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields
        scores = PersonaScore(
            dados=data.get("scores", {}).get("dados", 0),
            implementacao=data.get("scores", {}).get("performance", 0),
            stack=data.get("scores", {}).get("migracao", 0),
            testes=data.get("scores", {}).get("compliance", 0),
            escopo=data.get("scores", {}).get("escalabilidade", 0),
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
                id=q.get("id", f"DBA-{idx}"),
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
            scores=PersonaScore(dados=50, implementacao=50, stack=50, testes=50, escopo=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de dados indisponível (LLM fallback)",
                    suggested_action="Revisar modelo de dados manualmente",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="DBA-FALLBACK-1",
                    question_text="Qual é o modelo de dados esperado (SQL, NoSQL, híbrido)?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de DBA indisponível — fallback heurístico ativo)",
            passada=passada,
        )
