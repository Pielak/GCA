"""MVP 24 Fase 24.3 — Testes de dívida informacional.

Cobre:
  - PDF carrega Q__OFFERED_IDS (CSV dos UUIDs).
  - Parser devolve offered_ids e calcula skipped_ids corretamente.
  - generate_section_pdf incrementa offers_count em cada item persistido.
  - bump_skipped incrementa skip_count em pending items do próprio projeto.
  - bump_skipped rejeita cross-project (compartimentalização §2.2).
  - skip >= THRESHOLD cria BacklogItem category='info_debt' priority='critical'.
  - Segunda chamada com mesmo item não duplica BacklogItem (idempotente).
  - Ordenação de group_pending_items: skip_count DESC no topo.
  - Aplicador integra: skipped_ids → bump + promoted_ids no report.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from uuid import UUID, uuid4

import pypdf
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis, BacklogItem, GatekeeperItem, IngestedDocument,
    Organization, Project, User,
)
from app.services.arguider_questionnaire_parser import (
    ItemAnswer, ParsedQuestionnaire,
    apply_parsed_responses,
    parse_questionnaire_pdf,
)
from app.services.arguider_questionnaire_service import (
    QuestionnaireItem, bump_offers_count, generate_pdf, generate_section_pdf,
    group_pending_items,
)
from app.services.info_debt_service import (
    INFO_DEBT_THRESHOLD, INFO_DEBT_TITLE_PREFIX, bump_skipped,
)


async def _mk_user_proj_analysis(session):
    uniq = uuid4().hex[:6]
    user = User(
        id=uuid4(), email=f"p243-{uniq}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="P243", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    org = Organization(
        id=uuid4(), name=f"P243-Org-{uniq}", slug=f"p243-{uniq}",
        owner_id=user.id, is_active=True, created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name=f"P243 {uniq}", slug=f"p243-p-{uniq}",
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


async def _mk_pending_item(
    session, project, analysis, code: str, data: dict | None = None,
) -> GatekeeperItem:
    item = GatekeeperItem(
        id=uuid4(), project_id=project.id,
        arguider_analysis_id=analysis.id,
        item_type="gap", item_id_in_analysis=code,
        item_data=json.dumps(data or {"text": f"Pergunta {code}"}, ensure_ascii=False),
        status="pending",
    )
    session.add(item)
    await session.flush()
    return item


# ─── PDF carrega offered_ids ──────────────────────────────────────────


def test_pdf_carrega_offered_ids_hidden_field():
    items = [
        QuestionnaireItem(
            id="abc-1", code="G001", item_type="gap",
            question="Q1?", section="security",
            input_type="text",
        ),
        QuestionnaireItem(
            id="abc-2", code="G002", item_type="gap",
            question="Q2?", section="security",
            input_type="text",
        ),
    ]
    pdf = generate_pdf(project_name="T", section="security", items=items)
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    fields = reader.get_fields() or {}
    assert "Q__OFFERED_IDS" in fields
    # Value é CSV
    val = fields["Q__OFFERED_IDS"].get("/V") or getattr(fields["Q__OFFERED_IDS"], "value", "")
    assert "abc-1" in str(val)
    assert "abc-2" in str(val)


def test_parser_extrai_offered_e_calcula_skipped():
    items = [
        QuestionnaireItem(
            id="abc-1", code="G001", item_type="gap",
            question="Q1?", section="security", input_type="text",
        ),
        QuestionnaireItem(
            id="abc-2", code="G002", item_type="gap",
            question="Q2?", section="security", input_type="text",
        ),
        QuestionnaireItem(
            id="abc-3", code="G003", item_type="gap",
            question="Q3?", section="security", input_type="text",
        ),
    ]
    pdf = generate_pdf(project_name="T", section="security", items=items)
    # Preenche só 1 dos 3
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    writer = pypdf.PdfWriter(clone_from=reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, {"Q_abc-2": "respondi só essa"})
    out = io.BytesIO()
    writer.write(out)

    parsed = parse_questionnaire_pdf(out.getvalue())
    assert set(parsed.offered_ids) == {"abc-1", "abc-2", "abc-3"}
    assert parsed.answered_ids == {"abc-2"}
    assert parsed.skipped_ids == {"abc-1", "abc-3"}


# ─── bump_offers_count ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bump_offers_count_incrementa_contador(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending_item(db_session, project, analysis, "G100")

    await bump_offers_count(db_session, [str(item.id)])
    await bump_offers_count(db_session, [str(item.id)])
    await db_session.refresh(item)
    data = json.loads(item.item_data)
    assert data["offers_count"] == 2


@pytest.mark.asyncio
async def test_bump_offers_count_ignora_uuid_invalido(db_session: AsyncSession):
    await bump_offers_count(db_session, ["not-a-uuid", "another-garbage"])
    # Não explode; não há o que verificar além disso.


# ─── bump_skipped + info_debt backlog ────────────────────────────────


@pytest.mark.asyncio
async def test_bump_skipped_incrementa_skip_count(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending_item(db_session, project, analysis, "G101")

    await bump_skipped(db_session, project.id, [str(item.id)])
    await db_session.refresh(item)
    data = json.loads(item.item_data)
    assert data["skip_count"] == 1

    # Ainda não criou backlog (abaixo do threshold)
    backlog = (await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == project.id)
    )).scalars().all()
    assert len(backlog) == 0


@pytest.mark.asyncio
async def test_bump_skipped_promove_info_debt_no_threshold(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending_item(
        db_session, project, analysis, "G102",
        data={"question": "Qual a stack canônica?"},
    )

    # Round 1: skip = 1 → ainda não promove
    await bump_skipped(db_session, project.id, [str(item.id)])
    backlog_1 = (await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == project.id)
    )).scalars().all()
    assert len(backlog_1) == 0

    # Round 2: skip = 2 (threshold) → promove
    promoted = await bump_skipped(db_session, project.id, [str(item.id)])
    assert item.id in promoted

    backlog_2 = (await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == project.id)
    )).scalars().all()
    assert len(backlog_2) == 1
    b = backlog_2[0]
    assert b.category == "info_debt"
    assert b.priority == "critical"
    assert b.source == "arguider"
    assert b.title.startswith(INFO_DEBT_TITLE_PREFIX)
    assert "G102" in b.title
    assert "Qual a stack canônica?" in (b.description or "")


@pytest.mark.asyncio
async def test_bump_skipped_idempotente_sem_duplicar(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending_item(db_session, project, analysis, "G103")

    # 3 rounds sequenciais
    for _ in range(3):
        await bump_skipped(db_session, project.id, [str(item.id)])

    backlog = (await db_session.execute(
        select(BacklogItem).where(
            BacklogItem.project_id == project.id,
            BacklogItem.category == "info_debt",
        )
    )).scalars().all()
    assert len(backlog) == 1  # não duplica


@pytest.mark.asyncio
async def test_bump_skipped_rejeita_cross_project(db_session: AsyncSession):
    user_a, project_a, analysis_a = await _mk_user_proj_analysis(db_session)
    user_b, project_b, analysis_b = await _mk_user_proj_analysis(db_session)
    item_b = await _mk_pending_item(db_session, project_b, analysis_b, "G104")

    # Tenta bumpar item do projeto B usando project_id de A
    await bump_skipped(db_session, project_a.id, [str(item_b.id)])
    await db_session.refresh(item_b)
    data = json.loads(item_b.item_data)
    assert data.get("skip_count", 0) == 0

    # E nenhum backlog foi criado em A
    backlog_a = (await db_session.execute(
        select(BacklogItem).where(BacklogItem.project_id == project_a.id)
    )).scalars().all()
    assert backlog_a == []


@pytest.mark.asyncio
async def test_bump_skipped_ignora_items_ja_resolvidos(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    item = await _mk_pending_item(db_session, project, analysis, "G105")
    item.status = "resolved"
    db_session.add(item)
    await db_session.flush()

    await bump_skipped(db_session, project.id, [str(item.id)])
    await db_session.refresh(item)
    data = json.loads(item.item_data)
    assert data.get("skip_count", 0) == 0


# ─── group_pending_items ordena skip_count DESC ───────────────────────


@pytest.mark.asyncio
async def test_group_pending_ordena_por_skip_count(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    # Três itens na mesma seção, diferentes skip_counts
    i1 = await _mk_pending_item(db_session, project, analysis, "RNF-S-001",
        data={"question": "CWE?", "skip_count": 0})
    i2 = await _mk_pending_item(db_session, project, analysis, "RNF-S-002",
        data={"question": "Vault?", "skip_count": 3})
    i3 = await _mk_pending_item(db_session, project, analysis, "RNF-S-003",
        data={"question": "MFA?", "skip_count": 1})

    buckets = await group_pending_items(db_session, project.id)
    security = buckets["security"]
    assert [q.code for q in security] == ["RNF-S-002", "RNF-S-003", "RNF-S-001"]


# ─── Aplicador integra com bump_skipped ─────────────────────────────


@pytest.mark.asyncio
async def test_aplicador_bump_skipped_integrado(db_session: AsyncSession):
    user, project, analysis = await _mk_user_proj_analysis(db_session)
    i_answered = await _mk_pending_item(db_session, project, analysis, "G200")
    i_skipped = await _mk_pending_item(db_session, project, analysis, "G201",
        data={"question": "Pergunta deixada em branco", "skip_count": 1})

    parsed = ParsedQuestionnaire(
        answers=(ItemAnswer(item_id=str(i_answered.id), text="resposta"),),
        offered_ids=(str(i_answered.id), str(i_skipped.id)),
    )
    report = await apply_parsed_responses(
        db_session, project.id, user.id, parsed,
    )

    assert report.applied == 1
    # skip antes era 1; agora 2 → promove
    assert str(i_skipped.id) in report.info_debt_promoted

    await db_session.refresh(i_skipped)
    data = json.loads(i_skipped.item_data)
    assert data["skip_count"] == 2

    backlog = (await db_session.execute(
        select(BacklogItem).where(
            BacklogItem.project_id == project.id,
            BacklogItem.category == "info_debt",
        )
    )).scalars().all()
    assert len(backlog) == 1


@pytest.mark.asyncio
async def test_threshold_canonico_e_2():
    assert INFO_DEBT_THRESHOLD == 2
