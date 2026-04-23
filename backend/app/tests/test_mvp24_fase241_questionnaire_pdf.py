"""MVP 24 Fase 24.1 — Testes do `arguider_questionnaire_service`.

Cobre:
  - Classificação por prefixo RNF-* (S=security, C=legal, P/A=capacity).
  - Classificação por pillar e por keyword.
  - Decisão de shape: options 2=single, 3+=multi, suggestions=multi, vazio=text.
  - Agrupamento carrega só pending e distribui corretamente.
  - Geração de PDF com items preenchidos + PDF vazio (seção sem gaps).
  - IDs canônicos `Q_<uuid>` presentes nos form fields.
  - Campo `Q__COMPLEMENTS` sempre presente (contrato duro).
  - Endpoint HTTP retorna PDF + rejeita section inválida + 404 em projeto inexistente.
"""
from __future__ import annotations

import io
import json
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import pypdf
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.database import AsyncSessionLocal
from app.main import app
from app.models.base import (
    ArguiderAnalysis, GatekeeperItem, IngestedDocument,
    Organization, Project, Questionnaire, User,
)
from app.services.arguider_questionnaire_service import (
    CANONICAL_SECTIONS,
    QuestionnaireItem,
    classify_item,
    decide_input_shape,
    generate_pdf,
    generate_section_pdf,
    group_pending_items,
)


# ─── Pure helpers (sem DB) ────────────────────────────────────────────


class TestClassifyItem:
    def test_rnf_s_is_security(self):
        assert classify_item("RNF-S-001", {}) == "security"

    def test_rnf_c_is_legal(self):
        assert classify_item("RNF-C-001", {}) == "legal"

    def test_rnf_p_is_capacity(self):
        assert classify_item("RNF-P-001", {}) == "capacity"

    def test_rnf_a_is_capacity(self):
        assert classify_item("RNF-A-001", {}) == "capacity"

    def test_pillar_p2_is_legal(self):
        assert classify_item("G001", {"pillar": "P2"}) == "legal"

    def test_pillar_p7_is_security(self):
        assert classify_item("G001", {"pillar": "P7"}) == "security"

    def test_pillar_p5_is_architecture(self):
        assert classify_item("G001", {"pillar": "P5"}) == "architecture"

    def test_keyword_lgpd_overrides_to_legal(self):
        assert classify_item("G001", {"text": "tratar LGPD"}) == "legal"

    def test_keyword_cwe_overrides_to_security(self):
        assert classify_item("G001", {"text": "mitigar CWE-89"}) == "security"

    def test_keyword_latency_overrides_to_capacity(self):
        assert classify_item("G001", {"text": "latência alta no endpoint"}) == "capacity"

    def test_keyword_architecture_classifies_as_architecture(self):
        assert classify_item("G001", {"description": "revisar padrão arquitetural"}) == "architecture"

    def test_fallback_is_governance(self):
        assert classify_item("G001", {"text": "decisão sobre priorização"}) == "governance"


class TestDecideInputShape:
    def test_options_two_is_single(self):
        shape, opts = decide_input_shape({"options": ["Sim", "Não"]})
        assert shape == "single"
        assert opts == ("Sim", "Não")

    def test_options_three_is_multi(self):
        shape, opts = decide_input_shape({"options": ["A", "B", "C"]})
        assert shape == "multi"
        assert opts == ("A", "B", "C")

    def test_suggestions_is_multi(self):
        shape, opts = decide_input_shape({"suggestions": ["CWE-79", "CWE-89"]})
        assert shape == "multi"
        assert opts == ("CWE-79", "CWE-89")

    def test_empty_is_text(self):
        shape, opts = decide_input_shape({})
        assert shape == "text"
        assert opts == ()

    def test_options_non_list_ignored(self):
        shape, _ = decide_input_shape({"options": "invalid"})
        assert shape == "text"


# ─── PDF rendering (sem DB) ───────────────────────────────────────────


def _make_item(
    *, id: str = "item-uuid-1", code: str = "G001",
    section: str = "security", input_type: str = "text",
    options: tuple[str, ...] = (),
) -> QuestionnaireItem:
    return QuestionnaireItem(
        id=id, code=code, item_type="gap",
        question="Qual proteção CWE é obrigatória?",
        section=section,  # type: ignore[arg-type]
        input_type=input_type,  # type: ignore[arg-type]
        options=options,
    )


class TestGeneratePdf:
    def test_empty_section_still_produces_valid_pdf(self):
        pdf = generate_pdf(
            project_name="Test", section="security", items=[],
        )
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        fields = reader.get_fields() or {}
        # Complementos sempre presente
        assert "Q__COMPLEMENTS" in fields

    def test_text_item_produces_canonical_field(self):
        item = _make_item(id="abc123", input_type="text")
        pdf = generate_pdf(
            project_name="Test", section="security", items=[item],
        )
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        fields = reader.get_fields() or {}
        assert "Q_abc123" in fields
        assert "Q__COMPLEMENTS" in fields

    def test_single_choice_produces_dropdown_field(self):
        item = _make_item(
            id="abc123", input_type="single", options=("Sim", "Não"),
        )
        pdf = generate_pdf(
            project_name="Test", section="security", items=[item],
        )
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        fields = reader.get_fields() or {}
        assert "Q_abc123" in fields

    def test_multi_choice_produces_checkboxes_with_index(self):
        item = _make_item(
            id="abc123", input_type="multi",
            options=("CWE-79", "CWE-89", "CWE-798"),
        )
        pdf = generate_pdf(
            project_name="Test", section="security", items=[item],
        )
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        fields = reader.get_fields() or {}
        # Um checkbox por opção + o cb_outros
        assert "Q_abc123__cb_0" in fields
        assert "Q_abc123__cb_1" in fields
        assert "Q_abc123__cb_2" in fields
        assert "Q_abc123__cb_outros" in fields
        assert "Q_abc123__outros" in fields  # textfield do "Outros"

    def test_all_fields_have_canonical_prefix(self):
        """Contrato duro do parser 24.2: todo field começa com 'Q_'."""
        items = [
            _make_item(id="x1", input_type="text"),
            _make_item(id="x2", input_type="multi", options=("a", "b", "c")),
        ]
        pdf = generate_pdf(project_name="T", section="legal", items=items)
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        fields = reader.get_fields() or {}
        for name in fields.keys():
            assert name.startswith("Q_"), f"field fora do contrato: {name}"


# ─── DB integration ───────────────────────────────────────────────────


async def _make_admin(session) -> User:
    uid = uuid4()
    u = User(
        id=uid, email=f"q241-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="Q241 Tester", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(u)
    await session.flush()
    return u


async def _make_project(session, user) -> Project:
    uniq = uuid4().hex[:6]
    org = Organization(
        id=uuid4(), name=f"Q241-Org-{uniq}", slug=f"q241-{uniq}",
        owner_id=user.id, is_active=True, created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id, name=f"Q241 Proj {uniq}",
        slug=f"q241-p-{uniq}", description="t",
        deliverable_type="web_app", status="active",
        created_at=datetime.utcnow(),
    )
    session.add(project)
    await session.flush()
    return project


async def _make_analysis(session, project, user) -> ArguiderAnalysis:
    doc = IngestedDocument(
        id=uuid4(), project_id=project.id,
        filename=f"{uuid4().hex}.pdf", original_filename="req.pdf",
        file_type="pdf", file_hash="0" * 64, file_size_bytes=100,
        uploaded_by=user.id,
    )
    session.add(doc)
    await session.flush()
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=project.id,
        llm_model="test-model", tokens_used=0, latency_ms=1,
    )
    session.add(analysis)
    await session.flush()
    return analysis


async def _add_gk_item(
    session, project, analysis, *,
    code: str, item_type: str = "gap",
    data: dict, status: str = "pending",
) -> GatekeeperItem:
    item = GatekeeperItem(
        id=uuid4(), project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type=item_type,
        item_id_in_analysis=code,
        item_data=json.dumps(data, ensure_ascii=False),
        status=status,
    )
    session.add(item)
    await session.flush()
    return item


@pytest.mark.asyncio
async def test_group_pending_items_distributes_canonically(db_session: AsyncSession):
    user = await _make_admin(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_analysis(db_session, project, user)

    await _add_gk_item(db_session, project, analysis,
        code="RNF-S-001", data={"question": "Vault?"})
    await _add_gk_item(db_session, project, analysis,
        code="RNF-P-001", data={"question": "Latência?"})
    await _add_gk_item(db_session, project, analysis,
        code="RNF-C-001", data={"question": "LGPD?"})
    await _add_gk_item(db_session, project, analysis,
        code="G001", data={"pillar": "P5", "text": "revisar arquitetura"})
    await _add_gk_item(db_session, project, analysis,
        code="G002", data={"text": "definir priorização do backlog"})
    # item resolved não deve entrar
    await _add_gk_item(db_session, project, analysis,
        code="G099", data={"text": "resolvido"}, status="resolved")

    await db_session.flush()

    buckets = await group_pending_items(db_session, project.id)

    assert set(buckets.keys()) == set(CANONICAL_SECTIONS)
    assert len(buckets["security"]) == 1
    assert len(buckets["capacity"]) == 1
    assert len(buckets["legal"]) == 1
    assert len(buckets["architecture"]) == 1
    assert len(buckets["governance"]) == 1

    # item resolved foi excluído
    all_codes = {i.code for s in buckets.values() for i in s}
    assert "G099" not in all_codes


@pytest.mark.asyncio
async def test_generate_section_pdf_integracao(db_session: AsyncSession):
    user = await _make_admin(db_session)
    project = await _make_project(db_session, user)
    analysis = await _make_analysis(db_session, project, user)

    await _add_gk_item(db_session, project, analysis,
        code="RNF-S-001",
        data={
            "question": "Quais CWEs o projeto deve proteger?",
            "suggestions": ["CWE-79", "CWE-89", "CWE-798"],
        })
    await db_session.flush()

    pdf = await generate_section_pdf(db_session, project.id, "security")
    assert pdf is not None
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    fields = reader.get_fields() or {}
    assert "Q__COMPLEMENTS" in fields
    # Multi: 3 checkboxes + outros
    uuid_item = str(next(iter(
        [i for i in (
            [gk.id for gk in (await db_session.execute(__import__('sqlalchemy').select(GatekeeperItem).where(GatekeeperItem.project_id == project.id))).scalars().all()]
        )]
    )))
    assert f"Q_{uuid_item}__cb_0" in fields
    assert f"Q_{uuid_item}__cb_outros" in fields


@pytest.mark.asyncio
async def test_generate_section_pdf_projeto_inexistente(db_session: AsyncSession):
    pdf = await generate_section_pdf(db_session, uuid4(), "security")
    assert pdf is None


# ─── Endpoint HTTP ────────────────────────────────────────────────────


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_endpoint_retorna_pdf_da_secao():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project(session, user)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/arguider/questionnaire.pdf",
            params={"section": "security"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_endpoint_rejeita_section_invalida():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)
            project = await _make_project(session, user)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{project.id}/arguider/questionnaire.pdf",
            params={"section": "foobar"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_endpoint_404_projeto_inexistente():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await _make_admin(session)

    token = create_access_token(data={"sub": str(user.id)})
    async with _client() as c:
        r = await c.get(
            f"/api/v1/projects/{uuid4()}/arguider/questionnaire.pdf",
            params={"section": "security"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404
