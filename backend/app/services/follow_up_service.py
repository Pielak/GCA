"""
Follow-Up Questions Service

Após análise inicial (OCGIndividual), personas geram perguntas
de clarificação baseadas em gaps, ambiguidades ou incertezas
detectadas na análise.

Fluxo:
1. Análise inicial completa
2. Persona gera N follow-up questions
3. User responde perguntas
4. Persona re-analisa com contexto das respostas
5. OCG Individual refinado armazenado
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import structlog
import json
from typing import List, Dict

from app.models.base import (
    PersonaFollowUpQuestion,
    OCGIndividual,
    OCGIndividualRefined,
)

logger = structlog.get_logger(__name__)


# Prompts para gerar follow-up questions por persona
FOLLOW_UP_PROMPTS = {
    "Persona - DBA": """Baseado na sua análise anterior do documento, gere 3-5 perguntas
de clarificação que ajudem refinar a recomendação técnica sobre banco de dados.

Foque em:
- Volume de dados e padrões de crescimento
- Requisitos de replicação e backup
- SLAs de performance
- Conformidade e retenção

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",

    "Persona - Compliance": """Baseado na sua análise anterior, gere 3-5 perguntas
para esclarecer requisitos de conformidade.

Foque em:
- Classificação de dados (sensível/público)
- Regulações aplicáveis (LGPD, PCI, SOC2)
- Fluxo de dados cross-border
- Retenção e eliminação de dados

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",

    "Persona - Segurança": """Baseado na sua análise anterior, gere 3-5 perguntas
para refinar o modelo de segurança.

Foque em:
- Classificação de assets e dados
- Modelo de autenticação desejado
- Integração com IAM/SSO corporativo
- Histórico de incidentes ou preocupações

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",

    "Persona - Arquiteto": """Baseado na sua análise anterior, gere 3-5 perguntas
para refinar decisões arquiteturais.

Foque em:
- Escala esperada (users, transações, dados)
- Constraints de latência/throughput
- Integração com sistemas legacy
- Roadmap de evolução

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",

    "Persona - Desenvolvedor": """Baseado na sua análise anterior, gere 3-5 perguntas
para refinar abordagem de desenvolvimento.

Foque em:
- Experiência da equipe em tech stack proposto
- Constraints de time/prazo
- Prioridades (time-to-market vs qualidade)
- Ferramentas e processos preferidos

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",

    "Persona - Tester": """Baseado na sua análise anterior, gere 3-5 perguntas
para refinar estratégia de testes.

Foque em:
- Criticidade de features para teste
- Ambientes disponíveis (staging, prod-like)
- Ferramentas e frameworks em uso
- Requisitos de compliance de testes

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",

    "Persona - QA": """Baseado na sua análise anterior, gere 3-5 perguntas
para refinar critério de qualidade.

Foque em:
- Definition of Done atual
- SLAs de qualidade esperados
- Métricas de sucesso
- Processos de release atual

Retorne JSON: { "questions": [ { "text": "...", "context": "..." } ] }""",
}


class FollowUpService:
    """Serviço para gerar e gerenciar follow-up questions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_follow_up_questions(
        self,
        ocg_individual_id: UUID,
    ) -> List[PersonaFollowUpQuestion]:
        """
        Gera follow-up questions para um OCG Individual.

        Chama LLM para gerar perguntas baseadas na análise inicial.
        Armazena no banco de dados.
        """
        # 1. Buscar OCG Individual
        ocg = await self.db.get(OCGIndividual, ocg_individual_id)
        if not ocg:
            logger.warning("follow_up.ocg_not_found", ocg_id=str(ocg_individual_id))
            return []

        if ocg.status != "completed":
            logger.warning(
                "follow_up.ocg_not_ready",
                ocg_id=str(ocg_individual_id),
                status=ocg.status,
            )
            return []

        # 2. Gerar perguntas via LLM
        parecer_json = json.dumps(ocg.parecer, ensure_ascii=False)
        prompt = FOLLOW_UP_PROMPTS.get(ocg.persona_name, "")

        if not prompt:
            logger.warning("follow_up.unknown_persona", persona=ocg.persona_name)
            return []

        full_prompt = f"{prompt}\n\nAnálise anterior:\n{parecer_json}"

        try:
            from app.services.llm_service import LLMServiceFactory, LLMProvider
            from app.core.config import settings

            api_key = settings.ANTHROPIC_API_KEY
            client = LLMServiceFactory.create_client(LLMProvider.ANTHROPIC, api_key)

            response = await client.generate(
                prompt=full_prompt,
                max_tokens=1500,
                temperature=0.7,
            )

            # Parse resposta JSON
            import re
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                logger.warning("follow_up.invalid_json_response", ocg_id=str(ocg_individual_id))
                return []

            response_json = json.loads(json_match.group())
            questions_data = response_json.get("questions", [])

        except Exception as e:
            logger.error(
                "follow_up.generation_failed",
                ocg_id=str(ocg_individual_id),
                error=str(e),
            )
            return []

        # 3. Armazenar perguntas
        questions = []
        for i, q_data in enumerate(questions_data):
            question = PersonaFollowUpQuestion(
                project_id=ocg.project_id,
                document_id=ocg.document_id,
                ocg_individual_id=ocg.id,
                persona_id=ocg.persona_id,
                persona_name=ocg.persona_name,
                question_text=q_data.get("text", ""),
                context=q_data.get("context", ""),
                question_order=i,
                status="pending",
            )
            self.db.add(question)
            questions.append(question)

        await self.db.commit()

        logger.info(
            "follow_up.questions_generated",
            ocg_id=str(ocg_individual_id),
            count=len(questions),
            persona=ocg.persona_name,
        )

        return questions

    async def submit_answers(
        self,
        ocg_individual_id: UUID,
        answers: Dict[str, str],  # {question_id: answer}
        answered_by: UUID,
    ) -> bool:
        """
        User submete respostas às follow-up questions.

        Marca perguntas como respondidas e dispara re-análise.
        """
        try:
            # 1. Atualizar respostas no BD
            for question_id, answer_text in answers.items():
                question = await self.db.get(PersonaFollowUpQuestion, UUID(question_id))
                if question and question.ocg_individual_id == ocg_individual_id:
                    question.answer_text = answer_text
                    question.answer_provided_at = datetime.now(timezone.utc)
                    question.answered_by = answered_by
                    question.status = "answered"
                    self.db.add(question)

            await self.db.commit()

            # 2. Disparar refinement task (re-análise)
            from app.tasks.persona_tasks import refine_ocg_with_answers
            refine_ocg_with_answers.delay(
                ocg_individual_id=str(ocg_individual_id),
                answered_by=str(answered_by),
            )

            logger.info(
                "follow_up.answers_submitted",
                ocg_id=str(ocg_individual_id),
                answer_count=len(answers),
            )

            return True

        except Exception as e:
            logger.error(
                "follow_up.submit_failed",
                ocg_id=str(ocg_individual_id),
                error=str(e),
            )
            await self.db.rollback()
            return False

    async def get_pending_questions(
        self,
        project_id: UUID,
        document_id: UUID,
    ) -> List[PersonaFollowUpQuestion]:
        """Retorna perguntas não respondidas para um documento."""
        questions = await self.db.scalars(
            select(PersonaFollowUpQuestion).where(
                (PersonaFollowUpQuestion.project_id == project_id) &
                (PersonaFollowUpQuestion.document_id == document_id) &
                (PersonaFollowUpQuestion.status == "pending")
            )
        )
        return questions.all()
