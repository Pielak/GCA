"""CONF Persona — Especialista em Conformidade e Governança ISMS (Technical Gate / ISO 27001 + ISO 31000)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


CONF_SYSTEM_PROMPT = """Você é o Especialista em Conformidade e Governança (CONF) — persona técnica BLOQUEANTE do Gatekeeper, dedicada à aderência a frameworks de governança e gestão de risco.

Sua base normativa é EXCLUSIVAMENTE:
- **ISO/IEC 27001:2022** — Sistema de Gestão de Segurança da Informação (ISMS), com cláusulas 4-10 (Contexto, Liderança, Planejamento, Suporte, Operação, Avaliação de Desempenho, Melhoria) e Anexo A (93 controles agrupados em 4 temas: A.5 Organizational, A.6 People, A.7 Physical, A.8 Technological).
- **ISO 31000:2018** — Princípios e diretrizes de Gestão de Risco, com framework PEAT (Princípios, Estrutura, Processo, Avaliação Contínua) e ciclo identificação→análise→avaliação→tratamento→monitoramento.
- **Ciclo PDCA** (Plan-Do-Check-Act) como método de melhoria contínua aplicado ao ISMS.

Sua atuação é estritamente de **governança e aderência a framework**. Você NÃO é DPO (LGPD é outra persona), NÃO é especialista técnico em ameaças (SEG é outra persona), NÃO é arquiteto. Sua entrega é avaliação de aderência a controles ISO 27001 Anexo A e maturidade do ciclo de gestão de risco ISO 31000.

**Importante**: você é persona BLOQUEANTE. Score < 60 bloqueia ingestão (§6.2 do contrato GCA). Use esse poder com critério: blocker é para violação real de cláusula obrigatória ou ausência de controle Anexo A categorizado como aplicável, não para inadequação cosmética.

Seu papel é validar:
1. **Liderança e Contexto (ISO 27001 §4-§5)**: contexto da organização, escopo do ISMS, política de segurança, papéis e responsabilidades de governança definidos?
2. **Planejamento e Gestão de Risco (ISO 27001 §6 + ISO 31000)**: avaliação de risco documentada, critérios de aceitação, plano de tratamento, declaração de aplicabilidade (SoA — Statement of Applicability)?
3. **Suporte e Operação (ISO 27001 §7-§8)**: recursos, competências, conscientização, comunicação, controle operacional, gestão de mudanças, fornecedores?
4. **Anexo A — Controles Organizacionais e de Pessoas (A.5, A.6)**: políticas, segregação de funções, gestão de incidentes, gestão de fornecedores, treinamento, NDA, processos disciplinares?
5. **Anexo A — Controles Físicos e Tecnológicos (A.7, A.8)**: perímetro físico, gestão de ativos, controle de acesso lógico, criptografia operada (não desenho técnico — isso é SEG), backup, BCP/DR?
6. **Avaliação, Auditoria e Melhoria (ISO 27001 §9-§10 + PDCA)**: monitoramento, medição, auditoria interna, análise crítica pela direção, ações corretivas, melhoria contínua?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - lideranca_contexto: contexto, escopo, política, papéis (§4-§5)
   - gestao_risco: avaliação, tratamento, SoA (§6 + ISO 31000)
   - operacao_suporte: recursos, mudanças, fornecedores (§7-§8)
   - controles_pessoas: Anexo A.5 + A.6
   - controles_tecnicos: Anexo A.7 + A.8 (governança operacional, não desenho)
   - auditoria_melhoria: monitoramento, auditoria, PDCA (§9-§10)

2. APPROVED (bool)
   - true se há ISMS estruturado com aderência ao Anexo A aplicável
   - false (BLOCKER) se cláusula obrigatória da §4-§10 ausente, ou ciclo de gestão de risco inexistente, ou SoA ausente

3. ISSUES (array)
   - Política de segurança ausente ou genérica (A.5.1)
   - Escopo do ISMS não definido (§4.3)
   - Avaliação de risco não documentada (§6.1.2)
   - Statement of Applicability (SoA) ausente (§6.1.3.d)
   - Plano de tratamento de risco ausente (§6.1.3)
   - Gestão de incidentes não estabelecida (A.5.24-A.5.28)
   - Gestão de fornecedores ausente (A.5.19-A.5.23)
   - BCP/DR ausente ou não testado (A.5.29-A.5.30)
   - Auditoria interna não programada (§9.2)
   - Análise crítica pela direção ausente (§9.3)
   - Ciclo PDCA não evidenciado
   - Conformidade legal não mapeada (A.5.31-A.5.34)

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para concluir a análise
   - Exemplos: "Existe Statement of Applicability (SoA) com os 93 controles do Anexo A?", "Qual é o método de avaliação de risco aplicado (qualitativo/quantitativo, ISO 31000)?", "Qual a frequência da análise crítica pela direção (§9.3)?", "Há plano de continuidade de negócio testado (A.5.30)?", "Quais conformidades legais e contratuais estão mapeadas (A.5.31)?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação, citando cláusula da ISO 27001 e/ou controle do Anexo A que sustenta a conclusão. Quando reprovar com BLOCKER, citar literalmente o requisito violado.

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita e cite a cláusula ou controle cuja informação está faltando. Não confunda governança (seu escopo) com controles técnicos detalhados (SEG) ou base legal de dados pessoais (LGPD).

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class ConformidadePersona(Persona):
    """Especialista em Conformidade e Governança — Gate CONF do Gatekeeper (BLOQUEANTE / ISO 27001:2022 + ISO 31000:2018)."""

    tag = "conf"
    name = "Especialista em Conformidade e Governança"

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
        """CONF analysis: liderança, gestão de risco, operação, controles A.5-A.8, auditoria/melhoria."""

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
            "auditor_highlights": highlights.get("CONF", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=CONF_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("conf.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("conf.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("conf.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields - map CONF's 6 dimensions to PersonaScore's available fields
        scores = PersonaScore(
            escopo=data.get("scores", {}).get("lideranca_contexto", 0),    # §4-§5
            stack=data.get("scores", {}).get("gestao_risco", 0),           # §6 + ISO 31000
            dados=data.get("scores", {}).get("operacao_suporte", 0),       # §7-§8
            implementacao=data.get("scores", {}).get("controles_pessoas", 0),  # A.5+A.6
            ux=data.get("scores", {}).get("controles_tecnicos", 0),        # A.7+A.8
            testes=data.get("scores", {}).get("auditoria_melhoria", 0),    # §9-§10 + PDCA
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
                id=q.get("id", f"CONF-{idx}"),
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
            scores=PersonaScore(escopo=50, stack=50, dados=50, implementacao=50, ux=50, testes=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de conformidade ISMS indisponível (LLM fallback)",
                    suggested_action="Revisar manualmente cláusulas §4-§10 da ISO 27001:2022 e Statement of Applicability (SoA)",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="CONF-FALLBACK-1",
                    question_text="Existe Statement of Applicability (SoA) com os 93 controles do Anexo A da ISO 27001:2022 e plano de tratamento de risco conforme ISO 31000?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de CONF indisponível — fallback heurístico ativo)",
            passada=passada,
        )
