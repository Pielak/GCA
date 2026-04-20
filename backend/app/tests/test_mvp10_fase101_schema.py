"""MVP 10 Fase 10.1 — Schema TestSpec + LiveDoc.

Cobre:
  - CRUD básico dos dois modelos
  - UniqueConstraint idempotência (project_id, module_id, spec_type) e
    (project_id, module_id, doc_type)
  - module_id NULL permitido (specs globais security/compliance,
    docs consolidados index/architecture)
  - FK ON DELETE CASCADE (project e module)
  - Compartimentalização por project_id
  - Defaults corretos: status='draft', content=''
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, LiveDoc, ModuleCandidate,
    OCG, Questionnaire, TestSpec,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed(db):
    """Cria projeto + módulo + OCG pra testes."""
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"mvp10-{uuid4().hex[:6]}")
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="t.docx", filename=f"{uuid4()}.docx",
        file_type="docx", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    a = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=p.id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]), show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]), improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]), ocg_fields_to_update=json.dumps([]),
        llm_model="x", tokens_used=0, latency_ms=0,
    )
    db.add(a)
    await db.commit()
    q = Questionnaire(
        id=uuid4(), project_id=p.id, gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    db.add(q)
    await db.commit()
    db.add(OCG(
        id=uuid4(), project_id=p.id, questionnaire_id=q.id,
        version=1, change_type="CREATE", ocg_data=json.dumps({}),
    ))
    mc = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
        source="ocg_foundation", name="X", description="y",
        module_type="backend_service", priority="high", status="sugerido",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
    )
    db.add(mc)
    await db.commit()
    return p, mc, user


# ============================================================================
# TestSpec — CRUD e constraints
# ============================================================================

@pytest.mark.asyncio
async def test_create_test_spec_por_modulo(db_session):
    p, mc, _ = await _seed(db_session)
    spec = TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit",
        content="# Plano\nTestar método X",
        ocg_version_at_generation=1,
        generator_provider="ollama", generator_model="qwen2.5-coder:7b",
    )
    db_session.add(spec)
    await db_session.commit()

    row = (await db_session.execute(
        select(TestSpec).where(TestSpec.id == spec.id)
    )).scalar_one()
    assert row.status == "draft"  # default
    assert row.content.startswith("# Plano")
    assert row.generator_provider == "ollama"


@pytest.mark.asyncio
async def test_create_test_spec_global_sem_modulo(db_session):
    """Specs globais (security/compliance) têm module_id=NULL."""
    p, _, _ = await _seed(db_session)
    spec = TestSpec(
        project_id=p.id, module_id=None, spec_type="compliance",
        content="Requisitos LGPD do projeto inteiro",
        ocg_version_at_generation=1,
        generator_provider="anthropic", generator_model="claude-haiku-4-5-20251001",
    )
    db_session.add(spec)
    await db_session.commit()

    row = (await db_session.execute(
        select(TestSpec).where(TestSpec.id == spec.id)
    )).scalar_one()
    assert row.module_id is None


@pytest.mark.asyncio
async def test_unique_constraint_test_spec_por_modulo_e_tipo(db_session):
    """Não pode ter 2 specs unit pro mesmo módulo no mesmo projeto."""
    p, mc, _ = await _seed(db_session)
    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="v1",
    ))
    await db_session.commit()

    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="v2",
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_tolera_specs_de_tipos_diferentes(db_session):
    """Mesmo módulo pode ter unit + integration + e2e simultaneamente."""
    p, mc, _ = await _seed(db_session)
    for t in ("unit", "integration", "e2e"):
        db_session.add(TestSpec(
            project_id=p.id, module_id=mc.id, spec_type=t, content=f"plano {t}",
        ))
    await db_session.commit()

    rows = (await db_session.execute(
        select(TestSpec).where(TestSpec.module_id == mc.id)
    )).scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_provenance_json_armazena_contexto(db_session):
    """Provenance guarda: OCG version, questionário, ingestões, LLM, ts."""
    p, mc, _ = await _seed(db_session)
    provenance = {
        "ocg_version": 7,
        "questionnaire_id": str(uuid4()),
        "ingested_doc_ids": [str(uuid4()), str(uuid4())],
        "prompt_hash": "abc123",
    }
    spec = TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit",
        content="x", provenance_json=json.dumps(provenance),
    )
    db_session.add(spec)
    await db_session.commit()

    await db_session.refresh(spec)
    parsed = json.loads(spec.provenance_json)
    assert parsed["ocg_version"] == 7
    assert len(parsed["ingested_doc_ids"]) == 2


@pytest.mark.asyncio
async def test_test_spec_status_default_draft(db_session):
    p, mc, _ = await _seed(db_session)
    spec = TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="x",
    )
    db_session.add(spec)
    await db_session.commit()
    assert spec.status == "draft"


@pytest.mark.asyncio
async def test_compartimentalizacao_por_projeto(db_session):
    """Specs de projeto A não aparecem ao consultar projeto B."""
    p_a, mc_a, _ = await _seed(db_session)
    p_b, mc_b, _ = await _seed(db_session)
    db_session.add(TestSpec(
        project_id=p_a.id, module_id=mc_a.id, spec_type="unit", content="A",
    ))
    db_session.add(TestSpec(
        project_id=p_b.id, module_id=mc_b.id, spec_type="unit", content="B",
    ))
    await db_session.commit()

    rows = (await db_session.execute(
        select(TestSpec).where(TestSpec.project_id == p_a.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].content == "A"


# ============================================================================
# LiveDoc — CRUD e constraints
# ============================================================================

@pytest.mark.asyncio
async def test_create_live_doc_por_modulo(db_session):
    p, mc, _ = await _seed(db_session)
    doc = LiveDoc(
        project_id=p.id, module_id=mc.id, doc_type="module_doc",
        content="# Doc do módulo X",
        ocg_version_at_generation=1,
        generator_provider="ollama", generator_model="qwen2.5-coder:7b",
    )
    db_session.add(doc)
    await db_session.commit()
    assert doc.content.startswith("# Doc")


@pytest.mark.asyncio
async def test_create_live_doc_index_global(db_session):
    """Docs consolidados (index/architecture) têm module_id=NULL."""
    p, _, _ = await _seed(db_session)
    doc = LiveDoc(
        project_id=p.id, module_id=None, doc_type="index",
        content="# Índice de documentação do projeto",
        ocg_version_at_generation=2,
        generator_provider="anthropic",
    )
    db_session.add(doc)
    await db_session.commit()
    assert doc.module_id is None


@pytest.mark.asyncio
async def test_unique_constraint_live_doc(db_session):
    """Não pode ter 2 module_docs pro mesmo módulo."""
    p, mc, _ = await _seed(db_session)
    db_session.add(LiveDoc(
        project_id=p.id, module_id=mc.id, doc_type="module_doc", content="v1",
    ))
    await db_session.commit()

    db_session.add(LiveDoc(
        project_id=p.id, module_id=mc.id, doc_type="module_doc", content="v2",
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_live_doc_varios_tipos_mesmo_modulo_ok(db_session):
    """Mesmo módulo pode ter module_doc + architecture separadamente."""
    p, mc, _ = await _seed(db_session)
    for t in ("module_doc", "architecture"):
        db_session.add(LiveDoc(
            project_id=p.id, module_id=mc.id, doc_type=t, content=f"{t}",
        ))
    await db_session.commit()
    rows = (await db_session.execute(
        select(LiveDoc).where(LiveDoc.module_id == mc.id)
    )).scalars().all()
    assert len(rows) == 2


# ============================================================================
# FK cascade
# ============================================================================

@pytest.mark.asyncio
async def test_delete_modulo_apaga_specs_em_cascata(db_session):
    """ON DELETE CASCADE em module_candidates → test_specs."""
    from sqlalchemy import delete as _delete
    p, mc, _ = await _seed(db_session)
    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="x",
    ))
    await db_session.commit()

    await db_session.execute(_delete(ModuleCandidate).where(ModuleCandidate.id == mc.id))
    await db_session.commit()

    rows = (await db_session.execute(
        select(TestSpec).where(TestSpec.project_id == p.id)
    )).scalars().all()
    assert rows == []


# ============================================================================
# Contrato de tipos
# ============================================================================

@pytest.mark.asyncio
async def test_spec_type_aceita_todos_5_canonicos(db_session):
    """MVP 10 define: unit, integration, security, compliance, e2e."""
    p, mc, _ = await _seed(db_session)
    # unit e integration por módulo
    for t in ("unit", "integration", "e2e"):
        db_session.add(TestSpec(
            project_id=p.id, module_id=mc.id, spec_type=t, content=t,
        ))
    # security e compliance globais (module_id=NULL)
    for t in ("security", "compliance"):
        db_session.add(TestSpec(
            project_id=p.id, module_id=None, spec_type=t, content=t,
        ))
    await db_session.commit()

    rows = (await db_session.execute(
        select(TestSpec).where(TestSpec.project_id == p.id)
    )).scalars().all()
    types = {r.spec_type for r in rows}
    assert types == {"unit", "integration", "e2e", "security", "compliance"}
