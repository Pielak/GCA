"""MVP 25 Fase 25.2 — Helpers canônicos pra `STACK_RECOMMENDATION.frontend.design_tokens`.

Paralelo de `rnf_contracts.py` (MVP 23 Fase 23.1). Separa 3 responsabilidades:

  1. **Parser tolerante** (`from_ocg_dict`) — nunca levanta; campos ausentes
     viram defaults, tipos errados são ignorados silenciosamente.
  2. **Validador determinístico** (`validate_tokens_dict`) — retorna
     `list[ValidationError]`. Lista vazia = dict aceito pelo endpoint PUT.
  3. **Conversor do extractor** (`from_extractor_output`) — transforma o
     `DesignTokens` da Fase 25.1 no dict canônico pronto pro OCG.

Shape canônico (documentado no OCG via `STACK_RECOMMENDATION.frontend.design_tokens`):

  {
    "palette": {
      "top": [str, ...],                    # hex #rrggbb minúsculo
      "by_role": {role: "#rrggbb"},         # role canônico → hex
      "unique_count": int
    },
    "typography": {
      "families": [str, ...],
      "sizes_px": [int, ...],               # ordenado asc
      "weights": [int, ...],                # múltiplos de 100, 100-900
      "line_heights": [float, ...]
    },
    "spacing_px": [int, ...],               # ordenado asc, 0 < v <= 256
    "radii_px": [int, ...],                 # 0 <= v <= 9999
    "shadows": [str, ...],                  # top N
    "source": "css_ingested" | "manual" | "mixed",
    "generated_at": ISO-8601 | null
  }

Campo `source` canoniza a origem:
  - `css_ingested`: extractor rodou sobre CSS/SCSS ingerido.
  - `manual`: GP preencheu direto pelo endpoint PUT.
  - `mixed`: extractor rodou + GP editou manualmente depois.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


SourceKind = Literal["css_ingested", "manual", "mixed"]


#: Roles canônicos aceitos em `palette.by_role` (espelha o ROLE_NAMES
#: do extractor; duplicado aqui pra manter esse módulo independente).
CANONICAL_ROLES = frozenset({
    "primary", "secondary", "accent", "success", "warning", "danger", "error",
    "info", "muted", "background", "foreground", "text", "surface", "border",
    "link", "brand",
})


# ─── Dataclasses read-only ───────────────────────────────────────────


@dataclass(frozen=True)
class Palette:
    top: tuple[str, ...] = ()
    by_role: dict[str, str] = field(default_factory=dict)
    unique_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.top and not self.by_role


@dataclass(frozen=True)
class Typography:
    families: tuple[str, ...] = ()
    sizes_px: tuple[int, ...] = ()
    weights: tuple[int, ...] = ()
    line_heights: tuple[float, ...] = ()

    @property
    def is_empty(self) -> bool:
        return (
            not self.families and not self.sizes_px
            and not self.weights and not self.line_heights
        )


@dataclass(frozen=True)
class DesignTokensView:
    """Snapshot imutável canônico dos design tokens do OCG."""
    palette: Palette = field(default_factory=Palette)
    typography: Typography = field(default_factory=Typography)
    spacing_px: tuple[int, ...] = ()
    radii_px: tuple[int, ...] = ()
    shadows: tuple[str, ...] = ()
    source: Optional[SourceKind] = None
    generated_at: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return (
            self.palette.is_empty
            and self.typography.is_empty
            and not self.spacing_px
            and not self.radii_px
            and not self.shadows
        )


# ─── Parsing (tolerante) ──────────────────────────────────────────────


def from_ocg_dict(raw: Any) -> DesignTokensView:
    """Converte dict do OCG em view canônica. Nunca levanta."""
    if not isinstance(raw, dict):
        return DesignTokensView()

    palette_raw = raw.get("palette") if isinstance(raw.get("palette"), dict) else {}
    typo_raw = raw.get("typography") if isinstance(raw.get("typography"), dict) else {}

    palette = Palette(
        top=tuple(
            _norm_hex(c) for c in (palette_raw.get("top") or [])
            if isinstance(c, str) and _norm_hex(c)
        ),
        by_role={
            str(k).lower(): _norm_hex(v)
            for k, v in (palette_raw.get("by_role") or {}).items()
            if isinstance(v, str) and _norm_hex(v) and str(k).lower() in CANONICAL_ROLES
        },
        unique_count=_safe_int(palette_raw.get("unique_count")) or 0,
    )

    typography = Typography(
        families=tuple(
            str(f) for f in (typo_raw.get("families") or [])
            if isinstance(f, str) and f.strip()
        ),
        sizes_px=tuple(sorted({
            v for v in (_safe_int(x) for x in (typo_raw.get("sizes_px") or []))
            if v is not None and v > 0
        })),
        weights=tuple(sorted({
            v for v in (_safe_int(x) for x in (typo_raw.get("weights") or []))
            if v is not None and 100 <= v <= 1000 and v % 100 == 0
        })),
        line_heights=tuple(sorted({
            round(v, 2) for v in (
                _safe_float(x) for x in (typo_raw.get("line_heights") or [])
            ) if v is not None and 0.5 <= v <= 4.0
        })),
    )

    spacing_px = tuple(sorted({
        v for v in (_safe_int(x) for x in (raw.get("spacing_px") or []))
        if v is not None and 0 < v <= 256
    }))
    radii_px = tuple(sorted({
        v for v in (_safe_int(x) for x in (raw.get("radii_px") or []))
        if v is not None and 0 <= v <= 9999
    }))
    shadows = tuple(
        str(s) for s in (raw.get("shadows") or [])
        if isinstance(s, str) and s.strip()
    )

    source_raw = raw.get("source")
    source: Optional[SourceKind] = (
        source_raw if source_raw in ("css_ingested", "manual", "mixed") else None
    )
    generated_at = raw.get("generated_at") if isinstance(raw.get("generated_at"), str) else None

    return DesignTokensView(
        palette=palette,
        typography=typography,
        spacing_px=spacing_px,
        radii_px=radii_px,
        shadows=shadows,
        source=source,
        generated_at=generated_at,
    )


# ─── Conversor do extractor (Fase 25.1 → OCG) ─────────────────────────


def from_extractor_output(
    extractor_tokens: Any,
    *,
    previous: Optional[dict] = None,
) -> dict:
    """Serializa `DesignTokens` do extractor em dict canônico.

    `previous`: dict atual do OCG (opcional). Se GP já tinha editado
    manualmente antes, o novo dict preserva `by_role` customizado
    (merge) e marca `source="mixed"`. Sem previous, source="css_ingested".
    """
    if extractor_tokens is None:
        return {}

    # Duck typing — não importamos o módulo da Fase 25.1 pra manter independência.
    d = extractor_tokens.to_dict() if hasattr(extractor_tokens, "to_dict") else extractor_tokens
    if not isinstance(d, dict):
        return {}

    by_role_extracted = dict((d.get("palette") or {}).get("by_role") or {})
    source: SourceKind = "css_ingested"

    if isinstance(previous, dict):
        prev_source = previous.get("source")
        prev_by_role = ((previous.get("palette") or {}).get("by_role") or {})
        if prev_source == "manual" or (
            isinstance(prev_by_role, dict) and prev_by_role
        ):
            # GP mexeu antes — preserva overrides e marca como mixed.
            merged = {**by_role_extracted, **prev_by_role}
            by_role_extracted = merged
            source = "mixed"

    payload = {
        "palette": {
            "top": list((d.get("palette") or {}).get("top") or []),
            "by_role": by_role_extracted,
            "unique_count": int((d.get("palette") or {}).get("unique_count") or 0),
        },
        "typography": {
            "families": list((d.get("typography") or {}).get("families") or []),
            "sizes_px": list((d.get("typography") or {}).get("sizes_px") or []),
            "weights": list((d.get("typography") or {}).get("weights") or []),
            "line_heights": list((d.get("typography") or {}).get("line_heights") or []),
        },
        "spacing_px": list(d.get("spacing_px") or []),
        "radii_px": list(d.get("radii_px") or []),
        "shadows": list(d.get("shadows") or []),
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return payload


# ─── Validador (endpoint PUT) ─────────────────────────────────────────


@dataclass
class ValidationError:
    path: str
    message: str


def validate_tokens_dict(raw: Any) -> list[ValidationError]:
    """Valida dict de entrada pro endpoint PUT. Lista vazia = válido.

    Regra canônica:
      - dict vazio ou None = válido (sem tokens declarados)
      - chaves estranhas no top-level = erro
      - paleta.top: strings hex #rrggbb (3/6/8 aceitos, normalização downstream)
      - paleta.by_role: role canônico → hex
      - typography.sizes_px/weights: int positivos
      - spacing_px/radii_px: int
      - source: "css_ingested" | "manual" | "mixed" se presente
    """
    errors: list[ValidationError] = []
    if raw is None or raw == {}:
        return errors

    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$", message="design_tokens deve ser dict"))
        return errors

    allowed_roots = {
        "palette", "typography", "spacing_px", "radii_px",
        "shadows", "source", "generated_at",
    }
    for key in raw.keys():
        if key not in allowed_roots:
            errors.append(ValidationError(
                path=f"$.{key}",
                message=f"chave canônica desconhecida (aceitas: {sorted(allowed_roots)})",
            ))

    if "palette" in raw:
        errors.extend(_validate_palette(raw["palette"]))
    if "typography" in raw:
        errors.extend(_validate_typography(raw["typography"]))
    if "spacing_px" in raw:
        errors.extend(_validate_int_list(raw["spacing_px"], "$.spacing_px", lo=0, hi=256, strict_gt_lo=True))
    if "radii_px" in raw:
        errors.extend(_validate_int_list(raw["radii_px"], "$.radii_px", lo=0, hi=9999))
    if "shadows" in raw:
        s = raw["shadows"]
        if not isinstance(s, list) or not all(isinstance(x, str) for x in s):
            errors.append(ValidationError(
                path="$.shadows", message="deve ser lista de strings",
            ))
    if "source" in raw and raw["source"] not in (None, "css_ingested", "manual", "mixed"):
        errors.append(ValidationError(
            path="$.source",
            message="deve ser 'css_ingested', 'manual', 'mixed' ou null",
        ))

    return errors


# ─── Preview pro prompt do CodeGen (Fase 25.4 vai usar) ──────────────


def tokens_as_prompt_block(view: DesignTokensView) -> str:
    """Formata tokens como bloco canônico pro prompt do CodeGen.

    Retorna string vazia se view.is_empty — caller pula o bloco.
    """
    if view.is_empty:
        return ""

    lines: list[str] = ["## Design System (derivado da Ingestão)"]

    if not view.palette.is_empty:
        lines.append("")
        lines.append("### Paleta")
        if view.palette.by_role:
            for role in sorted(view.palette.by_role.keys()):
                lines.append(f"- **{role}**: `{view.palette.by_role[role]}`")
        if view.palette.top:
            lines.append(
                f"- Cores mais usadas: {', '.join(f'`{c}`' for c in view.palette.top[:8])}"
            )

    if not view.typography.is_empty:
        lines.append("")
        lines.append("### Tipografia")
        if view.typography.families:
            lines.append(
                f"- Famílias: {', '.join(f'`{f}`' for f in view.typography.families)}"
            )
        if view.typography.sizes_px:
            lines.append(
                f"- Escala de tamanhos (px): {list(view.typography.sizes_px)}"
            )
        if view.typography.weights:
            lines.append(f"- Pesos: {list(view.typography.weights)}")

    if view.spacing_px:
        lines.append("")
        lines.append(f"### Spacing (px): {list(view.spacing_px)}")

    if view.radii_px:
        lines.append(f"### Border-radius (px): {list(view.radii_px)}")

    if view.shadows:
        lines.append("")
        lines.append("### Shadows")
        for s in view.shadows[:3]:
            lines.append(f"- `{s}`")

    lines.append("")
    lines.append(
        "> O código gerado **deve** reutilizar estes tokens (CSS variables, "
        "theme.extend do Tailwind, ThemeProvider do styled-components, etc). "
        "Não inventar paleta nem criar variações sem justificativa."
    )
    return "\n".join(lines)


# ─── Privates ────────────────────────────────────────────────────────


_HEX_RE = __import__("re").compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _norm_hex(s: Any) -> str:
    """Normaliza hex #rrggbb minúsculo. Retorna '' se inválido."""
    if not isinstance(s, str):
        return ""
    v = s.strip().lower()
    if not _HEX_RE.match(v):
        return ""
    h = v.lstrip("#")
    if len(h) == 3:
        return "#" + "".join(c * 2 for c in h)
    if len(h) == 8:
        return "#" + h[:6]
    return "#" + h


def _safe_int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _validate_palette(raw: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$.palette", message="deve ser dict"))
        return errors

    if "top" in raw:
        tops = raw["top"]
        if not isinstance(tops, list):
            errors.append(ValidationError(path="$.palette.top", message="deve ser lista"))
        else:
            for i, v in enumerate(tops):
                if not isinstance(v, str) or not _norm_hex(v):
                    errors.append(ValidationError(
                        path=f"$.palette.top[{i}]",
                        message=f"hex inválido: {v!r}",
                    ))

    if "by_role" in raw:
        roles = raw["by_role"]
        if not isinstance(roles, dict):
            errors.append(ValidationError(path="$.palette.by_role", message="deve ser dict"))
        else:
            for role, hex_val in roles.items():
                r = str(role).lower()
                if r not in CANONICAL_ROLES:
                    errors.append(ValidationError(
                        path=f"$.palette.by_role.{role}",
                        message=f"role fora do canônico (aceitos: {sorted(CANONICAL_ROLES)})",
                    ))
                if not isinstance(hex_val, str) or not _norm_hex(hex_val):
                    errors.append(ValidationError(
                        path=f"$.palette.by_role.{role}",
                        message=f"hex inválido: {hex_val!r}",
                    ))

    if "unique_count" in raw and _safe_int(raw["unique_count"]) is None:
        errors.append(ValidationError(
            path="$.palette.unique_count", message="deve ser int",
        ))

    return errors


def _validate_typography(raw: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, dict):
        errors.append(ValidationError(path="$.typography", message="deve ser dict"))
        return errors

    if "families" in raw:
        fams = raw["families"]
        if not isinstance(fams, list) or not all(isinstance(x, str) for x in fams):
            errors.append(ValidationError(
                path="$.typography.families",
                message="deve ser lista de strings",
            ))

    errors.extend(_validate_int_list(
        raw.get("sizes_px") if "sizes_px" in raw else None,
        "$.typography.sizes_px", lo=0, hi=1000, strict_gt_lo=True,
    ) if "sizes_px" in raw else [])

    if "weights" in raw:
        weights = raw["weights"]
        if not isinstance(weights, list):
            errors.append(ValidationError(path="$.typography.weights", message="deve ser lista"))
        else:
            for i, v in enumerate(weights):
                iv = _safe_int(v)
                if iv is None or not (100 <= iv <= 1000) or iv % 100 != 0:
                    errors.append(ValidationError(
                        path=f"$.typography.weights[{i}]",
                        message=f"peso inválido: {v!r} (espera múltiplo de 100 entre 100 e 1000)",
                    ))

    if "line_heights" in raw:
        lhs = raw["line_heights"]
        if not isinstance(lhs, list):
            errors.append(ValidationError(path="$.typography.line_heights", message="deve ser lista"))
        else:
            for i, v in enumerate(lhs):
                fv = _safe_float(v)
                if fv is None or not (0.5 <= fv <= 4.0):
                    errors.append(ValidationError(
                        path=f"$.typography.line_heights[{i}]",
                        message=f"line-height inválido: {v!r} (espera 0.5..4.0)",
                    ))

    return errors


def _validate_int_list(
    raw: Any, path: str, *, lo: int, hi: int, strict_gt_lo: bool = False,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if raw is None:
        return errors
    if not isinstance(raw, list):
        errors.append(ValidationError(path=path, message="deve ser lista"))
        return errors
    for i, v in enumerate(raw):
        iv = _safe_int(v)
        low_ok = (iv > lo) if strict_gt_lo else (iv >= lo) if iv is not None else False
        if iv is None or not low_ok or iv > hi:
            op = ">" if strict_gt_lo else ">="
            errors.append(ValidationError(
                path=f"{path}[{i}]",
                message=f"inválido: {v!r} (espera int {op} {lo} e <= {hi})",
            ))
    return errors
