# Cobertura de linguagens no CodeGen do GCA

**Data-base:** 2026-04-18
**Status:** Sprint 1 da DT-058 (auditoria + base resiliente)

Este documento mapeia o estado real de suporte a cada linguagem oferecida
no questionário Q27/Q28, em cada camada do pipeline de geração. É *vivo*
— atualizar a cada sprint da DT-058.

## Legenda

- ✅ **Suportado** — código existe, testado, exercitado em dogfood
- 🟡 **Parcial** — código existe mas com gaps específicos
- ❌ **Faltando** — sem suporte; falha silenciosa ou fallback Python errado
- ❓ **Não-determinístico** — depende 100% do LLM (sem template)

## Matriz de cobertura

| Linguagem | Q27/Q28 | Test framework | Dockerfile | CI workflow | Scaffold inicial | Validado em dogfood |
|---|---|---|---|---|---|---|
| **Python** | ✅ Python + FastAPI/Django/Flask | ✅ pytest | ✅ python:3.11-slim | ✅ pytest workflow | ❓ delegado ao LLM | ✅ projeto Automação Jurídica |
| **JavaScript / TypeScript** | ✅ Node.js + NestJS/Express | ✅ jest | ✅ node:20-alpine multi-stage | ✅ jest workflow | ❓ delegado ao LLM | ❌ nunca |
| **Java** | ✅ Java + Spring Boot/Quarkus | ✅ junit5 | ✅ eclipse-temurin:21 + Maven/Gradle | ✅ Java workflow | ❌ NÃO existe | ❌ nunca |
| **Kotlin** | ✅ Kotlin (Q27 lista direta) | ✅ junit5 | 🟡 reusa template Java | 🟡 reusa template Java | ❌ NÃO existe | ❌ nunca |
| **Go** | ✅ Go | ✅ go_test | ✅ multi-stage golang:1.22 | ✅ Go workflow | ❌ NÃO existe | ❌ nunca |
| **C#** | ✅ C# + ASP.NET | ✅ xunit | ❌ NÃO existe | ❌ NÃO existe | ❌ NÃO existe | ❌ nunca |
| **PHP** | ✅ PHP (sem framework no Q28) | ✅ phpunit | ❌ NÃO existe | ❌ NÃO existe | ❌ NÃO existe | ❌ nunca |
| **Outra** (Q27) | ✅ texto livre | ❌ sem mapeamento | ❌ sem template | ❌ sem template | ❓ LLM tenta | ❌ nunca |

## Bugs estruturais conhecidos (Sprint 1 cobre)

### DT-059 — `piloter_service` quebrava sem `PILOTER_API_KEY` (CRITICAL — quitada)
- Antes: qualquer scaffold (Python ou outras) explodia com 401 do Piloter
  externo. Bug não aparecia em testes porque `piloter_service` era mockado.
- Fix: degradação graciosa — retorna stack vazio + flag `degraded=true` +
  log estruturado quando key ausente. Caller continua, LLM gera código
  baseado em `PROJECT_PROFILE` do OCG.
- Bug auxiliar consertado: `code_generation_service:214` chamava
  `get_stack_recommendations(language, architecture)` sem `project_id`
  — TypeError silencioso.

### `module_codegen_service:218` lê chave errada do OCG (a sanear no Sprint 2)
- Atualmente: `stack.get("primary_language", "python").lower()`.
- Estrutura real do OCG (após DT-046): `stack.backend.language`.
- Resultado: linguagem do GP é **ignorada**, fallback "python" sempre.
- Test em `test_dt058_language_matrix.py::test_extract_language_known_bug_module_codegen_today`
  documenta o bug — invertir assertiva quando consertado.

## Roadmap de fechamento

### Sprint 1 — Fundação ✅ ATUAL
- Audit + matriz visível (este doc)
- DT-059 piloter resiliente
- Tests parametrizados de framework por linguagem

### Sprint 2 — Templates Java/Spring
- Scaffolder determinístico Java/Spring Boot (`pom.xml`, `Application.java`,
  `application.yml`, estrutura `src/main/java/<pkg>/`)
- Variante Quarkus alternativa
- Despacho por language no `code_generation_service`
- Fix do bug de `primary_language` vs `backend.language`

### Sprint 3 — Demais linguagens
- Go, C#, PHP, Kotlin — 1 commit por linguagem
- Templates de scaffold + Dockerfile/CI faltantes (C#, PHP)

### Sprint 4 — Validação E2E
- 5 projetos-piloto no dogfood (1 por linguagem)
- Critério binário SIM/NÃO por projeto
- Requer autorização explícita do user para cada projeto criado

## Como atualizar este doc

A cada quitação de DT relacionada (DT-058 sprints, ou qualquer fix que mexa
em linguagem), trocar o ❌ correspondente por ✅ ou 🟡 e citar a DT que
fechou. Manter este doc é **obrigatório** para a DT-058 — sem
visibilidade da matriz, ninguém sabe se Java está realmente pronto.
