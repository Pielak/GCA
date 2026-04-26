"""MVP-H (2026-04-25) — Import nativo de Figma como entrada de design.

Antes do MVP-H, owner que quisesse alimentar o GCA com tokens de design
precisava colar CSS/SCSS na aba Design via Ingestão (MVP 25). Pressupõe
design já pronto fora do GCA. Pra a visão "input requisitos + telas →
app rodando", faltava porta de entrada Figma direto.

Esta primeira fase faz o caminho mínimo viável:
  1. Lê variables (cores) do arquivo Figma via REST API.
  2. Heurística mapeia nome da variável → role canônico (16 roles do MVP 25).
  3. Lista frames de cada página como specs candidatos a tela do scaffold
     (`pages/X.tsx`).
  4. Retorna estrutura compatível com o pipeline MVP 25 (palette por role +
     frames como deliverables).

Não persiste em arquivo nem dispara CodeGen — só prepara os dados pra
o caller (router) salvar no OCG. Code Connect e export de screenshots
são fase 2 (parked).

PAT do owner fica no vault via `vault_service` (secret_type='figma',
secret_key='pat'). file_key é pública (parte da URL Figma) e mora em
`project_settings` setting_type='figma'.

API REST do Figma usada (sem MCP):
  - GET /v1/files/{file_key}        — metadata + páginas + frames
  - GET /v1/files/{file_key}/variables/local — design tokens (variables)
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import httpx
import structlog

logger = structlog.get_logger(__name__)

FIGMA_BASE_URL = "https://api.figma.com"
FIGMA_HTTP_TIMEOUT = 30.0


# Heurística determinística pra mapear nome de variable Figma → role
# canônico do MVP 25. Padrões cobrem nomenclatura comum (primary,
# brand-color, btn-primary, color/primary/500, etc.).
_ROLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bprimary\b", re.IGNORECASE), "primary"),
    (re.compile(r"\bsecondary\b", re.IGNORECASE), "secondary"),
    (re.compile(r"\baccent\b", re.IGNORECASE), "accent"),
    (re.compile(r"\bsuccess\b", re.IGNORECASE), "success"),
    (re.compile(r"\bwarning\b|\bwarn\b", re.IGNORECASE), "warning"),
    (re.compile(r"\bdanger\b|\bnegative\b|\bdestructive\b", re.IGNORECASE), "danger"),
    (re.compile(r"\berror\b", re.IGNORECASE), "error"),
    (re.compile(r"\binfo\b|\binformational\b", re.IGNORECASE), "info"),
    (re.compile(r"\bmuted\b|\bdisabled\b", re.IGNORECASE), "muted"),
    (re.compile(r"\bbackground\b|\bbg\b", re.IGNORECASE), "background"),
    (re.compile(r"\bforeground\b|\bfg\b", re.IGNORECASE), "foreground"),
    (re.compile(r"\btext\b|\btypography\b", re.IGNORECASE), "text"),
    (re.compile(r"\bsurface\b|\bcard\b|\bpanel\b", re.IGNORECASE), "surface"),
    (re.compile(r"\bborder\b|\bdivider\b|\boutline\b", re.IGNORECASE), "border"),
    (re.compile(r"\blink\b|\banchor\b", re.IGNORECASE), "link"),
    (re.compile(r"\bbrand\b|\blogo\b", re.IGNORECASE), "brand"),
]


def _name_to_role(name: str) -> str | None:
    """Mapeia nome de variable pra role canônico. None se nenhum match."""
    if not name:
        return None
    for pat, role in _ROLE_PATTERNS:
        if pat.search(name):
            return role
    return None


def _figma_color_to_hex(color: dict[str, Any]) -> str | None:
    """Converte color object {r,g,b,a} (0..1 float) do Figma pra '#rrggbb'.
    Ignora alpha — palette canônica é só RGB sólido."""
    try:
        r = max(0, min(255, int(round(float(color.get("r", 0)) * 255))))
        g = max(0, min(255, int(round(float(color.get("g", 0)) * 255))))
        b = max(0, min(255, int(round(float(color.get("b", 0)) * 255))))
        return f"#{r:02x}{g:02x}{b:02x}"
    except (TypeError, ValueError):
        return None


async def fetch_figma_file(file_key: str, pat: str) -> dict[str, Any]:
    """GET /v1/files/{file_key}. Retorna o JSON cru. Levanta RuntimeError em
    erro de rede/HTTP com mensagem PT-BR pra caller mostrar pro user."""
    url = f"{FIGMA_BASE_URL}/v1/files/{file_key}"
    try:
        async with httpx.AsyncClient(timeout=FIGMA_HTTP_TIMEOUT) as client:
            resp = await client.get(
                url,
                headers={"X-Figma-Token": pat},
            )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Falha de rede ao acessar Figma: {exc}") from exc

    if resp.status_code == 403:
        raise RuntimeError(
            "Figma rejeitou o PAT (403). Verifique se o token tem permissão "
            "no arquivo e se não expirou.",
        )
    if resp.status_code == 404:
        raise RuntimeError(
            f"Arquivo Figma '{file_key}' não encontrado (404). Confira a URL.",
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Figma retornou {resp.status_code}: {resp.text[:200]}",
        )
    return resp.json()


async def fetch_figma_variables(file_key: str, pat: str) -> dict[str, Any]:
    """GET /v1/files/{file_key}/variables/local. Pode retornar 403 se o
    plano Figma do user não suporta variables (free tier sem variables) —
    nesse caso, retorna dict vazio em vez de levantar."""
    url = f"{FIGMA_BASE_URL}/v1/files/{file_key}/variables/local"
    try:
        async with httpx.AsyncClient(timeout=FIGMA_HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers={"X-Figma-Token": pat})
    except httpx.HTTPError:
        return {"meta": {}}
    if resp.status_code in (403, 404):
        # Plan sem variables ou file sem variables: degrade graceful.
        logger.info(
            "figma.variables_unavailable",
            file_key=file_key,
            status_code=resp.status_code,
        )
        return {"meta": {}}
    if resp.status_code >= 400:
        return {"meta": {}}
    return resp.json()


def extract_palette(variables_payload: dict[str, Any]) -> dict[str, str]:
    """Itera variables COLOR e retorna {role_canonico: hex}.

    Quando há colisão (várias vars mapeiam pro mesmo role), mantém a
    primeira encontrada — owner pode override depois na aba Design.
    """
    by_role: dict[str, str] = {}
    meta = variables_payload.get("meta") or {}
    variables = meta.get("variables") or {}
    for var_id, var in (variables.items() if isinstance(variables, dict) else []):
        if var.get("resolvedType") != "COLOR":
            continue
        name = var.get("name") or ""
        role = _name_to_role(name)
        if role is None or role in by_role:
            continue
        # Pega o valor do primeiro mode (mode default).
        values_by_mode = var.get("valuesByMode") or {}
        if not values_by_mode:
            continue
        first_mode_value = next(iter(values_by_mode.values()))
        if isinstance(first_mode_value, dict):
            hex_val = _figma_color_to_hex(first_mode_value)
            if hex_val:
                by_role[role] = hex_val
    return by_role


def extract_frames_as_pages(file_payload: dict[str, Any]) -> list[dict[str, str]]:
    """Lista frames top-level de cada página como specs candidatos a tela.

    Retorna lista de `{page_name, frame_name, suggested_path}`. O
    `suggested_path` é heurística: nomes em PascalCase + sufixo .tsx
    (frontend default React). Owner pode renomear depois.
    """
    out: list[dict[str, str]] = []
    document = file_payload.get("document") or {}
    pages = document.get("children") or []
    for page in pages:
        if page.get("type") != "CANVAS":
            continue
        page_name = page.get("name") or "Page"
        for frame in page.get("children") or []:
            if frame.get("type") != "FRAME":
                continue
            frame_name = frame.get("name") or "Frame"
            # Normaliza: remove non-alnum, capitaliza palavras → PascalCase
            slug_parts = re.findall(r"[A-Za-z0-9]+", frame_name)
            page_path = "".join(p.capitalize() for p in slug_parts) or "Page"
            if not page_path.endswith("Page"):
                page_path = f"{page_path}Page"
            out.append({
                "page_name": page_name,
                "frame_name": frame_name,
                "suggested_path": f"frontend/src/pages/{page_path}.tsx",
            })
    return out


async def import_figma_design(
    file_key: str,
    pat: str,
    project_id: UUID,
) -> dict[str, Any]:
    """Pipeline completo: file + variables → palette + frames.

    Retorna dict canônico:
        {
          "file_name": str,
          "version": str,
          "palette_by_role": {role: hex, ...},  # 0..16 entradas
          "frames": [{page_name, frame_name, suggested_path}, ...],
          "raw_variable_count": int,
        }
    """
    file_payload = await fetch_figma_file(file_key, pat)
    variables_payload = await fetch_figma_variables(file_key, pat)

    palette = extract_palette(variables_payload)
    frames = extract_frames_as_pages(file_payload)

    raw_var_count = 0
    meta = variables_payload.get("meta") or {}
    if isinstance(meta.get("variables"), dict):
        raw_var_count = sum(
            1 for v in meta["variables"].values() if v.get("resolvedType") == "COLOR"
        )

    logger.info(
        "figma.import_done",
        project_id=str(project_id),
        file_key=file_key,
        palette_size=len(palette),
        frames_count=len(frames),
        raw_color_variables=raw_var_count,
    )

    return {
        "file_name": file_payload.get("name") or "",
        "version": str(file_payload.get("version") or ""),
        "palette_by_role": palette,
        "frames": frames,
        "raw_variable_count": raw_var_count,
    }
