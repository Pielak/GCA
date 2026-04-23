"""MVP 25 Fase 25.1 — Extração determinística de design tokens a partir de CSS.

Zero LLM no caminho crítico. Zero deps novas (só stdlib). Paleta derivada
por **frequência de uso** no CSS; escalas tipográfica / spacing / radii
ordenadas como sets únicos. Custom properties (`--primary: #xxx`) mapeiam
role → cor quando GP usou convenção canônica.

Shape canônico do output — ver `DesignTokens` dataclass. Estável, não
muda silenciosamente (consumido por OCG schema na Fase 25.2 + codegen
prompt builder na Fase 25.4).

Regras duras:
  - Entrada inválida ou vazia → retorna `DesignTokens()` (tudo vazio). Nunca
    levanta. A detecção de "sem design tokens" fica com o caller.
  - Comentários `/* ... */` são removidos antes da análise — evitam
    contar cores de exemplos/snippets documentados.
  - Strings entre aspas não são limpas — pode gerar falso positivo em
    `content: "text #123456"`, mas na prática é raríssimo e custa
    menos do que parser completo.
  - Cor só entra se for **sintaticamente válida** (hex 3/4/6/8, rgb(),
    rgba(), hsl(), hsla(), nomes CSS canônicos). Valores como `inherit`,
    `currentColor`, `transparent` são ignorados (não são tokens).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional


# ─── Shape canônico ──────────────────────────────────────────────────


@dataclass(frozen=True)
class DesignTokens:
    """View canônica de design tokens extraídos de CSS."""
    palette_top: tuple[str, ...] = ()       # cores mais frequentes (hex normalizado)
    palette_by_role: dict[str, str] = field(default_factory=dict)
    colors_unique_count: int = 0

    font_families: tuple[str, ...] = ()     # ordem de aparição
    font_sizes_px: tuple[int, ...] = ()     # ordenado asc
    font_weights: tuple[int, ...] = ()
    line_heights: tuple[float, ...] = ()

    spacing_px: tuple[int, ...] = ()        # ordenado asc
    radii_px: tuple[int, ...] = ()
    shadows: tuple[str, ...] = ()           # lista top N por frequência

    @property
    def is_empty(self) -> bool:
        return (
            not self.palette_top
            and not self.font_families
            and not self.font_sizes_px
            and not self.spacing_px
            and not self.radii_px
            and not self.shadows
        )

    def to_dict(self) -> dict:
        return {
            "palette": {
                "top": list(self.palette_top),
                "by_role": dict(self.palette_by_role),
                "unique_count": self.colors_unique_count,
            },
            "typography": {
                "families": list(self.font_families),
                "sizes_px": list(self.font_sizes_px),
                "weights": list(self.font_weights),
                "line_heights": list(self.line_heights),
            },
            "spacing_px": list(self.spacing_px),
            "radii_px": list(self.radii_px),
            "shadows": list(self.shadows),
        }


# ─── Defaults canônicos ──────────────────────────────────────────────

#: Quantas cores entram em `palette_top`.
TOP_COLORS = 12

#: Quantas sombras entram em `shadows`.
TOP_SHADOWS = 6

#: Conversão rem→px usada quando CSS declara sem unidade ou em rem.
REM_TO_PX = 16

#: Nomes canônicos de role que o frontend costuma usar em custom properties.
#: Se o GP declarar `--primary: #xxx`, mapeamos pra `by_role["primary"]`.
ROLE_NAMES = (
    "primary", "secondary", "accent", "success", "warning", "danger", "error",
    "info", "muted", "background", "foreground", "text", "surface", "border",
    "link", "brand",
)

#: Nomes CSS canônicos básicos (não cobre os 140+; só os usados em tokens reais).
_CSS_NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
    "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
    "maroon": "#800000", "navy": "#000080", "teal": "#008080",
    "orange": "#ffa500", "purple": "#800080", "pink": "#ffc0cb",
    "brown": "#a52a2a", "cyan": "#00ffff", "magenta": "#ff00ff",
}

#: Palavras-chave que NÃO são cor (evita contar em `color: inherit`).
_COLOR_KEYWORDS_IGNORED = {"inherit", "initial", "unset", "currentcolor", "transparent", "none", "auto"}


# ─── Regex canônicos ─────────────────────────────────────────────────

_RE_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_RE_HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
_RE_RGB = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*[,\s]\s*(\d{1,3})\s*[,\s]\s*(\d{1,3})"
    r"(?:\s*[,/]\s*([\d.]+%?))?\s*\)",
    re.IGNORECASE,
)
_RE_HSL = re.compile(
    r"hsla?\(\s*(-?[\d.]+)(?:deg|rad|turn)?\s*[,\s]\s*([\d.]+)%?\s*[,\s]\s*([\d.]+)%?"
    r"(?:\s*[,/]\s*([\d.]+%?))?\s*\)",
    re.IGNORECASE,
)
_RE_CSS_VAR_DECL = re.compile(r"--([a-zA-Z0-9_-]+)\s*:\s*([^;]+);")

_RE_FONT_FAMILY = re.compile(
    r"font-family\s*:\s*([^;}]+)", re.IGNORECASE,
)
_RE_FONT_SIZE = re.compile(
    r"font-size\s*:\s*([\d.]+)(px|rem|em)", re.IGNORECASE,
)
_RE_FONT_WEIGHT = re.compile(
    r"font-weight\s*:\s*(\d{3}|bold|normal|bolder|lighter)",
    re.IGNORECASE,
)
_RE_LINE_HEIGHT = re.compile(
    r"line-height\s*:\s*([\d.]+)(?:px|rem|em)?", re.IGNORECASE,
)

#: Padding/margin/gap/inset — qualquer "length" válida no shorthand.
_RE_SPACING_CONTEXT = re.compile(
    r"(padding|margin|gap|row-gap|column-gap|inset)\s*(?:-[a-z]+)?\s*:\s*([^;}]+)",
    re.IGNORECASE,
)
_RE_RADIUS_CONTEXT = re.compile(
    r"border-radius\s*:\s*([^;}]+)", re.IGNORECASE,
)
_RE_LENGTH = re.compile(r"(-?\d*\.?\d+)(px|rem|em)", re.IGNORECASE)

_RE_BOX_SHADOW = re.compile(
    r"box-shadow\s*:\s*([^;}]+)", re.IGNORECASE,
)

_FONT_WEIGHT_NAMED = {"normal": 400, "bold": 700, "bolder": 800, "lighter": 300}


# ─── Entry point ─────────────────────────────────────────────────────


def extract_tokens(css: str) -> DesignTokens:
    """Entry point canônico — parseia CSS e retorna DesignTokens.

    Tolerante: entrada `None`, vazia, inválida → retorna tokens vazios.
    """
    if not isinstance(css, str) or not css.strip():
        return DesignTokens()

    clean = _RE_COMMENT.sub("", css)

    # Paleta
    all_colors = list(_iter_colors(clean))
    normalized = [_normalize_color(c) for c in all_colors]
    normalized = [c for c in normalized if c]
    colors_counter = Counter(normalized)
    palette_top = tuple(c for c, _ in colors_counter.most_common(TOP_COLORS))
    palette_by_role = _extract_role_map(clean)
    colors_unique_count = len(colors_counter)

    # Tipografia
    font_families = _extract_font_families(clean)
    font_sizes_px = _extract_font_sizes(clean)
    font_weights = _extract_font_weights(clean)
    line_heights = _extract_line_heights(clean)

    # Spacing & radii
    spacing_px = _extract_spacing(clean)
    radii_px = _extract_radii(clean)

    # Shadows
    shadows = _extract_shadows(clean)

    return DesignTokens(
        palette_top=palette_top,
        palette_by_role=palette_by_role,
        colors_unique_count=colors_unique_count,
        font_families=font_families,
        font_sizes_px=font_sizes_px,
        font_weights=font_weights,
        line_heights=line_heights,
        spacing_px=spacing_px,
        radii_px=radii_px,
        shadows=shadows,
    )


# ─── Colors ──────────────────────────────────────────────────────────


def _iter_colors(css: str) -> Iterable[str]:
    yield from _RE_HEX.findall(css)
    for m in _RE_RGB.finditer(css):
        yield f"rgb({m.group(1)},{m.group(2)},{m.group(3)})"
    for m in _RE_HSL.finditer(css):
        yield f"hsl({m.group(1)},{m.group(2)},{m.group(3)})"
    # nomes canônicos — precisa de word boundary pra não casar com `grey50`
    lower = css.lower()
    for name, hexv in _CSS_NAMED_COLORS.items():
        for _ in re.finditer(rf"\b{name}\b", lower):
            yield hexv


def _normalize_color(raw: str) -> Optional[str]:
    """Converte para hex #rrggbb minúsculo. None se não for válido."""
    s = raw.strip().lower()
    if s in _COLOR_KEYWORDS_IGNORED:
        return None
    if s.startswith("#"):
        h = s.lstrip("#")
        if len(h) == 3:
            return "#" + "".join(c * 2 for c in h)
        if len(h) == 4:
            return "#" + "".join(c * 2 for c in h[:3])  # drop alpha
        if len(h) == 6:
            return "#" + h
        if len(h) == 8:
            return "#" + h[:6]
        return None
    if s.startswith("rgb"):
        m = _RE_RGB.match(s)
        if not m:
            return None
        r, g, b = (int(x) for x in m.group(1, 2, 3))
        if not all(0 <= v <= 255 for v in (r, g, b)):
            return None
        return "#{:02x}{:02x}{:02x}".format(r, g, b)
    if s.startswith("hsl"):
        m = _RE_HSL.match(s)
        if not m:
            return None
        h_deg = float(m.group(1)) % 360
        s_pct = max(0.0, min(100.0, float(m.group(2)))) / 100
        l_pct = max(0.0, min(100.0, float(m.group(3)))) / 100
        r, g, b = _hsl_to_rgb(h_deg, s_pct, l_pct)
        return "#{:02x}{:02x}{:02x}".format(r, g, b)
    return None


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if 0 <= h < 60:
        r1, g1, b1 = c, x, 0.0
    elif 60 <= h < 120:
        r1, g1, b1 = x, c, 0.0
    elif 120 <= h < 180:
        r1, g1, b1 = 0.0, c, x
    elif 180 <= h < 240:
        r1, g1, b1 = 0.0, x, c
    elif 240 <= h < 300:
        r1, g1, b1 = x, 0.0, c
    else:
        r1, g1, b1 = c, 0.0, x
    return (
        round((r1 + m) * 255),
        round((g1 + m) * 255),
        round((b1 + m) * 255),
    )


def _extract_role_map(css: str) -> dict[str, str]:
    """Varre `--role: <cor>;` e mapeia role canônica → cor normalizada."""
    out: dict[str, str] = {}
    for m in _RE_CSS_VAR_DECL.finditer(css):
        name_raw = m.group(1).lower()
        value = m.group(2).strip()
        # Match por contenção: --color-primary, --primary-500, --primary-color
        role = next((r for r in ROLE_NAMES if r in name_raw), None)
        if not role:
            continue
        # Extrai primeira cor da value
        colors = list(_iter_colors(value))
        if not colors:
            continue
        norm = _normalize_color(colors[0])
        if not norm:
            continue
        # Primeiro vence (não sobrescreve) — preserva declaração mais "principal"
        out.setdefault(role, norm)
    return out


# ─── Typography ──────────────────────────────────────────────────────


def _extract_font_families(css: str) -> tuple[str, ...]:
    """Primeira família de cada `font-family:` — preserva ordem de aparição."""
    seen: list[str] = []
    for m in _RE_FONT_FAMILY.finditer(css):
        value = m.group(1).strip().rstrip(";").rstrip("}")
        # Primeira família (antes do primeiro `,`)
        first = value.split(",")[0].strip().strip("'\"").strip()
        if not first:
            continue
        # Ignora fallbacks genéricos comuns como única família
        if first.lower() in {"inherit", "initial", "unset"}:
            continue
        if first not in seen:
            seen.append(first)
    return tuple(seen)


def _extract_font_sizes(css: str) -> tuple[int, ...]:
    sizes: set[int] = set()
    for m in _RE_FONT_SIZE.finditer(css):
        px = _length_to_px(float(m.group(1)), m.group(2))
        if px is not None and px > 0:
            sizes.add(px)
    return tuple(sorted(sizes))


def _extract_font_weights(css: str) -> tuple[int, ...]:
    weights: set[int] = set()
    for m in _RE_FONT_WEIGHT.finditer(css):
        v = m.group(1).lower()
        if v.isdigit():
            w = int(v)
            if 100 <= w <= 1000 and w % 100 == 0:
                weights.add(w)
        elif v in _FONT_WEIGHT_NAMED:
            weights.add(_FONT_WEIGHT_NAMED[v])
    return tuple(sorted(weights))


def _extract_line_heights(css: str) -> tuple[float, ...]:
    heights: set[float] = set()
    for m in _RE_LINE_HEIGHT.finditer(css):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if 0.5 <= v <= 4.0:  # range plausível de line-height sem unidade
            heights.add(round(v, 2))
    return tuple(sorted(heights))


# ─── Spacing / Radii ──────────────────────────────────────────────────


def _extract_spacing(css: str) -> tuple[int, ...]:
    pxs: set[int] = set()
    for m in _RE_SPACING_CONTEXT.finditer(css):
        value = m.group(2)
        for lm in _RE_LENGTH.finditer(value):
            px = _length_to_px(float(lm.group(1)), lm.group(2))
            if px is not None and 0 < px <= 256:
                pxs.add(px)
    return tuple(sorted(pxs))


def _extract_radii(css: str) -> tuple[int, ...]:
    pxs: set[int] = set()
    for m in _RE_RADIUS_CONTEXT.finditer(css):
        value = m.group(1)
        for lm in _RE_LENGTH.finditer(value):
            px = _length_to_px(float(lm.group(1)), lm.group(2))
            if px is not None and 0 <= px <= 9999:
                pxs.add(px)
    return tuple(sorted(pxs))


def _length_to_px(value: float, unit: str) -> Optional[int]:
    unit = unit.lower()
    if unit == "px":
        return int(round(value))
    if unit in ("rem", "em"):
        return int(round(value * REM_TO_PX))
    return None


# ─── Shadows ──────────────────────────────────────────────────────────


def _extract_shadows(css: str) -> tuple[str, ...]:
    counter: Counter[str] = Counter()
    for m in _RE_BOX_SHADOW.finditer(css):
        raw = m.group(1).strip().rstrip(";").rstrip("}")
        if not raw or raw.lower() in _COLOR_KEYWORDS_IGNORED:
            continue
        # Normaliza espaços extras sem mexer no conteúdo canônico
        norm = re.sub(r"\s+", " ", raw)
        counter[norm] += 1
    return tuple(s for s, _ in counter.most_common(TOP_SHADOWS))
