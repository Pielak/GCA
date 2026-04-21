# Codegen e linguagens suportadas

O GCA gera **scaffolds determinísticos** por linguagem/framework a partir de `OCG.STACK_RECOMMENDATION`. "Determinístico" quer dizer: mesma entrada → mesmos arquivos, sem dependência de LLM. O LLM continua sendo usado para código de negócio (módulos individuais), mas a estrutura inicial é garantida.

## 9 linguagens canonicamente suportadas

| Linguagem / Framework | Scaffolder | Migration | Observações |
|---|---|---|---|
| Java / Spring Boot | `scaffold_java_spring` | Flyway | Java 21, Maven. ddl-auto=validate. |
| Java / Quarkus | `scaffold_java_quarkus` | Flyway | Java 21, Maven. GraalVM-ready. |
| Kotlin / Spring Boot | `scaffold_kotlin_spring` | Flyway | Kotlin + Spring (Ktor fica como candidato futuro). |
| Go | `scaffold_go` | go-migrate | Go 1.22, chi/v5 router, pgx/v5 pra Postgres, go-redis/v9. |
| C# / ASP.NET Core | `scaffold_csharp_aspnet` | EF Core | .NET 8, WebAPI. |
| PHP / Laravel | `scaffold_php_laravel` | Laravel migrations | PHP 8.3, Eloquent. |
| Node.js / NestJS | `scaffold_nodejs_nestjs` | TypeORM | TypeScript, enterprise, mais opinionado. Default do ecossistema Node. |
| Node.js / Express | `scaffold_nodejs_express` | Knex | TypeScript, minimalista. |
| **C++ / CMake + GoogleTest** (MVP 16) | `scaffold_cpp_cmake` | — | C++17 baseline (whitelist 14/17/20/23); executable V1; GoogleTest via FetchContent; Dockerfile multi-stage (gcc:13 → debian:bookworm-slim). |

**Python fica em LLM-only** (sem scaffolder determinístico) — o ecossistema Python tem FastAPI/Django/Flask + Alembic já maduros, e scaffold por template tem menos valor vs deixar o LLM compor. O DDL (Alembic) é injetado mesmo quando a linguagem é Python.

## Dispatch (backend/app/services/scaffolders/dispatch.py)

```
OCG.STACK.backend.language  →  normalize  →  branch
  "Java"                        → "java"       → scaffold_java_spring | scaffold_java_quarkus
  "Kotlin"                      → "kotlin"     → scaffold_kotlin_spring
  "Go"                          → "go"         → scaffold_go
  "C#" | ".net" | "dotnet"      → "csharp"     → scaffold_csharp_aspnet
  "PHP"                         → "php"        → scaffold_php_laravel
  "Node.js" | "TypeScript"      → "node.js"    → scaffold_nodejs_nestjs | scaffold_nodejs_express
  "C++" | "cpp" | "cplusplus"   → "c++"        → scaffold_cpp_cmake             (MVP 16)
  outros (Python, Rust, Ruby)   → None (LLM-only)
```

## DDL generator (MVP 10 DT-076)

A partir de `OCG.DATA_MODEL` (inferido automaticamente em MVP 10 Fase 10.1 se o agente não popula), o generator emite:

- **schema.sql** com CREATE TABLE + FKs + índices em dialeto nativo.
- **seed.sql** com INSERTs idempotentes (ON CONFLICT / INSERT IGNORE / etc).
- **Migration específica do framework** declarado na stack.

### 5 dialetos SQL suportados

- PostgreSQL (default, JSONB, TIMESTAMPTZ, UUID nativo)
- MySQL (JSON, TINYINT(1) para BOOLEAN, AUTO_INCREMENT)
- SQLite (tipos reduzidos, INTEGER PK)
- SQL Server (T-SQL com `IF OBJECT_ID`)
- Oracle (bloco `EXCEPTION` anônimo para idempotência)

### NoSQL

- **MongoDB**: `collections.json` com JSON Schema validators + `seed.js` com `updateOne({...}, {$setOnInsert}, {upsert: true})` + `createIndex` por índice declarado.

### 7 frameworks de migration

| Framework | Dialetos cobertos | Scaffolder alvo |
|---|---|---|
| Alembic | SQL todos | Python (quando futuro scaffolder Python existir) |
| Flyway | SQL todos | java_spring · java_quarkus · kotlin_spring |
| Knex | SQL todos | nodejs_express |
| TypeORM | SQL todos (+ Mongo via Cosmos) | nodejs_nestjs |
| EF Core | SQL todos (+ Mongo via Cosmos stub) | csharp_aspnet |
| Laravel | SQL menos Oracle | php_laravel |
| go-migrate | SQL todos | go_app |

Matriz completa: cada scaffolder SQL ganha schema.sql + seed.sql + migration nativa do framework. Mongo sai em TypeORM/EFCore como stub + recebe artefatos nativos (collections.json + seed.js) em `db/` independente do scaffolder escolhido.

## C++ Codegen (MVP 16 — cobertura V1)

Primeiro scaffolder **systems-level** do GCA. Arquivos emitidos:

```
CMakeLists.txt            # C++17, warnings estritos, CMake 3.14+
tests/CMakeLists.txt      # GoogleTest v1.14.0 via FetchContent
src/main.cpp              # Entrypoint executable V1
include/<target>/         # Diretório público de headers (vazio, .gitkeep)
tests/test_main.cpp       # Smoke TEST + fixture TEST_F
.clang-format             # Google Style + 4 espaços + 100 colunas
.clang-tidy               # bugprone, cert, cppcoreguidelines, modernize, performance
.gitignore                # Artefatos CMake + IDE + OS
.dockerignore             # Pula build/, _deps/, .git/
Dockerfile                # Multi-stage: gcc:13-bookworm → debian:bookworm-slim (non-root user)
README.md                 # Comandos build, test, docker, padrões
```

### Slug translation

`demo-app` vira target `demo_app` (CMake não aceita hífen em `project()`). Include dir usa target name: `include/demo_app/`, não `include/demo-app/`.

### cpp_standard whitelist

`OCG.STACK.backend.cpp_standard` aceita apenas `{ "14", "17", "20", "23" }`. Qualquer outro valor (número, string inválida, ausência) cai no default **"17"**.

### CI step

`backend-tests.yml` ganha job `cpp-scaffold-compile` que:

1. Materializa o scaffold em `/tmp/cpp_smoke` via Python.
2. Roda `docker run gcc:13-bookworm bash -c 'apt-get install cmake ninja-build && cmake -G Ninja -B build -DBUILD_TESTING=OFF && cmake --build build -j && ./build/bin/<target>'`.
3. Valida binariamente que o scaffold compila.

### Test spec generator GoogleTest-aware (MVP 16 Fase 16.3)

Quando `OCG.STACK.backend.language` é C++, o `test_spec_generator_service` anexa `CPP_GOOGLETEST_GUIDANCE` ao prompt LLM com idioms canônicos:

- `TEST(SuiteName, TestName)` / `TEST_F(FixtureClass, TestName)` com fixture `class XxxFixture : public ::testing::Test` + `SetUp()` / `TearDown()`.
- Assertivas canônicas: `EXPECT_EQ`, `EXPECT_NE`, `EXPECT_TRUE`, `EXPECT_FALSE`, `EXPECT_THROW`, `EXPECT_THAT` com matchers GMock.
- `ASSERT_*` apenas quando falha invalida o resto do teste.
- `GTEST_SKIP() << "motivo"` para cenários não suportados.
- Integração CMake: `add_executable(<target>_tests ...)` + `target_link_libraries(... GTest::gtest_main)` + `gtest_discover_tests(...)`.

Provenance JSON inclui `test_framework: "googletest"` quando aplicável.

### Fora de escopo V1 (backlog parked)

- **CI matrix multi-compiler** (gcc × clang × msvc) — MVP 17 Cluster B potencial.
- **Sanitizers automáticos** (ASan, UBSan, TSan, MSan) — idem.
- **Doxygen** integrado ao LiveDocs — idem.
- **CPack** (.deb / .rpm / .msi) — Cluster C.
- **Export macros ABI** (PIMPL, visibility) — Cluster C.
- **Embedded** (ARM Cortex-M, ESP32) e **GPU** (CUDA, HIP, SYCL) — Cluster D (parked).
- **vcpkg / conan** como package managers — V2.
- **Library / header-only / shared artifacts** — V2 (V1 cobre só executable).
- **Questionário C++ expandido** (Q-cpp-*: artifact_type, target_platforms, package_manager) — V2.

Gap completo mapeado em `gca_cpp_codegen_gap.md` (memória da sessão 24).

## Regras duras de CodeGen

- **Docstrings obrigatórias** em todo código gerado.
- **Teste funcional + massa de dados** por arquivo gerado (contrato §CODEGEN_RULES).
- **Preview antes do commit** (CodeGen nunca escreve direto no Git sem aprovação explícita).
- **Commit com mensagem canônica** formato Conventional Commits.
- **RBAC**: `code:write` requerido (Dev e GP; Admin via override).
- **Análise de adequação do provedor** antes de alta criticidade — modelo local não consolida nem decide arquitetura sozinho.
- **Eventos emitidos**: `CODEGEN_SCAFFOLD_GENERATED`, `CODEGEN_SCAFFOLD_APPLIED`, `CODEGEN_FILE_REGENERATED`.

## Ver também

- [OCG — STACK_RECOMMENDATION + DATA_MODEL](?section=05-ocg)
- [Pipeline canônico](?section=04-pipeline)
- [Troubleshooting](?section=10-troubleshooting) — quando scaffolder retorna None (linguagem não coberta).
