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
| **JavaScript / TypeScript** | ✅ Node.js + NestJS/Express | ✅ jest | ✅ node:20-alpine multi-stage | ✅ jest workflow | ✅ NestJS 10 + Express 4 (Sprint 3 ext DT-058) | ❌ pendente Sprint 4 |
| **Java** | ✅ Java + Spring Boot/Quarkus | ✅ junit5 | ✅ eclipse-temurin:21 + Maven/Gradle | ✅ Java workflow | ✅ Spring Boot 3.3 + Quarkus 3.13 (Sprint 2 DT-058) | ❌ pendente Sprint 4 |
| **Kotlin** | ✅ Kotlin (Q27 lista direta) | ✅ junit5 | 🟡 reusa template Java | 🟡 reusa template Java | ✅ Spring Boot 3.3 + Gradle KTS (Sprint 3 DT-058) | ❌ pendente Sprint 4 |
| **Go** | ✅ Go | ✅ go_test | ✅ multi-stage golang:1.22 | ✅ Go workflow | ✅ chi/v5 + cmd/internal layout (Sprint 3 DT-058) | ❌ pendente Sprint 4 |
| **C#** | ✅ C# + ASP.NET | ✅ xunit | ❌ NÃO existe | ❌ NÃO existe | ✅ .NET 8 Minimal API + xUnit (Sprint 3 DT-058) | ❌ pendente Sprint 4 |
| **PHP** | ✅ PHP (sem framework no Q28) | ✅ phpunit | ❌ NÃO existe | ❌ NÃO existe | ✅ Laravel 11 + PHPUnit (Sprint 3 DT-058) | ❌ pendente Sprint 4 |
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

### `module_codegen_service:218` lê chave errada do OCG ✅ QUITADO (Sprint 2.0)
- Antes: `stack.get("primary_language", "python").lower()` — chave que
  não existe na estrutura DT-046, fallback "python" sempre.
- Agora: leitura tolerante DT-046 (`backend.language`) com fallback
  legacy (`primary_language`). Linguagem do GP respeitada.
- Teste em `test_dt058_language_matrix.py::test_module_codegen_service_extracts_language_from_dt046_structure`.

## Roadmap de fechamento

### Sprint 1 — Fundação ✅ ATUAL
- Audit + matriz visível (este doc)
- DT-059 piloter resiliente
- Tests parametrizados de framework por linguagem

### Sprint 2 — Templates Java/Spring ✅ FECHADO 2026-04-18
- ✅ Scaffolder determinístico Java/Spring Boot 3.3 — `backend/app/services/scaffolders/java_spring.py`
- ✅ Variante Quarkus 3.13 — `backend/app/services/scaffolders/java_quarkus.py`
- ✅ Despacho por linguagem/framework — `dispatch_scaffold` em `dispatch.py`
- ✅ Fix do bug `primary_language` vs `backend.language` (Sprint 2.0)
- 46 testes novos cobrindo: estrutura, XML válido, deps por opção,
  determinismo, projeto real Automação Jurídica em modo Java

### Sprint 3 — Demais linguagens ✅ FECHADO 2026-04-18
- ✅ Go: chi/v5 + cmd/internal layout — `scaffolders/go_app.py`
- ✅ C#: .NET 8 Minimal API + xUnit — `scaffolders/csharp_aspnet.py`
- ✅ PHP: Laravel 11 + PHPUnit — `scaffolders/php_laravel.py`
- ✅ Kotlin: Spring Boot 3.3 + Gradle KTS — `scaffolders/kotlin_spring.py`
- 34 testes novos consolidados em `test_dt058_sprint3_scaffolders.py`

### Sprint 3 ext — Node.js/TypeScript ✅ FECHADO 2026-04-18
- ✅ NestJS 10 + TypeScript 5 — `scaffolders/nodejs_nestjs.py` (default Node.js)
- ✅ Express 4 + TypeScript 5 — `scaffolders/nodejs_express.py` (alternativa minimalista)
- 22 testes em `test_dt058_sprint3_nodejs.py`
- Dispatch: Node.js + framework=Express → Express; outro caso → NestJS
- Aliases: TypeScript / JavaScript caem no mesmo path

### Cobertura final do dispatcher (após Sprint 3 + ext)
6 linguagens com scaffold determinístico (Java, Kotlin, Go, C#, PHP, Node.js).
Python continua LLM-only por design (decisão de produto — ecossistema mais
maduro pra LLM gerar FastAPI/Django).

### Sprint 4 — Validação E2E
- 5 projetos-piloto no dogfood (1 por linguagem)
- Critério binário SIM/NÃO por projeto
- Requer autorização explícita do user para cada projeto criado

## Como atualizar este doc

A cada quitação de DT relacionada (DT-058 sprints, ou qualquer fix que mexa
em linguagem), trocar o ❌ correspondente por ✅ ou 🟡 e citar a DT que
fechou. Manter este doc é **obrigatório** para a DT-058 — sem
visibilidade da matriz, ninguém sabe se Java está realmente pronto.
