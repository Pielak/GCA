# GCA — Gerenciador Central de Arquiteturas

## Documento Tecnico Completo

**Versao:** 2.0
**Data:** 2026-04-10
**Autor:** Luiz Carlos Pielak
**Status:** Producao

---

## 1. O que e o GCA

O GCA (Gerenciador Central de Arquiteturas) e uma plataforma de governanca arquitetural e geracao de codigo assistida por inteligencia artificial. Ele gerencia o ciclo completo de um projeto de software — desde a captacao de requisitos ate a entrega de codigo testado, validado por seguranca e em conformidade com ISO 27001 e LGPD.

### O que o GCA faz

Imagine que voce precisa construir um sistema de software. O GCA:

1. **Recebe seus requisitos** — via questionario estruturado de 49 perguntas
2. **Analisa a viabilidade** — valida tecnologias, identifica riscos, pontua aderencia
3. **Gera a arquitetura** — o OCG (Objeto de Contexto Global) define stack, pilares, compliance
4. **Ingere documentos** — requisitos de negocio, tecnicos, regulatorios, ERDs, specs de tela
5. **Cria um backlog inteligente** — modulos, testes, fixes, priorizados por dependencia
6. **Gera codigo com IA** — usando DeepSeek, Anthropic, OpenAI ou outros providers
7. **Gera testes automaticamente** — unitarios e de integracao, cobertura minima 70%
8. **Valida seguranca** — OWASP Top 10, analise de vulnerabilidades
9. **Verifica compliance** — ISO 27001, LGPD, criptografia, auditoria
10. **Orquestra o pipeline** — via n8n, tudo automatico do codigo ao merge

### Para quem e

- **Gerentes de Projeto (GP)** que precisam de governanca e rastreabilidade
- **Equipes de desenvolvimento** que querem acelerar a entrega com qualidade
- **Compliance officers** que precisam de trilha de auditoria completa
- **Stakeholders** que querem visibilidade do progresso

---

## 2. Arquitetura do Sistema

### Visao Geral

```
+-------------------+     +-------------------+     +-------------------+
|    Frontend       |     |    Backend        |     |   Infraestrutura  |
|    React 18       |---->|    FastAPI        |---->|   PostgreSQL 16   |
|    Vite + TS      |     |    Python 3.11    |     |   Redis 7         |
|    Tailwind CSS   |     |    29 routers     |     |   n8n             |
|    27 paginas     |     |    197 endpoints  |     |   Docker          |
+-------------------+     |    43 servicos    |     +-------------------+
                          +-------------------+
                                   |
                          +-------------------+
                          |   Providers IA    |
                          |   DeepSeek        |
                          |   Anthropic       |
                          |   OpenAI          |
                          |   Gemini          |
                          |   Grok            |
                          +-------------------+
```

### Numeros

| Componente | Quantidade |
|-----------|-----------|
| Routers (API) | 29 |
| Endpoints | 197 |
| Servicos | 43 (~16.000 linhas) |
| Modelos de banco | 49 tabelas |
| Paginas frontend | 27 |
| Testes automatizados | 84 |
| Providers de IA | 6 |
| Servicos Docker | 5 |

### Stack Tecnologica

| Camada | Tecnologia |
|--------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, React Query |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 async, Pydantic v2 |
| Banco de dados | PostgreSQL 16 (asyncpg), esquemas isolados por projeto |
| Cache | Redis 7 |
| Automacao | n8n (workflow engine) |
| Seguranca | JWT RS256, Vault (PGP), bcrypt 12+ rounds |
| Deploy | Docker Compose, Cloudflare Tunnel |
| IA | Multi-provider: Anthropic, OpenAI, DeepSeek, Gemini, Grok |

---

## 3. Pipeline do Projeto

O GCA opera em um pipeline sequencial onde cada etapa alimenta a proxima:

```
Questionario → Ingestao → Gatekeeper → OCG → Arguidor
→ Backlog Inteligente → Geracao de Codigo → Geracao de Testes
→ Execucao CI (GitHub Actions) → Analise de Seguranca (OWASP)
→ Validacao de Compliance (ISO 27001 + LGPD)
→ Aprovacao QA → Commit ao Repositorio → Publicacao
```

### 3.1 Questionario Externo

O GP (Gerente de Projeto) solicita um novo projeto respondendo um questionario de 49 perguntas dividido em 8 secoes:

- Identificacao do projeto
- Requisitos funcionais
- Requisitos nao-funcionais
- Arquitetura desejada
- Stack tecnologica
- Compliance e regulamentacao
- Equipe e recursos
- Cronograma e entregaveis

O Admin aprova ou rejeita o projeto com base no score de aderencia.

### 3.2 Ingestao de Documentos

Apos aprovacao, o GP faz upload de documentos:

- Requisitos de negocio (PRDs, BRDs)
- Especificacoes tecnicas
- Modelos de dados (ERDs)
- Definicoes de tela e fluxos
- Documentos de compliance
- Regulamentacoes aplicaveis

Cada documento e analisado, classificado e deduplicado automaticamente.

### 3.3 Gatekeeper

O Gatekeeper analisa todos os documentos ingeridos e avalia contra 7 pilares:

1. **P1** — Viabilidade de Negocio
2. **P2** — Arquitetura Tecnica
3. **P3** — Seguranca e Compliance
4. **P4** — Performance e Escalabilidade
5. **P5** — Manutenibilidade
6. **P6** — Testabilidade
7. **P7** — Documentacao

Cada pilar recebe um score de 0-100. O score geral determina se o projeto avanca.

### 3.4 OCG (Objeto de Contexto Global)

O OCG e o coracao do GCA. E um objeto de estado evolutivo que:

- **Começa** no questionario
- **Expande** com boa ingestao de documentos
- **Contrai** com ingestao ruim ou conflitante
- **Registra** cada mudanca com delta-log versionado

O OCG contem:
- Stack recomendada (linguagem, framework, banco, infra)
- Scores dos 7 pilares
- Requisitos de teste
- Checklist de compliance
- Recomendacoes arquiteturais
- Status de aprovacao

### 3.5 Arguidor

O Arguidor analisa cada documento ingerido e produz:

- **Gaps** — informacoes faltantes
- **Show-stoppers** — problemas bloqueantes
- **Definicoes pobres** — ambiguidades
- **Sugestoes de melhoria**
- **Candidatos a modulo** — componentes sugeridos para o backlog

### 3.6 Backlog Inteligente

O backlog e gerado automaticamente a partir do OCG + Arguidor:

**Tipos de item:**
- `service` — servicos de backend
- `controller` — endpoints e controladores
- `model` — modelos de dados e migracoes
- `middleware` — autenticacao, logging, CORS
- `ui_screen` — telas do frontend
- `ui_flow` — fluxos de navegacao
- `test` — testes especificos
- `fix` — correcoes de seguranca/compliance

**Ciclo de vida de cada item:**
```
Bloqueado → Pronto → Gerando → Testes Executando
→ Analise de Seguranca → Validacao de Compliance
→ Aguardando QA → Pronto para Merge → Commitado → Publicado
```

**Verificacao de artefatos:**
Antes de um item ser marcado como "Pronto", o sistema verifica se todos os artefatos necessarios existem (spec de tela, ERD, regras de negocio, etc.).

### 3.7 Geracao de Codigo (CodeGen)

O GP seleciona um item "Pronto" no backlog e o LLM gera o codigo:

- Recebe contexto completo: OCG + stack + artefatos + compliance
- Gera codigo limpo e documentado
- Segue a stack definida no OCG
- Inclui tratamento de erros e logging

### 3.8 Geracao de Testes (TestGen)

Apos o codigo, o LLM gera testes automaticamente:

- Testes unitarios
- Testes de integracao
- Edge cases e cenarios de erro
- Cobertura minima projetada: 70%

### 3.9 Execucao de Testes (CI)

Os testes sao executados automaticamente via GitHub Actions:

1. Backend cria branch temporaria `feature/backlog-{item_id}`
2. Commita codigo + testes na branch
3. GitHub Actions executa os testes
4. Resultado (pass/fail) atualiza o status do item

### 3.10 Analise de Seguranca

O LLM analisa o codigo gerado contra OWASP Top 10:

- A01 — Broken Access Control
- A02 — Cryptographic Failures
- A03 — Injection
- A04 — Insecure Design
- A05 — Security Misconfiguration
- A06 — Vulnerable Components
- A07 — Authentication Failures
- A08 — Software/Data Integrity
- A09 — Logging/Monitoring Failures
- A10 — SSRF

**Cada vulnerabilidade encontrada vira um ticket no backlog** com severidade, descricao e sugestao de correcao. O GP pode clicar "Corrigir com IA" para gerar o patch automaticamente.

### 3.11 Validacao de Compliance

O LLM valida contra ISO 27001 + LGPD:

- **A.10.1.1** — Controle de acesso por papel (RBAC)
- **A.12.4** — Logs de auditoria para acoes sensiveis
- **A.13.1** — Criptografia em transito (TLS 1.2+) e repouso (AES-256)
- **A.14.1** — Gestao de vulnerabilidades
- **LGPD** — Protecao de dados pessoais, retencao, anonimizacao

Issues de compliance tambem viram tickets com remediacao sugerida.

### 3.12 Aprovacao QA

Acao humana obrigatoria. O QA:

- Revisa o codigo contra os requisitos
- Testa fluxos funcionais
- Valida UX em telas criticas
- Pode aprovar ou rejeitar com motivo

### 3.13 Commit e Publicacao

Apos aprovacao QA:

- GP revisa e clica "Commit ao Repositorio"
- Codigo commitado via GitHub API
- Commit message inclui tags: `[QA_APPROVED] [SEC_PASS] [COMPLIANCE_PASS]`
- Trilha de auditoria completa registrada

---

## 4. Sistema de Papeis (RBAC)

### 4.1 Papeis Disponiveis

| Papel | Descricao |
|-------|-----------|
| Admin | Configuracao global, gestao de GPs, read-only em projetos |
| GP (Gerente de Projeto) | Orquestrador do projeto, pode acumular papeis tecnicos |
| Tech Lead | Lidera arquitetura, revisa codigo, gerencia backlog |
| Dev Senior | Escreve e revisa codigo, executa pipeline |
| Dev Pleno | Escreve codigo, executa pipeline |
| QA | Aprova/rejeita entregas, visualiza auditoria |
| Compliance | Valida seguranca e conformidade, exporta auditorias |
| Stakeholder | Visualizacao apenas |

### 4.2 Multi-Papeis

Um membro pode ter multiplos papeis simultaneos. O GP pode se auto-atribuir papeis tecnicos (Dev, QA, Compliance) para executar todas as atividades do projeto sozinho, se necessario.

**Cada acao registra quem fez e com qual papel** — trilha de auditoria completa.

### 4.3 Matriz de Permissoes (15 acoes × 8 papeis)

| Acao | GP | Tech Lead | Dev Sr | Dev Pl | QA | Compliance | Stakeholder |
|------|----|-----------|---------|---------|----|------------|-------------|
| project:view | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| project:edit | ✓ | ✓ | - | - | - | ✓ | - |
| project:manage_team | ✓ | - | - | - | - | - | - |
| code:write | ✓ | ✓ | ✓ | ✓ | - | - | - |
| code:review | ✓ | ✓ | ✓ | - | - | - | - |
| pipeline:execute | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| security:review | ✓ | ✓ | - | - | - | ✓ | - |
| compliance:validate | ✓ | - | - | - | - | ✓ | - |
| qa:approve | ✓ | - | - | - | ✓ | - | - |
| git:commit | ✓ | ✓ | ✓ | - | - | - | - |
| backlog:manage | ✓ | ✓ | - | - | - | ✓ | - |
| audit:view | ✓ | ✓ | ✓ | - | ✓ | ✓ | - |
| audit:export | ✓ | - | - | - | - | ✓ | - |
| docs:edit | ✓ | ✓ | - | - | - | - | - |

---

## 5. Seguranca e Compliance

### 5.1 ISO 27001 — Controles Implementados

**A.10.1.1 — Controle de Acesso**
- RBAC com 15 acoes granulares por 8 papeis
- Audit log em todas as acoes com `user_id + role_used`
- Admin read-only em projetos (nao pode editar)

**A.12.4 — Logging e Monitoramento**
- Cada fase do pipeline registrada com timestamps
- Hash chain imutavel no audit log global
- Secrets nunca aparecem em logs (Vault PGP)

**A.13.1 — Criptografia**
- JWT RS256 para autenticacao
- TLS 1.2+ em transito (Cloudflare Tunnel)
- Senhas com bcrypt 12+ rounds
- API keys criptografadas no Vault (PGP sym_encrypt)
- Dados sensiveis em repouso (AES-256 via PostgreSQL)

**A.14.1 — Gestao de Vulnerabilidades**
- SAST automatico via LLM (OWASP Top 10) em cada codigo gerado
- Vulnerabilidades viram tickets com remediacao sugerida
- Dependency scanning (npm audit, pip audit) quando Semgrep configurado
- Secrets scanning em toda ingestao

### 5.2 LGPD — Conformidade

- Dados pessoais (PII) identificados e protegidos
- Retencao conforme politica (default 90 dias para logs)
- Criptografia de dados pessoais em repouso
- Acesso baseado em papeis (RBAC) — principio do menor privilegio
- Trilha de auditoria exportavel para compliance

### 5.3 Trilha de Auditoria

Formato JSON estruturado com todas as fases:

```json
{
  "project_id": "...",
  "item_id": "...",
  "phases": [
    {
      "phase": "code_generation",
      "status": "COMPLETED",
      "user_id": "...",
      "role_used": "dev_senior",
      "timestamp": "2026-04-10T13:00:00Z",
      "context": {"model": "deepseek-chat", "tokens_used": 4200}
    },
    {
      "phase": "security_review",
      "status": "FAILED",
      "context": {"vulnerabilities": 3, "has_critical": true}
    }
  ],
  "result": "SUCCESS"
}
```

Exportavel em JSON para auditores externos.

---

## 6. Inteligencia Artificial

### 6.1 Providers Suportados

| Provider | Modelos | Uso |
|----------|---------|-----|
| Anthropic | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 | CodeGen, analise |
| OpenAI | gpt-4-turbo, gpt-4o, gpt-3.5-turbo | CodeGen, testes |
| DeepSeek | deepseek-chat, deepseek-coder | CodeGen, testes (economia) |
| Gemini | gemini-2.0-pro, gemini-1.5-pro | Analise, classificacao |
| Grok | grok-3-mini, grok-3 | CodeGen alternativo |

### 6.2 Chaves por Projeto

Cada projeto tem suas proprias chaves de IA armazenadas no Vault (criptografadas). Nao ha fallback para chaves globais — o GP configura as chaves no setup do projeto.

### 6.3 Sistema de 8 Agentes para OCG

O OCG e gerado por um sistema de 8 agentes especializados:

1. **Analyzer** — Analisa o questionario e distribui para especialistas
2. **P1 Specialist** — Viabilidade de Negocio
3. **P2 Specialist** — Arquitetura Tecnica
4. **P3 Specialist** — Seguranca e Compliance
5. **P4 Specialist** — Performance e Escalabilidade
6. **P5 Specialist** — Manutenibilidade
7. **P6 Specialist** — Testabilidade
8. **Consolidator** — Consolida respostas em OCG final

### 6.4 Billing por Projeto

Cada chamada de IA e rastreada com:
- Tokens utilizados (input + output)
- Custo em USD
- Operacao (codegen, testgen, security, compliance, analysis)
- Provider e modelo

---

## 7. Infraestrutura

### 7.1 Servicos Docker

| Servico | Porta | Descricao |
|---------|-------|-----------|
| gca-backend | 8000 | FastAPI com uvicorn, auto-reload |
| gca-frontend | 5173 | React + Vite, preview mode |
| gca-postgres | 5432 | PostgreSQL 16 com asyncpg |
| gca-redis | 6379 | Redis 7 para cache |
| n8n | 5678 | Workflow automation engine |

### 7.2 Acesso Externo

| URL | Servico |
|-----|---------|
| `gca.code-auditor.com.br` | Frontend |
| `api.code-auditor.com.br` | Backend API |
| `n8n.code-auditor.com.br` | n8n Workflows |

Via Cloudflare Tunnel — reverse proxy para maquina local.

### 7.3 Orquestracao n8n

O n8n orquestra o pipeline completo:

```
Webhook Trigger → Generate Code → Generate Tests
→ Security Scan → Compliance Check → Notificar QA
```

Quando o GP clica "Executar Pipeline" no backlog, o GCA dispara o webhook do n8n que executa todas as etapas automaticamente.

---

## 8. Como Usar o GCA (Tutorial)

### Passo 1: Solicitar Projeto

1. Acesse `gca.code-auditor.com.br`
2. Clique "Criar Novo Projeto GCA"
3. Preencha o questionario de 49 perguntas
4. Aguarde aprovacao do Admin

### Passo 2: Configurar Projeto

Apos aprovacao, faca login e configure:

1. **Repositorio Git** — Conecte seu repo GitHub/GitLab/Bitbucket
2. **Chaves de IA** — Configure o provider e API key

Esses dois itens sao obrigatorios. Equipe e opcional.

### Passo 3: Ingerir Documentos

1. Va a aba "Ingestao"
2. Faca upload de documentos (requisitos, specs, ERDs)
3. O sistema analisa, classifica e deduplica automaticamente

### Passo 4: Gerar Backlog

1. Va a aba "Backlog"
2. Clique "Gerar Backlog Inteligente"
3. O sistema cria itens baseado nos documentos + OCG + Arguidor
4. Cada item mostra artefatos necessarios e status de completude

### Passo 5: Gerar Codigo

1. Selecione um item "Pronto" no backlog
2. Clique "Gerar Codigo" — o LLM gera o modulo
3. Revise no editor integrado
4. Clique "Gerar Testes" — testes automaticos
5. O pipeline avanca: Security → Compliance → QA

### Passo 6: Resolver Issues

Se o scan encontrar vulnerabilidades ou falhas de compliance:

1. Os issues aparecem como sub-items do backlog
2. Cada issue tem severidade, descricao e remediacao sugerida
3. Clique "Corrigir com IA" para gerar o patch automaticamente
4. Marque como resolvido
5. Quando todos resolvidos, o item libera para re-scan

### Passo 7: Aprovar e Publicar

1. QA recebe notificacao (ou GP com papel QA)
2. Revisa codigo + testes + scans
3. Aprova ou rejeita
4. Se aprovado, GP faz commit final ao repositorio

---

## 9. Como o GCA Pode Progredir

### Curto Prazo

- **Integracoes externas** — Figma para geracao de telas, Semgrep/SonarQube para SAST real
- **Dashboard de metricas** — tempo medio por etapa, custo por modulo, cobertura de testes
- **Notificacoes** — Slack/Discord/Email em cada mudanca de status
- **Templates de projeto** — iniciar com configuracoes pre-definidas por tipo (web app, API, mobile)

### Medio Prazo

- **Geracao de frontend** — LLM gerando componentes React/Vue a partir de specs de tela
- **Code review cruzado** — IA compara codigo gerado com padroes do projeto
- **Monitoramento pos-deploy** — integrar com Grafana/Datadog para feedback loop
- **Multi-tenant SaaS** — cada empresa com seu ambiente isolado

### Longo Prazo

- **IA treinada no projeto** — modelo fine-tuned com o codigo e padroes do proprio projeto
- **Geracao de infra** — Terraform/Kubernetes a partir da arquitetura do OCG
- **Predicao de riscos** — ML para identificar modulos propensos a bugs
- **Auto-refactoring** — IA sugere e aplica refatoracoes baseada em metricas de qualidade
- **Marketplace de plugins** — extensoes por dominio (fintech, healthtech, etc.)

---

## 10. Especificacoes Tecnicas Detalhadas

### 10.1 Banco de Dados — 49 Tabelas

**Tabelas principais:**
- `users` — usuarios do sistema
- `projects` — projetos gerenciados
- `project_members` — membros com papel base
- `project_member_roles` — papeis adicionais (N:N)
- `backlog_items` — itens do backlog inteligente
- `ocg` — versoes do Objeto de Contexto Global
- `ocg_delta_log` — historico de mudancas do OCG
- `ingested_documents` — documentos ingeridos
- `arguider_analysis` — analises do Arguidor
- `pipeline_audit_entries` — trilha de auditoria do pipeline
- `project_settings` — configuracoes por projeto (LLM, n8n)
- `project_secrets` — secrets criptografados (Vault)

### 10.2 Endpoints — 197 no Total

**Por area:**
- Autenticacao: 12
- Admin: 33
- Projetos: 18
- Pipeline de qualidade: 9
- Backlog + Roadmap: 7
- Ingestao: 6
- Gatekeeper: 7
- Code Generation: 6
- Git + Repos externos: 11
- Configuracoes: 6
- Audit: 6
- Orquestracao: 2
- Outros: 74

### 10.3 Testes — 84 Automatizados

- Permissoes e RBAC: 40 testes
- Resolucao de papeis: 4 testes
- Gestao de GP: 4 testes
- Integracao RBAC: 14 testes
- Setup de projeto: 3 testes
- Multi-papeis: 19 testes (overlap com RBAC)

---

**Documento preparado por:** Luiz Carlos Pielak
**Plataforma:** GCA v2.0
**Ultima atualizacao:** 2026-04-10
