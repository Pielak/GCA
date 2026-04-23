"""MVP 25 Fase 25.2 — Testes dos helpers canônicos de `design_tokens`.

Cobre:
  - from_ocg_dict tolerante com input inválido/parcial.
  - Normalização de hex (3/6/8 chars → #rrggbb).
  - Role filter: só roles canônicos entram em by_role.
  - from_extractor_output consome DesignTokens do extractor.
  - Source lifecycle: css_ingested → mixed quando há previous com roles.
  - validate_tokens_dict rejeita hex/role/weight/line_height inválidos.
  - tokens_as_prompt_block gera bloco canônico não-vazio; vazio retorna "".
"""
from __future__ import annotations

from app.services.css_token_extractor_service import extract_tokens
from app.services.design_tokens import (
    CANONICAL_ROLES,
    DesignTokensView,
    Palette,
    Typography,
    ValidationError,
    from_extractor_output,
    from_ocg_dict,
    tokens_as_prompt_block,
    validate_tokens_dict,
)


# ─── from_ocg_dict (parser tolerante) ─────────────────────────────────


def test_from_ocg_dict_none_retorna_view_vazia():
    assert from_ocg_dict(None).is_empty
    assert from_ocg_dict("not dict").is_empty  # type: ignore[arg-type]
    assert from_ocg_dict({}).is_empty


def test_from_ocg_dict_parse_paleta_basica():
    view = from_ocg_dict({
        "palette": {
            "top": ["#7c3aed", "#FFF", "#0EA5E9"],
            "by_role": {"primary": "#7c3aed", "secondary": "#0ea5e9"},
            "unique_count": 3,
        }
    })
    assert "#7c3aed" in view.palette.top
    assert "#ffffff" in view.palette.top  # #FFF expandido
    assert "#0ea5e9" in view.palette.top
    assert view.palette.by_role["primary"] == "#7c3aed"
    assert view.palette.unique_count == 3


def test_from_ocg_dict_ignora_hex_invalido():
    view = from_ocg_dict({"palette": {"top": ["#7c3aed", "not-a-color", "#xyz"]}})
    assert view.palette.top == ("#7c3aed",)


def test_from_ocg_dict_role_fora_canonico_e_filtrado():
    view = from_ocg_dict({"palette": {"by_role": {
        "primary": "#7c3aed",
        "some_random_role": "#000000",
    }}})
    assert "primary" in view.palette.by_role
    assert "some_random_role" not in view.palette.by_role


def test_from_ocg_dict_role_case_insensitive():
    view = from_ocg_dict({"palette": {"by_role": {"Primary": "#7c3aed"}}})
    assert view.palette.by_role["primary"] == "#7c3aed"


def test_from_ocg_dict_tipografia_filtra_invalidos():
    view = from_ocg_dict({"typography": {
        "sizes_px": [16, 0, -5, "bad", 32],        # só 16 e 32 válidos
        "weights": [400, 450, 1200, 700],          # só 400 e 700 válidos
        "line_heights": [1.5, 0.1, 5.0, 1.75],     # só 1.5 e 1.75 válidos
    }})
    assert view.typography.sizes_px == (16, 32)
    assert view.typography.weights == (400, 700)
    assert view.typography.line_heights == (1.5, 1.75)


def test_from_ocg_dict_spacing_e_radii_ordenados_com_limites():
    view = from_ocg_dict({
        "spacing_px": [16, 8, 4, -1, 0, 300],   # 0 strict_gt; 300 > limite
        "radii_px": [4, 10000, 9999, 0],        # 10000 fora
    })
    assert view.spacing_px == (4, 8, 16)
    assert view.radii_px == (0, 4, 9999)


def test_from_ocg_dict_source_valido_e_invalido():
    view_ok = from_ocg_dict({"source": "css_ingested"})
    assert view_ok.source == "css_ingested"
    view_bad = from_ocg_dict({"source": "foo"})
    assert view_bad.source is None


# ─── from_extractor_output (Fase 25.1 → OCG) ─────────────────────────


def test_from_extractor_output_none_retorna_vazio():
    assert from_extractor_output(None) == {}


def test_from_extractor_output_marca_source_css_ingested():
    tokens = extract_tokens(""":root { --primary: #7c3aed; } .a { color: #fff; }""")
    out = from_extractor_output(tokens)
    assert out["source"] == "css_ingested"
    assert out["palette"]["by_role"].get("primary") == "#7c3aed"
    assert "#ffffff" in out["palette"]["top"]
    assert out["generated_at"]  # ISO-8601 preenchido


def test_from_extractor_output_preserva_manual_e_marca_mixed():
    tokens = extract_tokens(""":root { --primary: #111111; }""")
    previous = {
        "palette": {"by_role": {"accent": "#ff00ff"}},  # GP tinha customizado accent
        "source": "manual",
    }
    out = from_extractor_output(tokens, previous=previous)
    assert out["source"] == "mixed"
    # Preserva accent manual + adiciona primary extraído
    assert out["palette"]["by_role"]["accent"] == "#ff00ff"
    assert out["palette"]["by_role"]["primary"] == "#111111"


def test_from_extractor_output_sem_previous_e_css_ingested():
    """Sem previous, sempre css_ingested."""
    tokens = extract_tokens(".a { color: #000; }")
    out = from_extractor_output(tokens, previous=None)
    assert out["source"] == "css_ingested"


def test_from_extractor_output_gera_generated_at_iso():
    from datetime import datetime
    tokens = extract_tokens(".a { color: #000; }")
    out = from_extractor_output(tokens)
    # parseia ISO 8601 — não levanta
    datetime.fromisoformat(out["generated_at"])


# ─── Validator ───────────────────────────────────────────────────────


def test_validator_aceita_dict_vazio_e_none():
    assert validate_tokens_dict(None) == []
    assert validate_tokens_dict({}) == []


def test_validator_rejeita_chave_desconhecida():
    errors = validate_tokens_dict({"foo": {}})
    assert any(e.path == "$.foo" for e in errors)


def test_validator_hex_invalido_em_palette_top():
    errors = validate_tokens_dict({"palette": {"top": ["#abc", "not-hex"]}})
    # #abc é válido (hex 3); not-hex é inválido
    assert any("top[1]" in e.path for e in errors)
    assert not any("top[0]" in e.path for e in errors)


def test_validator_role_fora_canonico():
    errors = validate_tokens_dict({"palette": {"by_role": {"foo": "#123456"}}})
    assert any("by_role.foo" in e.path for e in errors)


def test_validator_weight_fora_escala():
    errors = validate_tokens_dict({"typography": {"weights": [450, 700]}})
    assert any("weights[0]" in e.path for e in errors)
    assert not any("weights[1]" in e.path for e in errors)


def test_validator_line_height_fora_range():
    errors = validate_tokens_dict({"typography": {"line_heights": [0.1, 1.5]}})
    assert any("line_heights[0]" in e.path for e in errors)
    assert not any("line_heights[1]" in e.path for e in errors)


def test_validator_spacing_zero_nao_aceito_strict_gt():
    errors = validate_tokens_dict({"spacing_px": [0, 8]})
    assert any("spacing_px[0]" in e.path for e in errors)
    assert not any("spacing_px[1]" in e.path for e in errors)


def test_validator_radii_aceita_zero():
    """Radii aceita 0 (sem arredondamento)."""
    errors = validate_tokens_dict({"radii_px": [0, 8, 9999]})
    assert errors == []


def test_validator_source_invalido():
    errors = validate_tokens_dict({"source": "wrong"})
    assert any(e.path == "$.source" for e in errors)


def test_validator_aceita_payload_canonico_completo():
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
            "line_heights": [1.5],
        },
        "spacing_px": [4, 8, 16],
        "radii_px": [0, 8],
        "shadows": ["0 1px 2px rgba(0,0,0,0.05)"],
        "source": "manual",
    }
    assert validate_tokens_dict(payload) == []


# ─── Prompt block ────────────────────────────────────────────────────


def test_prompt_block_empty_retorna_string_vazia():
    assert tokens_as_prompt_block(DesignTokensView()) == ""


def test_prompt_block_inclui_roles_e_escala():
    view = DesignTokensView(
        palette=Palette(
            top=("#7c3aed", "#ffffff"),
            by_role={"primary": "#7c3aed", "secondary": "#0ea5e9"},
        ),
        typography=Typography(families=("Inter",), sizes_px=(16, 24), weights=(400, 700)),
        spacing_px=(4, 8, 16),
        radii_px=(8,),
        shadows=("0 1px 2px rgba(0,0,0,0.05)",),
    )
    block = tokens_as_prompt_block(view)
    assert "Design System" in block
    assert "primary" in block
    assert "#7c3aed" in block
    assert "Inter" in block
    assert "16" in block
    assert "400" in block and "700" in block
    assert "não inventar paleta" in block.lower() or "reutilizar estes tokens" in block.lower()


def test_canonical_roles_imutavel_frozenset():
    assert isinstance(CANONICAL_ROLES, frozenset)
    assert "primary" in CANONICAL_ROLES
    assert "secondary" in CANONICAL_ROLES
    assert "random_role" not in CANONICAL_ROLES


# ─── Integração end-to-end 25.1 → 25.2 ───────────────────────────────


def test_pipeline_completo_css_para_view_canonica():
    css = """
    :root {
      --primary: #7c3aed;
      --secondary: #0ea5e9;
    }
    body { font-family: 'Inter'; font-size: 16px; }
    .card { padding: 16px; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    """
    tokens = extract_tokens(css)
    ocg_payload = from_extractor_output(tokens)
    view = from_ocg_dict(ocg_payload)

    assert not view.is_empty
    assert view.palette.by_role["primary"] == "#7c3aed"
    assert "Inter" in view.typography.families
    assert 16 in view.typography.sizes_px
    assert 16 in view.spacing_px
    assert 8 in view.radii_px
    assert view.source == "css_ingested"
