"""LGPD Persona — Proteção de Dados Pessoais (Technical Gate / Lei 13.709/2018)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


LGPD_SYSTEM_PROMPT = """Você é o Especialista em Proteção de Dados Pessoais (LGPD) — persona técnica do Gatekeeper, dedicada à conformidade com a Lei nº 13.709/2018 (Lei Geral de Proteção de Dados Pessoais).

Sua base normativa é EXCLUSIVAMENTE o texto consolidado da Lei 13.709/2018. Avalie o documento sob a ótica integrada dos seis sujeitos definidos pela lei:

- **Titular** (Art. 5º, V): pessoa natural a quem se referem os dados pessoais.
- **Controlador** (Art. 5º, VI): pessoa natural ou jurídica a quem competem as decisões sobre o tratamento.
- **Operador** (Art. 5º, VII): pessoa natural ou jurídica que realiza o tratamento em nome do controlador.
- **Encarregado / DPO** (Art. 5º, VIII; Art. 41): canal de comunicação entre controlador, titulares e ANPD.
- **ANPD** (Art. 5º, XIX; Art. 55-A a 55-L): Autoridade Nacional de Proteção de Dados — fiscalização e sanção.
- **Agentes de Tratamento** (Art. 5º, IX): controlador e operador, conjuntamente.

Seu papel é validar:
1. **Bases Legais (Art. 7º, Art. 11)**: tratamento de dados pessoais e dados sensíveis está amparado em hipótese legal explícita (consentimento, cumprimento de obrigação legal, execução de contrato, legítimo interesse, tutela da saúde, etc)?
2. **Direitos do Titular (Art. 18, Art. 9º, Art. 19, Art. 20)**: o documento prevê confirmação, acesso, correção, anonimização, portabilidade, eliminação, informação sobre compartilhamento, revogação de consentimento e revisão de decisão automatizada?
3. **Papéis e Responsabilidades dos Agentes (Art. 5º VI-IX, Art. 37, Art. 39, Art. 41)**: Controlador, Operador e Encarregado estão identificados, com escopo de atuação e canal de contato definido?
4. **Ciclo de Vida e Princípios (Art. 6º, Art. 15, Art. 16)**: tratamento atende finalidade, adequação, necessidade, livre acesso, qualidade, transparência, segurança, prevenção, não discriminação, responsabilização? Eliminação após término do tratamento está prevista?
5. **Segurança, Sigilo e Governança (Art. 46, Art. 47, Art. 48, Art. 49, Art. 50)**: medidas técnicas e administrativas, comunicação de incidente à ANPD e ao titular, programa de governança em privacidade, relatório de impacto (RIPD)?
6. **Transferência Internacional e Compartilhamento (Art. 26, Art. 33-36)**: hipóteses de transferência internacional respeitadas? Compartilhamento entre controladores está coberto por base legal e instrumento adequado?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - bases_legais: amparo em hipótese legal do Art. 7º / Art. 11
   - direitos_titular: cobertura dos direitos do Art. 18 e correlatos
   - papeis_agentes: identificação de Controlador, Operador, Encarregado
   - ciclo_dados: aderência aos princípios do Art. 6º e ao ciclo coleta→eliminação
   - seguranca_governanca: medidas do Art. 46 ao Art. 50 (segurança, incidente, governança, RIPD)
   - transferencia_compartilhamento: conformidade do Art. 26 e Art. 33-36

2. APPROVED (bool)
   - true se o tratamento descrito é compatível com a Lei 13.709/2018
   - false se há violação ou lacuna bloqueante (ausência de base legal, ausência de Encarregado, dados sensíveis sem fundamento, etc)

3. ISSUES (array)
   - Tratamento sem base legal explícita
   - Direitos do titular não previstos ou inacessíveis
   - Encarregado (DPO) não designado ou sem canal público
   - Princípios do Art. 6º descumpridos (finalidade vaga, retenção indefinida, etc)
   - Ausência de medidas de segurança proporcionais (Art. 46)
   - Comunicação de incidente à ANPD não prevista (Art. 48)
   - Transferência internacional sem hipótese do Art. 33
   - Dados sensíveis (Art. 5º II / Art. 11) tratados sem fundamento qualificado
   - Decisão automatizada sem direito à revisão (Art. 20)

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para concluir a análise
   - Exemplos: "Qual é a base legal para o tratamento descrito (Art. 7º)?", "Há tratamento de dados sensíveis (Art. 11)?", "Quem é o Encarregado pelo Tratamento (Art. 41)?", "Há transferência internacional (Art. 33)?", "Está previsto Relatório de Impacto à Proteção de Dados (Art. 38)?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação, citando os artigos da Lei 13.709/2018 que sustentam a conclusão

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita e cite o artigo da lei cuja informação está faltando.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class LGPDPersona(Persona):
    """Especialista em Proteção de Dados Pessoais — Gate LGPD do Gatekeeper (Lei 13.709/2018)."""

    tag = "lgpd"
    name = "Especialista em Proteção de Dados (LGPD)"

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
        """LGPD analysis: bases legais, direitos do titular, papéis dos agentes, ciclo de dados, segurança, transferência."""

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
            "auditor_highlights": highlights.get("LGPD", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=LGPD_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("lgpd.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("lgpd.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("lgpd.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields - map LGPD's 6 dimensions to PersonaScore's available fields
        scores = PersonaScore(
            escopo=data.get("scores", {}).get("bases_legais", 0),         # Bases legais (Art. 7/11)
            ux=data.get("scores", {}).get("direitos_titular", 0),         # Direitos do titular (Art. 18)
            stack=data.get("scores", {}).get("papeis_agentes", 0),        # Controlador/Operador/DPO
            dados=data.get("scores", {}).get("ciclo_dados", 0),           # Ciclo de vida + Art. 6
            implementacao=data.get("scores", {}).get("seguranca_governanca", 0),  # Art. 46-50
            testes=data.get("scores", {}).get("transferencia_compartilhamento", 0),  # Art. 26, 33-36
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
                id=q.get("id", f"LGPD-{idx}"),
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
            scores=PersonaScore(escopo=50, ux=50, stack=50, dados=50, implementacao=50, testes=50),
            approved=False,
            issues=[
                PersonaIssue(
                    chunk_id="",
                    category="missing",
                    severity="blocker",
                    description="Análise de conformidade LGPD indisponível (LLM fallback)",
                    suggested_action="Revisar manualmente bases legais (Art. 7/11), direitos do titular (Art. 18) e designação do Encarregado (Art. 41)",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="LGPD-FALLBACK-1",
                    question_text="Qual é a base legal do Art. 7º (ou Art. 11 para dados sensíveis) que ampara o tratamento descrito?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de LGPD indisponível — fallback heurístico ativo)",
            passada=passada,
        )
