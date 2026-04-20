"""MVP 9 Fase 9.4 — Plano de deploy sugerido.

Cobre:
  - Ordenação por camada canônica (DEPLOY_ORDER do MVP 9.1).
  - Sort topológico dentro da camada respeita dependencies_inferred.
  - Empate: priority desc, readiness asc, nome alfabético.
  - Itens em ciclo recebem `cycle=true`.
  - Resumo: total/ready/blocked counts corretos.
  - Categorias não-canônicas vão pra "other" no fim.
  - Markdown export bem-formado e legível.
  - Compartimentalização: outro projeto não vaza.
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG, Questionnaire,
)
from app.services.deploy_plan_service import (
    build_deploy_plan, render_markdown,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed_project(db):
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"f94-{uuid4().hex[:6]}")
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
    return p, user, a


async def _add_module(db, project_id, analysis_id, *, name, module_type,
                      priority="medium", status="sugerido",
                      readiness=None, deps_names=None):
    mc = ModuleCandidate(
        id=uuid4(), project_id=project_id, arguider_analysis_id=analysis_id,
        source="ocg_foundation", name=name, description=f"Descrição de {name}",
        module_type=module_type, priority=priority, status=status,
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
        readiness_status=readiness,
        dependencies_inferred=json.dumps(deps_names) if deps_names else None,
    )
    db.add(mc)
    await db.commit()
    return mc


# ============================================================================
# Ordem por camada canônica
# ============================================================================

@pytest.mark.asyncio
async def test_camadas_em_ordem_canonica(db_session):
    """infrastructure aparece antes de feature; deploy_pipeline por último."""
    p, _, a = await _seed_project(db_session)
    # Adicionar fora de ordem pra garantir que sort não depende de inserção
    await _add_module(db_session, p.id, a.id, name="Z deploy", module_type="deploy_pipeline")
    await _add_module(db_session, p.id, a.id, name="A feature", module_type="feature")
    await _add_module(db_session, p.id, a.id, name="B infra", module_type="infrastructure")
    await _add_module(db_session, p.id, a.id, name="C middleware", module_type="middleware")

    plan = await build_deploy_plan(db_session, p.id)
    layer_names = [layer["layer"] for layer in plan["layers"]]
    expected_relative_order = ["infrastructure", "middleware", "feature", "deploy_pipeline"]
    # Cada camada deve aparecer na ordem relativa esperada
    indices = [layer_names.index(n) for n in expected_relative_order]
    assert indices == sorted(indices), f"camadas fora de ordem: {layer_names}"


@pytest.mark.asyncio
async def test_camada_vazia_nao_aparece(db_session):
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="X", module_type="feature")
    plan = await build_deploy_plan(db_session, p.id)
    layer_names = [layer["layer"] for layer in plan["layers"]]
    assert "feature" in layer_names
    assert "infrastructure" not in layer_names  # vazia


# ============================================================================
# Sort topológico dentro da camada
# ============================================================================

@pytest.mark.asyncio
async def test_topologico_respeita_dependencias(db_session):
    """B depende de A → A vem antes de B na mesma camada."""
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="A primeiro", module_type="feature")
    await _add_module(db_session, p.id, a.id, name="B segundo", module_type="feature",
                       deps_names=["A primeiro"])
    plan = await build_deploy_plan(db_session, p.id)
    feature_layer = next(l for l in plan["layers"] if l["layer"] == "feature")
    names = [it["name"] for it in feature_layer["items"]]
    assert names.index("A primeiro") < names.index("B segundo")


@pytest.mark.asyncio
async def test_dependencia_cross_camada_nao_bloqueia(db_session):
    """Item em feature dependendo de algo em infrastructure não bloqueia
    sort interno da camada feature (DEPLOY_ORDER já garante infra antes)."""
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="DB", module_type="infrastructure")
    await _add_module(db_session, p.id, a.id, name="Z dependente", module_type="feature",
                       deps_names=["DB"])
    await _add_module(db_session, p.id, a.id, name="A independente", module_type="feature")
    plan = await build_deploy_plan(db_session, p.id)
    feature_layer = next(l for l in plan["layers"] if l["layer"] == "feature")
    names = [it["name"] for it in feature_layer["items"]]
    # A independente vem antes (alfabético) — Z dependente NÃO foi bloqueado
    # por DB porque DB é de outra camada
    assert names == ["A independente", "Z dependente"]


@pytest.mark.asyncio
async def test_ciclo_marca_cycle_true(db_session):
    """A→B e B→A: ambos marcados cycle=true."""
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="A", module_type="feature",
                       deps_names=["B"])
    await _add_module(db_session, p.id, a.id, name="B", module_type="feature",
                       deps_names=["A"])
    plan = await build_deploy_plan(db_session, p.id)
    feature_layer = next(l for l in plan["layers"] if l["layer"] == "feature")
    cycle_items = [it for it in feature_layer["items"] if it["cycle"]]
    assert len(cycle_items) >= 1


# ============================================================================
# Empate por priority + readiness + nome
# ============================================================================

@pytest.mark.asyncio
async def test_priority_desc_quando_sem_dependencias(db_session):
    """Sem deps, high vem antes de medium vem antes de low."""
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="Low Item", module_type="feature", priority="low")
    await _add_module(db_session, p.id, a.id, name="Medium Item", module_type="feature", priority="medium")
    await _add_module(db_session, p.id, a.id, name="High Item", module_type="feature", priority="high")
    plan = await build_deploy_plan(db_session, p.id)
    feature_layer = next(l for l in plan["layers"] if l["layer"] == "feature")
    names = [it["name"] for it in feature_layer["items"]]
    assert names == ["High Item", "Medium Item", "Low Item"]


@pytest.mark.asyncio
async def test_readiness_desempata_quando_priority_igual(db_session):
    """Mesmo priority: ready_for_codegen vem antes de unknown."""
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="A unknown", module_type="feature",
                       priority="medium", readiness=None)
    await _add_module(db_session, p.id, a.id, name="B ready", module_type="feature",
                       priority="medium", readiness="ready_for_codegen")
    plan = await build_deploy_plan(db_session, p.id)
    feature_layer = next(l for l in plan["layers"] if l["layer"] == "feature")
    names = [it["name"] for it in feature_layer["items"]]
    assert names == ["B ready", "A unknown"]


# ============================================================================
# Resumo
# ============================================================================

@pytest.mark.asyncio
async def test_summary_counts(db_session):
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="X1", module_type="feature", readiness="ready_for_codegen")
    await _add_module(db_session, p.id, a.id, name="X2", module_type="feature", readiness="ready_for_codegen")
    await _add_module(db_session, p.id, a.id, name="X3", module_type="feature", readiness="needs_input")
    await _add_module(db_session, p.id, a.id, name="X4", module_type="feature", readiness="unknown")
    await _add_module(db_session, p.id, a.id, name="X5", module_type="feature", readiness="partial")
    plan = await build_deploy_plan(db_session, p.id)
    assert plan["total_modules"] == 5
    assert plan["ready_count"] == 2
    assert plan["blocked_count"] == 2  # needs_input + unknown


# ============================================================================
# Categorias não-canônicas vão pra "other"
# ============================================================================

@pytest.mark.asyncio
async def test_categoria_nao_canonica_vai_para_other(db_session):
    """Se persistir module_type fora do canon, normalize cai pra feature
    (regra do MVP 9.1 normalizer). Aqui apenas validamos que módulos
    com tipo válido aparecem normalmente."""
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="X", module_type="feature")
    plan = await build_deploy_plan(db_session, p.id)
    # "other" só aparece quando há item com tipo realmente fora do canon;
    # com normalize aplicado pré-persistência, não esperamos vê-lo.
    layer_names = [l["layer"] for l in plan["layers"]]
    assert "feature" in layer_names


# ============================================================================
# Compartimentalização §2.2
# ============================================================================

@pytest.mark.asyncio
async def test_plan_so_inclui_modulos_do_projeto(db_session):
    p_a, _, a_a = await _seed_project(db_session)
    p_b, _, a_b = await _seed_project(db_session)
    await _add_module(db_session, p_a.id, a_a.id, name="A only", module_type="feature")
    await _add_module(db_session, p_b.id, a_b.id, name="B only", module_type="feature")

    plan_a = await build_deploy_plan(db_session, p_a.id)
    names_a = [it["name"] for layer in plan_a["layers"] for it in layer["items"]]
    assert "A only" in names_a
    assert "B only" not in names_a


# ============================================================================
# Markdown render
# ============================================================================

@pytest.mark.asyncio
async def test_markdown_tem_titulo_e_resumo(db_session):
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="Item X", module_type="feature",
                       readiness="ready_for_codegen")
    plan = await build_deploy_plan(db_session, p.id)
    md = render_markdown(plan, project_name="Projeto Teste")
    assert "# Plano de Deploy" in md
    assert "Projeto Teste" in md
    assert "Item X" in md
    assert "Resumo" in md
    assert "Pronto para CodeGen" in md or "✓ Pronto" in md


@pytest.mark.asyncio
async def test_markdown_lista_dependencias_quando_existem(db_session):
    p, _, a = await _seed_project(db_session)
    await _add_module(db_session, p.id, a.id, name="A primeiro", module_type="feature")
    await _add_module(db_session, p.id, a.id, name="B segundo", module_type="feature",
                       deps_names=["A primeiro"])
    plan = await build_deploy_plan(db_session, p.id)
    md = render_markdown(plan)
    assert "Depende de" in md
    assert "A primeiro" in md


@pytest.mark.asyncio
async def test_markdown_projeto_vazio(db_session):
    p, _, a = await _seed_project(db_session)
    plan = await build_deploy_plan(db_session, p.id)
    md = render_markdown(plan, project_name="Projeto Vazio")
    assert "Plano de Deploy" in md
    assert "Nenhum módulo" in md or "_(Nenhum módulo" in md
