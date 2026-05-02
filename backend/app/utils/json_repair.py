"""Resiliência de parsing JSON para output de LLM — provider-agnóstico.

Oferece três níveis de abstração:
- normalize_llm_json(): corrige tipos inesperados em dicts (pós-parse)
- repair_llm_json(): tenta reparar JSON malformado (string → dict)
- safe_parse_llm_json(): cascade completa que nunca levanta exceção
"""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes de normalização (provider-agnostic)
# ---------------------------------------------------------------------------
NORMALIZE_DICT_KEYS: set[str] = {
    "scores", "highlights", "chunk_tags", "audit_findings",
}
NORMALIZE_LIST_KEYS: set[str] = {
    "issues", "questions", "backlog_to_specialists",
    "questionnaire_to_human", "requirementsFound",
    "risks", "gaps", "detectedTopics",
}

# ---------------------------------------------------------------------------
# Helpers de parsing (portados de arguider_service.py)
# ---------------------------------------------------------------------------
_CODE_FENCE_RE = re.compile(
    r"^```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?```\s*$",
    re.DOTALL,
)


def _strip_code_fence(text: str) -> str:
    """Remove marcação ```json ... ``` se envolver o texto todo."""
    match = _CODE_FENCE_RE.match(text.strip())
    if match:
        return match.group("body").strip()
    return text


def _extract_balanced_object(text: str) -> str | None:
    """Encontra o primeiro objeto JSON com {} balanceado no texto."""
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        char = text[i]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return None


def _remove_trailing_commas(text: str) -> str:
    """Remove vírgulas antes de } ou ] (padrão comum em JSON de LLM)."""
    return re.sub(r",(\s*[\]}])", r"\1", text)


def _repair_truncation(text: str) -> tuple[str, bool]:
    """Tenta fechar JSON truncado contando {} [] e strings abertas.

    Returns (repaired_text, was_truncated).
    """
    depth_braces = 0
    depth_brackets = 0
    in_string = False
    escape = False
    string_open = False

    for char in text:
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth_braces += 1
        elif char == "}":
            depth_braces -= 1
        elif char == "[":
            depth_brackets += 1
        elif char == "]":
            depth_brackets -= 1

    # Detecta string aberta no final
    string_open = in_string

    if depth_braces <= 0 and depth_brackets <= 0 and not string_open:
        return text, False

    repaired = text.rstrip()
    if string_open:
        repaired += '"'

    # Fecha brackets antes de braces
    for _ in range(max(0, depth_brackets)):
        repaired += "]"
    for _ in range(max(0, depth_braces)):
        repaired += "}"

    return repaired, True


# ---------------------------------------------------------------------------
# Dataclasses de metadata
# ---------------------------------------------------------------------------
@dataclass
class RepairResult:
    parsed: dict
    repaired: bool = False
    strategies_used: list[str] = field(default_factory=list)
    truncation_detected: bool = False
    error_preview: str | None = None


@dataclass
class ParseMeta:
    level: int = 0
    total_failure: bool = False
    warnings: list[str] = field(default_factory=list)
    truncated_fields: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# normalize_llm_json — corrige tipos inesperados (pós-parse)
# ---------------------------------------------------------------------------
def normalize_llm_json(data: Any) -> dict:
    """Corrige tipos inesperados no JSON retornado pelo LLM.

    - Guarda contra não-dict (string literal, null, número, array)
    - Converte strings→{} ou [] para chaves conhecidas
    - Recursão em dicts aninhados E em listas (ex: issues[], risks[])
    """
    if not isinstance(data, dict):
        logger.warning(
            "normalize_llm_json.not_a_dict",
            got_type=type(data).__name__,
            preview=str(data)[:300],
        )
        return {}

    for key, value in list(data.items()):
        if isinstance(value, list):
            data[key] = [
                normalize_llm_json(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str):
            if key in NORMALIZE_DICT_KEYS:
                data[key] = {}
            elif key in NORMALIZE_LIST_KEYS:
                data[key] = []
        elif isinstance(value, dict):
            data[key] = normalize_llm_json(value)
    return data


# ---------------------------------------------------------------------------
# repair_llm_json — tenta reparar JSON malformado (string → dict)
# ---------------------------------------------------------------------------
def repair_llm_json(text: str) -> RepairResult:
    """Tenta extrair um dict de texto potencialmente malformado.

    Estratégias em ordem (first-wins):
    1. json.loads direto → dict
    2. Strip markdown fences
    3. Remove trailing commas
    4. Fecha JSON truncado (braces/brackets/strings)
    5. Extrai objeto balanceado do meio do texto
    6. Falha total → retorna {} com error_preview
    """
    if not text or not text.strip():
        return RepairResult(
            parsed={},
            error_preview="empty text",
        )

    stripped = text.strip()

    # Estratégia 1: parse direto
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return RepairResult(parsed=parsed)
    except (json.JSONDecodeError, ValueError):
        pass

    # Estratégia 2: strip markdown fences
    unfenced = _strip_code_fence(stripped)
    if unfenced != stripped:
        try:
            parsed = json.loads(unfenced)
            if isinstance(parsed, dict):
                return RepairResult(
                    parsed=parsed,
                    repaired=True,
                    strategies_used=["strip_fence"],
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Estratégia 3: remove trailing commas
    cleaned = _remove_trailing_commas(stripped)
    if cleaned != stripped:
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return RepairResult(
                    parsed=parsed,
                    repaired=True,
                    strategies_used=["remove_trailing_commas"],
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Estratégia 4: fecha truncamento
    repaired, was_trunc = _repair_truncation(stripped)
    if was_trunc:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return RepairResult(
                    parsed=parsed,
                    repaired=True,
                    strategies_used=["close_truncation"],
                    truncation_detected=True,
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Estratégia 5: extrai objeto balanceado do meio do texto
    extracted = _extract_balanced_object(stripped)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return RepairResult(
                    parsed=parsed,
                    repaired=True,
                    strategies_used=["extract_balanced"],
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Estratégia 6: falha total
    logger.warning(
        "repair_llm_json.all_strategies_failed",
        text_preview=stripped[:500],
    )
    return RepairResult(
        parsed={},
        repaired=False,
        error_preview=stripped[:500],
    )


# ---------------------------------------------------------------------------
# safe_parse_llm_json — cascade completa, nunca levanta exceção
# ---------------------------------------------------------------------------
def safe_parse_llm_json(text: str) -> tuple[dict, ParseMeta]:
    """Parse resiliente de resposta JSON de LLM.

    Níveis da cascade:
    0. json.loads direto → dict
    1. normalize_llm_json (converte não-dict → {})
    2. repair_llm_json (markdown, commas, truncation, extract)
    3. regex extract balanced object (última tentativa)
    4. Falha total → ({}, total_failure=True)

    NUNCA levanta exceção. Sempre retorna (dict, ParseMeta).
    """
    if not text or not text.strip():
        logger.warning("safe_parse_llm_json.empty_text")
        return {}, ParseMeta(
            level=4,
            total_failure=True,
            warnings=["texto vazio ou None"],
        )

    stripped = text.strip()

    # Level 0 — parse direto
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed, ParseMeta(level=0)
        # Level 1 — não-dict (string literal, null, array, número)
        normalized = normalize_llm_json(parsed)
        return normalized, ParseMeta(
            level=1,
            warnings=[f"tipo inesperado no JSON raiz: {type(parsed).__name__}"],
        )
    except (json.JSONDecodeError, ValueError):
        pass

    # Level 2 — repair_llm_json
    repair = repair_llm_json(stripped)
    if repair.parsed:
        warnings = [f"reparo aplicado: {repair.strategies_used}"]
        if repair.truncation_detected:
            warnings.append("truncamento detectado e reparado")
        return repair.parsed, ParseMeta(
            level=2,
            warnings=warnings,
            truncated_fields=["unknown"] if repair.truncation_detected else [],
        )

    # Level 3 — regex extract (tentativa adicional com balanced object)
    extracted = _extract_balanced_object(stripped)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed, ParseMeta(
                    level=3,
                    warnings=["extração por regex de objeto balanceado"],
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Level 4 — falha total
    logger.error(
        "safe_parse_llm_json.total_failure",
        text_preview=stripped[:500],
    )
    return {}, ParseMeta(
        level=4,
        total_failure=True,
        warnings=["todas as estratégias de parsing falharam"],
    )
