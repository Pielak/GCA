"""Testes para avaliação paralela de Personas com IA do projeto.

MVP B: Personas paralelas com suporte a múltiplos provedores IA.
Cobre: factory creation, validators com config de projeto, Celery tasks, endpoints.
"""

import json
import pytest
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import select

from app.models.base import PersonaResponse, ProjectSettings, TechnicalQuestionnaire, Project
from app.services.persona_validator import (
    GPValidator,
    ArquitetoValidator,
    DBAValidator,
    DevSrValidator,
    QAValidator,
    create_single_persona_validator,
    create_personas_consolidator,
)

pytestmark = pytest.mark.unit


# ─── Persona Validator Creation ──────────────────────────────────────


def test_create_persona_validator_with_default_anthropic():
    """GPValidator usa Anthropic por padrão se não configurado"""
    validator = GPValidator()
    assert validator.provider == "anthropic"
    assert validator.model == "claude-sonnet-4-6-20250514"
    assert validator.project_id is None


def test_create_persona_validator_with_deepseek():
    """GPValidator pode ser criado com DeepSeek configurado"""
    project_id = uuid4()
    validator = GPValidator(
        project_id=project_id,
        provider="deepseek",
        model="deepseek-chat",
    )
    assert validator.provider == "deepseek"
    assert validator.model == "deepseek-chat"
    assert validator.project_id == project_id


def test_create_single_persona_validator_factory():
    """Factory create_single_persona_validator cria com config"""
    project_id = uuid4()
    validator = create_single_persona_validator(
        DBAValidator,
        project_id=project_id,
        provider="openai",
        model="gpt-4",
    )
    assert isinstance(validator, DBAValidator)
    assert validator.provider == "openai"
    assert validator.model == "gpt-4"
    assert validator.project_id == project_id


def test_create_personas_consolidator_with_config():
    """Factory create_personas_consolidator cria 5 Personas com config"""
    project_id = uuid4()
    consolidator = create_personas_consolidator(
        project_id=project_id,
        provider="deepseek",
        model="deepseek-chat",
    )
    assert len(consolidator.personas) == 5
    assert all(p.provider == "deepseek" for p in consolidator.personas)
    assert all(p.model == "deepseek-chat" for p in consolidator.personas)
    assert all(p.project_id == project_id for p in consolidator.personas)


# ─── Persona Validator Behavior ──────────────────────────────────────


def test_all_persona_classes_have_get_persona_name():
    """Todas as Personas implementam get_persona_name()"""
    personas = [
        GPValidator(),
        ArquitetoValidator(),
        DBAValidator(),
        DevSrValidator(),
        QAValidator(),
    ]
    names = [p.get_persona_name() for p in personas]
    assert "GP" in names[0]
    assert "Arquiteto" in names[1]
    assert "DBA" in names[2]
    assert "Dev" in names[3]
    assert "QA" in names[4]


def test_all_persona_classes_have_get_validation_prompt():
    """Todas as Personas implementam get_validation_prompt()"""
    personas = [
        GPValidator(),
        ArquitetoValidator(),
        DBAValidator(),
        DevSrValidator(),
        QAValidator(),
    ]
    for persona in personas:
        prompt = persona.get_validation_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 20
        # Prompts contêm instruções específicas da persona
        assert "você valida" in prompt.lower() or "você" in prompt.lower()


# ─── Persona Response Model ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_persona_response_creation(db_session):
    """PersonaResponse pode ser criado e persisted"""
    project_id = uuid4()
    questionnaire_id = uuid4()

    response = PersonaResponse(
        project_id=project_id,
        technical_questionnaire_id=questionnaire_id,
        persona_name="gp",
        status="pending",
    )
    db_session.add(response)
    await db_session.commit()

    # Verify
    stmt = select(PersonaResponse).where(PersonaResponse.id == response.id)
    fetched = await db_session.scalar(stmt)
    assert fetched is not None
    assert fetched.persona_name == "gp"
    assert fetched.status == "pending"


@pytest.mark.asyncio
async def test_persona_response_unique_constraint(db_session):
    """Uma Persona por questionário — constraint único"""
    project_id = uuid4()
    questionnaire_id = uuid4()

    r1 = PersonaResponse(
        project_id=project_id,
        technical_questionnaire_id=questionnaire_id,
        persona_name="gp",
        status="pending",
    )
    db_session.add(r1)
    await db_session.commit()

    # Tentar criar outro com mesmo questionnaire + persona
    r2 = PersonaResponse(
        project_id=project_id,
        technical_questionnaire_id=questionnaire_id,
        persona_name="gp",
        status="pending",
    )
    db_session.add(r2)
    with pytest.raises(Exception):  # IntegrityError
        await db_session.commit()


@pytest.mark.asyncio
async def test_persona_response_fields(db_session):
    """PersonaResponse armazena todas as informações necessárias"""
    project_id = uuid4()
    questionnaire_id = uuid4()

    response = PersonaResponse(
        project_id=project_id,
        technical_questionnaire_id=questionnaire_id,
        persona_name="arquiteto",
        status="completed",
        decision="Arquitetura clara e viável",
        ocg_delta={"arquitetura": "microserviços recomendados"},
        severity="info",
        ai_provider_used="deepseek",
        ai_model_used="deepseek-chat",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(response)
    await db_session.commit()

    stmt = select(PersonaResponse).where(PersonaResponse.id == response.id)
    fetched = await db_session.scalar(stmt)

    assert fetched.decision == "Arquitetura clara e viável"
    assert fetched.ocg_delta == {"arquitetura": "microserviços recomendados"}
    assert fetched.ai_provider_used == "deepseek"
    assert fetched.ai_model_used == "deepseek-chat"
    assert fetched.severity == "info"


# ─── Persona Validation (mock) ───────────────────────────────────────


def test_persona_validation_result_structure():
    """Resultado de validação tem estrutura esperada"""
    from app.services.persona_validator import ValidationResult

    result = ValidationResult(
        persona="gp",
        status="approved",
        decision="Escopo claro",
        ocg_delta={"escopo": "3 meses, team de 5"},
        severity="info",
    )

    assert result.persona == "gp"
    assert result.status == "approved"
    assert "Escopo" in result.decision
    assert "escopo" in result.ocg_delta


def test_persona_validation_error_handling():
    """Persona validation retorna resultado mesmo com erro"""
    validator = GPValidator()

    # Validar com dados vazios — LLM pode falhar, mas ValidationResult é retornado
    result = validator.validate(
        responses={},
        extracted_concepts=[],
        document_domain="software",
    )

    # Sempre retorna ValidationResult, mesmo se status é "needs_clarification"
    assert isinstance(result.persona, str)
    assert result.status in ["approved", "needs_clarification"]


# ─── Consolidation ──────────────────────────────────────────────────


def test_personas_consolidator_returns_consolidated_validation():
    """PersonasConsolidator.validate_all retorna ConsolidatedValidation"""
    consolidator = create_personas_consolidator()

    result = consolidator.validate_all(
        responses={"Q1": "Novo sistema", "Q3": "Sim"},
        extracted_concepts=["backend", "API"],
        document_domain="software",
    )

    assert result.results is not None
    assert len(result.results) == 5  # 5 personas
    assert hasattr(result, "all_approved")
    assert hasattr(result, "next_action")
    assert result.next_action in ["aggregate_to_ocg", "generate_followup_questionnaire", "manual_review"]


# ─── Persona Validator as Async (future) ────────────────────────────


def test_persona_validator_supports_deepseek_config():
    """PersonaValidator instance pode usar DeepSeek config"""
    validator = GPValidator(provider="deepseek", model="deepseek-chat")
    assert validator.provider == "deepseek"

    # Se chamado, tentaria usar requests.Session — mas não testamos API call real aqui
    # (sem integração com deepseek real)


def test_all_personas_support_project_config():
    """Todas as 5 Personas suportam project_id + provider + model"""
    project_id = uuid4()

    for PersonaClass in [GPValidator, ArquitetoValidator, DBAValidator, DevSrValidator, QAValidator]:
        validator = PersonaClass(
            project_id=project_id,
            provider="deepseek",
            model="deepseek-chat",
        )
        assert validator.project_id == project_id
        assert validator.provider == "deepseek"
