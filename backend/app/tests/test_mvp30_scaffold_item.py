"""MVP 30 — Testes unit standalone dos prompt builders do scaffold.

Cobre: build_plan_prompt, build_item_prompt. Sem DB, sem pytest fixtures
(respeita DT-034). Rodar: `python -m app.tests.test_mvp30_scaffold_item`.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.scaffold_planner import build_plan_prompt, build_item_prompt


def test_plan_prompt_contains_project_name():
    p = build_plan_prompt(
        project_name="X", project_slug="x", project_description="desc",
        stack={"backend": {"framework": "FastAPI"}}, architecture={},
        modules=[], arguider_modules=[],
    )
    assert "X" in p
    assert "FastAPI" in p


def test_plan_prompt_has_json_format_instruction():
    p = build_plan_prompt(
        project_name="P", project_slug="p", project_description=None,
        stack={}, architecture={}, modules=[], arguider_modules=[],
    )
    assert '"items"' in p
    assert '"summary"' in p
    assert "APENAS JSON" in p


def test_plan_prompt_accepts_none_description():
    p = build_plan_prompt(
        project_name="P", project_slug="p", project_description=None,
        stack={}, architecture={}, modules=[], arguider_modules=[],
    )
    assert "(não fornecida)" in p


def test_item_prompt_contains_path_and_purpose():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="src/main.py", item_purpose="entrypoint FastAPI",
        item_file_type="py", peer_paths=[],
    )
    assert "src/main.py" in p
    assert "entrypoint FastAPI" in p
    assert "py" in p


def test_item_prompt_lists_peers():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="a.py", item_purpose="x", item_file_type="py",
        peer_paths=["b.py", "c.py"],
    )
    assert "- b.py" in p
    assert "- c.py" in p


def test_item_prompt_includes_rnf_when_provided():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="a.py", item_purpose="x", item_file_type="py",
        peer_paths=[],
        rnf_contracts=[{"id": "RNF-01", "spec": "latency <100ms"}],
    )
    assert "RNF-01" in p
    assert "Contratos RNF" in p


def test_item_prompt_includes_design_tokens_for_frontend():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="App.tsx", item_purpose="root", item_file_type="tsx",
        peer_paths=[],
        design_tokens={"palette": {"primary": "#8B5CF6"}},
    )
    assert "#8B5CF6" in p
    assert "Design tokens" in p


def test_item_prompt_json_format_strict():
    p = build_item_prompt(
        project_name="P", project_slug="p",
        stack={}, architecture={},
        item_path="a.py", item_purpose="x", item_file_type="py",
        peer_paths=[],
    )
    assert '"content"' in p
    assert '"status"' in p
    assert "APENAS o JSON" in p


def _run_all():
    import inspect
    tests = [v for k, v in globals().items() if k.startswith("test_") and inspect.isfunction(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            failed.append((t.__name__, f"assertion: {e}"))
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*60}\nTotal: {len(tests)}  Passou: {passed}  Falhou: {len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run_all())
