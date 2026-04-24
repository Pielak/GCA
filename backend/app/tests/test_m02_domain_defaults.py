"""M02 — testes unit standalone (padrão MVP 29, sem pytest/DB de prod)."""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.domain_defaults_kb import all_defaults, find_matches
from app.services.domain_defaults_resolver import infer_project_context_tags


def test_kb_has_entries():
    assert len(all_defaults()) >= 10, "KB deve ter >=10 defaults canônicos"


def test_kb_entries_have_required_fields():
    for entry in all_defaults():
        assert "key" in entry and entry["key"], f"entry sem key: {entry}"
        assert "category" in entry and entry["category"] in (
            "legal", "security", "technical", "compliance", "architecture",
        ), f"category inválida: {entry.get('category')}"
        assert "matches_any_of" in entry and len(entry["matches_any_of"]) >= 1
        assert "value" in entry and entry["value"]
        assert "source" in entry and entry["source"], f"entry sem source: {entry['key']}"
        assert "rationale" in entry


def test_kb_keys_are_unique():
    keys = [e["key"] for e in all_defaults()]
    assert len(keys) == len(set(keys)), f"keys duplicadas: {[k for k in keys if keys.count(k) > 1]}"


def test_find_matches_retention_civil_hit():
    matches = find_matches(
        "prazo de retenção de processos cíveis não definido",
        ["domain:juridico", "project_type:processo_civil"],
    )
    keys = [m["key"] for m in matches]
    assert "retention.civil_cases" in keys


def test_find_matches_respects_applies_when():
    # Sem tag de domínio jurídico, não deve retornar defaults com applies_when domain:juridico
    matches = find_matches("retenção cível", [])
    keys = [m["key"] for m in matches]
    assert "retention.civil_cases" not in keys


def test_find_matches_universal_default_without_tags():
    # password_hashing não tem applies_when — deve aparecer com contexto vazio.
    matches = find_matches("armazenamento de senha em hash", [])
    keys = [m["key"] for m in matches]
    assert "security.password_hashing" in keys


def test_find_matches_ripd_lgpd():
    matches = find_matches(
        "RIPD não elaborado",
        ["compliance:lgpd"],
    )
    keys = [m["key"] for m in matches]
    assert "compliance.ripd_structure" in keys


def test_find_matches_datajud_rate_limit():
    matches = find_matches(
        "rate limit DataJud não definido",
        ["integration:datajud"],
    )
    keys = [m["key"] for m in matches]
    assert "technical.datajud_rate_limit" in keys


def test_find_matches_no_hit_returns_empty():
    matches = find_matches("pergunta completamente genérica sem palavra-chave canônica xyz", [])
    assert matches == []


def test_infer_tags_juridico_civil():
    ocg = {
        "PROJECT_PROFILE": {"domain": "Automação Jurídica Assistida — processo civil", "deliverables": ["AJA"]},
        "STACK_RECOMMENDATION": {"backend": {"library": "sqlite"}},
    }
    tags = infer_project_context_tags(ocg)
    assert "domain:juridico" in tags
    assert "project_type:processo_civil" in tags
    assert "stack:sqlite" in tags


def test_infer_tags_empty_ocg():
    assert infer_project_context_tags(None) == []
    assert infer_project_context_tags({}) == []


def test_infer_tags_datajud_integration():
    ocg = {
        "PROJECT_PROFILE": {"domain": "advogados e processos judiciais. Integração DataJud CNJ."},
        "STACK_RECOMMENDATION": {},
    }
    tags = infer_project_context_tags(ocg)
    assert "integration:datajud" in tags


def _run_all():
    import inspect
    tests = [v for k, v in globals().items() if k.startswith("test_") and inspect.isfunction(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t(); passed += 1
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, f"assertion: {e}")); print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}")); print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*60}\nTotal: {len(tests)}  Passou: {passed}  Falhou: {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
