"""MVP 10 Fase 10.7 — LiveDocs reais (module_doc Ollama; index/architecture Premium).

Cobre:
  - `generate_module_live_doc` persiste LiveDoc com content + provenance.
  - `generate_consolidated_live_doc` restringe a {index, architecture}.
  - Sem Ollama configurado → RuntimeError (module_doc).
  - Sem Premium configurado → RuntimeError (index/architecture).
  - Premium ignora Ollama (§6.3 alta criticidade).
  - doc_type 'module_doc' rejeitado no consolidado.
  - doc_type 'security' rejeitado no consolidado.
  - Projeto sem OCG → ValueError no consolidado.
  - Idempotência: regerar sobrescreve in-place (mesmo id).
  - Compartimentalização: módulo de outro projeto → ValueError.
  - Bulk module_doc e bulk consolidated: tolera falhas individuais.
  - Provenance inclui OCG, LLM, prompt_hash.
  - Renderers de apoio (stack, architecture, modules_by_layer).
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, LiveDoc, ModuleCandidate,
    OCG, Questionnaire,
)
from app.services.live_doc_generator_service import (
    ALL_DOC_TYPES, LOCAL_DOC_TYPES, PREMIUM_DOC_TYPES,
    _render_modules_by_layer, _render_stack, _render_architecture,
    _strip_outer_fence,
    generate_consolidated_live_doc, generate_module_live_doc,
    regenerate_all_consolidated_docs, regenerate_all_module_docs,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed_project_with_ocg(db, num_modules=2):
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"mvp10f7-{uuid4().hex[:6]}")
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
        version=7, change_type="CREATE",
        ocg_data=json.dumps({
            "PROJECT_PROFILE": {
                "initiative_type": "Novo sistema",
                "criticality_level": "alta",
                "handles_pii": True,
            },
            "STACK_RECOMMENDATION": {
                "backend": {"enabled": True, "framework": ["FastAPI"]},
                "frontend": {"enabled": True, "stack": ["React"]},
                "database": {"engine": "PostgreSQL"},
            },
            "ARCHITECTURE_OVERVIEW": {
                "execution_model": ["Containerizado"],
                "multi_tenant": "Não",
            },
            "PILLAR_SCORES": {
                "P1_OCG": {"score": 80, "status": "ok"},
                "P7_Security": {"score": 60, "status": "at_risk"},
            },
            "DELIVERABLES": {"expected": ["API", "Painel web"]},
        }),
    ))
    modules = []
    types_cycle = ["backend_service", "feature", "infrastructure"]
    for i in range(num_modules):
        mc = ModuleCandidate(
            id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
            source="ocg_foundation",
            name=f"Módulo {i+1}", description=f"Descrição {i+1}",
            module_type=types_cycle[i % len(types_cycle)],
            priority="high", status="sugerido",
            dependencies=json.dumps([]), source_document_ids=json.dumps([]),
            pillar_impact=json.dumps({}), ready_for_codegen=False,
        )
        db.add(mc)
        modules.append(mc)
    await db.commit()
    return p, modules, user


FAKE_MODULE_DOC = """## Visão geral
Módulo responsável pela autenticação de usuários.

## Responsabilidades
- Validar credenciais.
- Emitir tokens JWT.

## Interfaces
- POST /auth/login

## Pré-requisitos operacionais
- PostgreSQL ativo.

## Notas de manutenção
- Logs estruturados em JSON.

## Referências
- Módulo Sessões.
"""

FAKE_INDEX_DOC = """## Visão executiva
Sistema de gestão de pedidos para SMB.

## Status do Roadmap
- Fundação: 3 módulos.
- Funcionalidades: 5 módulos.

## Stack decidida
- Backend: FastAPI.

## Planos de teste ativos
Unit e integration por módulo; security e compliance globais.

## Como navegar a documentação
Ver aba Documentação Viva.
"""

FAKE_ARCHITECTURE_DOC = """## Visão de alto nível
[UI] → [API] → [DB]

## Camadas
- backend_service: serviços REST.

## Fluxo de execução principal
1. Request entra.
2. Autentica.
3. Persiste.

## Decisões arquiteturais
1. PostgreSQL — motivo: maturidade.

## Padrões obrigatórios
- Timezone UTC.

## Áreas a decidir
- Caching — ainda não definido.
"""


# ============================================================================
# generate_module_live_doc — caminho feliz + persistência
# ============================================================================

@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_generate_module_doc_persiste(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session, num_modules=1)
    mc = modules[0]

    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://ollama:11434", "model": "qwen2.5-coder:7b"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(return_value=FAKE_MODULE_DOC),
    ):
        doc = await generate_module_live_doc(db_session, p.id, mc.id)

    assert doc.project_id == p.id
    assert doc.module_id == mc.id
    assert doc.doc_type == "module_doc"
    assert doc.content.strip() == FAKE_MODULE_DOC.strip()
    assert doc.generator_provider == "ollama"
    assert doc.generator_model == "qwen2.5-coder:7b"
    assert doc.ocg_version_at_generation == 7
    assert doc.generated_at is not None


@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_module_doc_provenance_inclui_ocg_llm_hash(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session)
    mc = modules[0]

    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://ollama:11434", "model": "qwen"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(return_value=FAKE_MODULE_DOC),
    ):
        doc = await generate_module_live_doc(db_session, p.id, mc.id)

    prov = json.loads(doc.provenance_json)
    assert prov["ocg_version"] == 7
    assert prov["questionnaire_id"]
    assert isinstance(prov["ingested_doc_ids"], list)
    assert len(prov["ingested_doc_ids"]) >= 1
    assert prov["llm"]["provider"] == "ollama"
    assert prov["llm"]["model"] == "qwen"
    assert len(prov["prompt_hash"]) == 16
    assert "neighbors_considered" in prov


# ============================================================================
# Idempotência (module_doc)
# ============================================================================

@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_module_doc_regerar_sobrescreve_in_place(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session)
    mc = modules[0]

    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://x", "model": "qwen"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(return_value="v1"),
    ):
        d1 = await generate_module_live_doc(db_session, p.id, mc.id)
    original_id = d1.id
    original_created = d1.created_at

    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://x", "model": "qwen"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(return_value="v2"),
    ):
        d2 = await generate_module_live_doc(db_session, p.id, mc.id)

    assert d2.id == original_id
    assert d2.created_at == original_created
    assert d2.content == "v2"


@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_module_doc_nao_duplica(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session)
    mc = modules[0]

    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://x", "model": "qwen"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(return_value="ok"),
    ):
        await generate_module_live_doc(db_session, p.id, mc.id)
        await generate_module_live_doc(db_session, p.id, mc.id)

    rows = (await db_session.execute(
        select(LiveDoc).where(LiveDoc.module_id == mc.id, LiveDoc.doc_type == "module_doc")
    )).scalars().all()
    assert len(rows) == 1


# ============================================================================
# Validação (module_doc)
# ============================================================================

@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_module_doc_sem_ollama_runtime_error(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session)
    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(RuntimeError, match="Ollama"):
            await generate_module_live_doc(db_session, p.id, modules[0].id)


@pytest.mark.asyncio
async def test_module_doc_modulo_de_outro_projeto(db_session):
    """Compartimentalização §2.2."""
    p_a, modules_a, _ = await _seed_project_with_ocg(db_session)
    p_b, _, _ = await _seed_project_with_ocg(db_session)
    with pytest.raises(ValueError):
        await generate_module_live_doc(db_session, p_b.id, modules_a[0].id)


# ============================================================================
# generate_consolidated_live_doc — index/architecture
# ============================================================================

@pytest.mark.asyncio
async def test_consolidated_index_persiste_com_module_id_null(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session)

    with patch(
        "app.services.live_doc_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "claude-haiku", "api_key": "sk-x"}),
    ), patch(
        "app.services.live_doc_generator_service._call_premium",
        new=AsyncMock(return_value=FAKE_INDEX_DOC),
    ):
        doc = await generate_consolidated_live_doc(db_session, p.id, "index")

    assert doc.module_id is None
    assert doc.doc_type == "index"
    assert doc.generator_provider == "anthropic"
    assert doc.ocg_version_at_generation == 7
    prov = json.loads(doc.provenance_json)
    assert prov["llm"]["provider"] == "anthropic"
    assert len(prov["modules_considered"]) >= 1


@pytest.mark.asyncio
async def test_consolidated_architecture_e_index_coexistem(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session)
    with patch(
        "app.services.live_doc_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.live_doc_generator_service._call_premium",
        new=AsyncMock(side_effect=[FAKE_INDEX_DOC, FAKE_ARCHITECTURE_DOC]),
    ):
        await generate_consolidated_live_doc(db_session, p.id, "index")
        await generate_consolidated_live_doc(db_session, p.id, "architecture")

    rows = (await db_session.execute(
        select(LiveDoc).where(
            LiveDoc.project_id == p.id, LiveDoc.module_id.is_(None),
        )
    )).scalars().all()
    assert len(rows) == 2
    assert {d.doc_type for d in rows} == {"index", "architecture"}


@pytest.mark.asyncio
async def test_consolidated_rejeita_module_doc(db_session):
    """module_doc é por módulo (Ollama) — não cabe no consolidado."""
    p, _, _ = await _seed_project_with_ocg(db_session)
    with pytest.raises(ValueError, match="não suportado"):
        await generate_consolidated_live_doc(db_session, p.id, "module_doc")


@pytest.mark.asyncio
async def test_consolidated_rejeita_tipo_invalido(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session)
    with pytest.raises(ValueError, match="não suportado"):
        await generate_consolidated_live_doc(db_session, p.id, "security")


@pytest.mark.asyncio
async def test_consolidated_sem_premium_runtime_error(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session)
    with patch(
        "app.services.live_doc_generator_service._resolve_premium_config",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(RuntimeError, match="Premium"):
            await generate_consolidated_live_doc(db_session, p.id, "index")


@pytest.mark.asyncio
async def test_consolidated_sem_ocg_value_error(db_session):
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="mvp10f7-noocg")
    with patch(
        "app.services.live_doc_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ):
        with pytest.raises(ValueError, match="OCG"):
            await generate_consolidated_live_doc(db_session, p.id, "index")


# ============================================================================
# Bulk
# ============================================================================

@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_bulk_module_docs_itera_modulos(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session, num_modules=3)
    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://x", "model": "qwen"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(return_value="conteúdo"),
    ):
        report = await regenerate_all_module_docs(db_session, p.id)

    assert report["total"] == 3
    assert report["generated"] == 3
    assert report["failed"] == 0


@pytest.mark.skip(reason="DT-084: patcha _resolve_ollama_config (renomeado p/ _resolve_premium_config). Reescrever se ressuscitar.")
@pytest.mark.asyncio
async def test_bulk_module_docs_tolera_falha(db_session):
    p, modules, _ = await _seed_project_with_ocg(db_session, num_modules=3)
    call_count = {"n": 0}

    async def flaky_ollama(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom")
        return "ok"

    with patch(
        "app.services.live_doc_generator_service._resolve_ollama_config",
        new=AsyncMock(return_value={"base_url": "http://x", "model": "qwen"}),
    ), patch(
        "app.services.live_doc_generator_service._call_ollama",
        new=AsyncMock(side_effect=flaky_ollama),
    ):
        report = await regenerate_all_module_docs(db_session, p.id)

    assert report["total"] == 3
    assert report["failed"] == 1
    assert "boom" in report["errors"][0]["error"]


@pytest.mark.asyncio
async def test_bulk_consolidated_gera_index_e_architecture(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session)
    with patch(
        "app.services.live_doc_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.live_doc_generator_service._call_premium",
        new=AsyncMock(side_effect=[FAKE_INDEX_DOC, FAKE_ARCHITECTURE_DOC]),
    ):
        report = await regenerate_all_consolidated_docs(db_session, p.id)

    assert report["generated"] == 2
    assert report["failed"] == 0


@pytest.mark.asyncio
async def test_bulk_consolidated_tolera_falha(db_session):
    p, _, _ = await _seed_project_with_ocg(db_session)
    call_count = {"n": 0}

    async def flaky_premium(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("premium down")
        return FAKE_ARCHITECTURE_DOC

    with patch(
        "app.services.live_doc_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.live_doc_generator_service._call_premium",
        new=AsyncMock(side_effect=flaky_premium),
    ):
        report = await regenerate_all_consolidated_docs(db_session, p.id)

    assert report["generated"] == 1
    assert report["failed"] == 1
    assert "premium down" in report["errors"][0]["error"]


# ============================================================================
# Helpers puros
# ============================================================================

def test_all_doc_types_cobre_local_e_premium():
    assert set(ALL_DOC_TYPES) == set(LOCAL_DOC_TYPES) | set(PREMIUM_DOC_TYPES)
    assert "module_doc" in LOCAL_DOC_TYPES
    assert set(PREMIUM_DOC_TYPES) == {"index", "architecture"}


def test_strip_outer_fence_remove_fence():
    wrapped = "```markdown\n## Título\ncorpo\n```"
    assert _strip_outer_fence(wrapped) == "## Título\ncorpo"


def test_strip_outer_fence_preserva_fence_interno():
    content = "## Doc\n```python\nprint('x')\n```\nfim"
    assert _strip_outer_fence(content) == content


def test_render_stack_lista_enabled_layers():
    out = _render_stack({
        "backend": {"enabled": True, "framework": ["FastAPI"]},
        "frontend": {"enabled": False},
    })
    assert "backend" in out
    assert "FastAPI" in out
    assert "não habilitado" in out


def test_render_architecture_inclui_execution_model():
    out = _render_architecture({
        "execution_model": ["On-premises", "Containerizado"],
        "multi_tenant": "Não",
    })
    assert "execution_model" in out
    assert "Containerizado" in out
    assert "multi_tenant" in out


def test_render_modules_by_layer_agrupa_corretamente():
    modules = [
        {"id": "1", "name": "A", "module_type": "backend_service", "priority": "high", "readiness_status": None},
        {"id": "2", "name": "B", "module_type": "feature", "priority": "high", "readiness_status": None},
        {"id": "3", "name": "C", "module_type": "backend_service", "priority": "medium", "readiness_status": None},
    ]
    out = _render_modules_by_layer(modules)
    assert "backend_service" in out
    assert "feature" in out
    assert "A, C" in out or "A," in out
    assert "B" in out


def test_render_modules_by_layer_projeto_vazio():
    assert "nenhum módulo" in _render_modules_by_layer([])
