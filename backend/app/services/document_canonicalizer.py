"""MVP 29 Fase 2 — Pipeline de canonização de documentos.

Função pública: `canonicalize(file_bytes, filename, document_type)` → `DocumentCanonical`.

Fluxo:
  1. Chama extractor determinístico apropriado (PDF/DOCX/MD) → texto + metadata.
  2. Parseia o texto em seções (heading/bullet/paragraph) com depth.
  3. Classifica cada seção num `semantic_type` via keyword match.
  4. Extrai entidades via dicionário do projeto + regex canônicos.
  5. Destila listas derivadas: requirements (frases "X deve Y"), actors,
     rules, refs (URLs + arquivos mencionados).
  6. Monta `DocumentCanonical` + stats.

Zero chamada LLM. Zero cache no MVP (Fase 2 do Task adiciona).

Design completo em `docs/design/document_canonical_schema.md`.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

import structlog

from app.services.document_canonical import (
    CANONICAL_VERSION,
    DOCUMENT_TYPES,
    SEMANTIC_KEYWORDS,
    CanonicalEntity,
    CanonicalSection,
    DocumentCanonical,
    _PROJECT_DICTIONARY,
)

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------ #
# Regex canônicos (ver schema v1 §5)                                 #
# ------------------------------------------------------------------ #

_RE_DATE_BR = re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b")
_RE_DATE_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_RE_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-z0-9]+)?\b", re.IGNORECASE)
_RE_URL = re.compile(r"https?://[^\s)<>\"]+")
_RE_FILE_REF = re.compile(
    r"\b[\w-]+\.(?:pdf|docx|md|xlsx|json|yaml|yml|sql|py|ts|tsx|js|jsx|png|jpg)\b",
    re.IGNORECASE,
)
_RE_REQUIREMENT = re.compile(
    r"(?i)(?:o\s+sistema|a\s+aplica[cç][aã]o|o\s+m[oó]dulo|o\s+servi[cç]o|o\s+usu[aá]rio)"
    r"\s+(?:deve|dever[aá]|precisa|pode|deveria)\b[^.\n]{5,200}",
)
_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_RE_BULLET = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+(.+?)\s*$")


# ------------------------------------------------------------------ #
# Classificação semântica                                             #
# ------------------------------------------------------------------ #

def classify_semantic(text: str) -> str:
    """Classifica um bloco de texto em um dos `SEMANTIC_TYPES`.

    Heurística por keywords (primeiro match vence, ordem de
    `SEMANTIC_KEYWORDS` importa). Retorna 'unknown' se nada bate.
    """
    if not text:
        return "unknown"
    lowered = text.lower()
    for semantic_type, keywords in SEMANTIC_KEYWORDS:
        for kw in keywords:
            if kw in lowered:
                return semantic_type
    return "unknown"


# ------------------------------------------------------------------ #
# Parse de texto → seções                                            #
# ------------------------------------------------------------------ #

def parse_sections_from_text(text: str, document_type: str) -> list[CanonicalSection]:
    """Parseia texto plano em seções estruturadas.

    Suporta:
      - Headings MD (`#`, `##`, ...) com depth = número de #
      - Bullets (`-`, `*`, `•`, `1.`) com depth = heading pai + 1
      - Parágrafos (depth = heading pai)

    Pra PDF/DOCX onde o extractor devolve texto corrido, ainda funciona
    razoavelmente: linhas curtas isoladas entre parágrafos viram
    headings heurísticos quando não tem `#` marker.
    """
    if not text:
        return []

    sections: list[CanonicalSection] = []
    current_heading_depth = 0
    heading_counter = 0
    sub_counter: dict[int, int] = {}

    def _next_id(depth: int) -> str:
        nonlocal heading_counter
        if depth == 1 or (depth == 0 and current_heading_depth == 0):
            heading_counter += 1
            sub_counter.clear()
            return f"s{heading_counter}"
        sub = sub_counter.get(heading_counter, 0) + 1
        sub_counter[heading_counter] = sub
        return f"s{heading_counter}.{sub}"

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        if not line:
            continue

        # Heading MD explícito
        md_match = _RE_MD_HEADING.match(line)
        if md_match:
            depth = len(md_match.group(1))
            title = md_match.group(2)
            current_heading_depth = depth
            sid = _next_id(1)
            sections.append(CanonicalSection(
                id=sid,
                section_type="heading",
                semantic_type=classify_semantic(title),
                content=title,
                depth=depth,
                title=title,
            ))
            continue

        # Bullet
        bullet_match = _RE_BULLET.match(raw)
        if bullet_match:
            bullet_content = bullet_match.group(1)
            sid = _next_id(2)
            sections.append(CanonicalSection(
                id=sid,
                section_type="bullet",
                semantic_type=classify_semantic(bullet_content),
                content=bullet_content,
                depth=max(current_heading_depth + 1, 2),
            ))
            continue

        # Heading heurístico (linha curta, isolada, provável título de seção)
        # Aplica-se quando doc não tem markdown headers (PDF/DOCX texto corrido).
        is_heuristic_heading = (
            document_type in ("PDF", "DOCX")
            and len(line) < 80
            and not line.endswith((".", "!", "?", ":", ";", ","))
            and (i >= len(lines) or not lines[i].strip() or lines[i].strip().startswith(" "))
        )
        if is_heuristic_heading:
            depth = 2  # heurístico assume H2
            current_heading_depth = depth
            sid = _next_id(1)
            sections.append(CanonicalSection(
                id=sid,
                section_type="heading",
                semantic_type=classify_semantic(line),
                content=line,
                depth=depth,
                title=line,
            ))
            continue

        # Parágrafo — coleta linhas consecutivas até vazia ou próximo marker
        paragraph_lines = [line]
        while i < len(lines):
            next_raw = lines[i]
            next_line = next_raw.strip()
            if not next_line:
                break
            if _RE_MD_HEADING.match(next_line) or _RE_BULLET.match(next_raw):
                break
            paragraph_lines.append(next_line)
            i += 1

        paragraph = " ".join(paragraph_lines)
        sid = _next_id(2)
        sections.append(CanonicalSection(
            id=sid,
            section_type="paragraph",
            semantic_type=classify_semantic(paragraph),
            content=paragraph,
            depth=max(current_heading_depth, 1),
        ))

    return sections


# ------------------------------------------------------------------ #
# Extração de entidades                                              #
# ------------------------------------------------------------------ #

def extract_entities(sections: list[CanonicalSection]) -> list[CanonicalEntity]:
    """Extrai entidades via dicionário do projeto + regex canônicos.

    Dicionário → confidence 1.0.
    Regex → confidence 0.8-0.9.

    Dedup por (entity_type, value.lower) — mantém primeira ocorrência.
    """
    seen: set[tuple[str, str]] = set()
    out: list[CanonicalEntity] = []

    def _add(entity_type: str, value: str, confidence: float, section_id: str | None):
        key = (entity_type, value.lower().strip())
        if key in seen or not value.strip():
            return
        seen.add(key)
        out.append(CanonicalEntity(
            entity_type=entity_type,
            value=value.strip(),
            confidence=confidence,
            source_section_id=section_id,
        ))

    for section in sections:
        content = section.content
        if not content:
            continue

        # Dicionário (case-insensitive, palavra completa)
        for term in _PROJECT_DICTIONARY["actors"]:
            if re.search(rf"\b{re.escape(term)}\b", content, re.IGNORECASE):
                _add("actor", term, 1.0, section.id)
        for term in _PROJECT_DICTIONARY["systems"]:
            if re.search(rf"\b{re.escape(term)}\b", content, re.IGNORECASE):
                _add("system", term, 1.0, section.id)
        for term in _PROJECT_DICTIONARY["integrations"]:
            if re.search(rf"\b{re.escape(term)}\b", content, re.IGNORECASE):
                _add("integration", term, 1.0, section.id)

        # Regex — datas
        for m in _RE_DATE_BR.finditer(content):
            _add("date", m.group(0), 0.9, section.id)
        for m in _RE_DATE_ISO.finditer(content):
            _add("date", m.group(0), 0.9, section.id)

        # Versions (semver) — filtra falsos positivos tipo "1.0"
        for m in _RE_VERSION.finditer(content):
            v = m.group(0)
            # ignora números simples sem contexto (evita matchar "2.5" de metricas)
            if "." in v and len(v) >= 3:
                _add("version", v, 0.8, section.id)

    return out


def extract_requirements(sections: list[CanonicalSection]) -> list[str]:
    """Extrai frases-requisito via regex canônico ('X deve Y'). Dedup."""
    seen: set[str] = set()
    out: list[str] = []
    for section in sections:
        for m in _RE_REQUIREMENT.finditer(section.content):
            phrase = m.group(0).strip().rstrip(".;,")
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                out.append(phrase)
    return out


def extract_refs(sections: list[CanonicalSection]) -> list[str]:
    """URLs + nomes de arquivo mencionados. Dedup."""
    seen: set[str] = set()
    out: list[str] = []
    for section in sections:
        for m in _RE_URL.finditer(section.content):
            v = m.group(0).rstrip(".,);")
            if v.lower() not in seen:
                seen.add(v.lower())
                out.append(v)
        for m in _RE_FILE_REF.finditer(section.content):
            v = m.group(0)
            if v.lower() not in seen:
                seen.add(v.lower())
                out.append(v)
    return out


def derive_actors(entities: list[CanonicalEntity]) -> list[str]:
    """Lista ordenada de atores únicos (normalizados)."""
    return sorted({e.value for e in entities if e.entity_type == "actor"})


def derive_rules(sections: list[CanonicalSection]) -> list[str]:
    """Conteúdo de seções classificadas como business_rule."""
    return [s.content for s in sections if s.semantic_type == "business_rule"]


# ------------------------------------------------------------------ #
# Extração de texto por tipo                                          #
# ------------------------------------------------------------------ #

def _extract_text(file_bytes: bytes, document_type: str) -> tuple[str, str]:
    """Dispatcher de extração. Retorna `(text, inferred_title)`."""
    if document_type == "MD":
        text = file_bytes.decode("utf-8", errors="replace")
        # Título = primeira linha # se existir, senão ""
        for line in text.splitlines():
            m = _RE_MD_HEADING.match(line.strip())
            if m:
                return text, m.group(2)
        return text, ""

    if document_type == "DOCX":
        from app.services.rich_docx_extractor import extract_rich_text
        text = extract_rich_text(file_bytes)
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        return text, first_line[:120]

    if document_type == "PDF":
        from app.services.pdf_layered_extractor import extract_pdf_layered
        result = extract_pdf_layered(file_bytes)
        text = result.text
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        return text, first_line[:120]

    # Tipos não suportados no MVP (XLSX, IMAGE)
    raise NotImplementedError(
        f"Canonização de document_type={document_type!r} ainda não suportada "
        f"(MVP 29 cobre PDF/DOCX/MD; XLSX/IMAGE na fase 2)."
    )


# ------------------------------------------------------------------ #
# Entry point                                                         #
# ------------------------------------------------------------------ #

def canonicalize(
    file_bytes: bytes,
    filename: str,
    document_type: str,
    *,
    include_raw_fallback: bool = False,
) -> DocumentCanonical:
    """Entry point do MVP 29. Retorna `DocumentCanonical` determinístico.

    Args:
        file_bytes: conteúdo bruto do arquivo.
        filename: nome original (pra log e referência).
        document_type: um de PDF/DOCX/MD (XLSX/IMAGE gera NotImplementedError).
        include_raw_fallback: se True, inclui texto bruto em `raw_text_fallback`
            (útil pra debug; default False pra não inflar payload).

    Raises:
        NotImplementedError: se `document_type` não suportado no MVP.
        ValueError: se `document_type` não é canônico.
    """
    if document_type not in DOCUMENT_TYPES:
        raise ValueError(
            f"document_type inválido: {document_type!r}. Aceitos: {sorted(DOCUMENT_TYPES)}"
        )

    # Hash determinístico pra ID (fase 2 usa como cache key)
    doc_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    canonical_id = f"{doc_hash}:{CANONICAL_VERSION}"

    # 1. Extração
    text, inferred_title = _extract_text(file_bytes, document_type)

    # 2. Sections
    sections = parse_sections_from_text(text, document_type)

    # 3. Entities
    entities = extract_entities(sections)

    # 4. Derivações
    requirements = extract_requirements(sections)
    actors = derive_actors(entities)
    rules = derive_rules(sections)
    refs = extract_refs(sections)

    # 5. Monta canônico
    canonical = DocumentCanonical(
        id=canonical_id,
        title=inferred_title or filename,
        document_type=document_type,
        original_filename=filename,
        sections=sections,
        entities=entities,
        requirements=requirements,
        actors=actors,
        rules=rules,
        refs=refs,
        affected_pillars=[],  # fase 2 preenche
        extractor_version=CANONICAL_VERSION,
        raw_text_fallback=text if include_raw_fallback else None,
    )
    canonical.stats = canonical.stats_summary()

    logger.info(
        "canonicalizer.done",
        filename=filename,
        document_type=document_type,
        sections_count=len(sections),
        entities_count=len(entities),
        requirements_count=len(requirements),
        actors_count=len(actors),
        refs_count=len(refs),
        char_count_raw=len(text),
    )

    return canonical
