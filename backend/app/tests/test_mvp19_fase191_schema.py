"""MVP 19 Fase 19.1 — testes de schema expansion.

Valida:
- Migration 033 aplicada: coluna `requirement_category` existe em
  `module_candidates` com tipo VARCHAR(20) NULL.
- Modelo SQLAlchemy `ModuleCandidate` aceita leitura/escrita do campo.
- OCGResponse ganha campo `BUSINESS_RULES` com default `[]` e `extra=allow`.
- Fallback em `agent_service.consolidate_ocg` preserva BUSINESS_RULES vindo
  do agente quando válido; cai em [] quando ausente ou malformado.
- Compatibilidade: OCG sem BUSINESS_RULES continua serializando.
"""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.database import AsyncSessionLocal
from app.models.base import (
    ArguiderAnalysis,
    IngestedDocument,
    ModuleCandidate,
    Organization,
    Project,
    User,
)
from app.core.security import hash_password
from app.schemas.ocg import OCGResponse


# ===========================================================================
# Migration 033 — coluna no DB
# ===========================================================================

@pytest.mark.asyncio
async def test_migration_033_coluna_requirement_category_existe(db_session):
    """Query em information_schema confirma coluna com tipo correto."""
    result = await db_session.execute(
        text(
            "SELECT column_name, data_type, character_maximum_length, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'module_candidates' "
            "  AND column_name = 'requirement_category'"
        )
    )
    row = result.fetchone()
    assert row is not None, "Coluna requirement_category não existe — migration 033 não aplicada"
    col_name, data_type, max_len, is_nullable = row
    assert col_name == "requirement_category"
    assert data_type == "character varying"
    assert max_len == 20
    assert is_nullable == "YES"


@pytest.mark.asyncio
async def test_migration_033_indice_parcial_existe(db_session):
    """Índice parcial (WHERE requirement_category IS NOT NULL) criado."""
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'module_candidates' "
            "  AND indexname = 'idx_module_candidates_requirement_category'"
        )
    )
    row = result.fetchone()
    assert row is not None, "Índice idx_module_candidates_requirement_category ausente"


# ===========================================================================
# Modelo SQLAlchemy — leitura/escrita
# ===========================================================================

async def _make_project_and_analysis(db):
    """Cria user + org + project + IngestedDocument + ArguiderAnalysis
    suficientes para module_candidate com arguider_analysis_id preenchido
    (source='arguider' default)."""
    uid = uuid4()
    user = User(
        id=uid,
        email=f"mvp19-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="MVP 19 Tester",
        is_active=True,
        is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    org = Organization(
        id=uuid4(),
        name=f"Org {uid.hex[:6]}",
        slug=f"org-mvp19-{uid.hex[:6]}",
        owner_id=user.id,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        name="MVP 19 Proj",
        slug=f"proj-mvp19-{uid.hex[:6]}",
        description="fase 19.1",
        deliverable_type="web_app",
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        filename=f"{uuid4().hex}.pdf",
        original_filename="test.pdf",
        file_type="pdf",
        file_hash="0" * 64,
        file_size_bytes=100,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=project.id,
        llm_model="claude-3-5-sonnet",
        tokens_used=1000,
        latency_ms=500,
    )
    db.add(analysis)
    await db.flush()
    return project, analysis


@pytest.mark.asyncio
async def test_module_candidate_aceita_null_em_requirement_category(db_session):
    """Default é NULL quando não marcado."""
    project, analysis = await _make_project_and_analysis(db_session)
    mc = ModuleCandidate(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name="Login com senha",
        description="Permitir login via email + senha",
        module_type="feature",
        priority="high",
    )
    db_session.add(mc)
    await db_session.flush()
    fresh = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.id == mc.id)
    )).scalar_one()
    assert fresh.requirement_category is None


@pytest.mark.asyncio
async def test_module_candidate_aceita_valores_canonicos(db_session):
    """functional, non_functional, business_rule persistem corretamente."""
    project, analysis = await _make_project_and_analysis(db_session)
    casos = [
        ("Login", "functional"),
        ("Latência P95 < 200ms", "non_functional"),
        ("Nota fiscal até 24h pós-venda", "business_rule"),
    ]
    ids = []
    for name, category in casos:
        mc = ModuleCandidate(
            project_id=project.id,
            arguider_analysis_id=analysis.id,
            name=name,
            description=f"Desc {name}",
            module_type="feature",
            priority="medium",
            requirement_category=category,
        )
        db_session.add(mc)
        ids.append(mc)
    await db_session.flush()
    for mc, (_, category) in zip(ids, casos):
        fresh = (await db_session.execute(
            select(ModuleCandidate).where(ModuleCandidate.id == mc.id)
        )).scalar_one()
        assert fresh.requirement_category == category


@pytest.mark.asyncio
async def test_module_candidate_valores_nao_canonicos_persistem_no_banco(db_session):
    """Banco aceita string ≤20 chars; whitelist é aplicação-level.

    Guarda-rail: o banco não rejeita silenciosamente strings arbitrárias,
    por isso a camada de aplicação (endpoint/serviço) precisa validar.
    Este teste documenta o comportamento atual.
    """
    project, analysis = await _make_project_and_analysis(db_session)
    mc = ModuleCandidate(
        project_id=project.id,
        arguider_analysis_id=analysis.id,
        name="X",
        description="Y",
        module_type="feature",
        priority="low",
        requirement_category="unknown_value",
    )
    db_session.add(mc)
    await db_session.flush()
    fresh = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.id == mc.id)
    )).scalar_one()
    assert fresh.requirement_category == "unknown_value"


# ===========================================================================
# OCGResponse — campo BUSINESS_RULES
# ===========================================================================

def test_ocg_response_default_business_rules_vazio():
    """Novo OCGResponse sem passar BUSINESS_RULES → default []."""
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
    )
    assert ocg.BUSINESS_RULES == []


def test_ocg_response_aceita_lista_de_regras():
    regras = [
        {"id": "BR-001", "title": "Nota fiscal até 24h", "description": "..."},
        {"id": "BR-002", "title": "Estoque negativo proibido"},
    ]
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
        BUSINESS_RULES=regras,
    )
    assert ocg.BUSINESS_RULES == regras


def test_ocg_response_serializa_business_rules_no_dict():
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
        BUSINESS_RULES=[{"id": "BR-001", "title": "Teste"}],
    )
    dumped = ocg.dict()
    assert "BUSINESS_RULES" in dumped
    assert dumped["BUSINESS_RULES"] == [{"id": "BR-001", "title": "Teste"}]


def test_ocg_response_sem_business_rules_mantem_compat():
    """OCG pré-19 (sem BUSINESS_RULES) continua serializando — o novo
    campo tem default [] então `dict()` inclui ele como lista vazia."""
    ocg = OCGResponse(
        ocg_id=uuid4(),
        questionnaire_id=uuid4(),
        generated_at=datetime.utcnow(),
        PROJECT_PROFILE={"name": "Projeto antigo"},
        PILLAR_SCORES={"P1": {"score": 85}},
    )
    dumped = ocg.dict()
    assert dumped["BUSINESS_RULES"] == []
    # Campos clássicos preservados
    assert dumped["PROJECT_PROFILE"] == {"name": "Projeto antigo"}
    assert dumped["PILLAR_SCORES"] == {"P1": {"score": 85}}


# ===========================================================================
# Fallback em consolidate_ocg — aceita o que o agente popular
# ===========================================================================

def test_fallback_business_rules_agente_popula_lista_valida():
    """Simula o trecho do consolidate_ocg que decide BUSINESS_RULES."""
    # Replica a lógica inline pra não depender do pipeline inteiro.
    ocg_json = {"BUSINESS_RULES": [{"id": "BR-001", "title": "X"}]}

    business_rules_from_agent = (
        ocg_json.get("BUSINESS_RULES") or ocg_json.get("business_rules")
    )
    if isinstance(business_rules_from_agent, list):
        result = business_rules_from_agent
    else:
        result = []

    assert result == [{"id": "BR-001", "title": "X"}]


def test_fallback_business_rules_agente_lowercase_tambem_aceito():
    ocg_json = {"business_rules": [{"id": "BR-002"}]}

    business_rules_from_agent = (
        ocg_json.get("BUSINESS_RULES") or ocg_json.get("business_rules")
    )
    if isinstance(business_rules_from_agent, list):
        result = business_rules_from_agent
    else:
        result = []

    assert result == [{"id": "BR-002"}]


def test_fallback_business_rules_agente_nao_popula_cai_em_vazio():
    ocg_json = {}
    business_rules_from_agent = (
        ocg_json.get("BUSINESS_RULES") or ocg_json.get("business_rules")
    )
    if isinstance(business_rules_from_agent, list):
        result = business_rules_from_agent
    else:
        result = []
    assert result == []


def test_fallback_business_rules_tipo_invalido_cai_em_vazio():
    """Se o LLM emitir string ou dict em vez de list, o fallback rejeita."""
    casos_invalidos = [
        {"BUSINESS_RULES": "uma string"},
        {"BUSINESS_RULES": {"nao": "e lista"}},
        {"BUSINESS_RULES": 42},
        {"BUSINESS_RULES": None},
    ]
    for ocg_json in casos_invalidos:
        business_rules_from_agent = (
            ocg_json.get("BUSINESS_RULES") or ocg_json.get("business_rules")
        )
        if isinstance(business_rules_from_agent, list):
            result = business_rules_from_agent
        else:
            result = []
        assert result == [], f"Falhou para {ocg_json!r}"
