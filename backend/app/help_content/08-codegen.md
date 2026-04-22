# Codegen e linguagens suportadas

O GCA gera **scaffolds iniciais** (estrutura do projeto) a partir do `STACK_RECOMMENDATION` do OCG. Cada linguagem/framework tem um template determinístico — mesma entrada do OCG sempre gera os mesmos arquivos. Isso garante que o scaffold funcione independente do modelo de IA configurado.

O LLM continua responsável pelo código de negócio (módulos individuais); a estrutura inicial (arquivos de build, configs, entrypoint) vem de template determinístico.

## 8 linguagens canônicas · 9 scaffolders determinísticos

No enum `LinguagemBackend` o produto aceita **8 linguagens canônicas**: Python, Node.js, Java, C#, Go, PHP, Kotlin, C++ (mais `Outra` pra projetos LLM-only em linguagem não listada). Para a escolha de backend, Java e Node.js têm 2 frameworks cada, resultando em **9 scaffolders determinísticos**:

| Linguagem / Framework | Framework de migration | Observações |
|---|---|---|
| Java + Spring Boot | Flyway | Java 21, Maven, `ddl-auto=validate` |
| Java + Quarkus | Flyway | Java 21, Maven, pronto para GraalVM |
| Kotlin + Spring Boot | Flyway | Kotlin + Spring |
| Go | go-migrate | Go 1.22, chi/v5 router, pgx/v5 para Postgres, go-redis/v9 |
| C# + ASP.NET Core | EF Core | .NET 8, WebAPI |
| PHP + Laravel | Laravel migrations | PHP 8.3, Eloquent |
| Node.js + NestJS | TypeORM | TypeScript, enterprise, mais opinionado |
| Node.js + Express | Knex | TypeScript, minimalista |
| **C++ + CMake + GoogleTest** | — | C++17 baseline (permitido 14/17/20/23); executable; Dockerfile multi-stage (gcc:13 → debian:bookworm-slim). Adicionado no MVP 16 como 9ª linguagem de codegen. |

**Python fica em LLM-only** — o GCA não gera scaffold determinístico para Python. O ecossistema tem FastAPI, Django e Flask maduros, e template determinístico tem menos valor aí. O DDL (Alembic) é injetado mesmo em projetos Python.

**Expansão futura:** novas linguagens (Rust, Swift, Scala, Cobol) e saídas no-code (workflows n8n, Bubble, Retool) entram no GCA via o mesmo padrão de scaffolder — cada adapter novo custa ~2-3d de desenvolvimento.

## Como o GCA escolhe o scaffolder

O dispatcher olha `OCG.STACK.backend.language` e normaliza:

- `"Java"` → `java`
- `"Kotlin"` → `kotlin`
- `"Go"` → `go`
- `"C#" | ".net" | "dotnet"` → `csharp`
- `"PHP"` → `php`
- `"Node.js" | "TypeScript" | "JavaScript"` → `node.js`
- `"C++" | "cpp" | "cplusplus"` → `c++`
- Outros (Python, Rust, Ruby, Swift, etc) → sem scaffolder (cai no LLM-only)

Para Java e Node.js, o framework declarado (`STACK.backend.framework`) escolhe qual variante:

- Java + "quarkus" → Quarkus; senão → Spring Boot.
- Node.js + "express" sem "nest" → Express; senão → NestJS.

## DDL generator — 5 dialetos SQL + MongoDB

O GCA gera DDL automaticamente a partir do `DATA_MODEL` do OCG. Se o OCG não tiver um `DATA_MODEL` explícito, o Consolidator infere um a partir do perfil do projeto e da stack.

Cada scaffolder recebe o `DATA_MODEL` junto e injeta os artefatos em `db/`:

### Dialetos SQL

- **PostgreSQL** — JSONB, TIMESTAMPTZ, UUID nativo, `ON CONFLICT DO NOTHING` no seed.
- **MySQL** — JSON, `TINYINT(1)` para BOOLEAN, `AUTO_INCREMENT`, `INSERT IGNORE` no seed.
- **SQLite** — tipos reduzidos, `INTEGER PRIMARY KEY`, `INSERT OR IGNORE` no seed.
- **SQL Server** — T-SQL com `IF OBJECT_ID` para idempotência.
- **Oracle** — bloco anônimo com `EXCEPTION` tolerando `ORA-00955` (tabela já existe).

### NoSQL

- **MongoDB** — emite `collections.json` com validators (JSON Schema) + `seed.js` com `updateOne({...}, {$setOnInsert}, {upsert: true})` + `createIndex` por índice declarado.

### Frameworks de migration gerados

| Framework | Cobertura | Scaffolder que consome |
|---|---|---|
| Alembic | Todos SQL | Python (quando houver scaffolder Python) |
| Flyway | Todos SQL | Java Spring, Java Quarkus, Kotlin Spring |
| Knex | Todos SQL | Node.js Express |
| TypeORM | Todos SQL + Mongo (Cosmos stub) | Node.js NestJS |
| EF Core | Todos SQL + Mongo (Cosmos stub) | C# ASP.NET |
| Laravel | SQL menos Oracle | PHP Laravel |
| go-migrate | Todos SQL | Go |

Cada scaffolder SQL recebe: `db/schema.sql` + `db/seed.sql` + a migration nativa do framework. Mongo emite os artefatos nativos em `db/` independente do scaffolder escolhido.

## Scaffolder C++ em detalhe

### Arquivos emitidos

```
CMakeLists.txt             # C++17, warnings estritos, CMake 3.14+
tests/CMakeLists.txt       # GoogleTest via FetchContent (sem vcpkg/conan em V1)
src/main.cpp               # Entrypoint executable
include/<target>/          # Diretório para headers públicos (vem vazio, com .gitkeep)
tests/test_main.cpp        # Smoke TEST + fixture TEST_F
.clang-format              # Google Style + 4 espaços + 100 colunas
.clang-tidy                # Checks: bugprone, cert, cppcoreguidelines, modernize, performance
.gitignore                 # Artefatos CMake + IDE + OS
.dockerignore              # Pula build/, _deps/, .git/
Dockerfile                 # Multi-stage: gcc:13-bookworm → debian:bookworm-slim (usuário não-root)
README.md                  # Build, test, docker, padrões
```

### Slug → target

Slugs com hífen (ex.: `demo-app`) viram target `demo_app` dentro do CMake — o CMake não aceita hífen em `project()`. O diretório de include usa o nome do target: `include/demo_app/`.

### Padrão C++

`OCG.STACK.backend.cpp_standard` aceita `"14"`, `"17"`, `"20"` ou `"23"`. Valor inválido ou ausente cai no default **`"17"`**.

### Como testar localmente

Gerado o scaffold e aplicado no Git do projeto:

```bash
cd <repo-do-projeto>
cmake -B build
cmake --build build -j
./build/bin/<target>                    # executa
ctest --test-dir build --output-on-failure    # testes
docker build -t <target> .              # Docker multi-stage
docker run --rm <target>
```

### Test spec para C++

Quando o OCG identifica que o projeto é C++, o gerador de specs de teste usa idioms canônicos do GoogleTest:

- `TEST(SuiteName, TestName) { ... }` para testes simples.
- `TEST_F(FixtureClass, TestName) { ... }` com `class XxxFixture : public ::testing::Test` + `SetUp()` e `TearDown()` para testes que compartilham estado.
- Assertivas: `EXPECT_EQ`, `EXPECT_NE`, `EXPECT_TRUE`, `EXPECT_FALSE`, `EXPECT_THROW`, `EXPECT_THAT` com matchers GMock.
- `GTEST_SKIP() << "motivo"` para pular cenários não suportados.
- Integração CMake: `add_executable(<target>_tests ...)` + `target_link_libraries(... GTest::gtest_main)` + `gtest_discover_tests(...)`.

## Regras que governam o CodeGen

- **Docstrings obrigatórias** em todo código gerado.
- **Teste funcional + massa de dados** por arquivo gerado.
- **Preview antes do commit** — CodeGen nunca escreve direto no Git sem aprovação explícita do usuário.
- **Commit com mensagem padrão** (Conventional Commits).
- **Permissão `code:write`** — Dev ou GP (Admin pode via override).
- **Validação pós-geração** conforme a linguagem: pyflakes (Python), esprima (JS/TS), ast.parse (Python), cmake+gcc (C++).

## Ver também

- [OCG — STACK_RECOMMENDATION e DATA_MODEL](?section=05-ocg)
- [Pipeline canônico](?section=04-pipeline)
- [Solução de problemas](?section=10-troubleshooting) — scaffolder None (linguagem não coberta), erros de build C++, etc.
