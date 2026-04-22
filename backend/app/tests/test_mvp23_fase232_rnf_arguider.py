"""MVP 23 Fase 23.2 — testes do Arguidor dirigido para RNF.

Valida:
- Templates canônicos: 4 categorias (performance, security, compliance, availability).
- `detect_missing_categories`: OCG sem RNF → todas; com campo material → removida da lista.
- `seed_rnf_gaps`: sem ArguiderAnalysis anterior → skip (log + retorno vazio).
  Com ArguiderAnalysis → cria GatekeeperItem por categoria faltante.
  Idempotente: re-seed não duplica.
- `apply_rnf_answer`: payload inválido → errors sem aplicar.
  Payload válido → merge no OCG, bump version, audit, resolve gap.
  Payload idêntico ao atual → noop (applied=False, errors vazio).
- Categoria desconhecida → erro.
"""
import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.base import (
    ArguiderAnalysis,
    GatekeeperItem,
    GlobalAuditLog,
    IngestedDocument,
    OCG,
    Organization,
    Project,
    Questionnaire,
    User,
)
from app.services.rnf_arguider_service import (
    all_templates,
    apply_rnf_answer,
    detect_missing_categories,
    get_template,
    seed_rnf_gaps,
)


# ===========================================================================
# Helpers
# ===========================================================================


async def _make_user(db) -> User:
    uid = uuid4()
    u = User(
        id=uid,
        email=f"rnf-{uid.hex[:6]}@example.com",
        password_hash=hash_password("Test@1234"),
        full_name="RNF Tester",
        is_active=True, is_admin=True,
        created_at=datetime.utcnow(),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, user) -> Project:
    org = Organization(
        id=uuid4(), name=f"Org {uuid4().hex[:6]}",
        slug=f"org-rnf-{uuid4().hex[:6]}",
        owner_id=user.id, is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(org)
    project = Project(
        id=uuid4(), organization_id=org.id,
        name="RNF Proj", slug=f"rnf-{uuid4().hex[:6]}",
        description="t", deliverable_type="web_app",
        status="active", created_at=datetime.utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


async def _make_ocg(
    db, project: Project,
    *,
    rnf: dict | None = None,
    version: int = 1,
) -> OCG:
    q = Questionnaire(
        id=uuid4(),
        project_id=project.id,
        gp_email="test@example.com",
        responses="{}",
    )
    db.add(q)
    await db.flush()
    data = {}
    if rnf is not None:
        data["RNF_CONTRACTS"] = rnf
    ocg = OCG(
        id=uuid4(),
        project_id=project.id,
        version=version,
        questionnaire_id=q.id,
        ocg_data=json.dumps(data, ensure_ascii=False),
        status="NEEDS_REVIEW",
        overall_score=80.0,
        is_blocking=False,
    )
    db.add(ocg)
    await db.flush()
    return ocg


async def _make_arguider_analysis(db, project, user) -> ArguiderAnalysis:
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        filename=f"{uuid4().hex}.pdf",
        original_filename="req.pdf",
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
        llm_model="test-model",
        tokens_used=100,
        latency_ms=10,
    )
    db.add(analysis)
    await db.flush()
    return analysis


# ===========================================================================
# Templates canônicos
# ===========================================================================


def test_all_templates_tem_4_categorias():
    tpls = all_templates()
    assert set(tpls.keys()) == {"performance", "security", "compliance", "availability"}


def test_get_template_performance_tem_campos_canonicos():
    t = get_template("performance")
    keys = {f["key"] for f in t.fields}
    assert "latency_p95_ms" in keys
    assert "throughput_rps" in keys
    assert "per_operation" in keys


def test_get_template_security_tem_cwe_suggestions():
    t = get_template("security")
    cwe_field = next(f for f in t.fields if f["key"] == "required_cwe_protections")
    assert "CWE-89" in cwe_field.get("suggestions", [])
    assert "CWE-798" in cwe_field.get("suggestions", [])


def test_get_template_categoria_invalida_levanta():
    with pytest.raises(ValueError):
        get_template("unknown_category")  # type: ignore[arg-type]


# ===========================================================================
# detect_missing_categories
# ===========================================================================


def test_detect_missing_ocg_sem_rnf_todas_categorias_vazias():
    missing = detect_missing_categories({})
    assert set(missing) == {"performance", "security", "compliance", "availability"}


def test_detect_missing_ocg_com_rnf_vazio_todas_vazias():
    missing = detect_missing_categories({"RNF_CONTRACTS": {}})
    assert set(missing) == {"performance", "security", "compliance", "availability"}


def test_detect_missing_performance_preenchida_sai_da_lista():
    missing = detect_missing_categories({
        "RNF_CONTRACTS": {"performance": {"latency_p95_ms": 200}},
    })
    assert "performance" not in missing
    assert set(missing) == {"security", "compliance", "availability"}


def test_detect_missing_compliance_com_items_remove_da_lista():
    missing = detect_missing_categories({
        "RNF_CONTRACTS": {
            "compliance": [
                {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "both"},
            ],
        },
    })
    assert "compliance" not in missing


def test_detect_missing_tipo_errado_volta_todas():
    """RNF_CONTRACTS não-dict é tratado como vazio → todas faltam."""
    missing = detect_missing_categories({"RNF_CONTRACTS": "not a dict"})
    assert len(missing) == 4


# ===========================================================================
# seed_rnf_gaps
# ===========================================================================


@pytest.mark.asyncio
async def test_seed_sem_ocg_retorna_vazio(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    # Não cria OCG.
    created = await seed_rnf_gaps(db_session, project.id)
    assert created == []


@pytest.mark.asyncio
async def test_seed_sem_arguider_analysis_skip_log(db_session):
    """Projeto com OCG mas sem Arguider analysis anterior: skip seed."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})  # RNF vazio → 4 gaps
    # Sem ArguiderAnalysis → skip
    created = await seed_rnf_gaps(db_session, project.id)
    assert created == []


@pytest.mark.asyncio
async def test_seed_cria_gap_por_categoria_faltante(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})
    await _make_arguider_analysis(db_session, project, user)

    created = await seed_rnf_gaps(db_session, project.id)
    assert len(created) == 4
    categories = set()
    for item in created:
        data = json.loads(item.item_data)
        assert data["category"] == "rnf_contract"
        categories.add(data["rnf_category"])
    assert categories == {"performance", "security", "compliance", "availability"}


@pytest.mark.asyncio
async def test_seed_idempotente_nao_duplica(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})
    await _make_arguider_analysis(db_session, project, user)

    created1 = await seed_rnf_gaps(db_session, project.id)
    created2 = await seed_rnf_gaps(db_session, project.id)
    assert len(created1) == 4
    assert len(created2) == 0


@pytest.mark.asyncio
async def test_seed_nao_recria_gap_resolvido(db_session):
    """Se GP resolveu um gap (status=resolved), seed não reabre."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})
    await _make_arguider_analysis(db_session, project, user)

    created = await seed_rnf_gaps(db_session, project.id)
    # Marca um gap como resolved manualmente.
    first = created[0]
    first_category = json.loads(first.item_data)["rnf_category"]
    first.status = "resolved"
    db_session.add(first)
    await db_session.flush()

    # Re-seed — categoria resolved NÃO deve voltar.
    again = await seed_rnf_gaps(db_session, project.id)
    new_categories = [
        json.loads(g.item_data)["rnf_category"] for g in again
    ]
    assert first_category not in new_categories
    # (Nenhuma nova é criada, pois ainda há gaps pendentes das outras 3
    # categorias; seed vê existing_categories + resolved = todas.)
    assert again == []


@pytest.mark.asyncio
async def test_seed_so_categorias_faltantes_quando_preenchidas_parcialmente(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={
        "performance": {"latency_p95_ms": 200},
        "availability": {"uptime_pct": 99.0},
    })
    await _make_arguider_analysis(db_session, project, user)

    created = await seed_rnf_gaps(db_session, project.id)
    categories = [json.loads(c.item_data)["rnf_category"] for c in created]
    # Só as 2 faltantes.
    assert set(categories) == {"security", "compliance"}


# ===========================================================================
# apply_rnf_answer
# ===========================================================================


@pytest.mark.asyncio
async def test_apply_categoria_invalida_retorna_erro(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})

    result = await apply_rnf_answer(
        db_session, project.id, "invalid_cat", {},  # type: ignore[arg-type]
    )
    assert result["applied"] is False
    assert result["errors"]


@pytest.mark.asyncio
async def test_apply_payload_invalido_retorna_errors(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})

    result = await apply_rnf_answer(
        db_session, project.id, "performance",
        {"latency_p95_ms": -10},  # negativo → inválido
    )
    assert result["applied"] is False
    assert any("latency_p95_ms" in e["path"] for e in result["errors"])


@pytest.mark.asyncio
async def test_apply_sem_ocg_retorna_erro(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    # Não cria OCG.

    result = await apply_rnf_answer(
        db_session, project.id, "performance", {"latency_p95_ms": 200},
    )
    assert result["applied"] is False
    assert any("OCG" in e["message"] for e in result["errors"])


@pytest.mark.asyncio
async def test_apply_performance_valida_merge_e_bump_version(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ocg = await _make_ocg(db_session, project, rnf={}, version=5)

    result = await apply_rnf_answer(
        db_session, project.id, "performance",
        {"latency_p95_ms": 200, "throughput_rps": 500},
        resolved_by=user.id,
    )
    assert result["applied"] is True
    assert result["ocg_version_to"] == 6
    assert result["errors"] == []

    # Re-lê OCG
    reloaded = (await db_session.execute(
        select(OCG).where(OCG.id == ocg.id)
    )).scalar_one()
    data = json.loads(reloaded.ocg_data)
    assert data["RNF_CONTRACTS"]["performance"]["latency_p95_ms"] == 200
    assert data["RNF_CONTRACTS"]["performance"]["throughput_rps"] == 500
    assert reloaded.version == 6


@pytest.mark.asyncio
async def test_apply_compliance_usa_items_como_wrapper(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})

    payload = {
        "items": [
            {"regulation": "LGPD", "requirement_id": "ART-18", "enforcement": "runtime"},
            {"regulation": "GDPR", "requirement_id": "ART-32", "enforcement": "static"},
        ],
    }
    result = await apply_rnf_answer(db_session, project.id, "compliance", payload)
    assert result["applied"] is True

    reloaded = (await db_session.execute(
        select(OCG).where(OCG.project_id == project.id)
    )).scalar_one()
    data = json.loads(reloaded.ocg_data)
    assert len(data["RNF_CONTRACTS"]["compliance"]) == 2
    assert data["RNF_CONTRACTS"]["compliance"][0]["regulation"] == "LGPD"


@pytest.mark.asyncio
async def test_apply_idempotente_noop_quando_identico(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={
        "security": {"rate_limit_rpm_public": 60},
    }, version=3)

    result = await apply_rnf_answer(
        db_session, project.id, "security",
        {"rate_limit_rpm_public": 60},
    )
    # Não aplicou porque é igual.
    assert result["applied"] is False
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_apply_resolve_gap_correspondente(db_session):
    """Quando há GatekeeperItem RNF pendente da categoria, fica resolved."""
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    await _make_ocg(db_session, project, rnf={})
    await _make_arguider_analysis(db_session, project, user)

    await seed_rnf_gaps(db_session, project.id)

    # Aplica resposta de performance.
    await apply_rnf_answer(
        db_session, project.id, "performance",
        {"latency_p95_ms": 150},
        resolved_by=user.id,
    )

    # Gap de performance deve ter virado resolved.
    items = (await db_session.execute(
        select(GatekeeperItem).where(
            GatekeeperItem.project_id == project.id,
        )
    )).scalars().all()
    perf_item = next(
        i for i in items
        if json.loads(i.item_data).get("rnf_category") == "performance"
    )
    assert perf_item.status == "resolved"
    assert perf_item.resolved_by == user.id


@pytest.mark.asyncio
async def test_apply_emite_audit_ocg_updated(db_session):
    user = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ocg = await _make_ocg(db_session, project, rnf={}, version=2)

    await apply_rnf_answer(
        db_session, project.id, "availability",
        {"uptime_pct": 99.9, "rpo_minutes": 30, "rto_minutes": 60},
        resolved_by=user.id,
    )

    audits = (await db_session.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.resource_id == ocg.id,
        )
    )).scalars().all()
    assert any(a.event_type.upper() == "OCG_UPDATED" for a in audits)
