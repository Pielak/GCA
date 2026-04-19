"""MVP 9 Fase 9.5.1 — Template PDF AcroForm gerado por item.

Cobre:
  - Render produz PDF válido com AcroForm fields editáveis.
  - module_id embutido em hidden field + metadata pra detecção no upload.
  - Cabeçalho contém nome, categoria, status do item.
  - Seções vêm do details_json (Fase 9.2): fields com from_ocg viram texto
    fixo verde; sem from_ocg viram AcroForm field amarelo editável.
  - Sempre tem campo livre "notas adicionais".
  - Auto-gera details se ausente (chama Fase 9.2).
  - Compartimentalização: módulo de outro projeto retorna 404.
"""
import io
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG, Questionnaire,
)
from app.services.template_pdf_service import (
    HIDDEN_MODULE_ID_FIELD,
    generate_template_pdf,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed_module_with_details(db, details_dict=None):
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"f951-{uuid4().hex[:6]}")
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="t.docx", filename=f"{uuid4()}.docx",
        file_type="docx", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=p.id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]), show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]), improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]), ocg_fields_to_update=json.dumps([]),
        llm_model="x", tokens_used=0, latency_ms=0,
    )
    db.add(analysis)
    await db.commit()
    q = Questionnaire(
        id=uuid4(), project_id=p.id, gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    db.add(q)
    await db.commit()
    db.add(OCG(
        id=uuid4(), project_id=p.id, questionnaire_id=q.id,
        version=1, change_type="CREATE",
        ocg_data=json.dumps({"STACK_RECOMMENDATION": {"backend": {"enabled": True}}}),
    ))
    mc = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=analysis.id,
        source="ocg_foundation", name="Esqueleto do Backend",
        description="API skeleton em FastAPI", module_type="backend_service",
        priority="high", status="sugerido",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
        details_json=json.dumps(details_dict) if details_dict else None,
    )
    db.add(mc)
    await db.commit()
    return p, mc


def _parse_pdf(pdf_bytes):
    from pypdf import PdfReader
    return PdfReader(io.BytesIO(pdf_bytes))


# ============================================================================
# Render
# ============================================================================

@pytest.mark.asyncio
async def test_pdf_gerado_com_metadata_module_id(db_session):
    details = {
        "what_it_is": "Configurar projeto FastAPI inicial",
        "prerequisites": ["Python 3.11"],
        "missing_inputs": ["URL do banco"],
        "input_examples": [".env.example"],
        "suggested_template_sections": [],
    }
    p, mc = await _seed_module_with_details(db_session, details)

    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)

    assert pdf_bytes.startswith(b"%PDF-"), "Não é PDF válido"

    reader = _parse_pdf(pdf_bytes)
    meta = reader.metadata
    assert meta is not None
    # module_id no Subject
    assert f"gca-module:{mc.id}" in str(meta.subject)
    # module_id nas keywords
    assert str(mc.id) in str(meta.get("/Keywords", ""))


@pytest.mark.asyncio
async def test_pdf_tem_hidden_field_module_id(db_session):
    """O field _gca_module_id é o que a Fase 9.5.2 vai parsear."""
    details = {
        "what_it_is": "x", "prerequisites": [], "missing_inputs": [],
        "input_examples": [], "suggested_template_sections": [],
    }
    p, mc = await _seed_module_with_details(db_session, details)
    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)

    reader = _parse_pdf(pdf_bytes)
    fields = reader.get_form_text_fields() or {}
    assert HIDDEN_MODULE_ID_FIELD in fields
    assert fields[HIDDEN_MODULE_ID_FIELD] == str(mc.id)


@pytest.mark.asyncio
async def test_pdf_tem_acroform_fields_para_lacunas(db_session):
    """Cada field sem from_ocg vira AcroForm editável."""
    details = {
        "what_it_is": "x",
        "prerequisites": [], "missing_inputs": [], "input_examples": [],
        "suggested_template_sections": [
            {"section": "Banco de Dados", "fields": [
                {"name": "DB_URL", "from_ocg": None, "hint": "URL do PostgreSQL"},
                {"name": "DB_USER", "from_ocg": "postgres", "hint": None},
            ]},
        ],
    }
    p, mc = await _seed_module_with_details(db_session, details)
    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)

    reader = _parse_pdf(pdf_bytes)
    fields = reader.get_form_text_fields() or {}
    # DB_URL é lacuna → tem field editável
    db_url_keys = [k for k in fields if "db_url" in k.lower()]
    assert db_url_keys, f"sem AcroForm field pra DB_URL; campos: {list(fields.keys())}"
    # DB_USER tem from_ocg='postgres' → NÃO deve ser editável (sem field, é texto fixo)
    db_user_keys = [k for k in fields if "db_user" in k.lower()]
    assert not db_user_keys, f"DB_USER tinha from_ocg, não devia ser editável"


@pytest.mark.asyncio
async def test_pdf_tem_campo_livre_notas_sempre(db_session):
    """Independente do detalhamento, oferece campo livre."""
    details = {
        "what_it_is": "x", "prerequisites": [], "missing_inputs": [],
        "input_examples": [], "suggested_template_sections": [],
    }
    p, mc = await _seed_module_with_details(db_session, details)
    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)

    reader = _parse_pdf(pdf_bytes)
    fields = reader.get_form_text_fields() or {}
    notas_keys = [k for k in fields if "notas_livres" in k.lower()]
    assert notas_keys, "sem campo livre de notas"


@pytest.mark.asyncio
async def test_pdf_chama_geracao_quando_details_ausente(db_session):
    """Se details_json é None, dispara Fase 9.2 (Ollama)."""
    p, mc = await _seed_module_with_details(db_session, details_dict=None)
    fake_details = {
        "what_it_is": "gerado on-demand",
        "prerequisites": [], "missing_inputs": [],
        "input_examples": [], "suggested_template_sections": [],
    }
    with patch(
        "app.services.template_pdf_service._force_generate",
        new=AsyncMock(return_value=fake_details),
    ) as gen:
        pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)
    assert gen.await_count == 1
    assert pdf_bytes.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_pdf_compartimentalizacao_modulo_outro_projeto(db_session):
    """Módulo de outro projeto retorna ValueError (caller traduz pra 404)."""
    p_a, mc_a = await _seed_module_with_details(db_session, {
        "what_it_is": "x", "prerequisites": [], "missing_inputs": [],
        "input_examples": [], "suggested_template_sections": [],
    })
    p_b, _ = await _seed_module_with_details(db_session, {
        "what_it_is": "x", "prerequisites": [], "missing_inputs": [],
        "input_examples": [], "suggested_template_sections": [],
    })
    with pytest.raises(ValueError):
        await generate_template_pdf(db_session, p_b.id, mc_a.id)


@pytest.mark.asyncio
async def test_pdf_modulo_inexistente_levanta_value_error(db_session):
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="f951-noexist")
    with pytest.raises(ValueError):
        await generate_template_pdf(db_session, p.id, uuid4())


@pytest.mark.asyncio
async def test_pdf_details_corrompido_regenera(db_session):
    """details_json malformado dispara regeneração via Fase 9.2."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="f951-corrupt")
    import hashlib
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="t.docx", filename=f"{uuid4()}.docx",
        file_type="docx",
        file_hash=hashlib.sha256(f"{uuid4()}".encode()).hexdigest(),
        file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
    )
    db_session.add(doc)
    await db_session.commit()
    a = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=p.id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]), show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]), improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]), ocg_fields_to_update=json.dumps([]),
        llm_model="x", tokens_used=0, latency_ms=0,
    )
    db_session.add(a)
    await db_session.commit()
    mc = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
        source="arguider", name="X", description="x", module_type="feature",
        priority="medium", status="sugerido",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
        details_json="{not valid json",
    )
    db_session.add(mc)
    await db_session.commit()

    fake = {
        "what_it_is": "regerado", "prerequisites": [],
        "missing_inputs": [], "input_examples": [],
        "suggested_template_sections": [],
    }
    with patch(
        "app.services.template_pdf_service._force_generate",
        new=AsyncMock(return_value=fake),
    ) as gen:
        pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)
    assert gen.await_count == 1
    assert pdf_bytes.startswith(b"%PDF-")
