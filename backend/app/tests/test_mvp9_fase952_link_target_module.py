"""MVP 9 Fase 9.5.2 — Upload com vínculo + transição automática + DELIVERABLE.

Cobre:
  - Extractor de module_id de PDF (3 estratégias: hidden field, metadata,
    footer regex; PDF não-template retorna None).
  - Endpoint de upload aceita target_module_id no form.
  - Service auto-extrai module_id de PDF de template GCA quando ausente.
  - Compartimentalização: módulo de outro projeto é ignorado silenciosamente.
  - Hook _link_target_module_after_pipeline transita módulo → adicionado
    e cria DELIVERABLE idempotente.
  - Transição respeita is_allowed_transition (concluido não regride).
  - DELIVERABLE não duplica em chamadas repetidas.
"""
import io
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG,
    ProjectDeliverable, Questionnaire,
)
from app.services.pdf_module_id_extractor import (
    HIDDEN_FIELD_NAME, SUBJECT_PREFIX, extract_module_id,
)
from app.services.template_pdf_service import generate_template_pdf
from app.services.ingestion_service import IngestionService
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed_project_with_module(db, *, module_status="sugerido"):
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"f952-{uuid4().hex[:6]}")
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc_seed = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="seed.docx", filename=f"{uuid4()}.docx",
        file_type="docx", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
    )
    db.add(doc_seed)
    await db.commit()
    a = ArguiderAnalysis(
        id=uuid4(), document_id=doc_seed.id, project_id=p.id,
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
        version=1, change_type="CREATE",
        ocg_data=json.dumps({"STACK_RECOMMENDATION": {"backend": {"enabled": True}}}),
    ))
    mc = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
        source="ocg_foundation", name="Conector DataJud HTTP",
        description="Cliente HTTP", module_type="backend_service",
        priority="high", status=module_status,
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
        details_json=json.dumps({
            "what_it_is": "x", "prerequisites": [],
            "missing_inputs": [], "input_examples": [],
            "suggested_template_sections": [],
        }),
    )
    db.add(mc)
    await db.commit()
    return p, mc, user


# ============================================================================
# Extractor de module_id
# ============================================================================

@pytest.mark.asyncio
async def test_extractor_le_hidden_field_de_template_gca(db_session):
    """PDF gerado pela Fase 9.5.1 tem hidden field — deve ser detectado."""
    p, mc, _ = await _seed_project_with_module(db_session)
    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)
    extracted = extract_module_id(pdf_bytes)
    assert extracted == mc.id


def test_extractor_pdf_normal_retorna_none():
    """PDF criado por outro app, sem nenhum dos 3 sinais → None."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, "documento qualquer")
    c.showPage()
    c.save()
    assert extract_module_id(buf.getvalue()) is None


def test_extractor_bytes_invalidos_nao_quebra():
    assert extract_module_id(b"not a pdf at all") is None
    assert extract_module_id(b"") is None


def test_extractor_le_metadata_subject_quando_field_ausente():
    """Estratégia 2: PDF que perdeu AcroForm mas mantém metadata."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    target_uuid = uuid4()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setSubject(f"{SUBJECT_PREFIX}{target_uuid}")
    c.drawString(72, 800, "doc com metadata")
    c.showPage()
    c.save()
    assert extract_module_id(buf.getvalue()) == target_uuid


def test_extractor_uuid_invalido_em_metadata_retorna_none():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setSubject(f"{SUBJECT_PREFIX}não-é-uuid")
    c.drawString(72, 800, "doc")
    c.showPage()
    c.save()
    assert extract_module_id(buf.getvalue()) is None


# ============================================================================
# Service: upload auto-extrai PDF
# ============================================================================

@pytest.mark.asyncio
async def test_upload_pdf_template_gca_auto_extrai_module_id(db_session):
    p, mc, user = await _seed_project_with_module(db_session)
    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)

    svc = IngestionService(db_session)
    with patch("asyncio.create_task"):  # impede _analyze_async em background
        result = await svc.upload_document(
            project_id=p.id, uploaded_by=user.id,
            file_bytes=pdf_bytes, original_filename="meu_template.pdf",
        )

    doc_id = result["document_id"]
    doc = await db_session.get(IngestedDocument, doc_id)
    assert doc.target_module_id == mc.id


@pytest.mark.asyncio
async def test_upload_pdf_normal_nao_seta_target(db_session):
    """PDF qualquer (sem ID GCA embutido) → target_module_id permanece None."""
    p, _, user = await _seed_project_with_module(db_session)
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, "doc avulso")
    c.showPage()
    c.save()

    svc = IngestionService(db_session)
    with patch("asyncio.create_task"):
        result = await svc.upload_document(
            project_id=p.id, uploaded_by=user.id,
            file_bytes=buf.getvalue(), original_filename="avulso.pdf",
        )

    doc_id = result["document_id"]
    doc = await db_session.get(IngestedDocument, doc_id)
    assert doc.target_module_id is None


@pytest.mark.asyncio
async def test_upload_target_explicito_prevalece(db_session):
    """target_module_id passado como arg sobrepõe extração do PDF."""
    p, mc, user = await _seed_project_with_module(db_session)
    # Cria outro módulo no mesmo projeto
    mc_other = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=mc.arguider_analysis_id,
        source="arguider", name="Outro item", description="",
        module_type="feature", priority="medium", status="sugerido",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
    )
    db_session.add(mc_other)
    await db_session.commit()

    pdf_bytes = await generate_template_pdf(db_session, p.id, mc.id)
    svc = IngestionService(db_session)
    with patch("asyncio.create_task"):
        result = await svc.upload_document(
            project_id=p.id, uploaded_by=user.id,
            file_bytes=pdf_bytes, original_filename="t.pdf",
            target_module_id=mc_other.id,  # explícito
        )
    doc = await db_session.get(IngestedDocument, result["document_id"])
    assert doc.target_module_id == mc_other.id


@pytest.mark.asyncio
async def test_upload_pdf_template_de_outro_projeto_ignora(db_session):
    """Se PDF veio de outro projeto, não viola compartimentalização §2.2."""
    p_a, mc_a, _ = await _seed_project_with_module(db_session)
    p_b, _, user_b = await _seed_project_with_module(db_session)

    # PDF do projeto A
    pdf_bytes = await generate_template_pdf(db_session, p_a.id, mc_a.id)

    # Upload no projeto B
    svc = IngestionService(db_session)
    with patch("asyncio.create_task"):
        result = await svc.upload_document(
            project_id=p_b.id, uploaded_by=user_b.id,
            file_bytes=pdf_bytes, original_filename="invadiu.pdf",
        )

    doc = await db_session.get(IngestedDocument, result["document_id"])
    assert doc.target_module_id is None  # bloqueado silenciosamente


# ============================================================================
# Hook: transição + DELIVERABLE
# ============================================================================

@pytest.mark.asyncio
async def test_link_transita_modulo_para_adicionado(db_session):
    p, mc, user = await _seed_project_with_module(db_session, module_status="aguardando_resposta")
    # Cria doc vinculado
    import hashlib
    h = hashlib.sha256(b"x").hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="resposta.pdf", filename=f"{uuid4()}.pdf",
        file_type="pdf", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
        target_module_id=mc.id,
    )
    db_session.add(doc)
    await db_session.commit()

    await IngestionService._link_target_module_in_session(
        db_session, doc.id, p.id,
    )
    await db_session.commit()

    # Refresh com session do teste — _link usa AsyncSessionLocal própria
    # (visível em queries fresh).
    refreshed = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.id == mc.id)
    )).scalar_one()
    assert refreshed.status == "adicionado"


@pytest.mark.asyncio
async def test_link_cria_deliverable_automatico(db_session):
    p, mc, user = await _seed_project_with_module(db_session, module_status="sugerido")
    import hashlib
    h = hashlib.sha256(b"y").hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="r.pdf", filename=f"{uuid4()}.pdf",
        file_type="pdf", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
        target_module_id=mc.id,
    )
    db_session.add(doc)
    await db_session.commit()

    await IngestionService._link_target_module_in_session(
        db_session, doc.id, p.id,
    )
    await db_session.commit()

    delivs = (await db_session.execute(
        select(ProjectDeliverable).where(ProjectDeliverable.project_id == p.id)
    )).scalars().all()
    assert len(delivs) == 1
    assert "Conector DataJud HTTP" in delivs[0].name
    assert delivs[0].status == "declared"
    assert delivs[0].kind.startswith("roadmap_module:")


@pytest.mark.asyncio
async def test_link_idempotente_nao_duplica_deliverable(db_session):
    """Chamadas repetidas não criam DELIVERABLE duplicado (UniqueConstraint)."""
    p, mc, user = await _seed_project_with_module(db_session)
    import hashlib
    h = hashlib.sha256(b"z").hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="r.pdf", filename=f"{uuid4()}.pdf",
        file_type="pdf", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
        target_module_id=mc.id,
    )
    db_session.add(doc)
    await db_session.commit()

    for _ in range(3):
        await IngestionService._link_target_module_in_session(
            db_session, doc.id, p.id,
        )
        await db_session.commit()

    delivs = (await db_session.execute(
        select(ProjectDeliverable).where(ProjectDeliverable.project_id == p.id)
    )).scalars().all()
    assert len(delivs) == 1


@pytest.mark.asyncio
async def test_link_doc_sem_target_no_op(db_session):
    """Doc sem target_module_id — hook não faz nada."""
    p, _, user = await _seed_project_with_module(db_session)
    import hashlib
    h = hashlib.sha256(b"a").hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="a.pdf", filename=f"{uuid4()}.pdf",
        file_type="pdf", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
        target_module_id=None,
    )
    db_session.add(doc)
    await db_session.commit()

    await IngestionService._link_target_module_in_session(
        db_session, doc.id, p.id,
    )
    await db_session.commit()

    delivs = (await db_session.execute(
        select(ProjectDeliverable).where(ProjectDeliverable.project_id == p.id)
    )).scalars().all()
    assert delivs == []


@pytest.mark.asyncio
async def test_link_transicao_proibida_nao_regride_concluido(db_session):
    """Item já concluido NÃO regride pra adicionado (regra dura do contrato)."""
    p, mc, user = await _seed_project_with_module(db_session, module_status="concluido")
    import hashlib
    h = hashlib.sha256(b"b").hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="b.pdf", filename=f"{uuid4()}.pdf",
        file_type="pdf", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
        target_module_id=mc.id,
    )
    db_session.add(doc)
    await db_session.commit()

    await IngestionService._link_target_module_in_session(
        db_session, doc.id, p.id,
    )
    await db_session.commit()

    refreshed = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.id == mc.id)
    )).scalar_one()
    assert refreshed.status == "concluido"  # não regrediu


# ============================================================================
# Mapeamento de categoria do módulo → category do DELIVERABLE
# ============================================================================

def test_deliverable_category_mapping():
    fn = IngestionService._deliverable_category_from_module
    assert fn("infrastructure") == "config"
    assert fn("deploy_pipeline") == "config"
    assert fn("observability") == "config"
    assert fn("middleware") == "code"
    assert fn("backend_service") == "code"
    assert fn("feature") == "code"
    assert fn("desconhecido") == "other"
    assert fn(None) == "other"
