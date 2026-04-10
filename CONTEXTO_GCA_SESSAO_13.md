# GCA — Contexto do Projeto e Próximos Passos
**Data:** 08/04/2026 | **Versão:** v0.7.0 | **Tag:** `v0.7.0` | **Autor:** Luiz Carlos Pielak

---

## 1. ESTADO ATUAL DO PROJETO

### Números consolidados

| Métrica | Valor |
|---------|-------|
| Endpoints backend | 134 |
| Tabelas PostgreSQL | 22 |
| Testes unitários passando | 134 |
| Arquivos de teste | 26 |
| Páginas frontend | 29 |
| Serviços backend | 26 |
| Routers backend | 24 |
| Commits no repo próprio | 1 (consolidação v0.7.0) |
| Commits históricos (home) | 95 (sessions 1–13) |

### Stack

```
Backend:    FastAPI 0.104 / Python 3.11 / PostgreSQL 16 / Redis 7
Frontend:   React 18.3 / TypeScript 5.6 / Vite 6.0 / Tailwind CSS
IA:         Anthropic SDK (Claude) — multi-provider (OpenAI, DeepSeek, Gemini)
Infra:      Docker Compose / Cloudflare Tunnel / systemd
Repo:       https://github.com/Pielak/GCA.git (SSH)
Produção:   https://gca.code-auditor.com.br
```

### Repositório

O repositório foi **migrado para `.git` próprio** dentro de `/home/luiz/GCA/` na Session 13. Antes, o git estava na raiz do home (`/home/luiz/.git`) e rastreava todo o sistema (Chrome cache, emails, downloads — 2.8 GB de objetos). Isso causava pack > 2 GB e impedia push ao GitHub.

**Solução aplicada:** `git init` em `/home/luiz/GCA/`, commit consolidado, force push via SSH, tag v0.7.0.

---

## 2. AÇÕES DAS ÚLTIMAS 48 HORAS (Session 13)

### Fases implementadas (TASK_GCA_CONTINUACAO.md)

| Fase | Descrição | Status |
|------|-----------|--------|
| 6.1 | Self-healing com tenacity — `@gca_retry()` em ArguiderService, ModuleCodegenService, LiveDocsService | ✅ |
| 6.2 | Bootstrap Wizard — `/setup/status`, `/setup/complete`, SetupWizardPage 4 steps com HelpTooltips | ✅ |
| 6.3 | Frontends Core — HelpTooltip.tsx + IngestionPage, GatekeeperPage, LiveDocsPage, RoadmapPage atualizadas | ✅ |
| 6.4 | LegacyPage — análise de codebase legado (ZIP/URL), débito técnico, conflitos de stack | ✅ |
| 6.5 | MergeEnginePage — diff viewer side-by-side, merge sugerido, confidence score | ✅ |
| 6.6 | Admin Parametrização — aba Configurações GCA no AdminDashboardPage (pesos, thresholds, agentes) | ✅ |
| 6.7 | Testes E2E — 14 testes Playwright cobrindo fluxo completo | ✅ |
| 6.8 | Push + tag v0.7.0 — migração para repo próprio, remoção de secrets, push via SSH | ✅ |
| 6.9 | Teste real com Code Auditor | ⏳ Pendente |

### Arquivos criados na sessão

- `backend/app/utils/retry.py` — decorator `@gca_retry()` com tenacity
- `backend/app/routers/setup.py` — wizard de configuração inicial
- `backend/app/tests/test_retry_selfhealing.py` — 3 testes
- `backend/app/tests/test_setup_wizard.py` — 4 testes
- `backend/app/tests/e2e/test_fluxo_completo.py` — 14 testes E2E
- `frontend/src/components/ui/HelpTooltip.tsx` — componente reutilizável
- `frontend/src/pages/SetupWizardPage.tsx` — wizard 4 steps

### Problemas resolvidos

1. **Repo no home:** git init no diretório correto, migração limpa
2. **Secrets no repo:** 9 arquivos MD com API keys removidos + .gitignore
3. **Pack > 2 GB:** resolvido com repo próprio (sem Chrome/Thunderbird/Downloads)
4. **GitHub HTTP 500:** resolvido com push via SSH

---

## 3. ESTADO DOS SERVIÇOS CORE DO PIPELINE

### 3.1 ArguiderService (Agent 9) — ✅ COMPLETO

| Aspecto | Estado |
|---------|--------|
| Classe | `ArguiderService` + `DocumentExtractor` |
| LLM | Anthropic AsyncAnthropic (análise + Vision para imagens) |
| @gca_retry | ✅ Aplicado em `analyze_document` |
| Funcionalidade | Análise completa de documentos, parse JSON, evolução OCG, criação de ModuleCandidate |
| Frontend (ArguiderPage) | ❌ **Mock local** — sem API real, sem HelpTooltips, Q&A hardcoded |

**Próximos passos Arguidor:**
1. Conectar ArguiderPage à API real (`POST /agents/analyze`, `GET /agents/status/{job_id}`, `GET /agents/result/{job_id}`)
2. Adicionar HelpTooltips na ArguiderPage
3. Implementar polling de status com progress bar
4. Exibir resultado da análise (seções extraídas, módulos identificados, gaps)
5. Permitir re-análise de documentos específicos
6. Integrar com IngestionPage — botão "Iniciar Arguidor" deve chamar API real

---

### 3.2 GatekeeperService — ✅ COMPLETO (backend) / ⚠️ PARCIAL (integração)

| Aspecto | Estado |
|---------|--------|
| Classe | `GatekeeperService` |
| LLM | Não (scoring ponderado, sem IA) |
| @gca_retry | Não necessário (sem I/O externo) |
| Funcionalidade | CRUD completo: get, resolve, ignore, approve, reject, generate_report |
| Frontend (GatekeeperPage) | ✅ **API real** + HelpTooltips + Radar chart + Override |

**Próximos passos Gatekeeper:**
1. **TODO em `approve_module`:** disparar CodeGen automaticamente após aprovação (encadear com ModuleCodegenService)
2. Conectar `EvaluationService._get_pillar_weights` aos pesos configurados pelo Admin (atualmente retorna defaults)
3. `get_project_evaluations` retorna lista vazia — implementar query real
4. Adicionar botão "Avaliar Pendentes" funcional (chamar `POST /evaluation/artifacts/{id}/evaluate`)
5. Exportar relatório Gatekeeper como PDF (endpoint `generate_report_markdown` já existe)

---

### 3.3 ModuleCodegenService — ⚠️ PARCIAL

| Aspecto | Estado |
|---------|--------|
| Classe | `ModuleCodegenService` |
| LLM | Anthropic em `_generate_code_via_llm` (com fallback placeholder se LLM indisponível) |
| @gca_retry | ✅ Aplicado em `generate_module_from_candidate` |
| Funcionalidade | Geração de código real via LLM ✅, mas testes (unit/integration/UAT) apenas criam registros no DB sem gerar conteúdo real |

**Próximos passos Gerador de Módulos:**
1. **Implementar geração real de testes via LLM** — `generate_integration_tests` e `generate_uat_tests` devem gerar código de teste real, não apenas registros DB
2. Integrar com GitService — commitar código gerado no repositório do projeto automaticamente
3. Disparar LiveDocsService.update_on_module_generated após geração bem-sucedida
4. Disparar EvaluationService para avaliação automática pós-geração
5. Adicionar suporte a 12 linguagens mapeadas (verificar cobertura real vs mapeamento)

---

### 3.4 CodeGenerationService — ✅ COMPLETO (alternativo)

| Aspecto | Estado |
|---------|--------|
| Classe | `CodeGenerationService` + `CodeGenerationPromptBuilder` |
| LLM | Multi-provider via LLMServiceFactory (Anthropic/OpenAI/Grok/DeepSeek) |
| @gca_retry | ❌ Não aplicado (deveria estar) |
| Funcionalidade | Geração completa com enriquecimento OCG, multi-provider |
| Frontend (CodeGeneratorPage) | ✅ **API real** — IDE-like com sidebar Git, revisão IA, testes |

**Nota:** Este serviço é **paralelo/alternativo** ao ModuleCodegenService. O ModuleCodegenService opera por candidato aprovado no Gatekeeper; o CodeGenerationService opera diretamente no Code Generator IDE.

**Próximos passos Gerador de Código:**
1. Aplicar `@gca_retry()` no CodeGenerationService (esquecido na Fase 6.1)
2. Adicionar HelpTooltips na CodeGeneratorPage
3. Definir se ambos os serviços coexistem ou se devem ser unificados
4. Implementar revisão de código via endpoint `POST /code-generation/review-code` (frontend já chama)

---

### 3.5 CodeValidationService — ⚠️ BÁSICO

| Aspecto | Estado |
|---------|--------|
| Classe | `CodeValidationService` |
| LLM | Não |
| @gca_retry | Não necessário |
| Funcionalidade | Validação sintática (Python compile, JS bracket-matching), scan de segurança por regex, métricas de qualidade |

**Próximos passos Validação:**
1. Integrar linters externos (ruff para Python, eslint para JS/TS)
2. Integrar com Gatekeeper — alimentar scores dos pilares P3 (Segurança) e P6 (Manutenibilidade)
3. Adicionar validação de dependências reais (verificar se imports existem)

---

### 3.6 QA Readiness — ❌ PLACEHOLDER

| Aspecto | Estado |
|---------|--------|
| Backend | Não existe serviço dedicado (`qa_service.py` não existe) |
| Frontend (QAReadinessPage) | Mock local — KPIs, executor isolado, tabela de execuções, cobertura por tipo. Visual completo, sem API |
| HelpTooltips | ❌ Não tem |

**Próximos passos QA Readiness:**
1. **Criar `backend/app/services/qa_service.py`** — orquestrar execução de testes gerados pelo ModuleCodegenService
2. **Criar `backend/app/routers/qa_router.py`** — endpoints:
   - `POST /projects/{id}/qa/execute` — disparar plano de testes
   - `GET /projects/{id}/qa/status/{job_id}` — status da execução
   - `GET /projects/{id}/qa/results` — resultados consolidados
   - `GET /projects/{id}/qa/coverage` — cobertura por tipo
3. Implementar executor isolado (Docker-in-Docker ou subprocess) para rodar testes gerados
4. Conectar QAReadinessPage à API real
5. Adicionar HelpTooltips
6. Integrar com Gatekeeper — alimentar pilar P5 (Testabilidade) com resultados reais

---

## 4. FRONTEND — ESTADO DAS PÁGINAS DO PIPELINE

| Página | API Real | HelpTooltips | Status |
|--------|----------|--------------|--------|
| IngestionPage | ❌ Mock | ✅ 5 tooltips | Visual completo, upload sem envio real |
| ArguiderPage | ❌ Mock | ❌ | Q&A hardcoded, sem persistência |
| GatekeeperPage | ✅ Real | ✅ 10 tooltips | **Mais completa** — radar, score, override |
| CodeGeneratorPage | ✅ Real | ❌ | **IDE completa** — sidebar Git, revisão IA |
| QAReadinessPage | ❌ Mock | ❌ | Visual bonito, sem backend |
| LiveDocsPage | ❌ Mock | ✅ 2 tooltips | Visual completo, sem API |
| RoadmapPage | ❌ Mock | ✅ 2 tooltips | Timeline + ADRs, sem API |
| LegacyPage | ❌ Mock | ✅ 3 tooltips | ZIP/URL, débito técnico mockado |
| MergeEnginePage | ❌ Mock | ✅ 3 tooltips | Diff viewer, merge sugerido mockado |

---

## 5. PRIORIZAÇÃO — PRÓXIMAS AÇÕES RECOMENDADAS

### Prioridade 1: Conectar Frontend → API (páginas core)

As páginas IngestionPage e ArguiderPage são o **início do pipeline**. Sem elas funcionando com API real, nenhum fluxo end-to-end é possível.

1. **IngestionPage** — conectar upload real (`POST /ingestion`), listar documentos (`GET /livedocs`), botão Arguidor funcional
2. **ArguiderPage** — conectar Q&A ao backend, polling de status, exibir resultado da análise
3. **LiveDocsPage** — conectar aos endpoints existentes (`GET /livedocs`, `/livedocs/content`, `/livedocs/changelog`)
4. **RoadmapPage** — conectar ao `GET /roadmap`

### Prioridade 2: Completar pipeline Gatekeeper → CodeGen

5. **approve_module → CodeGen** — encadear aprovação no Gatekeeper com geração automática de código
6. **Geração real de testes** — ModuleCodegenService deve gerar testes via LLM, não apenas registros
7. **@gca_retry no CodeGenerationService** — esquecido na Fase 6.1

### Prioridade 3: QA Readiness (novo)

8. **Criar qa_service.py + qa_router.py** — serviço e endpoints
9. **Executor isolado** — rodar testes gerados em container Docker
10. **Conectar QAReadinessPage** à API + HelpTooltips

### Prioridade 4: Integração end-to-end

11. **Teste real com Code Auditor** (FASE 6.9 do TASK_GCA_CONTINUACAO.md)
12. **HelpTooltips** nas páginas que faltam (ArguiderPage, CodeGeneratorPage, QAReadinessPage)
13. **Unificar ou separar** ModuleCodegenService vs CodeGenerationService

---

## 6. FLUXO COMPLETO DO PIPELINE (estado atual)

```
Documento → [Upload IngestionPage]
                 ↓ ❌ (mock, sem API real)
         [ArguiderService] → Analisa documento → Atualiza OCG → Cria ModuleCandidates
                 ↓ ✅ (backend funcional)
         [GatekeeperService] → Avalia 7 pilares → Score → Approve/Reject
                 ↓ ✅ (backend + frontend reais)
         [ModuleCodegenService] → Gera código via LLM → Testes (parcial)
                 ↓ ⚠️ (código real, testes placeholder)
         [CodeValidationService] → Valida sintaxe → Scan segurança
                 ↓ ⚠️ (básico, sem linters)
         [QA Readiness] → Executa testes → Cobertura
                 ↓ ❌ (não existe backend)
         [LiveDocsService] → Documenta automaticamente
                 ↓ ✅ (backend funcional)
         [GitService] → Commit no repositório
                 ↓ ✅ (backend funcional)
```

**Gargalo principal:** O frontend não está conectado à API nos primeiros passos do pipeline (Ingestão + Arguidor). O backend funciona, mas o usuário não consegue usar via interface.

---

*Documento gerado em 08/04/2026 — Session 13*
*GCA v0.7.0 — https://github.com/Pielak/GCA*
