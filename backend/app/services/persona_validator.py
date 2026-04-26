"""
PersonaValidator — Análise de respostas do questionário por Personas

Cada Persona (GP, Arquiteto, DBA, Dev Sr, QA) valida respostas do M01.
Saída: aprovação OU novas questões de clarificação.
"""

from typing import List, Dict, Optional, TypeVar
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from anthropic import Anthropic
import json

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

class PersonaValidator(ABC):
    """Abstract base class para todas as Personas"""

    def __init__(self, anthropic_client: Anthropic = None):
        self.client = anthropic_client or Anthropic()
        self.model = "claude-sonnet-4-6-20250514"

    @abstractmethod
    def get_persona_name(self) -> str:
        """Retorna nome da Persona"""
        pass

    @abstractmethod
    def get_validation_prompt(self) -> str:
        """Retorna prompt de validação específico da Persona"""
        pass

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

        # Chamar Claude
        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Parse resposta
        response_text = message.content[0].text

        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Se falhar parsing, assumir que precisa clarificação
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
    """Consolida validações de todas as 5 Personas"""

    def __init__(self):
        self.personas = [
            GPValidator(),
            ArquitetoValidator(),
            DBAValidator(),
            DevSrValidator(),
            QAValidator()
        ]

    def validate_all(
        self,
        responses: Dict[str, str],
        extracted_concepts: List[str],
        document_domain: str = "software"
    ) -> ConsolidatedValidation:
        """
        Roda validação de todas as 5 Personas (em paralelo se possível)

        Args:
            responses: Respostas do questionário
            extracted_concepts: Conceitos extraídos
            document_domain: Domínio

        Returns:
            ConsolidatedValidation com resultados de todas as Personas
        """
        results = []

        # TODO: Paralelizar com asyncio/gather se performance for crítica
        for persona in self.personas:
            result = persona.validate(
                responses=responses,
                extracted_concepts=extracted_concepts,
                document_domain=document_domain
            )
            results.append(result)

        # Consolidar
        approved_count = sum(1 for r in results if r.status == "approved")
        all_approved = approved_count == 5

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
# HELPER FUNCTION
# ============================================================================

def create_personas_consolidator() -> PersonasConsolidator:
    """Factory para criar PersonasConsolidator com defaults"""
    return PersonasConsolidator()
