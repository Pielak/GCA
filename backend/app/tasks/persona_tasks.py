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
        # 1. Get persona user by full_name (personas have no email)
        persona_name = PERSONA_NAMES.get(persona_type)
        if not persona_name:
            logger.warning("persona.unknown_type", persona=persona_type)
            return

        from sqlalchemy import select
        persona = await db.scalar(
            select(User).where(User.full_name == persona_name)
        )
        if not persona:
            logger.warning("persona.user_not_found", persona=persona_type, full_name=persona_name)
            return

        # Fetch API key for authentication
        api_key_row = await db.scalar(
            select(
                "SELECT api_key_encrypted FROM user_api_keys WHERE user_id = :user_id"
            ).bindparams(user_id=persona.id)
        )
        if not api_key_row:
            logger.warning("persona.api_key_not_found", persona_id=str(persona.id))
            return

        # 2. Fetch document content (via internal API call)
        # TODO: implement document fetch with authentication
        document_content = "TODO: fetch from /projects/{project_id}/ingestion/{document_id}/content"

        # 3. Call LLM with persona-specific prompt
        # TODO: call LLM (Anthropic/OpenAI/DeepSeek based on project settings)
        ocg_individual = {
            "persona": persona_type,
            "titulo": f"Análise {persona_type}",
            "parecer": "TODO: LLM response",
            "criticidade": "MEDIA",
        }

        # 4. Store OCG Individual
        # TODO: create and persist OCG Individual record
        logger.info(
            "persona.ocg_individual_stored",
            persona=persona_type,
            project_id=str(project_id),
            document_id=str(document_id),
        )
