"""MVP 29 Fase 4 — Testes unit do canonicalizer.

Cobertura de: schema validation, classify_semantic, parse_sections,
extract_entities, extract_requirements, canonicalize end-to-end.

Executa standalone (zero DB, zero pytest fixtures) pra não depender
de infra de teste. Rodar via:
  docker exec gca-backend python -m app.tests.test_mvp29_document_canonical
ou
  cd backend && python -m pytest app/tests/test_mvp29_document_canonical.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permite rodar standalone sem pytest
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.document_canonical import (
    CANONICAL_VERSION,
    DOCUMENT_TYPES,
    SEMANTIC_TYPES,
    ENTITY_TYPES,
    CanonicalEntity,
    CanonicalSection,
    DocumentCanonical,
    get_project_dictionary,
)
from app.services.document_canonicalizer import (
    canonicalize,
    classify_semantic,
    derive_actors,
    derive_rules,
    extract_entities,
    extract_refs,
    extract_requirements,
    parse_sections_from_text,
)


# ------------------------------------------------------------------ #
#  Schema validation                                                  #
# ------------------------------------------------------------------ #

def test_canonical_entity_rejects_invalid_entity_type():
    try:
        CanonicalEntity(entity_type="foo_bar", value="x")
    except ValueError as e:
        assert "entity_type inválido" in str(e)
    else:
        raise AssertionError("Deveria ter levantado ValueError")


def test_canonical_entity_rejects_confidence_out_of_range():
    try:
        CanonicalEntity(entity_type="actor", value="x", confidence=1.5)
    except ValueError as e:
        assert "confidence deve estar em" in str(e)
    else:
        raise AssertionError("Deveria ter levantado ValueError")


def test_canonical_section_rejects_invalid_semantic_type():
    try:
        CanonicalSection(
            id="s1", section_type="heading",
            semantic_type="foo", content="",
        )
    except ValueError as e:
        assert "semantic_type inválido" in str(e)
    else:
        raise AssertionError("Deveria ter levantado ValueError")


def test_document_canonical_rejects_invalid_document_type():
    try:
        DocumentCanonical(
            id="x", title="t", document_type="CSV", original_filename="f",
        )
    except ValueError as e:
        assert "document_type inválido" in str(e)
    else:
        raise AssertionError("Deveria ter levantado ValueError")


def test_document_canonical_stats_summary():
    d = DocumentCanonical(id="x", title="t", document_type="MD", original_filename="f.md")
    d.sections.append(CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="abc",
    ))
    d.entities.append(CanonicalEntity(entity_type="system", value="PostgreSQL"))
    d.requirements.append("O sistema deve X")
    stats = d.stats_summary()
    assert stats["sections_count"] == 1
    assert stats["entities_count"] == 1
    assert stats["requirements_count"] == 1
    assert stats["char_count"] == 3


def test_canonical_version_is_set():
    assert CANONICAL_VERSION == "v1.0.0"


def test_project_dictionary_has_core_terms():
    d = get_project_dictionary()
    assert "GP" in d["actors"]
    assert "PostgreSQL" in d["systems"]
    assert "LGPD" in d["integrations"]


# ------------------------------------------------------------------ #
#  classify_semantic                                                  #
# ------------------------------------------------------------------ #

def test_classify_semantic_functional_requirement():
    assert classify_semantic("O sistema deve autenticar via OAuth") == "functional_requirement"


def test_classify_semantic_non_functional():
    assert classify_semantic("Latência máxima de 200ms") == "non_functional_requirement"


def test_classify_semantic_business_rule():
    assert classify_semantic("Regra: apenas admins podem deletar") == "business_rule"


def test_classify_semantic_risk():
    assert classify_semantic("Risco: vazamento de PII em logs") == "risk"


def test_classify_semantic_glossary():
    assert classify_semantic("Glossário de termos técnicos") == "glossary"


def test_classify_semantic_unknown_fallback():
    assert classify_semantic("Texto aleatório sem keywords") == "unknown"


def test_classify_semantic_empty_string():
    assert classify_semantic("") == "unknown"


# ------------------------------------------------------------------ #
#  parse_sections_from_text                                           #
# ------------------------------------------------------------------ #

def test_parse_sections_md_headings():
    md = "# Titulo\n\n## Subsecao\n\nTexto normal"
    sections = parse_sections_from_text(md, "MD")
    assert len(sections) >= 3
    headings = [s for s in sections if s.section_type == "heading"]
    assert len(headings) == 2
    assert headings[0].depth == 1
    assert headings[1].depth == 2


def test_parse_sections_md_bullets():
    md = "# T\n\n- item 1\n- item 2\n- item 3"
    sections = parse_sections_from_text(md, "MD")
    bullets = [s for s in sections if s.section_type == "bullet"]
    assert len(bullets) == 3


def test_parse_sections_depth_hierarchy():
    md = "# H1\n\n## H2\n\n### H3"
    sections = parse_sections_from_text(md, "MD")
    headings = [s for s in sections if s.section_type == "heading"]
    assert [h.depth for h in headings] == [1, 2, 3]


def test_parse_sections_empty_input():
    assert parse_sections_from_text("", "MD") == []


def test_parse_sections_paragraph_continuation():
    md = "Linha 1\nLinha 2 do mesmo parágrafo\nLinha 3\n\nNovo parágrafo"
    sections = parse_sections_from_text(md, "MD")
    paragraphs = [s for s in sections if s.section_type == "paragraph"]
    assert len(paragraphs) == 2
    assert "Linha 1" in paragraphs[0].content
    assert "Linha 2" in paragraphs[0].content
    assert paragraphs[1].content == "Novo parágrafo"


# ------------------------------------------------------------------ #
#  extract_entities                                                   #
# ------------------------------------------------------------------ #

def test_extract_entities_dictionary_hit_system():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="Stack: PostgreSQL + Redis + FastAPI",
    )]
    ents = extract_entities(secs)
    values = {e.value for e in ents if e.entity_type == "system"}
    assert "PostgreSQL" in values
    assert "Redis" in values
    assert "FastAPI" in values


def test_extract_entities_dictionary_hit_actor():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="O Tech Lead aprova, o GP revisa, o QA testa",
    )]
    ents = extract_entities(secs)
    actor_values = {e.value for e in ents if e.entity_type == "actor"}
    assert "Tech Lead" in actor_values
    assert "GP" in actor_values
    assert "QA" in actor_values


def test_extract_entities_regex_date_brazilian():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="Deadline: 23/04/2026 confirmado",
    )]
    ents = extract_entities(secs)
    dates = [e for e in ents if e.entity_type == "date"]
    assert any(e.value == "23/04/2026" for e in dates)


def test_extract_entities_dedup():
    secs = [
        CanonicalSection(id="s1", section_type="paragraph", semantic_type="unknown",
                         content="PostgreSQL 15"),
        CanonicalSection(id="s2", section_type="paragraph", semantic_type="unknown",
                         content="PostgreSQL backup"),
    ]
    ents = extract_entities(secs)
    systems = [e for e in ents if e.entity_type == "system" and e.value == "PostgreSQL"]
    assert len(systems) == 1


def test_extract_entities_confidence_dictionary_is_1():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="FastAPI",
    )]
    ents = extract_entities(secs)
    fa = [e for e in ents if e.value == "FastAPI"][0]
    assert fa.confidence == 1.0


# ------------------------------------------------------------------ #
#  extract_requirements                                               #
# ------------------------------------------------------------------ #

def test_extract_requirements_finds_o_sistema_deve():
    # Regex separa por '.' ou '\n' — frases devem estar em linhas/períodos distintos
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="O sistema deve autenticar via OAuth.\nO módulo deverá logar eventos.",
    )]
    reqs = extract_requirements(secs)
    assert len(reqs) >= 2, f"esperava >= 2, recebi {len(reqs)}: {reqs}"


def test_extract_requirements_dedup():
    secs = [
        CanonicalSection(id="s1", section_type="paragraph", semantic_type="unknown",
                         content="O sistema deve autenticar via OAuth"),
        CanonicalSection(id="s2", section_type="paragraph", semantic_type="unknown",
                         content="O sistema deve autenticar via OAuth"),
    ]
    reqs = extract_requirements(secs)
    assert len(reqs) == 1


def test_extract_requirements_ignores_non_matching():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="Texto genérico sem formato de requisito",
    )]
    assert extract_requirements(secs) == []


# ------------------------------------------------------------------ #
#  extract_refs                                                       #
# ------------------------------------------------------------------ #

def test_extract_refs_url():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="Ver https://example.com/doc para mais info",
    )]
    assert "https://example.com/doc" in extract_refs(secs)


def test_extract_refs_file_mention():
    secs = [CanonicalSection(
        id="s1", section_type="paragraph", semantic_type="unknown",
        content="Ver glossario.md e schema.json",
    )]
    refs = extract_refs(secs)
    assert "glossario.md" in refs
    assert "schema.json" in refs


# ------------------------------------------------------------------ #
#  derive_*                                                           #
# ------------------------------------------------------------------ #

def test_derive_actors_sorted_unique():
    ents = [
        CanonicalEntity(entity_type="actor", value="GP"),
        CanonicalEntity(entity_type="actor", value="Tech Lead"),
        CanonicalEntity(entity_type="system", value="PostgreSQL"),
    ]
    assert derive_actors(ents) == ["GP", "Tech Lead"]


def test_derive_rules_picks_business_rule_only():
    secs = [
        CanonicalSection(id="s1", section_type="paragraph",
                         semantic_type="business_rule", content="Regra X"),
        CanonicalSection(id="s2", section_type="paragraph",
                         semantic_type="functional_requirement", content="RF Y"),
    ]
    assert derive_rules(secs) == ["Regra X"]


# ------------------------------------------------------------------ #
#  canonicalize end-to-end (MD)                                       #
# ------------------------------------------------------------------ #

def test_canonicalize_md_basic():
    md = (
        "# Projeto X\n\n"
        "## Stack\n"
        "- Python\n"
        "- FastAPI\n"
        "- PostgreSQL\n\n"
        "## Requisitos\n"
        "- O sistema deve autenticar via OAuth\n"
        "- A aplicação deve responder em menos de 200ms\n\n"
        "Ver https://example.com/spec.pdf"
    )
    c = canonicalize(md.encode("utf-8"), "test.md", "MD")
    assert c.document_type == "MD"
    assert c.title == "Projeto X"
    assert len(c.sections) >= 5
    assert len(c.entities) >= 3  # Python, FastAPI, PostgreSQL
    assert len(c.requirements) >= 1
    assert "https://example.com/spec.pdf" in c.refs
    assert c.extractor_version == CANONICAL_VERSION
    assert c.id.endswith(CANONICAL_VERSION)


def test_canonicalize_md_empty():
    c = canonicalize(b"", "empty.md", "MD")
    assert c.document_type == "MD"
    assert c.title == "empty.md"  # fallback pro filename
    assert len(c.sections) == 0


def test_canonicalize_rejects_invalid_document_type():
    try:
        canonicalize(b"foo", "x.csv", "CSV")
    except ValueError as e:
        assert "document_type inválido" in str(e)
    else:
        raise AssertionError("Deveria ter levantado ValueError")


def test_canonicalize_xlsx_raises_not_implemented():
    try:
        canonicalize(b"foo", "x.xlsx", "XLSX")
    except NotImplementedError as e:
        assert "XLSX" in str(e) or "ainda não suportada" in str(e)
    else:
        raise AssertionError("Deveria ter levantado NotImplementedError")


# ------------------------------------------------------------------ #
#  Runner standalone (sem pytest)                                     #
# ------------------------------------------------------------------ #

def _run_all():
    import inspect
    test_fns = [
        obj for name, obj in globals().items()
        if name.startswith("test_") and inspect.isfunction(obj)
    ]
    passed = 0
    failed = []
    for fn in test_fns:
        try:
            fn()
            passed += 1
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failed.append((fn.__name__, f"assertion: {e}"))
            print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    total = len(test_fns)
    print(f"\n{'='*60}")
    print(f"Total: {total}  |  Passou: {passed}  |  Falhou: {len(failed)}")
    if failed:
        print("Falhas:")
        for name, err in failed:
            print(f"  {name}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
