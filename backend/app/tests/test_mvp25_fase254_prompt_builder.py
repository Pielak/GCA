"""MVP 25 Fase 25.4 — Testes de integração do prompt builder com design tokens.

Cobre:
  - _detect_frontend_stack_key identifica tailwind/styled-components/emotion/mui/vanilla-extract/css-modules/plain_css/generic.
  - _design_tokens_full_block retorna "" quando tokens ausentes.
  - _design_tokens_full_block monta bloco principal + hints por stack.
  - build_scaffold_prompt injeta bloco quando design_tokens presente.
  - build_scaffold_prompt omite bloco quando design_tokens None.
  - build_regenerate_file_prompt idem.
  - Hints Tailwind vs plain_css são diferentes e semânticos.
"""
from __future__ import annotations

from app.services.codegen_prompt_builder import (
    _design_tokens_full_block,
    _detect_frontend_stack_key,
    build_regenerate_file_prompt,
    build_scaffold_prompt,
)


# ─── Detector de stack ────────────────────────────────────────────────


def test_detect_sem_stack_retorna_generic():
    assert _detect_frontend_stack_key(None) == "generic"
    assert _detect_frontend_stack_key({}) == "generic"


def test_detect_tailwind_via_framework():
    assert _detect_frontend_stack_key(
        {"frontend": {"framework": "Tailwind CSS"}}
    ) == "tailwind"


def test_detect_styled_components():
    assert _detect_frontend_stack_key(
        {"frontend": {"styling": "styled-components"}}
    ) == "styled_components"


def test_detect_emotion():
    assert _detect_frontend_stack_key(
        {"frontend": {"framework": "React", "styling": "Emotion"}}
    ) == "emotion"


def test_detect_mui():
    assert _detect_frontend_stack_key(
        {"frontend": {"framework": "MUI"}}
    ) == "mui"


def test_detect_vanilla_extract():
    assert _detect_frontend_stack_key(
        {"frontend": {"framework": "vanilla-extract"}}
    ) == "vanilla_extract"


def test_detect_css_modules():
    assert _detect_frontend_stack_key(
        {"frontend": {"styling": "CSS Modules"}}
    ) == "css_modules"


def test_detect_frontend_generico_vira_plain_css():
    """Frontend declarado mas sem lib de estilo → plain_css (usa CSS vars)."""
    assert _detect_frontend_stack_key(
        {"frontend": {"framework": "React"}}
    ) == "plain_css"


# ─── _design_tokens_full_block ────────────────────────────────────────


def test_full_block_vazio_quando_tokens_none():
    assert _design_tokens_full_block(None, None) == ""
    assert _design_tokens_full_block({}, None) == ""


def test_full_block_vazio_quando_payload_sem_conteudo():
    payload = {"palette": {"top": []}, "typography": {}, "source": "manual"}
    assert _design_tokens_full_block(payload, None) == ""


def test_full_block_inclui_bloco_principal_e_hints_tailwind():
    payload = {
        "palette": {
            "top": ["#7c3aed", "#ffffff"],
            "by_role": {"primary": "#7c3aed"},
            "unique_count": 2,
        },
        "typography": {
            "families": ["Inter"],
            "sizes_px": [16, 24],
            "weights": [400, 700],
        },
        "spacing_px": [4, 8, 16],
    }
    stack = {"frontend": {"framework": "Tailwind CSS"}}
    block = _design_tokens_full_block(payload, stack)
    # bloco principal (tokens_as_prompt_block)
    assert "Design System" in block
    assert "#7c3aed" in block
    assert "Inter" in block
    # hints de Tailwind
    assert "Tailwind" in block
    assert "tailwind.config.ts" in block.lower() or "theme.extend" in block


def test_full_block_hints_plain_css_diferentes():
    payload = {"palette": {"by_role": {"primary": "#abc"}}}
    block = _design_tokens_full_block(
        payload, {"frontend": {"framework": "React"}},
    )
    # Heading de hints deve identificar plain CSS, não Tailwind
    assert "Implementação de tokens (CSS puro)" in block
    assert "Implementação de tokens (Tailwind" not in block
    assert "tokens.css" in block


def test_full_block_hints_styled_components():
    payload = {
        "palette": {"by_role": {"primary": "#abc"}},
        "typography": {"families": ["Inter"]},
    }
    block = _design_tokens_full_block(
        payload, {"frontend": {"styling": "styled-components"}},
    )
    assert "styled-components" in block
    assert "ThemeProvider" in block


def test_full_block_hints_mui():
    payload = {"palette": {"by_role": {"primary": "#abc"}}}
    block = _design_tokens_full_block(
        payload, {"frontend": {"framework": "MUI"}},
    )
    assert "MUI" in block
    assert "createTheme" in block or "palette: {" in block


# ─── build_scaffold_prompt injeção ────────────────────────────────────


def _minimal_scaffold_call(**overrides):
    defaults = dict(
        project_name="T",
        project_slug="t",
        project_description=None,
        stack={"frontend": {"framework": "Tailwind"}},
        architecture=None,
        testing=None,
        modules=None,
        arguider_modules=None,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
    )
    defaults.update(overrides)
    return build_scaffold_prompt(**defaults)


def test_scaffold_sem_design_tokens_nao_inclui_bloco():
    prompt = _minimal_scaffold_call(design_tokens=None)
    assert "Design System" not in prompt
    assert "Implementação de tokens" not in prompt


def test_scaffold_com_design_tokens_inclui_bloco_completo():
    tokens = {
        "palette": {
            "top": ["#7c3aed"],
            "by_role": {"primary": "#7c3aed"},
        },
        "typography": {"families": ["Inter"], "sizes_px": [16]},
        "spacing_px": [4, 8, 16],
    }
    prompt = _minimal_scaffold_call(design_tokens=tokens)
    assert "Design System" in prompt
    assert "#7c3aed" in prompt
    assert "Inter" in prompt
    assert "Tailwind" in prompt


def test_scaffold_com_rnf_e_design_tokens_ambos_injetados():
    rnf = {"security": {"rate_limit_rpm_public": 60}}
    tokens = {"palette": {"by_role": {"primary": "#abc"}}}
    prompt = _minimal_scaffold_call(
        rnf_contracts=rnf,
        design_tokens=tokens,
        stack={"frontend": {"framework": "React"}},
    )
    # Ambos os blocos presentes
    assert "Requisitos Não-Funcionais" in prompt
    assert "Design System" in prompt


# ─── build_regenerate_file_prompt ─────────────────────────────────────


def _minimal_regen_call(**overrides):
    defaults = dict(
        project_name="T",
        project_description=None,
        stack={"frontend": {"styling": "styled-components"}},
        architecture=None,
        path="src/app/Button.tsx",
        instruction=None,
        current_content=None,
    )
    defaults.update(overrides)
    return build_regenerate_file_prompt(**defaults)


def test_regenerate_sem_tokens_omite_bloco():
    prompt = _minimal_regen_call(design_tokens=None)
    assert "Design System" not in prompt


def test_regenerate_com_tokens_injeta_bloco_e_hints_por_stack():
    tokens = {
        "palette": {"by_role": {"primary": "#7c3aed"}},
        "typography": {"families": ["Inter"]},
    }
    prompt = _minimal_regen_call(design_tokens=tokens)
    assert "Design System" in prompt
    assert "styled-components" in prompt
    assert "ThemeProvider" in prompt
