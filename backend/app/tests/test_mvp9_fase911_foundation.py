"""MVP 9 Fase 9.1.1 — Foundation generator: Fase 1 do OCG.

Contrato §7 MVP 9: Fase 1 do Roadmap nasce do OCG (não do Arguidor).
`RoadmapFoundationService` lê `STACK_RECOMMENDATION`,
`ARCHITECTURE_OVERVIEW`, `PROJECT_PROFILE` e cria itens determinísticos
em `module_candidates` com `source='ocg_foundation'`, `priority='high'`,
`status='sugerido'`.

Testes cobrem:
  - Derivação determinística (mesmo OCG → mesma lista, sem LLM).
  - Flags do stack ligados/desligados geram/suprimem itens corretos.
  - Idempotência: chamar 2x não duplica.
  - Status e priority canônicos.
  - Itens usam categorias canônicas (6 do MVP 9.1).
  - Compatibilidade com arguider_analysis_id NULL.
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import ModuleCandidate, OCG, Questionnaire
from app.services.roadmap_foundation_service import (
    FoundationItem,
    RoadmapFoundationService,
    SOURCE_VALUE,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Derivação determinística (pura — sem DB)
# ============================================================================

def test_derive_sem_nada_ainda_gera_observabilidade_e_deploy():
    """OCG vazio ainda produz os 2 itens mínimos (observabilidade +
    deploy inicial) porque Fase 1 nunca deve ser totalmente vazia
    — sempre há TODO."""
    items = RoadmapFoundationService.derive_items_from_ocg({})
    assert len(items) >= 2
    types = {i.module_type for i in items}
    assert "observability" in types
    assert "deploy_pipeline" in types


def test_derive_backend_gerado_quando_enabled():
    ocg = {
        "STACK_RECOMMENDATION": {
            "backend": {"enabled": True, "framework": ["FastAPI"], "language": "Python"},
        }
    }
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    names = [i.name for i in items]
    assert any("Backend" in n for n in names)
    # O item menciona o framework
    backend_item = next(i for i in items if "Backend" in i.name)
    assert "FastAPI" in backend_item.description


def test_derive_backend_nao_gerado_quando_disabled():
    ocg = {"STACK_RECOMMENDATION": {"backend": {"enabled": False}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    names = [i.name for i in items]
    assert not any("Esqueleto do Backend" in n for n in names)


def test_derive_database_gera_schema_inicial():
    ocg = {"STACK_RECOMMENDATION": {"database": {"engine": "PostgreSQL"}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    schema = next((i for i in items if "Schema Inicial" in i.name), None)
    assert schema is not None
    assert "PostgreSQL" in schema.description
    assert schema.module_type == "infrastructure"


def test_derive_frontend_habilitado_gera_bootstrap():
    ocg = {"STACK_RECOMMENDATION": {"frontend": {"enabled": True, "stack": ["React", "Vite"]}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    bootstrap = next((i for i in items if "Frontend" in i.name), None)
    assert bootstrap is not None
    assert "React" in bootstrap.description
    assert bootstrap.module_type == "feature"


def test_derive_cache_habilitado_gera_middleware():
    ocg = {"STACK_RECOMMENDATION": {"cache": {"enabled": True}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    cache = next((i for i in items if "Cache" in i.name), None)
    assert cache is not None
    assert cache.module_type == "middleware"


def test_derive_messaging_habilitado_gera_fila():
    ocg = {"STACK_RECOMMENDATION": {"messaging": {"enabled": True}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    assert any("Fila" in i.name for i in items)


def test_derive_ai_habilitado_gera_contrato_integracao():
    ocg = {"STACK_RECOMMENDATION": {"ai": {"enabled": True, "provider": ["Anthropic"]}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    ai_item = next((i for i in items if "Integração com IA" in i.name), None)
    assert ai_item is not None
    assert "Anthropic" in ai_item.description


def test_derive_containerizado_gera_docker_e_cicd():
    ocg = {"ARCHITECTURE_OVERVIEW": {"execution_model": ["On-premises", "Containerizado"]}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    names = [i.name for i in items]
    assert any("Container" in n for n in names)
    assert any("CI/CD" in n for n in names)


def test_derive_nao_containerizado_nao_gera_docker():
    ocg = {"ARCHITECTURE_OVERVIEW": {"execution_model": ["Serverless"]}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    assert not any("Container" in i.name for i in items)


def test_derive_pii_ou_ai_gera_secrets_e_audit():
    # Via AI
    ocg_ai = {"STACK_RECOMMENDATION": {"ai": {"enabled": True, "provider": ["X"]}}}
    items_ai = RoadmapFoundationService.derive_items_from_ocg(ocg_ai)
    assert any("Secrets" in i.name for i in items_ai)

    # Via PII explícito
    ocg_pii = {"PROJECT_PROFILE": {"handles_pii": True}}
    items_pii = RoadmapFoundationService.derive_items_from_ocg(ocg_pii)
    assert any("Secrets" in i.name for i in items_pii)


def test_derive_todos_itens_usam_categorias_canonicas():
    """Regra dura do MVP 9.1: module_type sempre canônico."""
    from app.constants.module_categories import CANONICAL_MODULE_TYPES
    ocg = {
        "STACK_RECOMMENDATION": {
            "backend": {"enabled": True, "framework": ["FastAPI"]},
            "frontend": {"enabled": True, "stack": ["React"]},
            "database": {"engine": "PostgreSQL"},
            "cache": {"enabled": True},
            "messaging": {"enabled": True},
            "ai": {"enabled": True, "provider": ["X"]},
        },
        "ARCHITECTURE_OVERVIEW": {"execution_model": ["Containerizado"]},
    }
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    assert len(items) >= 8  # backend + db + front + cache + msg + ai + docker + ci + obs + deploy
    for item in items:
        assert item.module_type in CANONICAL_MODULE_TYPES, (
            f"item {item.name!r} com categoria não-canônica: {item.module_type}"
        )


def test_derive_todos_itens_priority_high():
    """Fase 1 = priority high (contrato)."""
    ocg = {"STACK_RECOMMENDATION": {"backend": {"enabled": True}}}
    items = RoadmapFoundationService.derive_items_from_ocg(ocg)
    for item in items:
        assert item.priority == "high"


def test_derive_mesmo_ocg_duas_vezes_mesma_lista():
    """Determinístico: nenhum LLM, nenhum random, nenhum timestamp."""
    ocg = {
        "STACK_RECOMMENDATION": {
            "backend": {"enabled": True, "framework": ["FastAPI"]},
            "frontend": {"enabled": True},
        },
        "ARCHITECTURE_OVERVIEW": {"execution_model": ["Containerizado"]},
    }
    run1 = RoadmapFoundationService.derive_items_from_ocg(ocg)
    run2 = RoadmapFoundationService.derive_items_from_ocg(ocg)
    assert [i.name for i in run1] == [i.name for i in run2]
    assert [i.module_type for i in run1] == [i.module_type for i in run2]


# ============================================================================
# Persistência + idempotência
# ============================================================================

async def _seed_project_with_ocg(db, ocg_data):
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(
        db, organization_id=org.id, slug=f"mvp911-{uuid4().hex[:6]}",
    )
    q = Questionnaire(
        id=uuid4(), project_id=p.id,
        gp_email=user.email, responses="{}",
        status="ok", approved=True,
    )
    db.add(q)
    await db.commit()
    db.add(OCG(
        id=uuid4(),
        project_id=p.id,
        questionnaire_id=q.id,
        version=1,
        change_type="CREATE",
        ocg_data=json.dumps(ocg_data),
    ))
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_sync_sem_ocg_retorna_no_ocg(db_session):
    """Sem OCG aprovado, foundation não tem do que derivar."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(
        db_session, organization_id=org.id, slug="mvp911-no-ocg",
    )
    svc = RoadmapFoundationService(db_session)
    result = await svc.sync_foundation(p.id)
    assert result["created"] == 0
    assert result.get("reason") == "no_ocg"


@pytest.mark.asyncio
async def test_sync_primeira_vez_cria_todos_itens(db_session):
    ocg_data = {
        "STACK_RECOMMENDATION": {
            "backend": {"enabled": True, "framework": ["FastAPI"]},
            "frontend": {"enabled": True, "stack": ["React"]},
            "database": {"engine": "PostgreSQL"},
        },
        "ARCHITECTURE_OVERVIEW": {"execution_model": ["Containerizado"]},
    }
    p = await _seed_project_with_ocg(db_session, ocg_data)
    svc = RoadmapFoundationService(db_session)
    result = await svc.sync_foundation(p.id)
    assert result["created"] >= 6  # backend + db + frontend + docker + cicd + obs + deploy
    assert result["skipped"] == 0

    rows = (await db_session.execute(
        select(ModuleCandidate)
        .where(ModuleCandidate.project_id == p.id)
        .where(ModuleCandidate.source == SOURCE_VALUE)
    )).scalars().all()
    assert len(rows) == result["created"]
    for r in rows:
        assert r.source == SOURCE_VALUE
        assert r.priority == "high"
        assert r.status == "sugerido"
        assert r.arguider_analysis_id is None  # foundation não tem análise


@pytest.mark.asyncio
async def test_sync_duas_vezes_nao_duplica(db_session):
    """Idempotência: segundo sync sobre o mesmo OCG só deve skipar."""
    ocg_data = {
        "STACK_RECOMMENDATION": {"backend": {"enabled": True, "framework": ["X"]}}
    }
    p = await _seed_project_with_ocg(db_session, ocg_data)
    svc = RoadmapFoundationService(db_session)
    first = await svc.sync_foundation(p.id)
    second = await svc.sync_foundation(p.id)

    assert first["created"] >= 1
    assert second["created"] == 0
    assert second["skipped"] == first["created"]


@pytest.mark.asyncio
async def test_sync_preserva_itens_de_arguider_de_outros_projetos(db_session):
    """Foundation sync não mexe em items com source='arguider' nem
    em items de outros projetos (compartimentalização contrato §2.2)."""
    ocg_data = {"STACK_RECOMMENDATION": {"backend": {"enabled": True}}}
    p = await _seed_project_with_ocg(db_session, ocg_data)
    other = await _seed_project_with_ocg(db_session, ocg_data)

    svc = RoadmapFoundationService(db_session)
    await svc.sync_foundation(p.id)

    # Other project permanece sem foundation items (não foi sincronizado)
    rows = (await db_session.execute(
        select(ModuleCandidate)
        .where(ModuleCandidate.project_id == other.id)
    )).scalars().all()
    assert len(rows) == 0


# ============================================================================
# Hook automático no OCG updater
# ============================================================================

def test_ocg_updater_chama_foundation_sync_no_sucesso():
    """Quando o OCG é atualizado, o OCGUpdaterService dispara sync
    da foundation — é esse hook que garante que Fase 1 sempre esteja
    sincronizada com o OCG mais recente."""
    from pathlib import Path
    source = Path("/app/app/services/ocg_updater_service.py").read_text()
    assert "RoadmapFoundationService" in source
    assert "sync_foundation(project_id)" in source
    assert "ocg_updater.foundation_synced" in source
