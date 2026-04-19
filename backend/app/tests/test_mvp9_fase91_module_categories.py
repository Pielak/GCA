"""MVP 9 Fase 9.1 — Categorias canônicas de módulos.

Garante que:
  - `normalize_module_type` força qualquer valor pra uma categoria
    canônica ou `feature` default.
  - Aliases legados (`component` → `feature`) não quebram Arguidor
    antigo que já está em prod.
  - Ordem de deploy está ancorada (infrastructure→deploy_pipeline).
  - Labels pt-BR existem pras 6 categorias (frontend depende).
  - Roadmap service inclui `module_type` e `description` no payload.
  - Prompt do Arguidor menciona as 6 categorias explicitamente.
"""
import json
from uuid import uuid4

import pytest
from pathlib import Path
from sqlalchemy import select

from app.constants.module_categories import (
    CANONICAL_MODULE_TYPES,
    CATEGORY_LABELS_PT_BR,
    DEPLOY_ORDER,
    LEGACY_MODULE_TYPE_ALIASES,
    is_canonical,
    normalize_module_type,
)
from app.models.base import ArguiderAnalysis, IngestedDocument, ModuleCandidate
from app.services.roadmap_service import RoadmapService
from app.tests.factories import (
    create_test_user, create_test_organization, create_test_project,
)


# ============================================================================
# Constantes canônicas
# ============================================================================

def test_6_categorias_canonicas_presentes():
    """As 6 categorias definidas no contrato MVP 9 §7 estão presentes."""
    expected = {
        "infrastructure", "observability", "middleware",
        "backend_service", "feature", "deploy_pipeline",
    }
    assert set(CANONICAL_MODULE_TYPES) == expected


def test_ordem_de_deploy_ancorada():
    """Infrastructure primeiro, deploy_pipeline por último. Garantia
    pra Fase 9.4 não regredir se alguém reordenar a tupla canônica."""
    assert DEPLOY_ORDER["infrastructure"] == 0
    assert DEPLOY_ORDER["deploy_pipeline"] == max(DEPLOY_ORDER.values())
    assert DEPLOY_ORDER["feature"] < DEPLOY_ORDER["deploy_pipeline"]
    assert DEPLOY_ORDER["backend_service"] < DEPLOY_ORDER["feature"]


def test_labels_ptbr_cobrem_todas_categorias():
    """Frontend depende do mapa — se falta, UI mostra enum cru."""
    for cat in CANONICAL_MODULE_TYPES:
        assert cat in CATEGORY_LABELS_PT_BR, f"sem label pt-BR pra {cat}"


# ============================================================================
# Normalização (retrocompat + defesa)
# ============================================================================

def test_normalize_valores_canonicos_passam_direto():
    for cat in CANONICAL_MODULE_TYPES:
        assert normalize_module_type(cat) == cat


def test_normalize_com_espacos_e_caixa():
    """LLM pode emitir 'Feature' ou ' backend_service '."""
    assert normalize_module_type("Feature") == "feature"
    assert normalize_module_type(" backend_service ") == "backend_service"
    assert normalize_module_type("INFRASTRUCTURE") == "infrastructure"


def test_normalize_alias_legado_component_vira_feature():
    """Arguidor antigo emitia 'component'; mantemos retrocompat."""
    assert normalize_module_type("component") == "feature"
    assert LEGACY_MODULE_TYPE_ALIASES["component"] == "feature"


def test_normalize_valor_desconhecido_vira_feature_default():
    """LLM criativo emitindo 'service' ou 'handler' não quebra DB."""
    assert normalize_module_type("service") == "feature"
    assert normalize_module_type("handler") == "feature"
    assert normalize_module_type("") == "feature"
    assert normalize_module_type(None) == "feature"


def test_is_canonical():
    assert is_canonical("feature") is True
    assert is_canonical("infrastructure") is True
    assert is_canonical("component") is False
    assert is_canonical("") is False


# ============================================================================
# Roadmap service — contrato de payload
# ============================================================================

async def _seed_project_with_modules(db, module_type_by_priority):
    """Helper — cria projeto + doc + análise + ModuleCandidate por entrada."""
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(
        db, organization_id=org.id, slug=f"mvp9-{uuid4().hex[:6]}",
    )
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="t.docx", filename=f"{uuid4()}.docx",
        file_type="docx", file_hash=h, file_size_bytes=100,
        arguider_status="completed", arguider_stage="completed",
        arguider_progress_percent=100, pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=p.id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]),
        show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]),
        improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]),
        ocg_fields_to_update=json.dumps([]),
        llm_model="anthropic:claude-haiku-4-5-20251001",
        tokens_used=0,
        latency_ms=0,
    )
    db.add(analysis)
    await db.commit()

    for priority, module_type in module_type_by_priority:
        db.add(ModuleCandidate(
            project_id=p.id,
            arguider_analysis_id=analysis.id,
            name=f"Test {module_type} {uuid4().hex[:4]}",
            description=f"Descrição técnica do {module_type}",
            module_type=module_type,
            priority=priority,
            dependencies=json.dumps([]),
            source_document_ids=json.dumps([]),
            pillar_impact=json.dumps({}),
            ready_for_codegen=False,
        ))
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_roadmap_payload_inclui_module_type(db_session):
    """Frontend precisa de module_type no payload pra filtrar/agrupar."""
    p = await _seed_project_with_modules(db_session, [
        ("high", "infrastructure"),
        ("medium", "feature"),
        ("low", "observability"),
    ])
    svc = RoadmapService(db_session)
    roadmap = await svc.get_roadmap(p.id)

    all_modules = []
    for phase in roadmap["phases"]:
        all_modules.extend(phase["modules"])

    assert len(all_modules) == 3
    types = {m["module_type"] for m in all_modules}
    assert types == {"infrastructure", "feature", "observability"}


@pytest.mark.asyncio
async def test_roadmap_payload_inclui_description(db_session):
    """Descrição técnica é obrigatória pro card detalhar o item."""
    p = await _seed_project_with_modules(db_session, [
        ("medium", "backend_service"),
    ])
    svc = RoadmapService(db_session)
    roadmap = await svc.get_roadmap(p.id)
    m = roadmap["phases"][1]["modules"][0]
    assert "description" in m
    assert "backend_service" in m["description"]


@pytest.mark.asyncio
async def test_roadmap_payload_inclui_id_do_candidato(db_session):
    """Fase 9.2 vai usar esse id pra detalhamento on-demand."""
    p = await _seed_project_with_modules(db_session, [
        ("medium", "middleware"),
    ])
    svc = RoadmapService(db_session)
    roadmap = await svc.get_roadmap(p.id)
    m = roadmap["phases"][1]["modules"][0]
    assert "id" in m
    # UUID válido
    from uuid import UUID as _UUID
    assert _UUID(m["id"])


# ============================================================================
# Arguidor — contrato de prompt
# ============================================================================

def test_prompt_do_arguider_menciona_6_categorias():
    """Sem essa instrução no prompt, LLM volta a gerar só 'feature'."""
    source = Path("/app/app/services/arguider_service.py").read_text()
    for cat in CANONICAL_MODULE_TYPES:
        assert f"`{cat}`" in source, (
            f"prompt do Arguidor não menciona categoria `{cat}`"
        )
    assert "CATEGORIAS CANÔNICAS" in source


def test_arguider_usa_normalize_module_type():
    """Defesa: mesmo que o LLM emita valor fora do canon, o backend
    normaliza antes de persistir."""
    source = Path("/app/app/services/arguider_service.py").read_text()
    assert "from app.constants.module_categories import" in source
    assert "normalize_module_type" in source
    assert "normalize_module_type(raw_type)" in source


# ============================================================================
# Integração — persistência com normalização
# ============================================================================

@pytest.mark.asyncio
async def test_valor_legado_component_normalizado_na_persistencia(db_session):
    """Simula LLM que emitiu `component` — ao salvar, deve virar `feature`."""
    import hashlib
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(
        db_session, organization_id=org.id, slug="mvp9-legacy",
    )
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="t.docx", filename=f"{uuid4()}.docx",
        file_type="docx", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
    )
    db_session.add(doc)
    await db_session.commit()
    analysis = ArguiderAnalysis(
        id=uuid4(),
        document_id=doc.id,
        project_id=p.id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]), show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]), improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]), ocg_fields_to_update=json.dumps([]),
        llm_model="x", tokens_used=0, latency_ms=0,
    )
    db_session.add(analysis)
    await db_session.commit()

    raw_from_llm = "component"  # legado pré-MVP9
    canonical = normalize_module_type(raw_from_llm)
    mc = ModuleCandidate(
        project_id=p.id,
        arguider_analysis_id=analysis.id,
        name="Item legado",
        description="",
        module_type=canonical,
        priority="medium",
        dependencies=json.dumps([]),
        source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}),
        ready_for_codegen=False,
    )
    db_session.add(mc)
    await db_session.commit()

    row = (await db_session.execute(
        select(ModuleCandidate).where(ModuleCandidate.id == mc.id)
    )).scalar_one()
    assert row.module_type == "feature"  # não é mais "component"
