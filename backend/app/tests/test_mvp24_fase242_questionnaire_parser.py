"""MVP 24 Fase 24.2 — Testes do detector/parser/aplicador de questionário respondido.

Cobre:
  - Detector: PDF com Q_<uuid> = True; PDF sem fields = False; PDF inválido = False.
  - Parser: text, dropdown, checkbox grid, outros+outros_text, Complementos.
  - Aplicador: marca resolved, cria IngestedDocument para Complementos,
    idempotente (item já resolved), compartimentalização (cross-project).
  - Upload hook: PDF de questionário resolve itens síncrono, sem disparar Celery.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pypdf
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.database import AsyncSessionLocal
from app.models.base import (
    ArguiderAnalysis, GatekeeperItem, IngestedDocument,
    Organization, Project, User,
)
from app.services.arguider_questionnaire_parser import (
    ItemAnswer, ParsedQuestionnaire,
    apply_parsed_responses,
    is_gca_questionnaire_pdf,
    parse_questionnaire_pdf,
)
from app.services.arguider_questionnaire_service import (
    QuestionnaireItem, generate_pdf,
)


def _item(uid: str, **kw) -> QuestionnaireItem:
    defaults = dict(
        id=uid, code="G001", item_type="gap",
        question="Qual proteção CWE?",
        section="security", input_type="text", options=(),
    )
    defaults.update(kw)
    return QuestionnaireItem(**defaults)  # type: ignore[arg-type]


# ─── Detector ─────────────────────────────────────────────────────────


def test_detector_pdf_vazio_retorna_false():
    # PDF mínimo válido sem AcroForm
    import reportlab.pdfgen.canvas as cv
    buf = io.BytesIO()
    c = cv.Canvas(buf)
    c.drawString(100, 100, "hello")
    c.save()
    assert is_gca_questionnaire_pdf(buf.getvalue()) is False


def test_detector_pdf_do_gca_retorna_true():
    pdf = generate_pdf(
        project_name="T", section="security",
        items=[_item("abc-123")],
    )
    assert is_gca_questionnaire_pdf(pdf) is True


def test_detector_bytes_invalidos_retorna_false():
    assert is_gca_questionnaire_pdf(b"not a pdf") is False


# ─── Parser ───────────────────────────────────────────────────────────


def _fill_pdf(pdf_bytes: bytes, updates: dict[str, str]) -> bytes:
    """Preenche fields de um PDF AcroForm e retorna bytes novos."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    writer = pypdf.PdfWriter(clone_from=reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, updates)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_parser_text_field():
    pdf = generate_pdf(
        project_name="T", section="security",
        items=[_item("abc-123", input_type="text")],
    )
    filled = _fill_pdf(pdf, {"Q_abc-123": "Minha resposta livre"})
    parsed = parse_questionnaire_pdf(filled)
    assert len(parsed.answers) == 1
    a = parsed.answers[0]
    assert a.item_id == "abc-123"
    assert a.text == "Minha resposta livre"
    assert a.selected == ()


def test_parser_complements():
    pdf = generate_pdf(project_name="T", section="security", items=[])
    filled = _fill_pdf(pdf, {"Q__COMPLEMENTS": "Info adicional relevante"})
    parsed = parse_questionnaire_pdf(filled)
    assert parsed.complements == "Info adicional relevante"


def test_parser_multi_checkboxes():
    pdf = generate_pdf(
        project_name="T", section="security",
        items=[_item("xyz", input_type="multi", options=("A", "B", "C"))],
    )
    filled = _fill_pdf(pdf, {
        "Q_xyz__cb_0": "/Yes",
        "Q_xyz__cb_2": "/Yes",
    })
    parsed = parse_questionnaire_pdf(filled)
    assert len(parsed.answers) == 1
    a = parsed.answers[0]
    assert set(a.selected) == {"__index__0", "__index__2"}


def test_parser_outros_preenchido():
    pdf = generate_pdf(
        project_name="T", section="security",
        items=[_item("xyz", input_type="multi", options=("A", "B", "C"))],
    )
    filled = _fill_pdf(pdf, {
        "Q_xyz__cb_outros": "/Yes",
        "Q_xyz__outros": "Algo fora da lista",
    })
    parsed = parse_questionnaire_pdf(filled)
    a = parsed.answers[0]
    assert a.outros == "Algo fora da lista"


def test_parser_ignora_fields_fora_do_contrato():
    import reportlab.pdfgen.canvas as cv
    buf = io.BytesIO()
    c = cv.Canvas(buf)
    c.acroForm.textfield(name="NOT_CANONICAL", x=100, y=100, width=100, height=20)
    c.showPage()
    c.save()
    parsed = parse_questionnaire_pdf(buf.getvalue())
    assert parsed.answers == ()
    assert parsed.complements is None


# ─── Aplicador (integração DB) ───────────────────────────────────────


async def _mk_user_proj_analysis(session):
    uniq = uuid4().hex[:6]
    user = User(
        id=uuid4(), email=f"p242-{uniq}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="P242", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    org = Organization(
        id=uuid4(), name=f"P242-Org-{uniq}", slug=f"p242-{uniq}",
        owner_id=user.id, is_active=True, created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name=f"P242 {uniq}", slug=f"p242-p-{uniq}",
        description="t", deliverable_type="web_app",
        status="active", created_at=datetime.utcnow(),
    )
    session.add(project)
    doc = IngestedDocument(
        id=uuid4(), project_id=project.id,
        filename=f"{uuid4().hex}.pdf", original_filename="req.pdf",
        file_type="pdf", file_hash="0" * 64, file_size_bytes=100,
        uploaded_by=user.id,
    )
    session.add(doc)
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=project.id,
        llm_model="test-model", tokens_used=0, latency_ms=1,
    )
    session.add(analysis)
    await session.flush()
    return user, project, analysis


@pytest.mark.asyncio
async def test_aplicador_resolve_item_text(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = GatekeeperItem(
        id=uuid4(), project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type="gap", item_id_in_analysis="G001",
        item_data=json.dumps({"text": "Qual?", "suggestions": ["a"]}),
        status="pending",
    )
    db_session.add(item)
    await db_session.flush()

    parsed = ParsedQuestionnaire(answers=(
        ItemAnswer(item_id=str(item.id), text="resposta do GP"),
    ))
    report = await apply_parsed_responses(
        db_session, project.id, user.id, parsed,
    )
    assert report.applied == 1
    await db_session.refresh(item)
    assert item.status == "resolved"
    assert item.resolved_by == user.id
    assert "resposta do GP" in (item.resolution_note or "")


@pytest.mark.asyncio
async def test_aplicador_materializa_checkbox_indices(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = GatekeeperItem(
        id=uuid4(), project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type="gap", item_id_in_analysis="G002",
        item_data=json.dumps({
            "text": "Quais CWEs?",
            "suggestions": ["CWE-79", "CWE-89", "CWE-798"],
        }),
        status="pending",
    )
    db_session.add(item)
    await db_session.flush()

    parsed = ParsedQuestionnaire(answers=(
        ItemAnswer(
            item_id=str(item.id),
            selected=("__index__0", "__index__2"),
            outros="CWE-22",
        ),
    ))
    report = await apply_parsed_responses(
        db_session, project.id, user.id, parsed,
    )
    assert report.applied == 1
    await db_session.refresh(item)
    note = item.resolution_note or ""
    assert "CWE-79" in note
    assert "CWE-798" in note
    assert "CWE-22" in note  # outros


@pytest.mark.asyncio
async def test_aplicador_nao_sobrescreve_resolved(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = GatekeeperItem(
        id=uuid4(), project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type="gap", item_id_in_analysis="G003",
        item_data="{}", status="resolved",
    )
    db_session.add(item)
    await db_session.flush()

    parsed = ParsedQuestionnaire(answers=(
        ItemAnswer(item_id=str(item.id), text="tentativa tardia"),
    ))
    report = await apply_parsed_responses(
        db_session, project.id, user.id, parsed,
    )
    assert report.applied == 0
    assert report.skipped_blank == 1


@pytest.mark.asyncio
async def test_aplicador_rejeita_cross_project(db_session: AsyncSession):
    user_a, project_a, analysis_a = await _mk_user_proj_analysis(db_session)
    user_b, project_b, _ = await _mk_user_proj_analysis(db_session)

    item = GatekeeperItem(
        id=uuid4(), project_id=project_b.id,  # item de OUTRO projeto
        arguider_analysis_id=analysis_a.id,
        item_type="gap", item_id_in_analysis="G004",
        item_data="{}", status="pending",
    )
    db_session.add(item)
    await db_session.flush()

    parsed = ParsedQuestionnaire(answers=(
        ItemAnswer(item_id=str(item.id), text="cross-tenant"),
    ))
    # Aplica no projeto A — não pode tocar item do B
    report = await apply_parsed_responses(
        db_session, project_a.id, user_a.id, parsed,
    )
    assert report.skipped_not_found == 1
    assert report.applied == 0
    await db_session.refresh(item)
    assert item.status == "pending"


@pytest.mark.asyncio
async def test_aplicador_cria_document_para_complements(db_session: AsyncSession):
    user, project, _ = await _mk_user_proj_analysis(db_session)
    parsed = ParsedQuestionnaire(
        answers=(),
        complements="Observações livres do GP",
    )
    report = await apply_parsed_responses(
        db_session, project.id, user.id, parsed,
    )
    assert report.complements_document_id is not None
    doc = await db_session.get(IngestedDocument, UUID(report.complements_document_id))
    assert doc is not None
    assert doc.document_category == "arguider_complements"
    assert doc.file_type == "txt"
    assert doc.arguider_status == "pending"


# ─── Hook na Ingestão (integração) ───────────────────────────────────


@pytest.mark.asyncio
async def test_upload_detecta_questionario_e_pula_pipeline():
    """PDF do questionário GCA é aplicado síncronamente; Celery NÃO é acionado."""
    from app.services.ingestion_service import IngestionService

    async with AsyncSessionLocal() as session:
        async with session.begin():
            user, project, analysis = await _mk_user_proj_analysis(session)
            item = GatekeeperItem(
                id=uuid4(), project_id=project.id,
                arguider_analysis_id=analysis.id,
                item_type="gap", item_id_in_analysis="G010",
                item_data=json.dumps({"text": "Qual stack?"}),
                status="pending",
            )
            session.add(item)
            await session.flush()
            item_id = item.id
            project_id = project.id
            user_id = user.id

    pdf = generate_pdf(
        project_name="T", section="governance",
        items=[_item(str(item_id), input_type="text")],
    )
    filled = _fill_pdf(pdf, {f"Q_{item_id}": "FastAPI + React"})

    async with AsyncSessionLocal() as session:
        service = IngestionService(session)
        with patch("app.tasks.pipeline.pipeline_ingest_task.delay") as mock_task:
            result = await service.upload_document(
                project_id=project_id,
                uploaded_by=user_id,
                file_bytes=filled,
                original_filename="questionario.pdf",
                content_type="application/pdf",
            )
        assert "questionnaire_applied" in result
        assert result["questionnaire_applied"]["applied"] == 1
        assert not mock_task.called, "Celery não deve ser acionado para PDF do GCA"

    # Item agora está resolved
    async with AsyncSessionLocal() as session:
        fresh = await session.get(GatekeeperItem, item_id)
        assert fresh.status == "resolved"
        assert fresh.resolved_by == user_id
