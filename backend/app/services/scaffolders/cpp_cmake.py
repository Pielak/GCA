"""MVP 16 Fase 16.1 — Scaffolder C++ (CMake + GoogleTest).

Gera estrutura inicial de um projeto C++ moderno com CMake. Não chama
LLM. Primeiro scaffolder C++ do GCA (DT-C++-1 do `gca_cpp_codegen_gap.md`).

Layout produzido:
    CMakeLists.txt
    .clang-format
    .clang-tidy
    .gitignore
    .dockerignore
    Dockerfile
    README.md
    src/main.cpp
    include/<project_slug>/.gitkeep
    tests/CMakeLists.txt
    tests/test_main.cpp

Decisões:
- C++17 (default baseline — V2 permitirá C++20/23 via Q-cpp-* no questionário).
- CMake 3.14+ (FetchContent estabilizado).
- GoogleTest via FetchContent (sem submodule, sem vcpkg/conan em V1).
- Artefato V1: executável apenas (library/header-only ficam para MVP 17).
- Padrões de compilação: -Wall -Wextra -Wpedantic (GCC/Clang) ou /W4 (MSVC).
- Dockerfile multi-stage: builder (`gcc:13`) + runner (`debian:bookworm-slim`).
- `.clang-format` + `.clang-tidy` emitidos mas não obrigados pelo build (MVP 17
  Cluster B transforma em gate).

Não gera:
- vcpkg.json/conanfile.txt (V2 via questionário expandido).
- CI matrix multi-compiler (MVP 17 Cluster B).
- CPack/packaging (.deb/.rpm/.msi — MVP 17 Cluster C).
- Doxygen Doxyfile (MVP 17 Cluster B).
"""
from typing import List

from .types import ScaffoldFile, ScaffoldSpec


_CPP_STANDARD_DEFAULT = "17"
_CMAKE_MIN_VERSION = "3.14"
_GOOGLETEST_TAG = "v1.14.0"


def _cmake_target_name(spec: ScaffoldSpec) -> str:
    """`demo-app` → `demo_app` (CMake prefere underscore)."""
    return spec.project_slug.replace("-", "_")


def _include_dir(spec: ScaffoldSpec) -> str:
    """`demo-app` → `include/demo_app` (header dir canônico)."""
    return f"include/{_cmake_target_name(spec)}"


def _cmakelists(spec: ScaffoldSpec) -> str:
    target = _cmake_target_name(spec)
    return f"""# Auto-gerado pelo GCA — raiz do projeto. [gca:auto]
cmake_minimum_required(VERSION {_CMAKE_MIN_VERSION})
project({target} VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD {_CPP_STANDARD_DEFAULT})
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Pastas de output previsíveis (facilita Dockerfile + CI).
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${{CMAKE_BINARY_DIR}}/bin)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${{CMAKE_BINARY_DIR}}/lib)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${{CMAKE_BINARY_DIR}}/lib)

# Flags de compilação — warnings estritos por padrão.
if(MSVC)
    add_compile_options(/W4 /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Target principal do app.
add_executable({target}
    src/main.cpp
)
target_include_directories({target} PUBLIC ${{CMAKE_SOURCE_DIR}}/include)

# Testes habilitados só se o usuário pedir (-DBUILD_TESTING=ON, default ON).
option(BUILD_TESTING "Build tests with GoogleTest" ON)
if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()
"""


def _tests_cmakelists(spec: ScaffoldSpec) -> str:
    target = _cmake_target_name(spec)
    return f"""# Auto-gerado pelo GCA — tests via GoogleTest/FetchContent. [gca:auto]
include(FetchContent)

FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        {_GOOGLETEST_TAG}
)
# Windows: força MSVC runtime compatível com o do projeto.
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

add_executable({target}_tests
    test_main.cpp
)
target_link_libraries({target}_tests PRIVATE GTest::gtest_main)
target_include_directories({target}_tests PRIVATE ${{CMAKE_SOURCE_DIR}}/include)

include(GoogleTest)
gtest_discover_tests({target}_tests)
"""


def _main_cpp(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — entrypoint. [gca:auto]
#include <iostream>

int main(int argc, char** argv) {{
    (void)argc;
    (void)argv;
    std::cout << "{spec.project_name} — scaffold C++ inicial do GCA." << std::endl;
    return 0;
}}
"""


def _test_main_cpp(spec: ScaffoldSpec) -> str:
    target = _cmake_target_name(spec)
    return f"""// Auto-gerado pelo GCA — smoke test GoogleTest. [gca:auto]
#include <gtest/gtest.h>

// Smoke: garante que o link contra GoogleTest funciona.
TEST({target}_smoke, gtest_link) {{
    EXPECT_EQ(1 + 1, 2);
}}

// Exemplo de fixture — substitua por testes do domínio do seu projeto.
class {target}_Fixture : public ::testing::Test {{
protected:
    void SetUp() override {{}}
    void TearDown() override {{}}
}};

TEST_F({target}_Fixture, placeholder) {{
    EXPECT_TRUE(true);
}}
"""


def _clang_format() -> str:
    return """# Auto-gerado pelo GCA — formatação canônica C++. [gca:auto]
# Baseado em Google Style com ajustes mínimos. Rode: clang-format -i <arquivo>
BasedOnStyle: Google
IndentWidth: 4
TabWidth: 4
UseTab: Never
ColumnLimit: 100
AllowShortFunctionsOnASingleLine: Empty
DerivePointerAlignment: false
PointerAlignment: Left
"""


def _clang_tidy() -> str:
    return """# Auto-gerado pelo GCA — checks canônicos C++. [gca:auto]
# Rode: clang-tidy -p build src/*.cpp
# MVP 17 Cluster B transformará em gate de CI; V1 é só sugestão.
Checks: >
    bugprone-*,
    cert-*,
    clang-analyzer-*,
    cppcoreguidelines-*,
    modernize-*,
    performance-*,
    readability-*,
    -modernize-use-trailing-return-type,
    -readability-magic-numbers,
    -cppcoreguidelines-avoid-magic-numbers
WarningsAsErrors: ''
HeaderFilterRegex: 'include/.*'
FormatStyle: file
"""


def _gitignore_cpp() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
# Build directories
build/
build-*/
cmake-build-*/
out/

# CMake cache
CMakeCache.txt
CMakeFiles/
CMakeScripts/
Testing/
Makefile
cmake_install.cmake
install_manifest.txt
compile_commands.json
CTestTestfile.cmake
_deps/

# Object / binary
*.o
*.obj
*.ko
*.elf
*.exe
*.out
*.app
*.i*86
*.x86_64
*.hex

# Precompiled headers
*.gch
*.pch

# Libraries
*.lib
*.a
*.la
*.lo
*.dll
*.so
*.so.*
*.dylib

# Debug files
*.dSYM/
*.su
*.idb
*.pdb

# Kernel module compile results
*.mod*
*.cmd
.tmp_versions/
modules.order
Module.symvers
Mkfile.old
dkms.conf

# IDE
.idea/
.vscode/
.vs/
*.swp
*.swo
*~
.cache/

# OS
.DS_Store
Thumbs.db
"""


def _dockerignore_cpp() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
.git/
.gitignore
.idea/
.vscode/
build/
build-*/
cmake-build-*/
out/
_deps/
*.o
*.obj
*.exe
README.md
Dockerfile
.dockerignore
"""


def _dockerfile(spec: ScaffoldSpec) -> str:
    target = _cmake_target_name(spec)
    return f"""# Auto-gerado pelo GCA — multi-stage build C++. [gca:auto]
# Stage 1 — builder com GCC 13 + CMake.
FROM gcc:13-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \\
        cmake \\
        ninja-build \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY CMakeLists.txt ./
COPY src ./src
COPY include ./include
COPY tests ./tests

# Build sem testes no stage de produção (testes rodam em outro job no CI).
RUN cmake -G Ninja -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \\
 && cmake --build build -j "$(nproc)"

# Stage 2 — runner mínimo.
FROM debian:bookworm-slim AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \\
        libstdc++6 \\
        ca-certificates \\
    && rm -rf /var/lib/apt/lists/* \\
    && useradd -r -u 10001 -s /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /build/build/bin/{target} /app/{target}
USER app

ENTRYPOINT ["/app/{target}"]
"""


def _readme(spec: ScaffoldSpec) -> str:
    target = _cmake_target_name(spec)
    return f"""# {spec.project_name}

> Scaffold inicial **C++ / CMake / GoogleTest** gerado pelo GCA (MVP 16
> Fase 16.1). Edite normalmente — apenas arquivos com cabeçalho
> `[gca:auto]` podem ser sobrescritos em regenerações futuras.

## Stack

- C++{_CPP_STANDARD_DEFAULT} (padrão baseline)
- CMake {_CMAKE_MIN_VERSION}+
- GoogleTest {_GOOGLETEST_TAG} (via FetchContent; sem vcpkg/conan em V1)
- Artefato V1: **executável** (`{target}`). Biblioteca/header-only ficam para V2.

## Como compilar

```bash
cmake -B build
cmake --build build -j
./build/bin/{target}
```

## Como testar

```bash
cmake -B build -DBUILD_TESTING=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
```

## Docker

```bash
docker build -t {target} .
docker run --rm {target}
```

## Layout

```
CMakeLists.txt         # entry do build
src/main.cpp           # entrypoint
include/{target}/      # headers públicos (adicione os seus aqui)
tests/                 # testes GoogleTest
.clang-format          # formatação canônica (clang-format -i)
.clang-tidy            # checks sugeridos (clang-tidy -p build src/*.cpp)
Dockerfile             # multi-stage (gcc:13 builder + debian runner)
```

## Padrões

- Warnings: `-Wall -Wextra -Wpedantic` (GCC/Clang) ou `/W4 /permissive-` (MSVC).
- Formatação: `clang-format` BasedOnStyle Google com 4 espaços, 100 colunas.
- Checks: `clang-tidy` com bugprone/cert/cppcoreguidelines/modernize/performance.
  V1 é só sugestão — MVP 17 Cluster B transforma em gate de CI.

## Próximos passos

- Adicione seus headers em `include/{target}/` e implementações em `src/`.
- Troque o target de executável para `add_library({target} ...)` quando
  for biblioteca (isso vira ajuste manual em V1; MVP 17 automatiza).
- CI multi-compiler matrix (gcc × clang × msvc) vem no MVP 17 Cluster B.
- Packaging CPack (.deb/.rpm/.msi) vem no MVP 17 Cluster C.
"""


def scaffold_cpp_cmake(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial de projeto C++ com CMake + GoogleTest.

    MVP 16 Fase 16.1 — cobertura V1: executable, C++17, GCC/Clang/MSVC,
    GoogleTest via FetchContent. Sem library/header-only, sem vcpkg/conan,
    sem CI matrix, sem packaging, sem Doxygen (todos ficam para MVP 17).
    """
    include_dir = _include_dir(spec)
    return [
        ScaffoldFile("CMakeLists.txt", _cmakelists(spec)),
        ScaffoldFile(".clang-format", _clang_format()),
        ScaffoldFile(".clang-tidy", _clang_tidy()),
        ScaffoldFile(".gitignore", _gitignore_cpp()),
        ScaffoldFile(".dockerignore", _dockerignore_cpp()),
        ScaffoldFile("Dockerfile", _dockerfile(spec)),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile("src/main.cpp", _main_cpp(spec)),
        # Gitkeep pro diretório de headers ficar rastreado mesmo vazio.
        ScaffoldFile(f"{include_dir}/.gitkeep", ""),
        ScaffoldFile("tests/CMakeLists.txt", _tests_cmakelists(spec)),
        ScaffoldFile("tests/test_main.cpp", _test_main_cpp(spec)),
    ]
