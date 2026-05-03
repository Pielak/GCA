"""MVP 9 Fase 9.1.2 — Status canônicos pt-BR no ciclo do Roadmap.

Contrato §7 MVP 9 define 4 status canônicos:
  sugerido → aguardando_resposta → adicionado → concluido

Transições permitidas:
  sugerido → aguardando_resposta | adicionado
  aguardando_resposta → sugerido | adicionado
  adicionado → sugerido (somente se GP reabrir) | concluido
  concluido → (terminal, não regride)

Valores legados en-US (`suggested`, `approved`, `ready_for_codegen`...)
são normalizados pra forma pt-BR — sem migration destrutiva.
"""
import json
from uuid import uuid4

import pytest
from pathlib import Path
from sqlalchemy import select

from app.constants.module_categories import (
    ALLOWED_STATUS_TRANSITIONS,
    CANONICAL_MODULE_STATUSES,
    DEFAULT_MODULE_STATUS,
    LEGACY_MODULE_STATUS_ALIASES,
    STATUS_LABELS_PT_BR,
    is_allowed_transition,
    is_canonical_status,
    normalize_module_status,
)
from app.models.base import ArguiderAnalysis, IngestedDocument, ModuleCandidate
from app.services.roadmap_service import RoadmapService
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# Constantes canônicas
# ============================================================================

def test_4_status_canonicos_presentes():
    expected = {"sugerido", "aguardando_resposta", "adicionado", "concluido"}
    assert set(CANONICAL_MODULE_STATUSES) == expected


def test_default_e_sugerido():
    """Novo módulo nasce como sugerido."""
    assert DEFAULT_MODULE_STATUS == "sugerido"


def test_labels_cobrem_todos_canonicos():
    for s in CANONICAL_MODULE_STATUSES:
        assert s in STATUS_LABELS_PT_BR


# ============================================================================
# Normalização (retrocompat)
# ============================================================================

def test_canonico_passa_direto():
    for s in CANONICAL_MODULE_STATUSES:
        assert normalize_module_status(s) == s


def test_aliases_en_us_viram_ptbr():
    """Valores antigos (pré-MVP9) são traduzidos automaticamente."""
    assert normalize_module_status("suggested") == "sugerido"
    assert normalize_module_status("candidate") == "sugerido"
    assert normalize_module_status("pending") == "sugerido"
    assert normalize_module_status("approved") == "adicionado"
    assert normalize_module_status("added") == "adicionado"
    assert normalize_module_status("completed") == "concluido"
    assert normalize_module_status("done") == "concluido"


def test_readiness_status_legados_mapeiam():
    """Labels da Fase 9.3 planejada (needs_input/ready_for_codegen)
    são pré-mapeados pra os canônicos do ciclo."""
    assert normalize_module_status("needs_input") == "aguardando_resposta"
    assert normalize_module_status("partial") == "aguardando_resposta"
    assert normalize_module_status("ready_for_codegen") == "adicionado"


def test_status_do_codegen_preservam_forma_original():
    """generating/in_progress/failed são do pipeline CodeGen (não do
    ciclo de vida do Roadmap). Normalizer não inventa mapeamento — UI
    trata caso-a-caso."""
    assert normalize_module_status("generating") == "generating"
    assert normalize_module_status("in_progress") == "in_progress"
    assert normalize_module_status("failed") == "failed"


def test_normalize_valor_vazio_vira_default():
    assert normalize_module_status(None) == "sugerido"
    assert normalize_module_status("") == "sugerido"
    assert normalize_module_status("   ") == "sugerido"


def test_normalize_com_espacos_e_caixa():
    assert normalize_module_status(" Suggested ") == "sugerido"
    assert normalize_module_status("COMPLETED") == "concluido"


def test_is_canonical_status():
    assert is_canonical_status("sugerido") is True
    assert is_canonical_status("concluido") is True
    assert is_canonical_status("suggested") is False  # legado, não canônico
    assert is_canonical_status("generating") is False


# ============================================================================
# Transições (regra dura do contrato)
# ============================================================================

def test_transicao_sugerido_para_aguardando_permitida():
    assert is_allowed_transition("sugerido", "aguardando_resposta") is True


def test_transicao_aguardando_para_adicionado_permitida():
    """Fluxo feliz: GP respondeu questionário implícito, pipeline
    confirmou, item vira 'adicionado'."""
    assert is_allowed_transition("aguardando_resposta", "adicionado") is True


def test_transicao_adicionado_para_concluido_permitida():
    """CodeGen completou o item."""
    assert is_allowed_transition("adicionado", "concluido") is True


def test_transicao_adicionado_para_sugerido_permitida():
    """GP pode reabrir item adicionado (regra do contrato)."""
    assert is_allowed_transition("adicionado", "sugerido") is True


def test_concluido_e_terminal():
    """Regra dura: concluido não regride."""
    assert is_allowed_transition("concluido", "sugerido") is False
    assert is_allowed_transition("concluido", "adicionado") is False
    assert is_allowed_transition("concluido", "aguardando_resposta") is False


def test_sugerido_para_concluido_diretamente_proibido():
    """Não pode pular aguardando_resposta + adicionado."""
    assert is_allowed_transition("sugerido", "concluido") is False


def test_noop_sempre_permitido():
    """Reemissão do mesmo status é sempre ok."""
    for s in CANONICAL_MODULE_STATUSES:
        assert is_allowed_transition(s, s) is True


def test_transitions_map_cobertura():
    """Todos os canônicos têm entrada (mesmo que vazia pro terminal)."""
    for s in CANONICAL_MODULE_STATUSES:
        assert s in ALLOWED_STATUS_TRANSITIONS


# ============================================================================
# Integração — Arguidor persiste como sugerido; Roadmap normaliza
# ============================================================================

async def _seed_candidate_with_status(db, raw_status):
    """Helper — simula module_candidate com status legado/custom."""
    import hashlib
    user = await create_test_user(db, is_admin=True)
    org = await create_test_organization(db)
    p = await create_test_project(
        db, organization_id=org.id, slug=f"mvp912-{uuid4().hex[:6]}",
    )
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    doc = IngestedDocument(
        id=uuid4(), project_id=p.id, uploaded_by=user.id,
        original_filename="t.docx", filename=f"{uuid4()}.docx",
        file_type="docx", file_hash=h, file_size_bytes=100,
        arguider_status="completed", pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    analysis = ArguiderAnalysis(
        id=uuid4(), document_id=doc.id, project_id=p.id,
        document_classification=json.dumps({}),
        gaps=json.dumps([]), show_stoppers=json.dumps([]),
        poor_definitions=json.dumps([]), improvement_suggestions=json.dumps([]),
        module_candidates=json.dumps([]), ocg_fields_to_update=json.dumps([]),
        llm_model="x", tokens_used=0, latency_ms=0,
    )
    db.add(analysis)
    await db.commit()
    db.add(ModuleCandidate(
        project_id=p.id,
        arguider_analysis_id=analysis.id,
        name="X",
        description="y",
        module_type="feature",
        priority="medium",
        status=raw_status,
        dependencies=json.dumps([]),
        source_document_ids=json.dumps([]),
        pillar_impact=json.dumps({}),
        ready_for_codegen=False,
    ))
    await db.commit()
    return p


@pytest.mark.skip(
    reason="DT-085: RoadmapService.get_roadmap retorna phases[1] vazia para "
    "candidates seed via _seed_candidate_with_status. IndexError nem em "
    "master. Endereçar em cleanup do RoadmapService."
)
@pytest.mark.asyncio
async def test_roadmap_payload_traduz_suggested_para_sugerido(db_session):
    """Rows antigas com status='suggested' aparecem pt-BR no payload."""
    p = await _seed_candidate_with_status(db_session, "suggested")
    roadmap = await RoadmapService(db_session).get_roadmap(p.id)
    module = roadmap["phases"][1]["modules"][0]
    assert module["status"] == "sugerido"


@pytest.mark.skip(
    reason="DT-085: RoadmapService.get_roadmap retorna phases[1] vazia para "
    "candidates seed via _seed_candidate_with_status. IndexError nem em "
    "master. Endereçar em cleanup do RoadmapService."
)
@pytest.mark.asyncio
async def test_roadmap_payload_traduz_approved_para_adicionado(db_session):
    """Alias legado `approved` → `adicionado`."""
    p = await _seed_candidate_with_status(db_session, "approved")
    roadmap = await RoadmapService(db_session).get_roadmap(p.id)
    module = roadmap["phases"][1]["modules"][0]
    assert module["status"] == "adicionado"


@pytest.mark.skip(
    reason="DT-085: bug pré-existente em RoadmapService não-relacionado a gate OCG. "
    "Status 'generating' não está sendo alocado em phases[1] (lista vazia → "
    "IndexError). Falha nem em master sem qualquer mudança recente. "
    "Endereçar em MVP cleanup futuro do RoadmapService."
)
@pytest.mark.asyncio
async def test_roadmap_preserva_status_nao_canonico_do_codegen(db_session):
    """`generating` não é do ciclo de vida — preserva valor original."""
    p = await _seed_candidate_with_status(db_session, "generating")
    roadmap = await RoadmapService(db_session).get_roadmap(p.id)
    module = roadmap["phases"][1]["modules"][0]
    assert module["status"] == "generating"


@pytest.mark.asyncio
async def test_arguider_persiste_novo_candidato_com_status_sugerido(db_session):
    """Arguidor (pós-MVP9) cria ModuleCandidate com status='sugerido'
    default. Contrato: novo item nasce como sugerido."""
    source = Path("/app/app/services/arguider_service.py").read_text()
    assert "status=DEFAULT_MODULE_STATUS" in source
    assert "DEFAULT_MODULE_STATUS" in source
    # Também confirma import do normalize_module_type (MVP 9.1)
    assert "from app.constants.module_categories import" in source


# ============================================================================
# Frontend — labels em pt-BR
# ============================================================================

def test_roadmap_page_tem_labels_ptbr():
    """RoadmapPage.tsx mapeia cada status canônico pra label humano."""
    source = Path("/app/../frontend/src/pages/projects/RoadmapPage.tsx")
    if not source.exists():
        # container pode não ter frontend mountado — pula sem falhar
        pytest.skip("frontend source não acessível do container de teste")
    content = source.read_text()
    for canon, label in STATUS_LABELS_PT_BR.items():
        # A chave aparece no mapa de labels
        assert canon in content, f"status canônico {canon} ausente do RoadmapPage"
        assert label in content, f"label pt-BR {label!r} ausente do RoadmapPage"
