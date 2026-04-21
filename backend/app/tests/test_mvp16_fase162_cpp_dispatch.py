"""MVP 16 Fase 16.2 — LinguagemBackend.CPP + dispatch + cpp_standard.

Valida:
- Enum `LinguagemBackend` inclui `CPP = "C++"`.
- `ScaffoldSpec.cpp_standard` novo campo opcional.
- `dispatch_scaffold` despacha `language in {c++, cpp, cplusplus}` para
  `scaffold_cpp_cmake`.
- `_build_spec` propaga `backend.cpp_standard` do OCG.STACK.
- Fallback do scaffolder: valor inválido ou ausente → "17".
- Whitelist canônica: apenas "14", "17", "20", "23" são aceitos.
"""
from app.services.scaffolders import (
    ScaffoldFile,
    ScaffoldSpec,
    dispatch_scaffold,
    scaffold_cpp_cmake,
)
from app.schemas.questionnaire import LinguagemBackend


def _by_path(files, path: str) -> ScaffoldFile:
    for f in files:
        if f.path == path:
            return f
    raise AssertionError(f"Não gerado: {path}. Gerados: {[f.path for f in files]}")


# ===========================================================================
# Enum LinguagemBackend
# ===========================================================================

def test_linguagem_backend_enum_includes_cpp():
    assert LinguagemBackend.CPP == "C++"
    assert "C++" in {e.value for e in LinguagemBackend}


def test_linguagem_backend_enum_preserves_existing_members():
    # Guard-rail: Fase 16.2 não deve remover nenhum membro existente.
    existing = {"Python", "Node.js", "Java", "C#", "Go", "PHP", "Kotlin", "Outra"}
    enum_values = {e.value for e in LinguagemBackend}
    for v in existing:
        assert v in enum_values, f"Membro removido acidentalmente: {v}"


# ===========================================================================
# ScaffoldSpec.cpp_standard
# ===========================================================================

def test_scaffold_spec_has_cpp_standard_field_optional():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    # Campo existe e default é None (scaffolder decide fallback).
    assert spec.cpp_standard is None


def test_scaffold_spec_accepts_cpp_standard():
    spec = ScaffoldSpec(
        project_name="X", project_slug="x", package="com.gca.x",
        cpp_standard="20",
    )
    assert spec.cpp_standard == "20"


# ===========================================================================
# dispatch_scaffold — branches C++
# ===========================================================================

def test_dispatch_language_cpp_returns_cpp_cmake():
    stack = {"backend": {"language": "C++"}}
    result = dispatch_scaffold(stack, "Demo", "demo-cpp")
    assert result is not None
    name, files = result
    assert name == "cpp_cmake"
    assert any(f.path == "CMakeLists.txt" for f in files)


def test_dispatch_language_cpp_lowercase_also_works():
    stack = {"backend": {"language": "c++"}}
    result = dispatch_scaffold(stack, "Demo", "demo-cpp")
    assert result is not None
    name, _ = result
    assert name == "cpp_cmake"


def test_dispatch_language_cpp_alias_cpp():
    stack = {"backend": {"language": "cpp"}}
    result = dispatch_scaffold(stack, "Demo", "demo-cpp")
    assert result is not None
    name, _ = result
    assert name == "cpp_cmake"


def test_dispatch_language_cpp_alias_cplusplus():
    stack = {"backend": {"language": "cplusplus"}}
    result = dispatch_scaffold(stack, "Demo", "demo-cpp")
    assert result is not None
    name, _ = result
    assert name == "cpp_cmake"


def test_dispatch_language_unknown_still_returns_none():
    # Guard-rail: Fase 16.2 não altera comportamento para linguagens não
    # cobertas (rust, ruby, swift, etc).
    for lang in ("rust", "ruby", "swift", "zig"):
        stack = {"backend": {"language": lang}}
        result = dispatch_scaffold(stack, "Demo", "demo")
        assert result is None, f"Regressão: {lang} virou scaffoldable inesperadamente"


# ===========================================================================
# cpp_standard propagation via dispatch
# ===========================================================================

def test_dispatch_propagates_cpp_standard_from_stack():
    stack = {"backend": {"language": "C++", "cpp_standard": "20"}}
    _, files = dispatch_scaffold(stack, "Demo", "demo-cpp")
    cmake = _by_path(files, "CMakeLists.txt").content
    assert "set(CMAKE_CXX_STANDARD 20)" in cmake


def test_dispatch_uses_default_when_cpp_standard_absent():
    stack = {"backend": {"language": "C++"}}
    _, files = dispatch_scaffold(stack, "Demo", "demo-cpp")
    cmake = _by_path(files, "CMakeLists.txt").content
    assert "set(CMAKE_CXX_STANDARD 17)" in cmake


def test_dispatch_rejects_invalid_cpp_standard_and_falls_back():
    # Whitelist: só 14/17/20/23. "11" (obsoleto), "99" (inventado),
    # "17 " (espaço) seguem o fallback para 17.
    stack = {"backend": {"language": "C++", "cpp_standard": "99"}}
    _, files = dispatch_scaffold(stack, "Demo", "demo-cpp")
    cmake = _by_path(files, "CMakeLists.txt").content
    assert "set(CMAKE_CXX_STANDARD 17)" in cmake
    assert "set(CMAKE_CXX_STANDARD 99)" not in cmake


def test_dispatch_accepts_all_canonical_standards():
    for std in ("14", "17", "20", "23"):
        stack = {"backend": {"language": "C++", "cpp_standard": std}}
        _, files = dispatch_scaffold(stack, "Demo", "demo-cpp")
        cmake = _by_path(files, "CMakeLists.txt").content
        assert f"set(CMAKE_CXX_STANDARD {std})" in cmake


def test_dispatch_ignores_non_string_cpp_standard():
    """Se o LLM emitir `cpp_standard: 20` (int) em vez de "20" (str),
    `_build_spec` deve ignorar e cair no default."""
    stack = {"backend": {"language": "C++", "cpp_standard": 20}}
    _, files = dispatch_scaffold(stack, "Demo", "demo-cpp")
    cmake = _by_path(files, "CMakeLists.txt").content
    assert "set(CMAKE_CXX_STANDARD 17)" in cmake


# ===========================================================================
# Direct scaffolder behavior (independent of dispatch)
# ===========================================================================

def test_scaffolder_direct_respects_cpp_standard():
    spec = ScaffoldSpec(
        project_name="X", project_slug="x", package="com.gca.x",
        cpp_standard="23",
    )
    files = scaffold_cpp_cmake(spec)
    cmake = _by_path(files, "CMakeLists.txt").content
    assert "set(CMAKE_CXX_STANDARD 23)" in cmake


def test_scaffolder_direct_readme_reflects_cpp_standard():
    spec = ScaffoldSpec(
        project_name="X", project_slug="x", package="com.gca.x",
        cpp_standard="20",
    )
    readme = _by_path(scaffold_cpp_cmake(spec), "README.md").content
    assert "C++20" in readme


# ===========================================================================
# Regressão das 8 linguagens já cobertas (guard-rail)
# ===========================================================================

def test_existing_scaffolders_unaffected_by_fase_162():
    """Fase 16.2 é aditiva — não muda nenhuma das 8 linguagens prévias."""
    cases = [
        ({"backend": {"language": "Java", "framework": "Spring"}}, "java_spring"),
        ({"backend": {"language": "Java", "framework": "Quarkus"}}, "java_quarkus"),
        ({"backend": {"language": "Kotlin"}}, "kotlin_spring"),
        ({"backend": {"language": "Go"}}, "go_app"),
        ({"backend": {"language": "C#"}}, "csharp_aspnet"),
        ({"backend": {"language": "PHP"}}, "php_laravel"),
        ({"backend": {"language": "Node.js", "framework": "NestJS"}}, "nodejs_nestjs"),
        ({"backend": {"language": "Node.js", "framework": "Express"}}, "nodejs_express"),
    ]
    for stack, expected_name in cases:
        result = dispatch_scaffold(stack, "X", "x")
        assert result is not None, f"Stack {stack} perdeu dispatch"
        name, _ = result
        assert name == expected_name, f"{stack} → {name}, esperado {expected_name}"
