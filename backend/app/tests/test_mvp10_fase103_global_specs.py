"""MVP 10 Fase 10.3 — Specs globais security/compliance via Premium.

Cobre:
  - Resolve Premium (Anthropic > OpenAI; Ollama ignorado §6.3).
  - Sem Premium → RuntimeError (sem fallback local).
  - Geração persiste com module_id=NULL, status='draft', ocg_version.
  - Idempotência: regerar sobrescreve in-place + rebaixa status.
  - spec_type fora de {security, compliance} → ValueError.
  - Compartimentalização por projeto.
  - Prompt inclui OCG consolidado (profile, stack, arch, pillars, compliance).
  - Parser strip fence externo.
  - Bulk regenera ambos.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG,
    Questionnaire, TestSpec,
)
from app.services.global_spec_generator_service import (
    SUPPORTED_GLOBAL_TYPES, _build_prompt, _render_compliance,
    _render_deliverables, _render_pillars, _render_stack,
    _resolve_premium_config, _strip_outer_fence,
    generate_global_spec, regenerate_all_global_specs,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Helpers
# ============================================================================

async def _seed_project_with_rich_ocg(db):
    """Seed com OCG realista pra validar que prompt pega tudo."""
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(db, organization_id=org.id, slug=f"mvp10f3-{uuid4().hex[:6]}")
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
        version=5, change_type="CREATE",
        ocg_data=json.dumps({
            "PROJECT_PROFILE": {
                "initiative_type": "Novo sistema",
                "handles_pii": True,
                "criticality_level": "alta",
            },
            "STACK_RECOMMENDATION": {
                "backend": {"enabled": True, "framework": ["FastAPI"]},
                "frontend": {"enabled": True, "stack": ["React"]},
                "database": {"engine": "PostgreSQL"},
                "ai": {"enabled": True, "provider": ["Anthropic"]},
            },
            "ARCHITECTURE_OVERVIEW": {
                "execution_model": ["On-premises", "Containerizado"],
                "multi_tenant": "Não",
                "high_availability": "Futuramente",
            },
            "PILLAR_SCORES": {
                "P2_Compliance": {"score": 78, "status": "ok"},
                "P7_Security": {"score": 65, "status": "at_risk"},
            },
            "COMPLIANCE_CHECKLIST": {"lgpd": True, "iso27001": "parcial"},
            "DELIVERABLES": {
                "expected": ["API", "Painel web"],
                "output_formats": ["JSON", "PDF"],
            },
        }),
    ))
    mc = ModuleCandidate(
        id=uuid4(), project_id=p.id, arguider_analysis_id=a.id,
        source="ocg_foundation", name="Conector X",
        description="y", module_type="backend_service",
        priority="high", status="sugerido",
        dependencies=json.dumps([]), source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}), ready_for_codegen=False,
    )
    db.add(mc)
    await db.commit()
    return p, user


FAKE_SECURITY = """## Objetivo
Validar controles mínimos pro projeto.

## Modelo de ameaças
- Spoofing: login sem MFA. Severidade: Alta.

## Controles obrigatórios
- JWT + rotação.

## Testes de segurança
- Teste 1: rate limit.

## Fora do escopo técnico
- Pen-test externo.

## Riscos residuais
- Injeção SQL residual.
"""

FAKE_COMPLIANCE = "## Objetivo\nLGPD.\n\n## Aderência a normas\n- LGPD ok."


# ============================================================================
# Resolve Premium
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
    assert cfg["model"]


@pytest.mark.asyncio
async def test_resolve_premium_ignora_ollama():
    """§6.3: alta criticidade não cai pra local. Ollama explicitamente
    pulado mesmo quando é o default."""
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
    assert cfg["provider"] == "openai"  # pulou Ollama


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
        assert await _resolve_premium_config(MagicMock(), uuid4()) is None


# ============================================================================
# Validação
# ============================================================================

@pytest.mark.asyncio
async def test_spec_type_unit_rejeita_aqui(db_session):
    """Aqui só aceita security/compliance; unit/integration/e2e ficam
    na Fase 10.2 (Ollama)."""
    p, _ = await _seed_project_with_rich_ocg(db_session)
    with pytest.raises(ValueError, match="não suportado"):
        await generate_global_spec(db_session, p.id, "unit")


@pytest.mark.asyncio
async def test_sem_premium_runtime_error(db_session):
    p, _ = await _seed_project_with_rich_ocg(db_session)
    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(RuntimeError, match="Premium"):
            await generate_global_spec(db_session, p.id, "security")


@pytest.mark.asyncio
async def test_projeto_sem_ocg_value_error(db_session):
    """Projeto sem OCG não dá pra gerar spec global."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug="mvp10-no-ocg")
    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ):
        with pytest.raises(ValueError, match="OCG"):
            await generate_global_spec(db_session, p.id, "security")


# ============================================================================
# Persistência
# ============================================================================

@pytest.mark.asyncio
async def test_generate_persiste_security_com_module_id_null(db_session):
    p, _ = await _seed_project_with_rich_ocg(db_session)

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "claude-haiku", "api_key": "sk-x"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(return_value=FAKE_SECURITY),
    ):
        spec = await generate_global_spec(db_session, p.id, "security")

    assert spec.module_id is None  # GLOBAL
    assert spec.spec_type == "security"
    assert spec.status == "draft"
    assert spec.generator_provider == "anthropic"
    assert spec.ocg_version_at_generation == 5
    prov = json.loads(spec.provenance_json)
    assert prov["llm"]["provider"] == "anthropic"
    assert prov["ocg_version"] == 5


@pytest.mark.asyncio
async def test_generate_compliance_separado_de_security(db_session):
    """Security e compliance coexistem — ambos com module_id=NULL mas
    spec_type diferente."""
    p, _ = await _seed_project_with_rich_ocg(db_session)

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(side_effect=[FAKE_SECURITY, FAKE_COMPLIANCE]),
    ):
        await generate_global_spec(db_session, p.id, "security")
        await generate_global_spec(db_session, p.id, "compliance")

    rows = (await db_session.execute(
        select(TestSpec).where(
            TestSpec.project_id == p.id,
            TestSpec.module_id.is_(None),
        )
    )).scalars().all()
    assert len(rows) == 2
    assert {r.spec_type for r in rows} == {"security", "compliance"}


# ============================================================================
# Idempotência
# ============================================================================

@pytest.mark.asyncio
async def test_regerar_rebaixa_status_e_mantem_id(db_session):
    p, user = await _seed_project_with_rich_ocg(db_session)

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(return_value=FAKE_SECURITY),
    ):
        s1 = await generate_global_spec(db_session, p.id, "security")

    # Aprova manualmente
    s1.status = "approved"
    from datetime import datetime, timezone as _tz
    s1.approved_by = user.id
    s1.approved_at = datetime.now(_tz.utc)
    await db_session.commit()
    original_id = s1.id

    # Regenera
    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(return_value="## Objetivo\nv2"),
    ):
        s2 = await generate_global_spec(db_session, p.id, "security")

    assert s2.id == original_id
    assert s2.status == "draft"
    assert s2.approved_by is None
    assert "v2" in s2.content


# ============================================================================
# Prompt content
# ============================================================================

@pytest.mark.asyncio
async def test_prompt_security_inclui_ocg_blocks(db_session):
    p, _ = await _seed_project_with_rich_ocg(db_session)

    captured_prompt = {"text": ""}

    async def capture_call(**kwargs):
        captured_prompt["text"] = kwargs.get("user_prompt", "")
        return FAKE_SECURITY

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(side_effect=capture_call),
    ):
        await generate_global_spec(db_session, p.id, "security")

    prompt = captured_prompt["text"]
    # OCG v5 no cabeçalho
    assert "OCG v5" in prompt
    # Perfil inclui handles_pii
    assert "handles_pii" in prompt
    # Stack inclui FastAPI
    assert "FastAPI" in prompt
    # Arquitetura inclui Containerizado
    assert "Containerizado" in prompt
    # Pilares aparecem
    assert "P2_Compliance" in prompt
    assert "P7_Security" in prompt
    # Estrutura de output: seções obrigatórias do template
    for section in ("## Objetivo", "## Modelo de ameaças", "## Controles obrigatórios",
                    "## Testes de segurança", "## Fora do escopo", "## Riscos residuais"):
        assert section in prompt


@pytest.mark.asyncio
async def test_prompt_compliance_inclui_checklist(db_session):
    p, _ = await _seed_project_with_rich_ocg(db_session)

    captured = {"text": ""}

    async def capture_call(**kwargs):
        captured["text"] = kwargs.get("user_prompt", "")
        return FAKE_COMPLIANCE

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(side_effect=capture_call),
    ):
        await generate_global_spec(db_session, p.id, "compliance")

    assert "lgpd" in captured["text"].lower()
    assert "iso27001" in captured["text"].lower() or "iso" in captured["text"].lower()
    for section in ("## Aderência a normas", "## Evidências técnicas", "## Testes de compliance",
                    "## Decisões que exigem parecer", "## Riscos de não-conformidade"):
        assert section in captured["text"]


# ============================================================================
# Bulk
# ============================================================================

@pytest.mark.asyncio
async def test_bulk_gera_security_e_compliance(db_session):
    p, _ = await _seed_project_with_rich_ocg(db_session)

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(side_effect=[FAKE_SECURITY, FAKE_COMPLIANCE]),
    ):
        report = await regenerate_all_global_specs(db_session, p.id)

    assert report["generated"] == 2
    assert report["failed"] == 0


@pytest.mark.asyncio
async def test_bulk_tolera_falha_individual(db_session):
    p, _ = await _seed_project_with_rich_ocg(db_session)

    call_count = {"n": 0}

    async def flaky(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:  # falha na 2ª chamada
            raise RuntimeError("simulated")
        return FAKE_SECURITY

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(side_effect=flaky),
    ):
        report = await regenerate_all_global_specs(db_session, p.id)

    assert report["generated"] == 1
    assert report["failed"] == 1
    assert len(report["errors"]) == 1


# ============================================================================
# Compartimentalização
# ============================================================================

@pytest.mark.asyncio
async def test_compartimentalizacao_projetos_separados(db_session):
    p_a, _ = await _seed_project_with_rich_ocg(db_session)
    p_b, _ = await _seed_project_with_rich_ocg(db_session)

    with patch(
        "app.services.global_spec_generator_service._resolve_premium_config",
        new=AsyncMock(return_value={"provider": "anthropic", "model": "x", "api_key": "k"}),
    ), patch(
        "app.services.global_spec_generator_service._call_premium",
        new=AsyncMock(return_value=FAKE_SECURITY),
    ):
        await generate_global_spec(db_session, p_a.id, "security")

    # B não tem spec — compartimentalizado
    rows = (await db_session.execute(
        select(TestSpec).where(TestSpec.project_id == p_b.id)
    )).scalars().all()
    assert rows == []


# ============================================================================
# Helpers internos
# ============================================================================

def test_render_stack_formato_legivel():
    stack = {
        "backend": {"enabled": True, "framework": ["FastAPI"], "language": "Python"},
        "frontend": {"enabled": False},
        "database": {"engine": "PostgreSQL"},
    }
    rendered = _render_stack(stack)
    assert "backend" in rendered
    assert "FastAPI" in rendered
    assert "frontend: não habilitado" in rendered
    assert "PostgreSQL" in rendered


def test_render_compliance_dict_e_list():
    dict_c = _render_compliance({"lgpd": True, "iso": "parcial"})
    assert "lgpd" in dict_c and "iso" in dict_c

    list_c = _render_compliance(["lgpd", "hipaa"])
    assert "lgpd" in list_c
    assert "hipaa" in list_c


def test_render_compliance_vazio():
    assert _render_compliance({}) == "(compliance não declarada)"
    assert _render_compliance(None) == "(compliance não declarada)"


def test_render_pillars_dict():
    p = {"P7_Security": {"score": 65, "status": "at_risk"}}
    rendered = _render_pillars(p)
    assert "P7_Security" in rendered
    assert "65" in rendered


def test_render_deliverables_dict():
    d = _render_deliverables({"expected": ["API", "Painel"], "output_formats": ["JSON"]})
    assert "API" in d
    assert "JSON" in d


def test_strip_outer_fence_remove_envolvente():
    wrapped = "```markdown\n## T\n```"
    assert _strip_outer_fence(wrapped) == "## T"


def test_supported_global_types():
    assert set(SUPPORTED_GLOBAL_TYPES) == {"security", "compliance"}
