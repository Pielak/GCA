"""
PersonaValidator — Análise de respostas do questionário por Personas

Cada Persona (GP, Arquiteto, DBA, Dev Sr, QA) valida respostas do M01.
Saída: aprovação OU novas questões de clarificação.
"""

from typing import List, Dict, Optional, TypeVar, Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from anthropic import Anthropic
import json
import structlog
from uuid import UUID

logger = structlog.get_logger(__name__)

# ============================================================================
# SCHEMAS
# ============================================================================

@dataclass
class ValidationResult:
    """Resultado da validação de uma Persona"""
    persona: str  # "gp" | "arquiteto" | "dba" | "dev_sr" | "qa"
    status: str  # "approved" | "needs_clarification"
    decision: str  # Explicação breve da decisão
    ocg_delta: Dict = field(default_factory=dict)  # Seção do OCG a agregar (se approved)
    followup_questions: Optional[List[Dict]] = None  # Novas questões (se needs_clarification)
    severity: str = "info"  # "info" | "warning" | "critical"


@dataclass
class ConsolidatedValidation:
    """Consolidação de validações de todas as 5 Personas"""
    all_approved: bool
    results: List[ValidationResult]
    ready_for_ocg_aggregation: bool  # True se 5/5 aprovaram
    next_action: str  # "aggregate_to_ocg" | "generate_followup_questionnaire" | "manual_review"


# ============================================================================
# PERSONA VALIDATORS (5 CONCRETAS)
# ============================================================================

async def get_ia_client_for_project(project_id: UUID, db: Any) -> tuple[str, str, Any]:
    """Fetch IA provider configuration from ProjectSettings and return (provider, model, client).

    Returns:
        Tuple of (provider_name, model_name, client_instance)
        - provider_name: "anthropic" | "deepseek" | "openai" | "gemini"
        - model_name: e.g. "claude-sonnet-4-6", "deepseek-chat", "gpt-4"
        - client_instance: initialized client for the provider
    """
    from app.models.base import ProjectSettings

    # Fetch project settings (LLM configuration)
    stmt = "SELECT settings_json FROM project_settings WHERE project_id = :pid AND setting_type = 'llm' LIMIT 1"
    result = await db.execute(f"SELECT settings_json FROM project_settings WHERE project_id = '{project_id}' AND setting_type = 'llm' LIMIT 1")
    row = result.scalar_one_or_none() if hasattr(result, 'scalar_one_or_none') else None

    # Default to Anthropic if not configured
    if not row:
        return "anthropic", "claude-sonnet-4-6-20250514", Anthropic()

    settings = json.loads(row) if isinstance(row, str) else row
    provider = settings.get("provider", "anthropic").lower()
    model = settings.get("model", "claude-sonnet-4-6-20250514")

    if provider == "deepseek":
        # Initialize DeepSeek client
        import requests
        from requests.adapters import HTTPAdapter
        api_key = settings.get("api_key", "")
        # DeepSeek uses OpenAI-compatible API
        deepseek_client = requests.Session()
        deepseek_client.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
        return provider, model, deepseek_client
    elif provider == "openai":
        # Initialize OpenAI client
        from openai import OpenAI as OpenAIClient
        api_key = settings.get("api_key", "")
        openai_client = OpenAIClient(api_key=api_key)
        return provider, model, openai_client
    elif provider == "gemini":
        # Initialize Gemini client
        import google.generativeai as genai
        api_key = settings.get("api_key", "")
        genai.configure(api_key=api_key)
        return provider, model, genai
    else:
        # Default to Anthropic
        return "anthropic", model, Anthropic()


class PersonaValidator(ABC):
    """Abstract base class para todas as Personas com suporte a múltiplos providers IA"""

    def __init__(self, anthropic_client: Anthropic = None, project_id: UUID = None, provider: str = None, model: str = None):
        self.client = anthropic_client or Anthropic()
        self.model = model or "claude-sonnet-4-6-20250514"
        self.provider = provider or "anthropic"
        self.project_id = project_id

    @abstractmethod
    def get_persona_name(self) -> str:
        """Retorna nome da Persona"""
        pass

    @abstractmethod
    def get_validation_prompt(self) -> str:
        """Retorna prompt de validação específico da Persona"""
        pass

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM based on provider type. Retorna text response."""
        if self.provider == "anthropic":
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            return message.content[0].text
        elif self.provider == "deepseek":
            # DeepSeek uses OpenAI-compatible API
            import json as stdlib_json
            response = self.client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                timeout=30
            )
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            # Default to Anthropic
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            return message.content[0].text

    def validate(
        self,
        responses: Dict[str, str],
        extracted_concepts: List[str],
        document_domain: str = "software"
    ) -> ValidationResult:
        """
        Valida respostas do questionário

        Args:
            responses: Dicionário de {question_id: resposta_texto}
            extracted_concepts: Conceitos extraídos do documento original
            document_domain: Domínio (software, juridico, financeiro, etc)

        Returns:
            ValidationResult com status, delta, e opcionais followup_questions
        """
        persona_name = self.get_persona_name()
        validation_prompt = self.get_validation_prompt()

        # Montar prompt de validação
        responses_text = "\n".join([f"- {q}: {r}" for q, r in responses.items()])

        user_prompt = f"""
Você é a Persona {persona_name} no sistema GCA (Gestão de Codificação Assistida).

DOMÍNIO DO PROJETO: {document_domain}
CONCEITOS EXTRAÍDOS: {', '.join(extracted_concepts)}

RESPOSTAS DO USUÁRIO PARA O QUESTIONÁRIO M01:
{responses_text}

{validation_prompt}

RESPOSTA (JSON):
"""

        system_prompt = f"""Você é a Persona {persona_name} validando respostas de questionário.

Sua responsabilidade é validar se as respostas são CLARAS e SUFICIENTES para o OCG.

Retorne JSON com:
{{
  "status": "approved" | "needs_clarification",
  "decision": "explicação breve (1-2 frases)",
  "ocg_delta": {{"secao": "conteúdo"}}, // Se approved, seção OCG a agregar
  "followup_questions": [ // Se needs_clarification
    {{
      "id": "M01_F1",
      "text": "pergunta de clarificação",
      "tipo": "aberta|escolha|multipla",
      "opcoes": null | ["opção1", ...],
      "dica": null | "dica"
    }}
  ],
  "severity": "info" | "warning" | "critical"
}}
"""

        try:
            if self.provider == "anthropic":
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                response_text = message.content[0].text
            elif self.provider == "deepseek":
                # DeepSeek uses requests session
                response = self.client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2048
                    },
                    timeout=30
                )
                result = response.json()
                response_text = result["choices"][0]["message"]["content"]
            else:
                # Fallback to Anthropic
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                response_text = message.content[0].text
        except Exception as exc:
            logger.error(
                "persona_validator.llm_call_failed",
                persona=persona_name,
                provider=self.provider,
                error=str(exc)
            )
            return ValidationResult(
                persona=persona_name,
                status="needs_clarification",
                decision="Erro ao chamar IA — peça clarificação",
                severity="critical"
            )

        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(
                "persona_validator.json_parse_failed",
                persona=persona_name,
                response=response_text[:200]
            )
            return ValidationResult(
                persona=persona_name,
                status="needs_clarification",
                decision="Erro ao processar respostas — peça clarificação",
                severity="critical"
            )

        return ValidationResult(
            persona=persona_name,
            status=parsed.get("status", "needs_clarification"),
            decision=parsed.get("decision", ""),
            ocg_delta=parsed.get("ocg_delta", {}),
            followup_questions=parsed.get("followup_questions"),
            severity=parsed.get("severity", "info")
        )


class GPValidator(PersonaValidator):
    """Persona: Gerente de Projetos — valida viabilidade e escopo"""

    def get_persona_name(self) -> str:
        return "GP (Gerente de Projetos)"

    def get_validation_prompt(self) -> str:
        return """
Como GP, você valida se:
1. ESCOPO está claro (objetivo, requisitos, limites)
2. VIABILIDADE de negócio é aparente (ROI, timeline, recursos)
3. STAKEHOLDERS estão identificados
4. RISCOS de negócio foram considerados

Se QUALQUER um destes está vago/ambíguo → precisa clarificação.

Se tudo está OK → agregue ao OCG na seção "Escopo & Viabilidade".
"""


class ArquitetoValidator(PersonaValidator):
    """Persona: Arquiteto — valida stack e decisões arquiteturais"""

    def get_persona_name(self) -> str:
        return "Arquiteto de Soluções"

    def get_validation_prompt(self) -> str:
        return """
Como Arquiteto, você valida se:
1. STACK está escolhido (linguagem, framework, DB, cache, queue)
2. PADRÕES arquiteturais estão definidos (monolito? microserviços? serverless?)
3. INTEGRAÇÕES externas estão claras
4. NFRs (performance, escalabilidade, disponibilidade) são mensuráveis

Se QUALQUER um está vago → precisa mais detalhe.

Se tudo OK → agregue ao OCG em "Arquitetura & Stack".
"""


class DBAValidator(PersonaValidator):
    """Persona: DBA — valida schema, migrations, retenção, performance"""

    def get_persona_name(self) -> str:
        return "DBA (Especialista em Dados)"

    def get_validation_prompt(self) -> str:
        return """
Como DBA, você valida se:
1. DATABASE tipo está escolhido (SQL, NoSQL, vector, graph, etc)
2. SCHEMA é esboçado (tables, relacionamentos principais)
3. RETENÇÃO de dados está definida (quanto tempo guarda? backup?)
4. PERFORMANCE esperada é realista (índices, query patterns)
5. COMPLIANCE de dados (LGPD, GDPR, auditoria) foi considerado

Se QUALQUER um está vago → precisa clarificação.

Se tudo OK → agregue ao OCG em "Dados & Persistência".
"""


class DevSrValidator(PersonaValidator):
    """Persona: Dev Senior — valida implementabilidade"""

    def get_persona_name(self) -> str:
        return "Dev Senior"

    def get_validation_prompt(self) -> str:
        return """
Como Dev Sr, você valida se:
1. FEATURES são implementáveis no timeline indicado
2. DEPENDÊNCIAS técnicas (libs, services externos) não são bloqueadores
3. DÍVIDA TÉCNICA não é proibitiva
4. EQUIPE tem skills suficientes (ou treinar é viável)

Se QUALQUER coisa é "impossível em 6 meses" → precisa escopar menos.

Se tudo realista → agregue ao OCG em "Implementação & Timeline".
"""


class QAValidator(PersonaValidator):
    """Persona: QA/Tester — valida testabilidade e critérios de aceite"""

    def get_persona_name(self) -> str:
        return "QA (Qualidade)"

    def get_validation_prompt(self) -> str:
        return """
Como QA, você valida se:
1. TESTES são viáveis (unit, integration, E2E definidos?)
2. COBERTURA esperada é realista (meta %)
3. CRITÉRIOS DE ACEITE são claros (não ambíguos)
4. REGRESSÃO é rastreável (CI/CD, baseline)

Se QUALQUER um está vago → precisa mais específico.

Se tudo OK → agregue ao OCG em "Qualidade & Testes".
"""


# ============================================================================
# CONSOLIDATED VALIDATOR
# ============================================================================

class PersonasConsolidator:
    """Consolida validações de todas as Personas (5 base + 2 adicionais para MVP B)"""

    def __init__(self, project_id: UUID = None, provider: str = None, model: str = None):
        self.project_id = project_id
        self.provider = provider or "anthropic"
        self.model = model
        self.personas = [
            GPValidator(project_id=project_id, provider=provider, model=model),
            ArquitetoValidator(project_id=project_id, provider=provider, model=model),
            DBAValidator(project_id=project_id, provider=provider, model=model),
            DevSrValidator(project_id=project_id, provider=provider, model=model),
            QAValidator(project_id=project_id, provider=provider, model=model)
        ]

    def validate_all(
        self,
        responses: Dict[str, str],
        extracted_concepts: List[str],
        document_domain: str = "software"
    ) -> ConsolidatedValidation:
        """
        Roda validação de todas as Personas

        Args:
            responses: Respostas do questionário
            extracted_concepts: Conceitos extraídos
            document_domain: Domínio

        Returns:
            ConsolidatedValidation com resultados de todas as Personas
        """
        results = []

        for persona in self.personas:
            result = persona.validate(
                responses=responses,
                extracted_concepts=extracted_concepts,
                document_domain=document_domain
            )
            results.append(result)

        # Consolidar
        approved_count = sum(1 for r in results if r.status == "approved")
        all_approved = approved_count == len(self.personas)

        if all_approved:
            next_action = "aggregate_to_ocg"
        else:
            # Coletar todas as followup_questions de Personas com needs_clarification
            followup_pool = []
            for r in results:
                if r.status == "needs_clarification" and r.followup_questions:
                    followup_pool.extend(r.followup_questions)

            if followup_pool:
                next_action = "generate_followup_questionnaire"
            else:
                next_action = "manual_review"

        return ConsolidatedValidation(
            all_approved=all_approved,
            results=results,
            ready_for_ocg_aggregation=all_approved,
            next_action=next_action
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_personas_consolidator(project_id: UUID = None, provider: str = None, model: str = None) -> PersonasConsolidator:
    """Factory para criar PersonasConsolidator com configuração do projeto"""
    return PersonasConsolidator(project_id=project_id, provider=provider, model=model)


def create_single_persona_validator(
    persona_class,
    project_id: UUID = None,
    provider: str = None,
    model: str = None
) -> PersonaValidator:
    """Factory para criar uma Persona única com configuração do projeto"""
    return persona_class(project_id=project_id, provider=provider, model=model)
