"""MVP 25 Fase 25.1 — Testes do `css_token_extractor_service`.

Cobre:
  - Entrada inválida/vazia → DesignTokens vazio.
  - Paleta derivada por frequência (top N).
  - hex 3/6/8, rgb(), rgba(), hsl(), nomes canônicos.
  - Role map via custom properties `--primary`, `--color-primary-500`, etc.
  - Ignora inherit/currentColor/transparent.
  - Tipografia: familias únicas em ordem, sizes ordenados, weights normalizados.
  - Spacing: px+rem+em convertidos; ordenados, sem duplicatas.
  - Radii: 0 a 9999, ordenados.
  - Shadows: top N por frequência.
  - Comentários CSS são removidos antes da análise.
"""
from __future__ import annotations

from app.services.css_token_extractor_service import (
    DesignTokens, REM_TO_PX, TOP_COLORS, extract_tokens,
)


def test_entrada_vazia_retorna_tokens_vazios():
    assert extract_tokens("").is_empty
    assert extract_tokens(None).is_empty  # type: ignore[arg-type]
    assert extract_tokens("   \n  ").is_empty


def test_hex_6_caracteres():
    css = """
    .a { color: #7C3AED; }
    .b { color: #7c3aed; }
    .c { background: #ffffff; }
    """
    t = extract_tokens(css)
    assert "#7c3aed" in t.palette_top
    assert "#ffffff" in t.palette_top
    # Case-insensitive normalização: #7C3AED e #7c3aed contam como 1 só
    assert t.colors_unique_count == 2


def test_hex_3_caracteres_expande():
    t = extract_tokens(".x { color: #f00; }")
    assert t.palette_top == ("#ff0000",)


def test_hex_8_caracteres_drop_alpha():
    t = extract_tokens(".x { color: #7c3aed80; }")
    assert t.palette_top == ("#7c3aed",)


def test_rgb_e_rgba():
    css = """
    .a { color: rgb(124, 58, 237); }
    .b { background: rgba(255, 255, 255, 0.5); }
    """
    t = extract_tokens(css)
    assert "#7c3aed" in t.palette_top
    assert "#ffffff" in t.palette_top


def test_hsl_convertido_pra_hex():
    # hsl(0, 100%, 50%) = #ff0000
    t = extract_tokens(".x { color: hsl(0, 100%, 50%); }")
    assert "#ff0000" in t.palette_top


def test_nomes_canonicos():
    t = extract_tokens(".x { color: black; border: 1px solid white; }")
    assert "#000000" in t.palette_top
    assert "#ffffff" in t.palette_top


def test_keywords_ignoradas():
    """inherit, currentColor, transparent, none não entram na paleta."""
    css = """
    .a { color: inherit; }
    .b { background: transparent; }
    .c { border-color: currentColor; }
    """
    t = extract_tokens(css)
    assert t.palette_top == ()
    assert t.colors_unique_count == 0


def test_paleta_ordenada_por_frequencia():
    # #aabbcc aparece 3x, #112233 aparece 1x
    css = ".a{color:#aabbcc;}.b{color:#aabbcc;}.c{color:#aabbcc;}.d{color:#112233;}"
    t = extract_tokens(css)
    assert t.palette_top[0] == "#aabbcc"
    assert t.palette_top[1] == "#112233"


def test_role_map_via_custom_property():
    css = """
    :root {
      --primary: #7c3aed;
      --color-secondary: rgb(14, 165, 233);
      --accent-500: hsl(0, 100%, 50%);
    }
    """
    t = extract_tokens(css)
    assert t.palette_by_role["primary"] == "#7c3aed"
    assert t.palette_by_role["secondary"] == "#0ea5e9"
    assert t.palette_by_role["accent"] == "#ff0000"


def test_role_map_primeira_declaracao_vence():
    css = """
    :root { --primary: #000000; }
    .override { --primary: #ffffff; }
    """
    t = extract_tokens(css)
    assert t.palette_by_role["primary"] == "#000000"


def test_font_families_ordem_aparicao_unica():
    css = """
    body { font-family: 'Inter', sans-serif; }
    h1   { font-family: 'Outfit', 'Inter'; }
    code { font-family: 'JetBrains Mono', monospace; }
    p    { font-family: 'Inter'; }  /* duplicada, ignora */
    """
    t = extract_tokens(css)
    assert t.font_families == ("Inter", "Outfit", "JetBrains Mono")


def test_font_sizes_px_e_rem():
    css = """
    h1 { font-size: 2rem; }
    h2 { font-size: 24px; }
    p  { font-size: 1rem; }
    """
    t = extract_tokens(css)
    # 1rem=16, 2rem=32, 24px=24
    assert t.font_sizes_px == (16, 24, 32)


def test_font_weights_numericos_e_nomeados():
    css = """
    .a { font-weight: 400; }
    .b { font-weight: bold; }
    .c { font-weight: 700; }   /* duplicada de bold */
    .d { font-weight: normal; } /* duplicada de 400 */
    """
    t = extract_tokens(css)
    assert t.font_weights == (400, 700)


def test_line_heights():
    css = """
    .a { line-height: 1.5; }
    .b { line-height: 1.2; }
    .c { line-height: 1.75; }
    """
    t = extract_tokens(css)
    assert t.line_heights == (1.2, 1.5, 1.75)


def test_spacing_px_e_rem_conversao():
    css = """
    .a { padding: 8px 16px; }
    .b { margin: 1rem; }
    .c { gap: 0.5rem; }
    .d { padding-left: 4px; }
    """
    t = extract_tokens(css)
    # 4, 8, 16, 16 (1rem), 8 (0.5rem) → únicos: 4, 8, 16
    assert t.spacing_px == (4, 8, 16)


def test_radii_escala():
    css = """
    .a { border-radius: 4px; }
    .b { border-radius: 8px 16px; }
    .c { border-radius: 9999px; }
    """
    t = extract_tokens(css)
    assert t.radii_px == (4, 8, 16, 9999)


def test_shadows_top_por_frequencia():
    css = """
    .a { box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .b { box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .c { box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
    """
    t = extract_tokens(css)
    # Primeiro é o mais frequente
    assert t.shadows[0].startswith("0 1px 2px")
    assert len(t.shadows) == 2


def test_comentarios_sao_removidos():
    """Cores dentro de /* ... */ não contam — evita exemplos documentais."""
    css = """
    /* Esta cor #deadbe está em comentário */
    .a { color: #abcdef; }
    """
    t = extract_tokens(css)
    assert "#abcdef" in t.palette_top
    assert "#deadbe" not in t.palette_top


def test_palette_top_limita_em_12():
    # 15 cores distintas
    css = "\n".join(f".c{i} {{ color: #{i:02x}{i:02x}{i:02x}; }}" for i in range(15))
    t = extract_tokens(css)
    assert len(t.palette_top) == TOP_COLORS
    assert t.colors_unique_count == 15


def test_to_dict_shape_canonico():
    t = extract_tokens(".a { color: #7c3aed; font-size: 16px; padding: 8px; }")
    d = t.to_dict()
    assert set(d.keys()) == {"palette", "typography", "spacing_px", "radii_px", "shadows"}
    assert set(d["palette"].keys()) == {"top", "by_role", "unique_count"}
    assert set(d["typography"].keys()) == {"families", "sizes_px", "weights", "line_heights"}


def test_rem_to_px_constant():
    """Contrato canônico — conversão rem→px é 16."""
    assert REM_TO_PX == 16


def test_input_malformado_nao_explode():
    """Entrada quebrada → retorna o que conseguir, sem levantar."""
    css = "this is { not css ; at all :::: } #abc color font-size"
    t = extract_tokens(css)
    # Cor #abc (3 chars) ainda é detectada via regex tolerante
    assert isinstance(t, DesignTokens)


def test_fluxo_realista_end_to_end():
    """CSS mini-mas-realista → tokens canônicos esperados."""
    css = """
    :root {
      --primary: #7c3aed;
      --secondary: #0ea5e9;
      --bg: #0f0f1e;
    }
    body {
      font-family: 'Inter', 'system-ui', sans-serif;
      font-size: 16px;
      line-height: 1.5;
      color: #e2e8f0;
      background: var(--bg);
    }
    h1 { font-family: 'Outfit'; font-size: 32px; font-weight: 700; }
    .card {
      padding: 16px;
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .btn-primary {
      background: #7c3aed;
      padding: 8px 12px;
      font-weight: 600;
    }
    """
    t = extract_tokens(css)
    # Paleta
    assert "#7c3aed" in t.palette_top
    assert "#0ea5e9" in t.palette_top
    assert "#0f0f1e" in t.palette_top
    # Roles
    assert t.palette_by_role.get("primary") == "#7c3aed"
    assert t.palette_by_role.get("secondary") == "#0ea5e9"
    # Tipografia
    assert "Inter" in t.font_families
    assert "Outfit" in t.font_families
    assert 16 in t.font_sizes_px
    assert 32 in t.font_sizes_px
    assert 600 in t.font_weights
    assert 700 in t.font_weights
    # Spacing
    assert 8 in t.spacing_px
    assert 12 in t.spacing_px
    assert 16 in t.spacing_px
    # Radii
    assert 8 in t.radii_px
    # Shadow
    assert len(t.shadows) == 1
    assert "1px 2px" in t.shadows[0]
