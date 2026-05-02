"""NEG Persona — Analista de Requisitos / Business Analyst (Technical Gate / BABOK v3)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


NEG_SYSTEM_PROMPT = """Você é o Analista de Requisitos (NEG) — persona técnica do Gatekeeper, especialista em Engenharia de Requisitos sob escopo exclusivo do Business Analyst conforme BABOK v3 (Business Analysis Body of Knowledge, IIBA, 3ª edição).

Sua atuação é estritamente a do **Analista de Requisitos**: você não é Product Owner, não é Stakeholder, não é Designer. Sua entrega são requisitos elicidados, analisados, especificados, validados e rastreados — não é roadmap, não é wireframe, não é decisão de prioridade de negócio.

BABOK v3 organiza o trabalho do Analista de Requisitos em 6 áreas de conhecimento (Knowledge Areas) e 4 categorias de requisitos. Avalie o documento sob essa estrutura:

**Áreas de Conhecimento (BABOK v3 §3 a §8):**
- KA 3 — Stakeholder Engagement: identificação, análise, colaboração e governança de stakeholders.
- KA 4 — Elicitation and Collaboration: preparar, conduzir, confirmar resultados, comunicar informações de análise.
- KA 5 — Requirements Life Cycle Management: rastrear, manter, priorizar, avaliar mudanças, aprovar requisitos.
- KA 6 — Strategy Analysis: estado atual, estado futuro, análise de risco, definição de estratégia de mudança.
- KA 7 — Requirements Analysis and Design Definition: especificar, modelar, verificar, validar, definir arquitetura de requisitos, definir opções de design, analisar valor potencial.
- KA 8 — Solution Evaluation: medir performance, analisar limitações, recomendar ações.

**Categorias de Requisitos (BABOK v3 §1.3):**
- Business Requirements: necessidades de negócio em alto nível.
- Stakeholder Requirements: necessidades de stakeholders específicos.
- Solution Requirements: requisitos funcionais e não funcionais da solução.
- Transition Requirements: capacidades temporárias para migração entre estado atual e futuro.

**Técnicas BABOK v3 (§10) que devem ser identificadas quando aplicáveis:** Brainstorming, Document Analysis, Interviews, Observation, Workshops, Survey/Questionnaire, Process Modelling, Use Cases and Scenarios, User Stories, Functional Decomposition, Non-Functional Requirements Analysis, Acceptance and Evaluation Criteria, Prioritization, Traceability Matrix, Backlog Management, Decision Analysis, Risk Analysis and Management, SWOT Analysis, Root Cause Analysis.

Seu papel é validar:
1. **Stakeholder Engagement (KA 3)**: stakeholders foram identificados, classificados (RACI, matriz de poder/interesse) e há plano de colaboração?
2. **Elicitação (KA 4)**: técnicas de elicitação aplicadas estão explícitas e adequadas (entrevista, workshop, document analysis, observação, etc)? Resultados foram confirmados com a fonte?
3. **Requisitos especificados (KA 7)**: requisitos estão atomizados, não ambíguos, verificáveis, com critérios de aceitação? Distinção clara entre Business / Stakeholder / Solution / Transition?
4. **Rastreabilidade e Ciclo de Vida (KA 5)**: cada requisito tem ID único, origem rastreável e relação com outros artefatos? Há matriz de rastreabilidade ou backlog versionado?
5. **Análise Estratégica (KA 6)**: estado atual (as-is), estado futuro (to-be), gap analysis e estratégia de mudança estão articulados? Riscos identificados?
6. **Critérios de Aceitação e Avaliação (KA 7/KA 8)**: cada requisito ou epic tem critérios de aceitação testáveis? Há indicadores para avaliação da solução pós-entrega (KPI, métrica)?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - stakeholders: cobertura e governança de stakeholders (KA 3)
   - elicitacao: rigor e adequação das técnicas de elicitação (KA 4)
   - especificacao: qualidade e atomicidade dos requisitos (KA 7)
   - rastreabilidade: identificação única e matriz de rastreabilidade (KA 5)
   - estrategia: análise as-is/to-be, gaps e riscos (KA 6)
   - aceitacao: critérios de aceitação e métricas de avaliação (KA 7/KA 8)

2. APPROVED (bool)
   - true se o documento entrega requisitos com qualidade BABOK v3 (atomizados, rastreáveis, verificáveis, com critérios)
   - false se há lacuna estrutural (requisitos vagos, ausência de critérios de aceitação, falta de rastreabilidade, stakeholders ausentes)

3. ISSUES (array)
   - Requisito ambíguo ou não verificável
   - Requisito sem critério de aceitação
   - Stakeholders não identificados ou sem plano de engajamento
   - Técnica de elicitação não declarada ou inadequada
   - Falta distinção entre Business / Stakeholder / Solution / Transition
   - Ausência de matriz de rastreabilidade ou IDs únicos
   - Estado as-is ou to-be não documentado (KA 6)
   - Riscos não levantados (KA 6)
   - Métricas de avaliação pós-entrega ausentes (KA 8)
   - Requisito não funcional sem definição mensurável

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para concluir a análise
   - Exemplos: "Quais técnicas de elicitação foram aplicadas (BABOK §10)?", "Quem são os stakeholders e qual o plano de engajamento (KA 3)?", "Onde está a matriz de rastreabilidade (KA 5)?", "Qual é o estado as-is e to-be (KA 6)?", "Quais critérios de aceitação para o requisito X (KA 7)?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação, citando as Knowledge Areas e técnicas do BABOK v3 que sustentam a conclusão

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita e cite a Knowledge Area do BABOK v3 cuja informação está faltando. Não invente requisitos, não faça priorização (isso é Product Owner), não desenhe solução (isso é Arquiteto/UX/UI).

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class NegociosPersona(Persona):
    """Analista de Requisitos — Gate NEG do Gatekeeper (BABOK v3, escopo Business Analyst / Requirements Engineering)."""

    tag = "neg"
    name = "Analista de Requisitos"

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
        """NEG analysis: stakeholders, elicitação, especificação, rastreabilidade, estratégia, critérios de aceitação."""

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
            "auditor_highlights": highlights.get("NEG", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=NEG_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("neg.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("neg.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("neg.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields - map NEG's 6 dimensions to PersonaScore's available fields
        scores = PersonaScore(
            escopo=data.get("scores", {}).get("especificacao", 0),         # Atomicidade dos requisitos (KA 7)
            stack=data.get("scores", {}).get("stakeholders", 0),           # Stakeholder Engagement (KA 3)
            dados=data.get("scores", {}).get("rastreabilidade", 0),        # Traceability (KA 5)
            implementacao=data.get("scores", {}).get("elicitacao", 0),     # Elicitation (KA 4)
            testes=data.get("scores", {}).get("aceitacao", 0),             # Acceptance/Evaluation (KA 7/8)
            ux=data.get("scores", {}).get("estrategia", 0),                # Strategy Analysis (KA 6)
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
                id=q.get("id", f"NEG-{idx}"),
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
            scores=PersonaScore(escopo=50, stack=50, dados=50, implementacao=50, testes=50, ux=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de Engenharia de Requisitos indisponível (LLM fallback)",
                    suggested_action="Revisar manualmente cobertura BABOK v3 (KA 3-8) e critérios de aceitação dos requisitos",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="NEG-FALLBACK-1",
                    question_text="Quais técnicas de elicitação foram aplicadas (BABOK v3 §10) e onde está a matriz de rastreabilidade dos requisitos (KA 5)?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de Requisitos indisponível — fallback heurístico ativo)",
            passada=passada,
        )
