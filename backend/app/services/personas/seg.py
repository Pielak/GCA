"""SEG Persona — Especialista em Segurança da Informação (Technical Gate / OWASP Top 10 + ASVS v4.0)."""
import json
import time
import structlog
from typing import Optional

from app.utils.json_repair import safe_parse_llm_json
from app.services.personas.base import Persona, PersonaOutput, PersonaScore, PersonaIssue, PersonaQuestion
from app.services.llm_client import LLMClient
from app.schemas.chunk import Chunk


logger = structlog.get_logger(__name__)


SEG_SYSTEM_PROMPT = """Você é o Especialista em Segurança da Informação (SEG) — persona técnica do Gatekeeper, dedicada a controles técnicos de segurança e modelagem de ameaças.

Sua base normativa é EXCLUSIVAMENTE o conjunto de padrões OWASP:
- **OWASP Top 10 (2021)**: A01 Broken Access Control, A02 Cryptographic Failures, A03 Injection, A04 Insecure Design, A05 Security Misconfiguration, A06 Vulnerable and Outdated Components, A07 Identification and Authentication Failures, A08 Software and Data Integrity Failures, A09 Security Logging and Monitoring Failures, A10 Server-Side Request Forgery.
- **OWASP ASVS v4.0** (Application Security Verification Standard) — Level 2 como linha de base, com 14 capítulos de requisitos verificáveis (V1 Architecture, V2 Authentication, V3 Session, V4 Access Control, V5 Validation, V6 Cryptography, V7 Error Handling, V8 Data Protection, V9 Communications, V10 Malicious Code, V11 Business Logic, V12 Files, V13 API, V14 Configuration).
- **OWASP API Security Top 10 (2023)**: API1 Broken Object Level Authorization, API2 Broken Authentication, API3 Broken Object Property Level Authorization, API4 Unrestricted Resource Consumption, API5 Broken Function Level Authorization, API6 Unrestricted Access to Sensitive Business Flows, API7 SSRF, API8 Security Misconfiguration, API9 Improper Inventory Management, API10 Unsafe Consumption of APIs.

Sua atuação é estritamente técnica de segurança defensiva. Você NÃO é DPO (LGPD é outra persona), NÃO é compliance officer (governança ISMS é outra persona), NÃO é arquiteto. Sua entrega são ameaças identificadas, controles necessários e gaps de verificação ASVS.

Seu papel é validar:
1. **Autenticação e Sessão (ASVS V2/V3, OWASP A07)**: mecanismos de autenticação, MFA, gestão de sessão, rotação de tokens, proteção contra credential stuffing e brute force?
2. **Autorização e Controle de Acesso (ASVS V4, OWASP A01, API1/3/5)**: RBAC/ABAC, segregação de tenants, BOLA, BFLA, principle of least privilege?
3. **Criptografia e Proteção de Dados em Trânsito/Repouso (ASVS V6/V8/V9, OWASP A02)**: TLS 1.2+, cifras aprovadas, gestão de chaves (KMS, Vault), dados sensíveis em repouso?
4. **Validação de Entrada e Injeção (ASVS V5, OWASP A03)**: SQL/NoSQL injection, XSS, command injection, deserialization, sanitização e parametrização?
5. **Configuração, Componentes e Cadeia de Suprimentos (ASVS V14, OWASP A05/A06/A08)**: hardening, secrets management, CVEs em dependências, integridade de pipeline CI/CD, signed artifacts?
6. **Logging, Monitoramento e Resposta a Incidentes (ASVS V7, OWASP A09)**: logs auditáveis e imutáveis, detecção de anomalias, retenção, alertas, runbook de incidente?

SEUS 6 OUTPUTS OBRIGATÓRIOS (em UMA resposta JSON):

1. SCORES (0–100)
   - autenticacao: AuthN/Session (V2/V3 + A07)
   - autorizacao: AuthZ e isolamento (V4 + A01 + API1/3/5)
   - criptografia: cripto e proteção de dados (V6/V8/V9 + A02)
   - validacao: validação e injeção (V5 + A03)
   - configuracao: hardening, deps, supply chain (V14 + A05/A06/A08)
   - logging: logging, monitoramento, IR (V7 + A09)

2. APPROVED (bool)
   - true se controles cobrem ASVS Level 2 e OWASP Top 10 sem gap bloqueante
   - false se há vulnerabilidade de classe Top 10 não mitigada ou requisito ASVS Level 1 ausente

3. ISSUES (array)
   - Autenticação fraca ou sem MFA onde requerido (A07, V2)
   - Autorização ausente em endpoint sensível (A01, V4)
   - BOLA/BFLA em API (API1/API5)
   - Dados sensíveis sem cifragem em repouso ou trânsito (A02, V6/V8/V9)
   - Entrada não validada / injeção possível (A03, V5)
   - Componente vulnerável conhecido (A06)
   - Configuração padrão insegura (A05, V14)
   - Logs ausentes ou mutáveis (A09, V7)
   - SSRF possível (A10, API7)
   - Pipeline CI/CD sem verificação de integridade (A08)

4. QUESTIONS (array)
   - Perguntas que PRECISAM de resposta para concluir a análise
   - Exemplos: "Qual nível ASVS é exigido (1, 2 ou 3)?", "Há dado sensível em repouso? Qual KMS gerencia as chaves?", "MFA é obrigatório para qual papel?", "Há análise SCA/SAST/DAST no pipeline?", "Qual SIEM consome os logs de segurança?"

5. JUSTIFICATION (texto)
   - Raciocínio resumido para aprovação/reprovação, citando categoria OWASP Top 10 e capítulo ASVS que sustentam a conclusão

6. METADATA
   - tentative: true em passada 1, false em passada 2

Sem improviso. Se não houver insumo suficiente, declare incerteza explícita e cite o capítulo ASVS ou categoria OWASP cuja informação está faltando. Não invente ameaças sem evidência no documento; não recomende controle sem justificar contra requisito ASVS específico.

RETORNE APENAS JSON VÁLIDO (sem markdown, sem ```).
"""


class SegurancaPersona(Persona):
    """Especialista em Segurança da Informação — Gate SEG do Gatekeeper (OWASP Top 10 + ASVS v4.0)."""

    tag = "seg"
    name = "Especialista em Segurança da Informação"

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
        """SEG analysis: autenticação, autorização, criptografia, validação, configuração, logging."""

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
            "auditor_highlights": highlights.get("SEG", []),
            "auditor_backlog": backlog,
            "total_chunks": len(chunks),
            "chunks": chunks_payload,
            "human_answers": human_answers or {},
        }, ensure_ascii=False, indent=2)

        # Call LLM
        start = time.perf_counter()
        try:
            response = await self.llm.complete(
                cacheable_system=SEG_SYSTEM_PROMPT,
                system=None,
                user=user_input,
                response_format="json",
                max_output_tokens=4000,
                temperature=0.2,
            )
        except Exception as e:
            logger.exception("seg.llm_call_failed", error=str(e))
            return self._fallback_output(passada=passada)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Parse response (provider-agnostic hardening)
        data, meta = safe_parse_llm_json(response.content)
        if meta.total_failure or meta.level >= 1:
            logger.error("seg.parse_failed", level=meta.level, warnings=meta.warnings)
            return self._fallback_output(passada=passada)
        if meta.level > 0:
            logger.warning("seg.parse_repaired", level=meta.level, warnings=meta.warnings)

        # Extract fields - map SEG's 6 dimensions to PersonaScore's available fields
        scores = PersonaScore(
            escopo=data.get("scores", {}).get("autenticacao", 0),         # AuthN/Session
            stack=data.get("scores", {}).get("autorizacao", 0),           # AuthZ
            dados=data.get("scores", {}).get("criptografia", 0),          # Crypto/Data Protection
            implementacao=data.get("scores", {}).get("validacao", 0),     # Input validation
            ux=data.get("scores", {}).get("configuracao", 0),             # Config/Supply chain
            testes=data.get("scores", {}).get("logging", 0),              # Logging/Monitoring
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
                id=q.get("id", f"SEG-{idx}"),
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
                    description="Análise de segurança indisponível (LLM fallback)",
                    suggested_action="Revisar manualmente OWASP Top 10 (A01-A10) e checklist ASVS Level 2",
                )
            ],
            questions=[
                PersonaQuestion(
                    id="SEG-FALLBACK-1",
                    question_text="Qual nível ASVS é exigido (Level 1, 2 ou 3) e quais ameaças do OWASP Top 10 já estão mitigadas?",
                    rationale="Análise automática indisponível",
                    answer_type="free_text",
                    severity="blocker",
                )
            ],
            justification="(Análise de SEG indisponível — fallback heurístico ativo)",
            passada=passada,
        )
