"""MVP 10 Fase 10.6 — Fluxo approve/reject de TestSpecs.

Testes de contrato sobre a lógica das transições (chamando handlers
diretamente, sem HTTP — TestClient + sessão async é frágil). Cobre:
  - draft → approved preenche approved_by/at + limpa rejection
  - rejected → approved idempotente e limpa rejection
  - Aprovar já approved é no-op
  - draft → rejected exige reason ≥ 10 chars
  - approved → rejected reverte (limpa approved_by/at)
  - reason < 10 chars → 400 (HTTPException)
  - stale → approve/reject bloqueado (requer regenerar antes)
  - Compartimentalização: spec de outro projeto → 404

Rota é pt-BR via backlog:manage/qa:approve no RBAC — permission check
é do dependency, não da lógica.
"""
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG,
    Questionnaire, TestSpec,
)
from app.routers.qa_router import (
    _RejectSpecBody, approve_test_spec, reject_test_spec,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed(db, initial_status="draft"):
    """Cria projeto + módulo + spec com status inicial."""
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"mvp10f6-{uuid4().hex[:6]}")
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
        source="ocg_foundation", name="M",
        description="", module_type="backend_service",
        priority="high", status="sugerido",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
    )
    db.add(mc)
    spec = TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit",
        content="# plano\nteste 1", status=initial_status,
        ocg_version_at_generation=1,
    )
    db.add(spec)
    await db.commit()
    return p, mc, user, spec


# ============================================================================
# Approve
# ============================================================================

@pytest.mark.asyncio
async def test_approve_draft_marca_approved_e_audit(db_session):
    p, _, user, spec = await _seed(db_session, initial_status="draft")
    result = await approve_test_spec(
        project_id=p.id, spec_id=spec.id,
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    assert result["status"] == "approved"
    assert result["approved_by"] == str(user.id)
    assert result["approved_at"] is not None

    await db_session.refresh(spec)
    assert spec.status == "approved"
    assert spec.approved_by == user.id
    assert spec.approved_at is not None
    assert spec.rejection_reason is None
    assert spec.rejected_by is None


@pytest.mark.asyncio
async def test_approve_rejected_reabre_e_limpa_rejection(db_session):
    """GP/QA aprovou após rejeição prévia — apaga rejection_reason."""
    p, _, user, spec = await _seed(db_session, initial_status="rejected")
    spec.rejected_by = user.id
    spec.rejection_reason = "motivo antigo"
    await db_session.commit()

    await approve_test_spec(
        project_id=p.id, spec_id=spec.id,
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    await db_session.refresh(spec)
    assert spec.status == "approved"
    assert spec.rejection_reason is None
    assert spec.rejected_by is None


@pytest.mark.asyncio
async def test_approve_ja_approved_noop(db_session):
    """Aprovar spec já approved é idempotente — não erra, não zera data."""
    p, _, user, spec = await _seed(db_session, initial_status="approved")
    from datetime import datetime, timezone as _tz
    original_approved_at = datetime.now(_tz.utc)
    spec.approved_by = user.id
    spec.approved_at = original_approved_at
    await db_session.commit()

    await approve_test_spec(
        project_id=p.id, spec_id=spec.id,
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    await db_session.refresh(spec)
    assert spec.status == "approved"
    # approved_at preserva timestamp original (não muda porque já approved)
    assert spec.approved_at == original_approved_at


@pytest.mark.asyncio
async def test_approve_stale_bloqueado(db_session):
    """Spec com status='stale' não pode ser aprovado — regenere antes."""
    p, _, user, spec = await _seed(db_session, initial_status="stale")

    with pytest.raises(HTTPException) as exc_info:
        await approve_test_spec(
            project_id=p.id, spec_id=spec.id,
            _perm={"user_id": user.id}, db=db_session,
            current_user_id=user.id,
        )
    assert exc_info.value.status_code == 400
    assert "inválida" in exc_info.value.detail.lower() or "stale" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_approve_spec_inexistente_404(db_session):
    p, _, user, _ = await _seed(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await approve_test_spec(
            project_id=p.id, spec_id=uuid4(),
            _perm={"user_id": user.id}, db=db_session,
            current_user_id=user.id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_spec_de_outro_projeto_404(db_session):
    """Compartimentalização §2.2."""
    p_a, _, user_a, spec_a = await _seed(db_session)
    p_b, _, _, _ = await _seed(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await approve_test_spec(
            project_id=p_b.id, spec_id=spec_a.id,
            _perm={"user_id": user_a.id}, db=db_session,
            current_user_id=user_a.id,
        )
    assert exc_info.value.status_code == 404


# ============================================================================
# Reject
# ============================================================================

@pytest.mark.asyncio
async def test_reject_draft_marca_rejected_com_reason(db_session):
    p, _, user, spec = await _seed(db_session, initial_status="draft")
    result = await reject_test_spec(
        project_id=p.id, spec_id=spec.id,
        body=_RejectSpecBody(reason="Faltam casos de erro específicos pro DataJud"),
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    assert result["status"] == "rejected"
    assert result["rejected_by"] == str(user.id)
    assert "DataJud" in result["rejection_reason"]


@pytest.mark.asyncio
async def test_reject_reason_curto_400(db_session):
    """Reason < 10 chars é bloqueado — evita rejeição sem contexto."""
    p, _, user, spec = await _seed(db_session, initial_status="draft")
    with pytest.raises(HTTPException) as exc_info:
        await reject_test_spec(
            project_id=p.id, spec_id=spec.id,
            body=_RejectSpecBody(reason="curto"),
            _perm={"user_id": user.id}, db=db_session,
            current_user_id=user.id,
        )
    assert exc_info.value.status_code == 400
    assert "10" in exc_info.value.detail


@pytest.mark.asyncio
async def test_reject_reason_vazio_400(db_session):
    p, _, user, spec = await _seed(db_session, initial_status="draft")
    with pytest.raises(HTTPException) as exc_info:
        await reject_test_spec(
            project_id=p.id, spec_id=spec.id,
            body=_RejectSpecBody(reason="   "),  # só whitespace
            _perm={"user_id": user.id}, db=db_session,
            current_user_id=user.id,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reject_approved_reverte_aprovacao(db_session):
    """GP/QA pode rejeitar spec já approved — limpa approved_by."""
    from datetime import datetime, timezone as _tz
    p, _, user, spec = await _seed(db_session, initial_status="approved")
    spec.approved_by = user.id
    spec.approved_at = datetime.now(_tz.utc)
    await db_session.commit()

    await reject_test_spec(
        project_id=p.id, spec_id=spec.id,
        body=_RejectSpecBody(reason="Mudança de direção arquitetural, refazer"),
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    await db_session.refresh(spec)
    assert spec.status == "rejected"
    assert spec.approved_by is None
    assert spec.approved_at is None
    assert "arquitetural" in spec.rejection_reason


@pytest.mark.asyncio
async def test_reject_stale_bloqueado(db_session):
    p, _, user, spec = await _seed(db_session, initial_status="stale")
    with pytest.raises(HTTPException) as exc_info:
        await reject_test_spec(
            project_id=p.id, spec_id=spec.id,
            body=_RejectSpecBody(reason="Qualquer motivo longo o suficiente"),
            _perm={"user_id": user.id}, db=db_session,
            current_user_id=user.id,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reject_cross_project_404(db_session):
    p_a, _, user_a, spec_a = await _seed(db_session)
    p_b, _, _, _ = await _seed(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await reject_test_spec(
            project_id=p_b.id, spec_id=spec_a.id,
            body=_RejectSpecBody(reason="Motivo longo pra testar compartimentalizacao"),
            _perm={"user_id": user_a.id}, db=db_session,
            current_user_id=user_a.id,
        )
    assert exc_info.value.status_code == 404


# ============================================================================
# Fluxo aprove → reject → aprove (ping-pong)
# ============================================================================

@pytest.mark.asyncio
async def test_fluxo_aprove_reject_reaprove(db_session):
    p, _, user, spec = await _seed(db_session, initial_status="draft")

    # Aprova
    await approve_test_spec(
        project_id=p.id, spec_id=spec.id,
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    await db_session.refresh(spec)
    assert spec.status == "approved"

    # Rejeita
    await reject_test_spec(
        project_id=p.id, spec_id=spec.id,
        body=_RejectSpecBody(reason="Reverter aprovação por conflito novo"),
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    await db_session.refresh(spec)
    assert spec.status == "rejected"
    assert spec.approved_by is None  # limpo

    # Re-aprova
    await approve_test_spec(
        project_id=p.id, spec_id=spec.id,
        _perm={"user_id": user.id}, db=db_session,
        current_user_id=user.id,
    )
    await db_session.refresh(spec)
    assert spec.status == "approved"
    assert spec.rejection_reason is None  # limpo
    assert spec.approved_by == user.id
