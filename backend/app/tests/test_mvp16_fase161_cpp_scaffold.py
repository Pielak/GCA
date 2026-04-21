"""MVP 16 Fase 16.1 — testes do scaffolder C++ CMake.

Valida estrutura, paths, conteúdos mínimos, idempotência e conformidade
com as decisões documentadas em `cpp_cmake.py`:
- C++17 baseline
- GoogleTest via FetchContent (sem vcpkg/conan em V1)
- Executable V1 (sem library)
- Dockerfile multi-stage gcc:13 + debian:bookworm-slim
- Target CMake com underscore (slug `demo-app` → `demo_app`)
"""
from app.services.scaffolders import ScaffoldFile, ScaffoldSpec, scaffold_cpp_cmake


def _by_path(files, path: str) -> ScaffoldFile:
    for f in files:
        if f.path == path:
            return f
    raise AssertionError(f"Não gerado: {path}. Gerados: {[f.path for f in files]}")


# ===========================================================================
# Estrutura mínima
# ===========================================================================

def test_cpp_scaffold_emits_canonical_files():
    spec = ScaffoldSpec(project_name="DemoCpp", project_slug="demo-cpp", package="com.gca.demo")
    files = scaffold_cpp_cmake(spec)
    paths = {f.path for f in files}
    assert "CMakeLists.txt" in paths
    assert ".clang-format" in paths
    assert ".clang-tidy" in paths
    assert ".gitignore" in paths
    assert ".dockerignore" in paths
    assert "Dockerfile" in paths
    assert "README.md" in paths
    assert "src/main.cpp" in paths
    assert "include/demo_cpp/.gitkeep" in paths
    assert "tests/CMakeLists.txt" in paths
    assert "tests/test_main.cpp" in paths


def test_cpp_scaffold_count_matches_documented_layout():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_cpp_cmake(spec)
    # Layout documentado em cpp_cmake.py tem exatamente 11 arquivos.
    assert len(files) == 11


def test_cpp_scaffold_returns_scaffold_file_instances():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_cpp_cmake(spec)
    for f in files:
        assert isinstance(f, ScaffoldFile)
        assert isinstance(f.path, str) and len(f.path) > 0
        assert isinstance(f.content, str)


# ===========================================================================
# CMakeLists raiz
# ===========================================================================

def test_cmake_root_uses_cpp17_default():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "CMakeLists.txt").content
    assert "set(CMAKE_CXX_STANDARD 17)" in cmake
    assert "CMAKE_CXX_STANDARD_REQUIRED ON" in cmake
    assert "CMAKE_CXX_EXTENSIONS OFF" in cmake


def test_cmake_root_translates_slug_to_underscore_target():
    # `demo-app` deve virar target `demo_app` (CMake não aceita hífen em project()).
    spec = ScaffoldSpec(project_name="X", project_slug="demo-app", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "CMakeLists.txt").content
    assert "project(demo_app " in cmake
    assert "add_executable(demo_app" in cmake


def test_cmake_root_has_strict_warnings_per_compiler():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "CMakeLists.txt").content
    # MSVC branch
    assert "/W4" in cmake
    assert "/permissive-" in cmake
    # GCC/Clang branch
    assert "-Wall" in cmake
    assert "-Wextra" in cmake
    assert "-Wpedantic" in cmake


def test_cmake_root_gates_tests_via_build_testing_option():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "CMakeLists.txt").content
    assert 'option(BUILD_TESTING "Build tests with GoogleTest" ON)' in cmake
    assert "enable_testing()" in cmake
    assert "add_subdirectory(tests)" in cmake


def test_cmake_root_minimum_version_is_3_14():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "CMakeLists.txt").content
    assert "cmake_minimum_required(VERSION 3.14)" in cmake


# ===========================================================================
# CMakeLists de tests
# ===========================================================================

def test_tests_cmake_uses_fetchcontent_googletest():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "tests/CMakeLists.txt").content
    assert "FetchContent" in cmake
    assert "github.com/google/googletest.git" in cmake
    assert "v1.14.0" in cmake
    assert "GTest::gtest_main" in cmake


def test_tests_cmake_forces_msvc_shared_crt():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "tests/CMakeLists.txt").content
    assert "gtest_force_shared_crt" in cmake


def test_tests_cmake_uses_gtest_discover_tests():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "tests/CMakeLists.txt").content
    assert "gtest_discover_tests" in cmake


def test_tests_cmake_links_include_dir():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "tests/CMakeLists.txt").content
    assert "include" in cmake


# ===========================================================================
# src/main.cpp
# ===========================================================================

def test_main_cpp_compiles_minimal_structure():
    spec = ScaffoldSpec(project_name="DemoX", project_slug="demo-x", package="com.gca.x")
    main = _by_path(scaffold_cpp_cmake(spec), "src/main.cpp").content
    assert "#include <iostream>" in main
    assert "int main(int argc, char** argv)" in main
    assert "return 0;" in main
    # Suppression de argc/argv evita warning -Wunused-parameter
    assert "(void)argc;" in main
    assert "(void)argv;" in main
    # Project name no output
    assert "DemoX" in main


# ===========================================================================
# tests/test_main.cpp
# ===========================================================================

def test_test_main_cpp_has_smoke_and_fixture():
    spec = ScaffoldSpec(project_name="X", project_slug="demo-x", package="com.gca.x")
    t = _by_path(scaffold_cpp_cmake(spec), "tests/test_main.cpp").content
    assert "#include <gtest/gtest.h>" in t
    # Smoke TEST macro com nome baseado no target (underscore)
    assert "TEST(demo_x_smoke, gtest_link)" in t
    # Fixture com TEST_F
    assert "class demo_x_Fixture : public ::testing::Test" in t
    assert "TEST_F(demo_x_Fixture, placeholder)" in t


# ===========================================================================
# Dockerfile
# ===========================================================================

def test_dockerfile_multi_stage():
    spec = ScaffoldSpec(project_name="X", project_slug="demo-x", package="com.gca.x")
    df = _by_path(scaffold_cpp_cmake(spec), "Dockerfile").content
    assert "FROM gcc:13-bookworm AS builder" in df
    assert "FROM debian:bookworm-slim AS runner" in df
    assert "COPY --from=builder" in df
    # Build Release + sem testes no stage prod
    assert "-DCMAKE_BUILD_TYPE=Release" in df
    assert "-DBUILD_TESTING=OFF" in df
    # Target com underscore
    assert "/app/demo_x" in df
    # Usuário não-root
    assert "useradd -r -u 10001" in df
    assert "USER app" in df


def test_dockerfile_installs_cmake_and_ninja_in_builder():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    df = _by_path(scaffold_cpp_cmake(spec), "Dockerfile").content
    assert "cmake" in df
    assert "ninja-build" in df


def test_dockerignore_excludes_build_dirs():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    di = _by_path(scaffold_cpp_cmake(spec), ".dockerignore").content
    assert "build/" in di
    assert ".git/" in di
    assert "_deps/" in di


# ===========================================================================
# Configs de código (.clang-format, .clang-tidy, .gitignore)
# ===========================================================================

def test_clang_format_based_on_google():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    cf = _by_path(scaffold_cpp_cmake(spec), ".clang-format").content
    assert "BasedOnStyle: Google" in cf
    assert "ColumnLimit: 100" in cf
    assert "IndentWidth: 4" in cf


def test_clang_tidy_enables_canonical_checks():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    ct = _by_path(scaffold_cpp_cmake(spec), ".clang-tidy").content
    assert "bugprone-" in ct
    assert "cppcoreguidelines-" in ct
    assert "modernize-" in ct
    assert "performance-" in ct


def test_gitignore_ignores_cmake_artifacts():
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    gi = _by_path(scaffold_cpp_cmake(spec), ".gitignore").content
    assert "build/" in gi
    assert "CMakeCache.txt" in gi
    assert "CMakeFiles/" in gi
    assert "_deps/" in gi
    assert "compile_commands.json" in gi


# ===========================================================================
# README
# ===========================================================================

def test_readme_has_build_instructions():
    spec = ScaffoldSpec(project_name="DemoProj", project_slug="demo-proj", package="com.gca.x")
    readme = _by_path(scaffold_cpp_cmake(spec), "README.md").content
    assert "DemoProj" in readme
    assert "cmake -B build" in readme
    assert "ctest" in readme
    assert "docker build" in readme
    # Target com underscore
    assert "demo_proj" in readme


# ===========================================================================
# Idempotência e marcadores [gca:auto]
# ===========================================================================

def test_scaffold_is_idempotent():
    """Duas chamadas com o mesmo spec retornam exatamente o mesmo conteúdo."""
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files_a = scaffold_cpp_cmake(spec)
    files_b = scaffold_cpp_cmake(spec)
    assert len(files_a) == len(files_b)
    for a, b in zip(files_a, files_b):
        assert a.path == b.path
        assert a.content == b.content


def test_gca_auto_markers_in_generated_files():
    """Arquivos principais devem carregar `[gca:auto]` pra sinalizar
    que podem ser sobrescritos em regenerações futuras."""
    spec = ScaffoldSpec(project_name="X", project_slug="x", package="com.gca.x")
    files = scaffold_cpp_cmake(spec)
    expected_auto = {
        "CMakeLists.txt",
        "tests/CMakeLists.txt",
        "src/main.cpp",
        "tests/test_main.cpp",
        "Dockerfile",
        ".clang-format",
        ".clang-tidy",
        ".gitignore",
        ".dockerignore",
    }
    for f in files:
        if f.path in expected_auto:
            assert "[gca:auto]" in f.content, f"Falta [gca:auto] em {f.path}"


# ===========================================================================
# Slug → target translation
# ===========================================================================

def test_slug_without_hyphens_is_preserved_as_target():
    spec = ScaffoldSpec(project_name="X", project_slug="simple", package="com.gca.x")
    cmake = _by_path(scaffold_cpp_cmake(spec), "CMakeLists.txt").content
    assert "project(simple " in cmake
    assert "add_executable(simple" in cmake


def test_include_dir_uses_target_name_not_slug():
    """Include dir deve refletir o target (underscore), não o slug (hífen)."""
    spec = ScaffoldSpec(project_name="X", project_slug="multi-word-app", package="com.gca.x")
    files = scaffold_cpp_cmake(spec)
    paths = {f.path for f in files}
    assert "include/multi_word_app/.gitkeep" in paths
    # Não deve gerar a versão com hífen.
    assert "include/multi-word-app/.gitkeep" not in paths
