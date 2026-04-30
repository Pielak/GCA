"""
Celery tasks for Persona analysis of ingested documents.
Each persona analyzes a document and generates an OCG Individual.
"""
from uuid import UUID
from datetime import datetime, timezone
import structlog
import json

from app.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.core.config import settings
from app.models.base import User

logger = structlog.get_logger(__name__)

PERSONA_PROMPTS = {
    "IA_DBA": """Você é uma DBA experiente. Analise os requisitos de projeto fornecidos e gere um parecer técnico focado em:
1. Estrutura de dados e schema
2. Performance e índices
3. Escalabilidade e replicação
4. Backup e disaster recovery
5. Segurança e encriptação de dados
6. Conformidade LGPD/compliance
7. Retenção de dados

Formato: JSON com campos: titulo, parecer (texto), riscos (lista), recomendacoes (lista), criticidade (BAIXA/MEDIA/ALTA)""",

    "IA_Compliance": """Você é especialista em conformidade. Analise os requisitos e gere parecer focado em:
1. Conformidade regulatória (LGPD, PCI, SOC2)
2. Governança de dados
3. Auditoria e rastreabilidade
4. Controles de acesso
5. Políticas de privacidade
6. Retenção legal
7. Relatórios e evidências

Formato: JSON com campos: titulo, parecer (texto), violacoes (lista), controles_requeridos (lista), criticidade""",

    "IA_Security": """Você é especialista em segurança. Analise requisitos e gere parecer sobre:
1. Autenticação e autorização
2. Criptografia (transit e rest)
3. Gestão de secrets
4. Vulnerabilidades conhecidas
5. Segurança de rede
6. Logging e monitoring
7. Incident response

Formato: JSON com campos: titulo, parecer (texto), vulnerabilidades (lista), mitigacoes (lista), criticidade""",

    "IA_Arquiteto": """Você é arquiteto de software. Analise e gere parecer sobre:
1. Arquitetura geral (monolito/microserviços)
2. Padrões de design
3. Escalabilidade horizontal
4. Integração com sistemas legados
5. Escolha de tecnologias
6. API design
7. Evolução futura da arquitetura

Formato: JSON com campos: titulo, parecer (texto), padroes_recomendados (lista), trade_offs (lista), criticidade""",

    "IA_Dev": """Você é desenvolvedor sênior. Analise e gere parecer sobre:
1. Qualidade de código
2. Testes (unitários, integração, E2E)
3. CI/CD pipeline
4. Dependency management
5. Code review process
6. Documentação de código
7. Debt técnica

Formato: JSON com campos: titulo, parecer (texto), tasks_implementacao (lista), dependencias (lista), criticidade""",

    "IA_Tester": """Você é tester/QA sênior. Analise e gere parecer sobre:
1. Estratégia de testes
2. Casos de teste críticos
3. Cobertura de testes
4. Regressão
5. Performance e carga
6. Acessibilidade
7. Testes de segurança

Formato: JSON com campos: titulo, parecer (texto), cenarios_criticos (lista), metricas_qualidade (lista), criticidade""",

    "IA_QA": """Você é QA lead. Analise e gere parecer sobre:
1. Critério de aceite
2. Definition of Done
3. Rastreabilidade requisitos-testes
4. Risco residual
5. Release readiness
6. Checklists pré-produção
7. Métricas de qualidade

Formato: JSON com campos: titulo, parecer (texto), blockers (lista), observacoes (lista), criticidade""",
}

PERSONA_NAMES = {
    "IA_DBA": "Persona - DBA",
    "IA_Compliance": "Persona - Compliance",
    "IA_Security": "Persona - Segurança",
    "IA_Arquiteto": "Persona - Arquiteto",
    "IA_Dev": "Persona - Desenvolvedor",
    "IA_Tester": "Persona - Tester",
    "IA_QA": "Persona - QA",
}


@celery_app.task(bind=True, max_retries=3, acks_late=True)
def analyze_document_with_persona(self, document_id: str, project_id: str, persona_type: str):
    """
    Persona analyzes an ingested document and generates OCG Individual.
    Runs async work inside sync Celery task.
    """
    import asyncio

    try:
        asyncio.run(
            _analyze_document_async(
                document_id=UUID(document_id),
                project_id=UUID(project_id),
                persona_type=persona_type,
            )
        )
        logger.info(
            "persona.analysis_complete",
            persona=persona_type,
            project_id=project_id,
            document_id=document_id,
        )
    except Exception as exc:
        logger.error(
            "persona.analysis_failed",
            persona=persona_type,
            error=str(exc),
            project_id=project_id,
            document_id=document_id,
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _analyze_document_async(
    document_id: UUID,
    project_id: UUID,
    persona_type: str,
):
    """
    Async implementation: fetch document, call LLM, store result.
    """
    async with AsyncSessionLocal() as db:
        # 1. Get persona user by full_name
        persona_name = PERSONA_NAMES.get(persona_type)
        if not persona_name:
            logger.warning("persona.unknown_type", persona=persona_type)
            return

        from sqlalchemy import select, text
        persona = await db.scalar(
            select(User).where(User.full_name == persona_name)
        )
        if not persona:
            logger.warning("persona.user_not_found", persona=persona_type)
            return

        # 2. Fetch document content from database
        from app.models.base import IngestedDocument
        document = await db.scalar(
            select(IngestedDocument).where(IngestedDocument.id == document_id)
        )
        if not document:
            logger.warning("persona.document_not_found", document_id=str(document_id))
            return

        # Read document content from filesystem
        import os
        doc_path = f"/app/data/ingestion/{document.filename}"
        if not os.path.exists(doc_path):
            logger.warning("persona.document_file_not_found", path=doc_path)
            return

        try:
            with open(doc_path, "r", encoding="utf-8", errors="ignore") as f:
                document_content = f.read()[:5000]  # Limitar a 5K chars
        except Exception as e:
            logger.error("persona.document_read_failed", document_id=str(document_id), error=str(e))
            return

        # 3. Call LLM with persona-specific prompt
        prompt = PERSONA_PROMPTS[persona_type]
        full_prompt = f"{prompt}\n\n---DOCUMENTO---\n{document.original_filename}\n\n{document_content}\n\n---INSTRUÇÃO---\nGere um parecer estruturado em JSON com os campos especificados acima."

        try:
            # Import LLM service
            from app.services.llm_service import LLMServiceFactory, LLMProvider
            from app.core.config import settings

            # Get API key for Anthropic
            api_key = settings.ANTHROPIC_API_KEY
            client = LLMServiceFactory.create_client(LLMProvider.ANTHROPIC, api_key)

            # Call LLM
            response = await client.generate(
                prompt=full_prompt,
                max_tokens=2000,
                temperature=0.5,
            )

            # Parse LLM response (esperando JSON)
            import re
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                parecer = json.loads(json_match.group())
            else:
                parecer = {
                    "titulo": f"Análise {persona_type}",
                    "parecer": response,
                    "criticidade": "MEDIA",
                }

        except Exception as e:
            logger.error(
                "persona.llm_call_failed",
                persona=persona_type,
                document_id=str(document_id),
                error=str(e),
            )
            parecer = {
                "titulo": f"Análise {persona_type}",
                "parecer": f"Erro na análise: {str(e)}",
                "criticidade": "MEDIA",
            }

        # 4. Store OCG Individual
        from app.models.base import OCGIndividual
        from datetime import datetime, timezone

        ocg = OCGIndividual(
            project_id=project_id,
            document_id=document_id,
            persona_id=persona.id,
            persona_name=persona_name,
            parecer=parecer,
            status="completed",
            ai_provider="anthropic",
            ai_model="claude-opus-4-7",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(ocg)
        await db.commit()

        logger.info(
            "persona.ocg_individual_stored",
            persona=persona_type,
            project_id=str(project_id),
            document_id=str(document_id),
        )

        # Disparar geração de follow-up questions após análise completar
        generate_follow_up_questions.delay(str(ocg.id))

        # Disparar consolidação automática (se todas 7 completarem)
        auto_consolidate_ocg.delay(str(document_id), str(project_id))


@celery_app.task(bind=True, max_retries=2, acks_late=True)
def generate_follow_up_questions(self, ocg_individual_id: str):
    """
    Gera follow-up questions para um OCG Individual.
    Disparado após análise inicial completar.
    """
    import asyncio

    try:
        asyncio.run(
            _generate_follow_up_async(UUID(ocg_individual_id))
        )
        logger.info(
            "persona.follow_up_generated",
            ocg_id=ocg_individual_id,
        )
    except Exception as exc:
        logger.error(
            "persona.follow_up_generation_failed",
            ocg_id=ocg_individual_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=60)


async def _generate_follow_up_async(ocg_individual_id: UUID):
    """Gera follow-up questions async."""
    from app.services.follow_up_service import FollowUpService

    async with AsyncSessionLocal() as db:
        service = FollowUpService(db)
        await service.generate_follow_up_questions(ocg_individual_id)


@celery_app.task(bind=True, max_retries=2, acks_late=True)
def refine_ocg_with_answers(self, ocg_individual_id: str, answered_by: str):
    """
    Re-analisa OCG Individual após user responder follow-up questions.
    Armazena parecer refinado.
    """
    import asyncio

    try:
        asyncio.run(
            _refine_ocg_async(UUID(ocg_individual_id), UUID(answered_by))
        )
        logger.info(
            "persona.ocg_refined",
            ocg_id=ocg_individual_id,
        )
    except Exception as exc:
        logger.error(
            "persona.ocg_refinement_failed",
            ocg_id=ocg_individual_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=60)


async def _refine_ocg_async(ocg_individual_id: UUID, answered_by: UUID):
    """Re-analisa OCG com contexto de respostas."""
    from app.models.base import (
        OCGIndividual,
        PersonaFollowUpQuestion,
        OCGIndividualRefined,
    )
    from app.services.llm_service import LLMServiceFactory, LLMProvider
    from app.core.config import settings

    async with AsyncSessionLocal() as db:
        # 1. Buscar OCG original
        ocg = await db.get(OCGIndividual, ocg_individual_id)
        if not ocg:
            logger.warning("persona.ocg_not_found_for_refinement", ocg_id=str(ocg_individual_id))
            return

        # 2. Buscar perguntas e respostas
        from sqlalchemy import select
        questions = await db.scalars(
            select(PersonaFollowUpQuestion).where(
                PersonaFollowUpQuestion.ocg_individual_id == ocg_individual_id
            )
        )
        questions_list = questions.all()

        # Montar contexto de Q&A
        qa_context = "Respostas do usuário às perguntas de clarificação:\n\n"
        for q in questions_list:
            qa_context += f"P: {q.question_text}\n"
            qa_context += f"R: {q.answer_text or '(sem resposta)'}\n\n"

        # 3. Re-analisar com contexto
        persona_name = ocg.persona_name
        original_parecer = json.dumps(ocg.parecer, ensure_ascii=False)

        prompt = f"""Refine sua análise anterior baseado nas respostas do usuário.

ANÁLISE ANTERIOR:
{original_parecer}

CONTEXTO ADICIONAL (respostas do usuário):
{qa_context}

Gere um parecer REFINADO em JSON com os mesmos campos, mas atualizado com as novas informações.
Destaque quais campos mudaram e por quê.

Retorne JSON: {{ "parecer_refined": {{...}}, "changed_fields": [...], "change_summary": "..." }}"""

        try:
            api_key = settings.ANTHROPIC_API_KEY
            client = LLMServiceFactory.create_client(LLMProvider.ANTHROPIC, api_key)

            response = await client.generate(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.5,
            )

            # Parse resposta
            import re
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                logger.warning("persona.invalid_refinement_response", ocg_id=str(ocg_individual_id))
                return

            response_json = json.loads(json_match.group())

            # 4. Armazenar análise refinada
            refined = OCGIndividualRefined(
                ocg_individual_id=ocg_individual_id,
                refinement_iteration=1,
                parecer_refined=response_json.get("parecer_refined", {}),
                changed_fields=response_json.get("changed_fields", []),
                change_summary=response_json.get("change_summary", ""),
            )
            db.add(refined)

            # Marcar perguntas como refinement_complete
            for q in questions_list:
                q.status = "refinement_complete"
                db.add(q)

            await db.commit()

            logger.info(
                "persona.ocg_refinement_complete",
                ocg_id=str(ocg_individual_id),
                changed_fields=response_json.get("changed_fields", []),
            )

        except Exception as e:
            logger.error(
                "persona.refinement_llm_failed",
                ocg_id=str(ocg_individual_id),
                error=str(e),
            )


@celery_app.task(bind=True, max_retries=2, acks_late=True)
def auto_consolidate_ocg(self, document_id: str, project_id: str):
    """
    Consolida OCG Global automaticamente após todas as 7 análises completarem.
    Disparado por cada persona após completar análise.
    """
    import asyncio

    try:
        asyncio.run(
            _auto_consolidate_async(UUID(document_id), UUID(project_id))
        )
        logger.info(
            "persona.ocg_auto_consolidation_triggered",
            document_id=document_id,
            project_id=project_id,
        )
    except Exception as exc:
        logger.error(
            "persona.ocg_auto_consolidation_failed",
            document_id=document_id,
            project_id=project_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=60)


async def _auto_consolidate_async(document_id: UUID, project_id: UUID):
    """Verifica se todas as 7 análises completaram e consolida."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import OCGIndividual, OCGGlobal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # 1. Contar análises completas
        completed = await db.scalar(
            select(OCGIndividual).where(
                (OCGIndividual.document_id == document_id) &
                (OCGIndividual.status == "completed")
            )
        )
        
        # 2. Se todas as 7 completaram, consolidar
        total_personas = await db.scalar(
            select(OCGIndividual).where(
                OCGIndividual.document_id == document_id
            )
        )

        # Contar de forma mais eficiente
        from sqlalchemy import func
        completed_count = await db.scalar(
            select(func.count(OCGIndividual.id)).where(
                (OCGIndividual.document_id == document_id) &
                (OCGIndividual.status == "completed")
            )
        )

        if completed_count == 7:
            # Verificar se já foi consolidado
            existing = await db.scalar(
                select(OCGGlobal).where(OCGGlobal.document_id == document_id)
            )

            if not existing:
                # Disparar consolidação
                from app.services.ocg_consolidation_service import OCGConsolidationService
                service = OCGConsolidationService(db)
                ocg_global = await service.consolidate_document(project_id, document_id)

                if ocg_global:
                    logger.info(
                        "persona.ocg_auto_consolidated",
                        document_id=str(document_id),
                        project_id=str(project_id),
                    )

                    # NOVO: Disparar regeneração de Pilares Vivos após OCG consolidado
                    # Obter user_id que fez upload do documento
                    from app.models.base import IngestedDocument
                    doc = await db.get(IngestedDocument, document_id)
                    if doc:
                        from app.tasks.pilares_vivos_task import regenerar_pilares_apos_analise
                        regenerar_pilares_apos_analise.delay(
                            project_id=str(project_id),
                            user_id=str(doc.uploaded_by),
                            trigger="ingestao",
                        )
                        logger.info(
                            "pilares_vivos.regeneracao_disparada",
                            project_id=str(project_id),
                            trigger="ingestao",
                            document_id=str(document_id),
                        )
