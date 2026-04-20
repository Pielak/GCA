"""DT-076 Fase 5 — Template architecture do LiveDoc inclui DATA_MODEL.

Cobre:
  - _render_data_model retorna texto informativo quando dm presente
  - Engine + count aparecem no render
  - Warnings aparecem quando presentes
  - Tabelas listadas com contagem de colunas
  - Ausência de DATA_MODEL não quebra (retorna string informativa)
  - Build completo do prompt inclui seção 'Modelo de dados'
  - Template inclui a placeholder {data_model_block}
"""
from __future__ import annotations

from app.services.data_model_inference import infer_data_model
from app.services.live_doc_generator_service import (
    ARCHITECTURE_DOC_TEMPLATE, _build_architecture_prompt, _render_data_model,
)


def test_template_cita_data_model_block():
    assert "{data_model_block}" in ARCHITECTURE_DOC_TEMPLATE
    assert "Modelo de dados" in ARCHITECTURE_DOC_TEMPLATE


def test_render_data_model_vazio_retorna_msg_informativa():
    r = _render_data_model({})
    assert r  # não vazio
    assert "DATA_MODEL" in r or "não foi inferido" in r


def test_render_data_model_none_retorna_msg_informativa():
    assert _render_data_model(None)


def test_render_data_model_cita_engine_e_contagem():
    dm = infer_data_model(
        {"initiative_type": "E-commerce", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )
    r = _render_data_model(dm)
    assert "PostgreSQL" in r
    assert "Tabelas:" in r
    # E-commerce gera ≥ 9 tabelas
    n = len(dm["tables"])
    assert f"Tabelas: {n}" in r


def test_render_data_model_lista_tabelas_nomes():
    dm = infer_data_model(
        {"initiative_type": "E-commerce"},
        {"database": {"engine": "PostgreSQL"}},
    )
    r = _render_data_model(dm)
    assert "users" in r
    assert "orders" in r or "products" in r


def test_render_data_model_warnings_aparecem():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "Oracle 19c"}},
    )
    r = _render_data_model(dm)
    assert "Warnings" in r
    assert "Oracle" in r


def test_render_data_model_diz_quando_nao_suportado():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "Oracle 19c"}},
    )
    r = _render_data_model(dm)
    assert "automático: não" in r


def test_render_data_model_diz_quando_suportado():
    dm = infer_data_model(
        {"initiative_type": "generic"},
        {"database": {"engine": "PostgreSQL"}},
    )
    r = _render_data_model(dm)
    assert "automático: sim" in r


def test_render_data_model_inclui_relacoes_quando_ha_fks():
    dm = infer_data_model(
        {"initiative_type": "E-commerce"},
        {"database": {"engine": "PostgreSQL"}},
    )
    r = _render_data_model(dm)
    # E-commerce tem fks orders→customers, order_items→orders, etc
    assert "Relações" in r or "FKs" in r


def test_build_architecture_prompt_inclui_data_model():
    """Prompt completo inclui seção 'Modelo de dados' com conteúdo real."""
    dm = infer_data_model(
        {"initiative_type": "E-commerce", "handles_pii": True},
        {"database": {"engine": "PostgreSQL"}},
    )
    ocg_ctx = {
        "version": 7,
        "data": {
            "STACK_RECOMMENDATION": {
                "backend": {"enabled": True, "framework": ["FastAPI"]},
                "database": {"engine": "PostgreSQL"},
            },
            "ARCHITECTURE_OVERVIEW": {"execution_model": ["Containerizado"]},
            "PILLAR_SCORES": {"P1": {"score": 80, "status": "ok"}},
            "DATA_MODEL": dm,
        },
    }
    prompt = _build_architecture_prompt(
        ocg_ctx=ocg_ctx,
        modules=[{"id": "1", "name": "API", "module_type": "backend_service", "priority": "high", "readiness_status": None}],
    )
    assert "DATA_MODEL" in prompt
    assert "PostgreSQL" in prompt
    assert "users" in prompt
    # Instruções específicas do template pra LLM
    assert "Modelo de dados" in prompt
    assert "Relações importantes" in prompt or "FKs críticas" in prompt


def test_build_architecture_prompt_sem_data_model_nao_quebra():
    """OCG legado sem DATA_MODEL não quebra a construção do prompt."""
    ocg_ctx = {
        "version": 1,
        "data": {
            "STACK_RECOMMENDATION": {},
            "ARCHITECTURE_OVERVIEW": {},
            "PILLAR_SCORES": {},
            # Sem DATA_MODEL
        },
    }
    prompt = _build_architecture_prompt(ocg_ctx=ocg_ctx, modules=[])
    assert prompt
    assert "Modelo de dados" in prompt  # seção ainda presente
