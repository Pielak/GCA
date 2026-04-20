"""MVP 10 Fase 10.4 — Stale detection (TestSpec + LiveDoc).

Cobre heurística pura:
  - Projeto sem OCG → is_stale=False
  - Spec sem ocg_version_at_generation → is_stale=True (legado)
  - Generated == current → is_stale=False
  - Generated < current → is_stale=True com reason citando versões + deltas
  - Generated > current (raro) → is_stale=False

Cobre integração com DB:
  - evaluate_test_spec_staleness itera todas as specs do projeto
  - evaluate_live_doc_staleness funciona análogo
  - build_stale_summary agrega por tipo
  - _count_deltas_grouped_by_from_version usa ocg_delta_log

Compartimentalização: specs de projeto A não vazam pra staleness de B.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, LiveDoc, ModuleCandidate,
    OCG, OCGDeltaLog, Questionnaire, TestSpec,
)
from app.services.stale_detection_service import (
    StaleInfo, _compute_stale, _format_reason, _group_summary,
    _is_stale_simple, build_stale_summary,
    evaluate_live_doc_staleness, evaluate_test_spec_staleness,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Pure unit — _compute_stale
# ============================================================================

def test_compute_stale_sem_ocg_retorna_false():
    info = _compute_stale(current_version=None, generated_version=None, delta_counts={})
    assert info.is_stale is False
    assert info.reason is None


def test_compute_stale_generated_ausente_e_ocg_existe_retorna_true():
    """Legado pré-MVP10 (sem rastro) conta como stale."""
    info = _compute_stale(current_version=5, generated_version=None, delta_counts={})
    assert info.is_stale is True
    assert "sem rastro" in info.reason


def test_compute_stale_mesma_versao_nao_stale():
    info = _compute_stale(current_version=7, generated_version=7, delta_counts={})
    assert info.is_stale is False
    assert info.reason is None
    assert info.deltas_since_generation == 0


def test_compute_stale_generated_menor_stale_com_deltas():
    info = _compute_stale(current_version=10, generated_version=7, delta_counts={7: 3})
    assert info.is_stale is True
    assert "v7" in info.reason
    assert "v10" in info.reason
    assert "3 mudanças" in info.reason
    assert info.deltas_since_generation == 3


def test_compute_stale_generated_menor_sem_delta_count_usa_diff():
    """Se não temos delta_count mapeado, cai pra diferença simples."""
    info = _compute_stale(current_version=10, generated_version=7, delta_counts={})
    assert info.is_stale is True
    assert info.deltas_since_generation == 3  # fallback: 10 - 7


def test_compute_stale_generated_maior_que_current_nao_stale():
    """Edge case raro (regen feito numa versão já superada)."""
    info = _compute_stale(current_version=5, generated_version=7, delta_counts={})
    assert info.is_stale is False


def test_format_reason_singular_e_plural():
    assert "1 mudança" in _format_reason(7, 8, 1)
    assert "5 mudanças" in _format_reason(7, 12, 5)


# ============================================================================
# Summary group
# ============================================================================

def test_group_summary_agrega_por_tipo():
    rows = [
        ("unit", 5),        # com current=7 → stale
        ("unit", 7),        # igual → não-stale
        ("integration", 5), # stale
        ("security", None), # stale (sem rastro)
    ]
    s = _group_summary(rows, current_version=7)
    assert s["total"] == 4
    assert s["stale"] == 3
    assert s["by_type"]["unit"] == {"total": 2, "stale": 1}
    assert s["by_type"]["integration"] == {"total": 1, "stale": 1}
    assert s["by_type"]["security"] == {"total": 1, "stale": 1}


def test_group_summary_sem_ocg_zera_stale():
    rows = [("unit", 3), ("unit", None)]
    s = _group_summary(rows, current_version=None)
    assert s["stale"] == 0  # nada pra comparar


def test_is_stale_simple():
    assert _is_stale_simple(7, 5) is True
    assert _is_stale_simple(7, 7) is False
    assert _is_stale_simple(None, 5) is False  # sem OCG
    assert _is_stale_simple(7, None) is True   # legado


# ============================================================================
# Integração com DB
# ============================================================================

async def _seed_project_with_ocg(db, ocg_version=3):
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"mvp10f4-{uuid4().hex[:6]}")
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
        version=ocg_version, change_type="CREATE", ocg_data=json.dumps({}),
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
    await db.commit()
    return p, mc, user


@pytest.mark.asyncio
async def test_evaluate_specs_todas_nao_stale_quando_ocg_igual(db_session):
    p, mc, _ = await _seed_project_with_ocg(db_session, ocg_version=3)
    # Specs gerados com ocg_version=3 — todos alinhados
    for t in ("unit", "integration"):
        db_session.add(TestSpec(
            project_id=p.id, module_id=mc.id, spec_type=t, content="x",
            ocg_version_at_generation=3,
        ))
    await db_session.commit()

    result = await evaluate_test_spec_staleness(db_session, p.id)
    assert len(result) == 2
    for info in result.values():
        assert info.is_stale is False


@pytest.mark.asyncio
async def test_evaluate_specs_stale_quando_ocg_avancou(db_session):
    p, mc, _ = await _seed_project_with_ocg(db_session, ocg_version=5)
    # Spec gerado quando OCG estava em v2 — agora é v5
    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="x",
        ocg_version_at_generation=2,
    ))
    await db_session.commit()

    result = await evaluate_test_spec_staleness(db_session, p.id)
    info = next(iter(result.values()))
    assert info.is_stale is True
    assert "v2" in info.reason
    assert "v5" in info.reason


@pytest.mark.asyncio
async def test_evaluate_specs_legacy_sem_generated_version_stale(db_session):
    p, mc, _ = await _seed_project_with_ocg(db_session, ocg_version=3)
    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="x",
        ocg_version_at_generation=None,  # legado
    ))
    await db_session.commit()

    result = await evaluate_test_spec_staleness(db_session, p.id)
    info = next(iter(result.values()))
    assert info.is_stale is True
    assert "sem rastro" in info.reason


@pytest.mark.asyncio
async def test_evaluate_specs_projeto_sem_ocg_nao_stale(db_session):
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="mvp10f4-noocg")
    # Spec sem OCG no projeto
    db_session.add(TestSpec(
        project_id=p.id, module_id=None, spec_type="security", content="x",
        ocg_version_at_generation=5,
    ))
    await db_session.commit()

    result = await evaluate_test_spec_staleness(db_session, p.id)
    info = next(iter(result.values()))
    assert info.is_stale is False  # current_version=None → nada pra comparar


@pytest.mark.asyncio
async def test_evaluate_usa_delta_log_quando_presente(db_session):
    p, mc, _ = await _seed_project_with_ocg(db_session, ocg_version=5)
    # 3 deltas entre v2 e v5 (2→3, 3→4, 4→5)
    for from_v, to_v in ((2, 3), (3, 4), (4, 5)):
        db_session.add(OCGDeltaLog(
            project_id=p.id,
            ocg_version_from=from_v, ocg_version_to=to_v,
            fields_changed="{}",
            change_summary="test delta",
            trigger_source="document_ingestion",
        ))
    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="x",
        ocg_version_at_generation=2,
    ))
    await db_session.commit()

    result = await evaluate_test_spec_staleness(db_session, p.id)
    info = next(iter(result.values()))
    assert info.is_stale is True
    assert info.deltas_since_generation >= 3
    assert "mudanças" in info.reason


# ============================================================================
# Live Doc staleness (análoga)
# ============================================================================

@pytest.mark.asyncio
async def test_evaluate_live_docs_stale(db_session):
    p, mc, _ = await _seed_project_with_ocg(db_session, ocg_version=6)
    db_session.add(LiveDoc(
        project_id=p.id, module_id=mc.id, doc_type="module_doc",
        content="d", ocg_version_at_generation=3,
    ))
    db_session.add(LiveDoc(
        project_id=p.id, module_id=None, doc_type="index",
        content="i", ocg_version_at_generation=6,  # alinhado
    ))
    await db_session.commit()

    result = await evaluate_live_doc_staleness(db_session, p.id)
    assert len(result) == 2
    stales = [info for info in result.values() if info.is_stale]
    assert len(stales) == 1


# ============================================================================
# Summary
# ============================================================================

@pytest.mark.asyncio
async def test_summary_agrega_specs_e_docs(db_session):
    p, mc, _ = await _seed_project_with_ocg(db_session, ocg_version=5)
    # 3 specs: 2 unit (um stale v2, um alinhado v5) + 1 integration (stale v3)
    db_session.add(TestSpec(
        project_id=p.id, module_id=mc.id, spec_type="unit", content="a",
        ocg_version_at_generation=2,  # stale
    ))
    # unit pra outro módulo (sem criar outro module real — usa NULL pra global)
    db_session.add(TestSpec(
        project_id=p.id, module_id=None, spec_type="security", content="b",
        ocg_version_at_generation=5,  # alinhado
    ))
    db_session.add(TestSpec(
        project_id=p.id, module_id=None, spec_type="compliance", content="c",
        ocg_version_at_generation=3,  # stale
    ))
    # 1 live_doc stale
    db_session.add(LiveDoc(
        project_id=p.id, module_id=mc.id, doc_type="module_doc",
        content="d", ocg_version_at_generation=2,
    ))
    await db_session.commit()

    summary = await build_stale_summary(db_session, p.id)
    assert summary["current_ocg_version"] == 5
    assert summary["test_specs"]["total"] == 3
    assert summary["test_specs"]["stale"] == 2
    assert summary["live_docs"]["total"] == 1
    assert summary["live_docs"]["stale"] == 1
    assert summary["needs_regeneration"] is True


@pytest.mark.asyncio
async def test_summary_projeto_sem_specs_e_sem_docs(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session, ocg_version=1)
    summary = await build_stale_summary(db_session, p.id)
    assert summary["test_specs"]["total"] == 0
    assert summary["live_docs"]["total"] == 0
    assert summary["needs_regeneration"] is False


# ============================================================================
# Compartimentalização
# ============================================================================

@pytest.mark.asyncio
async def test_evaluate_nao_vaza_entre_projetos(db_session):
    p_a, mc_a, _ = await _seed_project_with_ocg(db_session, ocg_version=5)
    p_b, mc_b, _ = await _seed_project_with_ocg(db_session, ocg_version=2)

    # Spec no B gerado em v1 (stale vs v2)
    db_session.add(TestSpec(
        project_id=p_b.id, module_id=mc_b.id, spec_type="unit",
        content="b", ocg_version_at_generation=1,
    ))
    await db_session.commit()

    # Evaluate do A: não vê spec do B
    result_a = await evaluate_test_spec_staleness(db_session, p_a.id)
    assert result_a == {}

    # Evaluate do B: vê seu próprio spec como stale
    result_b = await evaluate_test_spec_staleness(db_session, p_b.id)
    assert len(result_b) == 1
    info = next(iter(result_b.values()))
    assert info.is_stale is True
    assert info.current_ocg_version == 2  # usa OCG do B, não do A


# ============================================================================
# Dataclass StaleInfo
# ============================================================================

def test_stale_info_immutable_dataclass():
    """StaleInfo é frozen — garante que service não muta acidentalmente."""
    info = StaleInfo(
        is_stale=True, reason="teste",
        current_ocg_version=5, generated_ocg_version=3,
        deltas_since_generation=2,
    )
    with pytest.raises(Exception):
        info.is_stale = False  # type: ignore
