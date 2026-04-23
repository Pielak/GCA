"""MVP 25 Fase 25.3 — Testes do applier + hook da Ingestão.

Cobre:
  - apply_tokens_to_ocg: bump version + audit OCG_UPDATED.
  - Idempotência: payload idêntico não bumpa (só generated_at diferente).
  - Sem OCG → reason="no_ocg".
  - seed_design_tokens_gap_if_needed: cria DT-DSGN001 pendente.
  - Gap idempotente (mesmo código não duplica).
  - Tokens já presentes → não seed.
  - Sem análise Arguidor → reason="no_analysis".
  - Upload de CSS → tokens no OCG + status=completed + Celery NÃO disparado.
  - Upload de PNG sem tokens → gap criado.
  - CSS vazio/sem tokens → doc marcado completed (não reclama).
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.database import AsyncSessionLocal
from app.models.base import (
    ArguiderAnalysis, GatekeeperItem, GlobalAuditLog, IngestedDocument,
    OCG, Organization, Project, Questionnaire, User,
)
from app.services.audit_service import AuditEvents
from app.services.design_tokens_applier_service import (
    DESIGN_GAP_CODE, apply_tokens_to_ocg, seed_design_tokens_gap_if_needed,
)


async def _mk_user_proj(session) -> tuple[User, Project]:
    uniq = uuid4().hex[:6]
    user = User(
        id=uuid4(), email=f"p253-{uniq}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="P253", is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    org = Organization(
        id=uuid4(), name=f"P253-Org-{uniq}", slug=f"p253-{uniq}",
        owner_id=user.id, is_active=True, created_at=datetime.utcnow(),
    )
    session.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name=f"P253 {uniq}", slug=f"p253-p-{uniq}",
        description="t", deliverable_type="web_app",
        status="active", created_at=datetime.utcnow(),
    )
    session.add(project)
    await session.flush()
    return user, project


async def _mk_ocg_with_data(session, project: Project, ocg_data: dict | None = None) -> OCG:
    q = Questionnaire(
        id=uuid4(), project_id=project.id,
        gp_email="test@example.com", responses="{}",
    )
    session.add(q)
    await session.flush()
    ocg = OCG(
        id=uuid4(), project_id=project.id, version=1,
        questionnaire_id=q.id,
        ocg_data=json.dumps(ocg_data or {}, ensure_ascii=False),
        status="NEEDS_REVIEW", overall_score=75.0, is_blocking=False,
    )
    session.add(ocg)
    await session.flush()
    return ocg


async def _mk_analysis(session, project: Project, user: User) -> ArguiderAnalysis:
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


# ─── apply_tokens_to_ocg ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_sem_ocg_retorna_no_ocg(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    result = await apply_tokens_to_ocg(
        db_session, project.id, {"palette": {"top": ["#7c3aed"]}},
        actor_id=user.id,
    )
    assert result["applied"] is False
    assert result["reason"] == "no_ocg"


@pytest.mark.asyncio
async def test_apply_payload_vazio_retorna_empty(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project)
    result = await apply_tokens_to_ocg(
        db_session, project.id, {}, actor_id=user.id,
    )
    assert result["reason"] == "empty_payload"


@pytest.mark.asyncio
async def test_apply_cria_subsection_frontend_e_bump_version(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    ocg = await _mk_ocg_with_data(db_session, project)
    payload = {
        "palette": {"top": ["#7c3aed"], "by_role": {"primary": "#7c3aed"}, "unique_count": 1},
        "source": "css_ingested",
        "generated_at": "2026-04-22T10:00:00+00:00",
    }
    result = await apply_tokens_to_ocg(
        db_session, project.id, payload, actor_id=user.id,
    )
    assert result["applied"] is True
    assert result["ocg_version_to"] == 2

    await db_session.refresh(ocg)
    data = json.loads(ocg.ocg_data)
    dt = data["STACK_RECOMMENDATION"]["frontend"]["design_tokens"]
    assert dt["palette"]["by_role"]["primary"] == "#7c3aed"
    assert ocg.version == 2


@pytest.mark.asyncio
async def test_apply_idempotente_so_timestamp_muda(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project)
    payload = {
        "palette": {"top": ["#111"]}, "source": "css_ingested",
        "generated_at": "2026-04-22T10:00:00+00:00",
    }
    r1 = await apply_tokens_to_ocg(db_session, project.id, payload, actor_id=user.id)
    assert r1["applied"] is True
    assert r1["ocg_version_to"] == 2

    # Segunda chamada com mesmo conteúdo (outro generated_at) → NOOP
    payload_same = {**payload, "generated_at": "2026-04-22T11:00:00+00:00"}
    r2 = await apply_tokens_to_ocg(db_session, project.id, payload_same, actor_id=user.id)
    assert r2["applied"] is False
    assert r2["reason"] == "noop"
    assert r2["ocg_version_to"] == 2


@pytest.mark.asyncio
async def test_apply_emite_audit_ocg_updated(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project)
    await apply_tokens_to_ocg(
        db_session, project.id, {"palette": {"top": ["#abc"]}, "source": "manual"},
        actor_id=user.id,
    )
    rows = (await db_session.execute(
        select(GlobalAuditLog).where(GlobalAuditLog.event_type == AuditEvents.OCG_UPDATED)
    )).scalars().all()
    assert any(
        "design_tokens_ingestion" in (r.details or "")
        for r in rows
    )


# ─── seed_design_tokens_gap_if_needed ─────────────────────────────────


@pytest.mark.asyncio
async def test_seed_cria_gap_quando_sem_tokens(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project)
    await _mk_analysis(db_session, project, user)

    result = await seed_design_tokens_gap_if_needed(
        db_session, project.id, triggered_by_document_id=None,
    )
    assert result["created"] is True
    assert result["item_id"] is not None

    gaps = (await db_session.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project.id,
            GatekeeperItem.item_id_in_analysis == DESIGN_GAP_CODE,
        )
    )).scalars().all()
    assert len(gaps) == 1
    assert gaps[0].status == "pending"
    data = json.loads(gaps[0].item_data)
    assert data["pillar"] == "P5"
    assert "design_tokens" in data["category"]


@pytest.mark.asyncio
async def test_seed_nao_duplica_gap_ja_pendente(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project)
    await _mk_analysis(db_session, project, user)

    r1 = await seed_design_tokens_gap_if_needed(db_session, project.id)
    r2 = await seed_design_tokens_gap_if_needed(db_session, project.id)
    assert r1["created"] is True
    assert r2["created"] is False
    assert r2["reason"] == "already_seeded"

    gaps = (await db_session.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project.id,
            GatekeeperItem.item_id_in_analysis == DESIGN_GAP_CODE,
        )
    )).scalars().all()
    assert len(gaps) == 1


@pytest.mark.asyncio
async def test_seed_skip_quando_ocg_ja_tem_tokens(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project, ocg_data={
        "STACK_RECOMMENDATION": {
            "frontend": {"design_tokens": {"palette": {"top": ["#abc"]}}}
        }
    })
    await _mk_analysis(db_session, project, user)

    result = await seed_design_tokens_gap_if_needed(db_session, project.id)
    assert result["created"] is False
    assert result["reason"] == "tokens_present"


@pytest.mark.asyncio
async def test_seed_sem_analysis_nao_cria(db_session: AsyncSession):
    user, project = await _mk_user_proj(db_session)
    await _mk_ocg_with_data(db_session, project)
    result = await seed_design_tokens_gap_if_needed(db_session, project.id)
    assert result["created"] is False
    assert result["reason"] == "no_analysis"


# ─── Hook na Ingestão (integração) ───────────────────────────────────


@pytest.mark.asyncio
async def test_upload_css_aplica_tokens_e_pula_celery():
    """CSS ingerido extrai tokens → OCG bumpa; Celery não é disparado."""
    from app.services.ingestion_service import IngestionService

    async with AsyncSessionLocal() as session:
        async with session.begin():
            user, project = await _mk_user_proj(session)
            await _mk_ocg_with_data(session, project)
            user_id = user.id
            project_id = project.id

    css = """
    :root { --primary: #7c3aed; --secondary: #0ea5e9; }
    body { font-family: 'Inter'; font-size: 16px; }
    .card { padding: 16px; border-radius: 8px; }
    """

    async with AsyncSessionLocal() as session:
        service = IngestionService(session)
        with patch("app.tasks.pipeline.pipeline_ingest_task.delay") as mock_task:
            result = await service.upload_document(
                project_id=project_id,
                uploaded_by=user_id,
                file_bytes=css.encode("utf-8"),
                original_filename="theme.css",
                content_type="text/css",
            )
        assert "design_tokens_applied" in result, result
        applied = result["design_tokens_applied"]
        assert applied["applied"] is True
        assert applied["ocg_version_to"] == 2
        assert not mock_task.called, "Celery NÃO deve ser disparado para stylesheet"

    # OCG foi bumpado com tokens
    async with AsyncSessionLocal() as session:
        ocg = (await session.execute(
            select(OCG).where(OCG.project_id == project_id)
        )).scalar_one()
        data = json.loads(ocg.ocg_data)
        dt = data["STACK_RECOMMENDATION"]["frontend"]["design_tokens"]
        assert dt["palette"]["by_role"].get("primary") == "#7c3aed"
        assert ocg.version == 2


@pytest.mark.asyncio
async def test_upload_png_sem_tokens_cria_gap():
    """PNG ingerido quando OCG não tem tokens → gap DT-DSGN001 no Arguidor."""
    from app.services.ingestion_service import IngestionService

    async with AsyncSessionLocal() as session:
        async with session.begin():
            user, project = await _mk_user_proj(session)
            await _mk_ocg_with_data(session, project)
            await _mk_analysis(session, project, user)
            user_id = user.id
            project_id = project.id

    # Bytes PNG mínimos válidos (1x1 transparent)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa"
        b"\x0f\x00\x00\x01\x01\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    async with AsyncSessionLocal() as session:
        service = IngestionService(session)
        with patch("app.tasks.pipeline.pipeline_ingest_task.delay"):
            await service.upload_document(
                project_id=project_id,
                uploaded_by=user_id,
                file_bytes=png_bytes,
                original_filename="mock.png",
                content_type="image/png",
            )

    async with AsyncSessionLocal() as session:
        gaps = (await session.execute(
            select(GatekeeperItem).where(
                GatekeeperItem.project_id == project_id,
                GatekeeperItem.item_id_in_analysis == DESIGN_GAP_CODE,
            )
        )).scalars().all()
        assert len(gaps) == 1
        assert gaps[0].status == "pending"


@pytest.mark.asyncio
async def test_upload_css_vazio_marca_completed():
    """reset.css sem tokens detectáveis não levanta nem cria lixo no OCG."""
    from app.services.ingestion_service import IngestionService

    async with AsyncSessionLocal() as session:
        async with session.begin():
            user, project = await _mk_user_proj(session)
            await _mk_ocg_with_data(session, project)
            user_id = user.id
            project_id = project.id

    css = "* { box-sizing: border-box; }"  # sem cores/font-size/spacing

    async with AsyncSessionLocal() as session:
        service = IngestionService(session)
        with patch("app.tasks.pipeline.pipeline_ingest_task.delay") as mock_task:
            result = await service.upload_document(
                project_id=project_id,
                uploaded_by=user_id,
                file_bytes=css.encode("utf-8"),
                original_filename="reset.css",
                content_type="text/css",
            )
        # Não tem design_tokens_applied no payload — extração foi vazia
        assert "design_tokens_applied" not in result
        assert not mock_task.called

    async with AsyncSessionLocal() as session:
        doc_id = UUID(result["document_id"])
        doc = await session.get(IngestedDocument, doc_id)
        assert doc.arguider_status == "completed"
        assert doc.document_category == "design_stylesheet_empty"
