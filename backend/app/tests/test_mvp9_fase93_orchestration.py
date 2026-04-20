"""MVP 9 Fase 9.3 — Orquestração Premium do Roadmap.

Cobre:
  - Resolve provider Premium (Anthropic preferido > OpenAI; Ollama
    explicitamente ignorado).
  - Parser tolerante (puro, fence, balanced).
  - Normalização força shape estável + limites + sanitiza dependencies
    pra só nomes/ids existentes em neighbors.
  - Sanity: ready_for_codegen com gaps vira partial.
  - Persistência: campos readiness_* no module_candidates.
  - Compartimentalização entre projetos.
  - Erro explícito sem Premium configurado.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG, Questionnaire,
)
from app.services.module_orchestration_service import (
    CANONICAL_READINESS, _normalize_response, _parse_response,
    _resolve_premium_config, evaluate_module_readiness,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed_project_with_modules(db, modules=None):
    """Seeds projeto + ocg + 1 módulo principal + N vizinhos."""
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"f93-{uuid4().hex[:6]}")
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
        version=1, change_type="CREATE",
        ocg_data=json.dumps({"STACK_RECOMMENDATION": {"backend": {"enabled": True, "framework": ["FastAPI"]}}}),
    ))

    main = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
        source="ocg_foundation", name="Conector DataJud HTTP",
        description="Cliente HTTP", module_type="backend_service",
        priority="high", status="adicionado",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
        details_json=json.dumps({
            "what_it_is": "Cliente HTTP pra DataJud", "prerequisites": [],
            "missing_inputs": [], "input_examples": [],
            "suggested_template_sections": [],
        }),
    )
    db.add(main)
    other_neighbor = None
    if modules:
        for n in modules:
            mc = ModuleCandidate(
                id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
                source="arguider", name=n, description="",
                module_type="feature", priority="medium", status="sugerido",
                dependencies=json.dumps([]), source_document_ids=json.dumps([]),
                pillar_impact=json.dumps({}), ready_for_codegen=False,
            )
            db.add(mc)
            other_neighbor = mc
    await db.commit()
    return p, main, other_neighbor


# ============================================================================
# Resolve Premium config
# ============================================================================

@pytest.mark.asyncio
async def test_resolve_premium_anthropic_preferido():
    chain = [
        {"provider": "anthropic", "model": None, "base_url": None},
        {"provider": "openai", "model": None, "base_url": None},
    ]
    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value="sk-fake"),
    ):
        cfg = await _resolve_premium_config(MagicMock(), uuid4())
    assert cfg["provider"] == "anthropic"
    assert cfg["model"]  # default aplicado


@pytest.mark.asyncio
async def test_resolve_premium_ignora_ollama():
    """Ollama é local — alta criticidade não usa local (regra dura §6.3)."""
    chain = [
        {"provider": "ollama", "model": "qwen", "base_url": "http://x"},
        {"provider": "openai", "model": "gpt-4o-mini", "base_url": None},
    ]
    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value="sk-openai"),
    ):
        cfg = await _resolve_premium_config(MagicMock(), uuid4())
    assert cfg["provider"] == "openai"  # pulou ollama


@pytest.mark.asyncio
async def test_resolve_premium_sem_chave_retorna_none():
    chain = [{"provider": "anthropic", "model": None, "base_url": None}]
    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value=None),
    ):
        cfg = await _resolve_premium_config(MagicMock(), uuid4())
    assert cfg is None


# ============================================================================
# Parser
# ============================================================================

def test_parse_json_puro():
    out = _parse_response('{"readiness_status": "ready_for_codegen", "gaps": []}')
    assert out["readiness_status"] == "ready_for_codegen"


def test_parse_em_fence():
    text = '```json\n{"readiness_status": "partial", "gaps": ["x"]}\n```'
    assert _parse_response(text)["readiness_status"] == "partial"


def test_parse_lixo_total_retorna_dict_vazio():
    assert _parse_response("não consegui") == {}


# ============================================================================
# Normalização
# ============================================================================

def test_normalize_status_invalido_vira_unknown():
    out = _normalize_response({"readiness_status": "definitely_yes"}, neighbors=[])
    assert out["readiness_status"] == "unknown"


def test_normalize_canonicos_preservados():
    for s in CANONICAL_READINESS:
        out = _normalize_response({"readiness_status": s}, neighbors=[])
        # ready_for_codegen demote-se quando há gaps; sem gaps, mantém
        if s == "ready_for_codegen":
            assert out["readiness_status"] == "ready_for_codegen"
        else:
            assert out["readiness_status"] == s


def test_normalize_ready_com_gaps_vira_partial():
    """Sanity check do contrato: ready_for_codegen exige zero gaps."""
    out = _normalize_response(
        {"readiness_status": "ready_for_codegen", "gaps": ["falta X"]},
        neighbors=[],
    )
    assert out["readiness_status"] == "partial"


def test_normalize_gaps_limitados_a_8():
    out = _normalize_response(
        {"readiness_status": "partial", "gaps": [f"gap {i}" for i in range(20)]},
        neighbors=[],
    )
    assert len(out["gaps"]) == 8


def test_normalize_gaps_aceita_dict_com_text():
    out = _normalize_response(
        {"readiness_status": "partial", "gaps": [{"text": "x"}, {"description": "y"}]},
        neighbors=[],
    )
    assert out["gaps"] == ["x", "y"]


def test_normalize_dependencies_filtra_pra_neighbors_existentes():
    """LLM pode chutar nomes — só aceitamos os que estão na lista."""
    neighbors = [
        {"id": "uuid-1", "name": "Módulo A", "module_type": "feature", "status": "sugerido"},
        {"id": "uuid-2", "name": "Módulo B", "module_type": "feature", "status": "sugerido"},
    ]
    out = _normalize_response(
        {"readiness_status": "partial",
         "dependencies": ["uuid-1", "Módulo B", "Módulo Inventado", "uuid-9999"]},
        neighbors=neighbors,
    )
    # Aceita uuid-1 (id match) e "Módulo B" (name match)
    assert "uuid-1" in out["dependencies"]
    assert "Módulo B" in out["dependencies"]
    assert "Módulo Inventado" not in out["dependencies"]
    assert "uuid-9999" not in out["dependencies"]


def test_normalize_dependencies_case_insensitive():
    neighbors = [{"id": "x", "name": "Módulo A", "module_type": "f", "status": "s"}]
    out = _normalize_response(
        {"readiness_status": "partial", "dependencies": ["módulo a"]},
        neighbors=neighbors,
    )
    assert "módulo a" in out["dependencies"]


def test_normalize_dependencies_limite_5():
    neighbors = [{"id": str(i), "name": f"M{i}", "module_type": "f", "status": "s"} for i in range(20)]
    deps_raw = [str(i) for i in range(20)]
    out = _normalize_response(
        {"readiness_status": "partial", "dependencies": deps_raw},
        neighbors=neighbors,
    )
    assert len(out["dependencies"]) == 5


def test_normalize_complexity_invalida_vira_none():
    out = _normalize_response(
        {"readiness_status": "partial", "estimated_complexity": "extreme"},
        neighbors=[],
    )
    assert out["estimated_complexity"] is None


def test_normalize_shape_completo():
    out = _normalize_response({}, neighbors=[])
    expected = {"readiness_status", "readiness_reasoning", "gaps", "dependencies", "estimated_complexity"}
    assert set(out.keys()) == expected


# ============================================================================
# Persistência
# ============================================================================

@pytest.mark.asyncio
async def test_evaluate_persiste_readiness_no_modulo(db_session):
    p, main, _ = await _seed_project_with_modules(db_session)

    fake_response = json.dumps({
        "readiness_status": "needs_input",
        "readiness_reasoning": "Falta endpoint da API DataJud",
        "gaps": ["URL base do DataJud", "Schema de paginação"],
        "dependencies": [],
        "estimated_complexity": "medium",
    })

    with patch(
        "app.services.module_orchestration_service._resolve_premium_config",
        new=AsyncMock(return_value={
            "provider": "anthropic", "model": "claude-haiku", "api_key": "sk-fake",
        }),
    ), patch(
        "app.services.module_orchestration_service._call_premium",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await evaluate_module_readiness(db_session, p.id, main.id)

    assert result["readiness_status"] == "needs_input"
    assert len(result["gaps"]) == 2
    assert result["_provider"] == "anthropic"

    await db_session.refresh(main)
    assert main.readiness_status == "needs_input"
    persisted_gaps = json.loads(main.readiness_gaps)
    assert "URL base do DataJud" in persisted_gaps
    assert main.readiness_provider == "anthropic"
    assert main.readiness_evaluated_at is not None


@pytest.mark.asyncio
async def test_evaluate_modulo_outro_projeto_value_error(db_session):
    p_a, main_a, _ = await _seed_project_with_modules(db_session)
    p_b, _, _ = await _seed_project_with_modules(db_session)
    with pytest.raises(ValueError):
        await evaluate_module_readiness(db_session, p_b.id, main_a.id)


@pytest.mark.asyncio
async def test_evaluate_sem_premium_levanta_runtime(db_session):
    p, main, _ = await _seed_project_with_modules(db_session)
    with patch(
        "app.services.module_orchestration_service._resolve_premium_config",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(RuntimeError, match="Premium"):
            await evaluate_module_readiness(db_session, p.id, main.id)


@pytest.mark.asyncio
async def test_evaluate_filtra_dependencias_a_neighbors(db_session):
    """Mesmo se Premium chutar dependência, filtramos pros vizinhos reais."""
    p, main, neighbor = await _seed_project_with_modules(
        db_session, modules=["Módulo Vizinho Real"],
    )

    fake = json.dumps({
        "readiness_status": "partial",
        "readiness_reasoning": "ok",
        "gaps": ["x"],
        "dependencies": ["Módulo Inventado", neighbor.name],
        "estimated_complexity": "low",
    })

    with patch(
        "app.services.module_orchestration_service._resolve_premium_config",
        new=AsyncMock(return_value={
            "provider": "anthropic", "model": "claude-haiku", "api_key": "sk-x",
        }),
    ), patch(
        "app.services.module_orchestration_service._call_premium",
        new=AsyncMock(return_value=fake),
    ):
        await evaluate_module_readiness(db_session, p.id, main.id)

    await db_session.refresh(main)
    persisted_deps = json.loads(main.dependencies_inferred)
    assert neighbor.name in persisted_deps
    assert "Módulo Inventado" not in persisted_deps


# ============================================================================
# Hook contrato
# ============================================================================

def test_pipeline_dispara_evaluate_readiness_apos_link():
    """Após Fase 9.5.2 vincular módulo, hook chama evaluate Premium."""
    from pathlib import Path
    source = Path("/app/app/services/ingestion_service.py").read_text()
    assert "_evaluate_readiness_safe" in source
    assert "evaluate_module_readiness" in source
    # readiness_skipped_no_premium documenta path quando Premium ausente
    assert "ingestion.readiness_skipped_no_premium" in source
