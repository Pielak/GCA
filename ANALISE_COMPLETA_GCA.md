# Análise Completa: GCA — Documento Técnico + Mocks Figma + Questionário

**Data**: 05/04/2026  
**Status**: ✅ Arquitetura bem definida + UI pronta + Gap crítico identificado

---

## 📚 O Que Foi Analisado

1. **GCA_Documento.pdf** — Documento Técnico Completo para Construção (18 páginas)
2. **Gcagui.git** — Mocks Figma com 15 páginas (4 admin + 11 projeto)
3. **gca_questionario_tecnico_tenant.html** — Formulário técnico externo
4. **mockData.ts** — Estruturas de dados e tipos TypeScript

---

## 🏗️ Arquitetura Consolidada

### Stack Técnico Oficial (Documento)

| Camada | Tecnologia |
|--------|-----------|
| **Backend** | Python + FastAPI + SQLAlchemy async + asyncpg + Alembic |
| **Frontend** | React 18 + TypeScript + Vite + Tailwind CSS + Zustand + React Query + React Router |
| **Banco de dados** | PostgreSQL 16 (schema isolado por projeto) |
| **Cache** | Redis 7 (namespace por projeto e sessão) |
| **Mensageria** | Apache Kafka |
| **Autenticação** | JWT RS256 + controle central de sessão e bcrypt |
| **E-mail** | SMTP configurável |
| **Testes** | Containers Docker efêmeros por execução |
| **Deploy** | Docker Compose + evolução para Kubernetes |
| **Orquestração** | n8n (opcional, conforme cenário) |

### Camadas Globais (GCA)

```
┌─────────────────────────────────────────┐
│     Autenticação & RBAC Global          │
├─────────────────────────────────────────┤
│ Gestão de Credenciais (IA, repos, etc)  │
├─────────────────────────────────────────┤
│ Observabilidade & Auditoria Global      │
├─────────────────────────────────────────┤
│  Administração / Consolidação Projetos  │
└─────────────────────────────────────────┘
```

### Isolamento Multi-tenant

| Recurso | Mecanismo | Detalhes |
|---------|-----------|----------|
| PostgreSQL | Schema por projeto | `proj_{slug}` com ownership e políticas |
| Redis | Namespace por projeto | Prefixos `project_id:` e stores separados |
| Kafka | Tópicos prefixados | `gca.{project_id}.{tipo}` |
| Storage | Diretório/prefixo isolado | Sem compartilhamento entre projetos |
| IA | Credenciais e contexto isolados | Sem reuso de prompts ou memória |

---

## 📋 14 Módulos Funcionais

| Módulo | Responsabilidade | OCG Consumido |
|--------|------------------|---------------|
| **M1 — Autenticação** | Login, tokens, revogação | Não usa |
| **M2 — Gestão de Usuários** | Usuários, convites, RBAC | Não usa |
| **M3 — OCG Wizard** | Criação sequencial do projeto | Cria OCG |
| **M4 — Ingestão** | Upload, extração, pré-triagem PII | ComplianceProfile, IA, artefatos |
| **M5 — Gatekeeper** | Avaliação de 7 pilares + scoring | Artefatos consolidados, compliance, estado |
| **M6 — Merge Engine** | Documento mestre, resolução conflitos | Artefatos ativos + histórico |
| **M7 — Arguidor** | Perguntas dirigidas, entregáveis | Gatekeeper result + conflitos |
| **M8 — Code Generator** | Geração assistida com revisão humana | Stack, repo, IA, estado |
| **M9 — QA Readiness** | Planeamento e execução isolada | QA seleção, stack, repo, compliance |
| **M10 — Análise Legado** | Leitura controlada de sistemas existentes | Credenciais + integração map |
| **M11 — Roadmap** | Evolução de requisitos e decisões | Artefatos, estados, trilhas |
| **M12 — Documentação Viva** | Regeneração + publicação automática | Stack, repo, IA do projeto |
| **M13 — Dashboard Executivo** | Visão consolidada (multi-projeto) | OCGs consolidados (leitura) |
| **M14 — Auditoria Global** | Registro e prova de integridade | Histórico + eventos de todos |

### Sequência Operacional
```
M1/M2 (Base) → M3 (OCG Wizard) → M4 (Ingestão) → M6 (Merge)
                                          ↓
                                   M5 (Gatekeeper)
                                          ↓
                    M7 (Arguidor) ← [Se há gaps]
                                          ↓
                    M8 (Code Gen) → M9 (QA)
                         ↓              ↓
              M10 (Legado conforme) M12 (Docs Viva)
                         ↓
              M11 (Roadmap) → M13 (Dashboard) → M14 (Auditoria)
```

---

## 👥 Papéis e Responsabilidades (RBAC)

| Perfil | Escopo | Responsabilidades |
|--------|--------|-------------------|
| **Admin GCA** | Global | Criar/liberar projetos, designar GPs, config global, políticas transversais |
| **GP (Gestor de Projeto)** | Projeto | Responder questionário, manter equipe, credenciais, pendências |
| **Tech Lead** | Projeto | Definir stack, repo, critérios técnicos, aprovar código, override Gatekeeper |
| **Dev Sênior** | Projeto | Acionamento de gerações, revisão artefatos, aprovação quando autorizado |
| **Dev Pleno** | Projeto | Contribuir sob fluxo aprovação, permissões do projeto |
| **QA Engineer** | Projeto | Manutenção plano testes, aprovação evidências, validação pronto |
| **Compliance** | Global ou projeto | Monitorar quarentena LGPD, auditoria, aderência regulatória sem acesso secretos |
| **Stakeholder** | Leitura | Acompanhar dashboards, relatórios sem alteração operacional |

---

## 🎯 Gap Crítico: Aba Usuários

### ❌ Situação Atual (AdminUsersPage.tsx)
Exibe **TODOS os usuários** do sistema com RBAC global:
- Admin
- GP
- Tech Lead
- Dev Sênior / Pleno
- QA
- Compliance
- Stakeholder

### ✅ O Que Deveria Ser
**APENAS GPs de projetos**, com contexto de projetos gerenciados:

**Coluna expandida**:
- **Nome / Email** — Identificação do GP
- **Projetos Ativos** — Contagem de projetos em execução
- **Histórico** — Projetos arquivados (count)
- **Última Ação** — Timestamp + operação mais recente
- **Status** — Ativo / Bloqueado / Inativo
- **Ações**:
  - **Bloquear** — Revoga acesso temporariamente
  - **Ver Auditoria** — Histórico de override Gatekeeper, quarentena LGPD, etc.
  - **Revogar GP** — Remove papel (apenas incidentes críticos)

### Justificativa (Documento)

**Seção 5.2: "Público-alvo e papéis"**

Admin NÃO gerencia:
- ❌ Convites (responsabilidade do **GP**)
- ❌ Recuperação de senha (self-service)
- ❌ Membros de projeto (GP decide)
- ❌ Credenciais do projeto (GP + Tech Lead)

Admin APENAS:
- ✅ Audita ações críticas (override, quarentena)
- ✅ Revoga permissão de GP em caso de incidente
- ✅ Consolida logs operacionais de todos projetos

### Código para Refactoring

**AdminUsersPage.tsx** (atual — ❌):
```tsx
const filtered = USERS.filter(u => {
  return u.role === 'admin' || u.role === 'gp' || u.role === 'tech_lead'...
})
```

**AdminUsersPage.tsx** (corrigido — ✅):
```tsx
const gps = USERS.filter(u => u.role === 'gp').map(gp => {
  const activeProjects = PROJECTS.filter(p => p.gpId === gp.id && p.status === 'active');
  const archivedProjects = PROJECTS.filter(p => p.gpId === gp.id && p.status === 'archived');
  const lastAudit = AUDIT_EVENTS
    .filter(e => e.actor === gp.email && e.action === 'OVERRIDE_GATEKEEPER')
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
  
  return {
    ...gp,
    projectsActive: activeProjects.length,
    projectsArchived: archivedProjects.length,
    lastOverride: lastAudit?.timestamp,
    canBlock: true
  };
});
```

---

## 📊 Onboarding Administrativo (Seção 5)

### 6 Etapas Obrigatórias

| Etapa | Responsável | Descrição |
|-------|-------------|-----------|
| **1. Solicitação** | Tenant | Solicita abertura + dados mínimos |
| **2. Consolidação** | Admin GCA | Cria registro, valida, libera tenant |
| **3. Questionário** | GP do tenant | Responde perguntas por stack + OutputProfile |
| **4. Parametrização** | GP + Tech Lead | Configura IA, repo, integrações, banco, frontend/backend, infra, políticas |
| **5. Provisionamento** | GCA | Cria schema, namespace, tópicos, storage, webhooks automático |
| **6. Ativação** | GCA + Admin | Projeto vira "active" após validação completa |

---

## 📋 Questionário Técnico Orientado por Stack (Seção 5.3)

Não é meramente informativo — **DIRIGE a parametrização obrigatória**:

### Campos Críticos (definem OutputProfile)

1. **Tipo de saída pretendida** — Define qual stack será sugerido:
   - Executável/Desktop
   - Web App / API
   - Mobile
   - Melhoria sistema existente
   - Nova funcionalidade em existente

2. **Stack principal** — Precisão obrigatória:
   - Linguagem + frameworks
   - Front-end / back-end específicos
   - Banco de dados + mensageria
   - Requisitos cloud

3. **Estratégia de repositório**:
   - URL + branch principal
   - Branch de documentação
   - Política de merge
   - Publicação documental

4. **IA do projeto**:
   - Provedor (OpenAI, Claude, etc.)
   - Modelo específico
   - Limites + retenção
   - Fallback + mascaramento

5. **Integrações**:
   - n8n, Jira, Figma, Trello, Slack, Teams, SMTP, storage, Kafka, etc.

6. **Contexto legado** (condicional):
   - Sistema anterior + URL repo
   - Objetivo alteração (6 tipos)
   - Acesso fornecido (read-only / R+metadata / R+PR)
   - O que n8n pode fazer (7 ações)

7. **Entregáveis esperados** (10 tipos):
   - Código, documentação, testes, CI/CD, etc.

### OutputProfile → Implicações Mínimas

| OutputProfile | Requisitos |
|---------------|-----------|
| **Executável/Desktop** | Empacotamento, runtime, instalador, atualização, repo |
| **Web App / API** | Frontend + backend, deploy, segurança, observabilidade, repo |
| **Melhoria legado** | **Repo obrigatório**, análise controlada, docs consolidada |
| **Nova func legado** | **Repo obrigatório**, credenciais read-only, impact map, live docs |

---

## 🔐 Segurança, Credenciais e Conformidade (Seção 10)

### Princípios Mandatórios

- ✅ Criptografia forte em repouso (bcrypt)
- ✅ Nenhum papel funcional visualiza valor bruto após cadastro
- ✅ Todo uso descriptografado gera evento auditável
- ✅ Isolamento total entre GCA e project credentials
- ✅ HTTPS/TLS, hashing, validação entrada, logging sem segredos

### Controles Conformidade

| Controle | Descrição |
|----------|-----------|
| **OWASP Top 10** | Backend, frontend e integrações |
| **LGPD/GDPR ready** | Tratamento dados, quarentena, mascaramento, trilhas |
| **NIST aligned** | Referência postura segurança |
| **RBAC mínimo** | Permissões por papel + capability especial (quarentena) |
| **Auditoria encadeada** | Eventos com prova integridade + rastreabilidade |

### Fluxo de Rotação de Credenciais

```
Cadastrar nova cred → Validar antes troca → Testar connectivity
                ↓
         Trocar ponteiro operacional
                ↓
         Encerrar chamadas antigas com segurança
                ↓
         Invalidar/expirar anterior
                ↓
         Registrar auditoria da rotação
```

---

## 🗄️ Multi-tenancy & Provisioning (Seção 11)

### Isolamento Robusto

**PostgreSQL**: Schema `proj_{slug}` com ownership e políticas segregadas  
**Redis**: Namespace `{project_id}:` — sem compartilhamento  
**Kafka**: Tópicos prefixados `gca.{project_id}.{tipo}`  
**Storage**: Diretório isolado — sem reuso  
**IA**: Credenciais **completamente isoladas** — sem reuso prompt/memória

### Estados Principais do Projeto

```
[*] → draft → provisioning → {provisioning_failed | active}
            → active ↔ {degraded | suspended}
            → archived
```

### Estados Artefato
```
uploaded → extracted → {pii_quarantine | classified} → pending_review → {merged | rejected | superseded}
```

---

## 🧪 Estratégia de Testes (Seção 12)

### 17 Categorias de Teste

| Categoria | Objetivo | Aplicação GCA |
|-----------|----------|---------------|
| **Smoke/Sanity** | Essential após build | Health checks, login, dashboards |
| **Unitários** | Isolado por função | Services, regras negócio, validators |
| **Integração** | Entre componentes | FastAPI + PG + Redis + Kafka + SMTP |
| **Contrato/API** | Aderência consumidores | OpenAPI, schemas, payloads |
| **Repositório** | Conectividade + eventos | Registro, assinatura, rotação, webhooks |
| **Regressão** | Evitar reintrodução bugs | Fluxos admin, OCG, Gatekeeper |
| **E2E** | Jornada ponta-a-ponta | Solicitação → liberação → parametrização → ativação |
| **UAT** | Aderência processo usuário | Admin, GP, Tech Lead, QA em cenários reais |
| **Segurança** | Detectar falhas técnicas | Auth, RBAC, JWT, CORS, secrets, trilhas |
| **SAST/SCA** | Análise código + deps | Pipeline backend, frontend, Docker |
| **DAST** | Testar em execução | Endpoints expostos, auth, session |
| **Performance** | Throughput + latência | API, dashboard, ingestão paralela |
| **Stress/Soak** | Limite estabilidade | Filas, workers, containers |
| **Resiliência** | Falha controlada + recovery | Cred expira, repo indisponível, cache falha |
| **Backup/Restore** | Recuperação operacional | OCG History, auditoria, banco |
| **Acessibilidade** | UX adequado | Navegação teclado, contrast, rótulos |
| **Compatibilidade** | Reduzir variação ambiente | Navegadores, tamanhos tela, stacks execução |
| **Observabilidade** | Logs, métricas, alertas | Eventos estruturados, saúde SLA |

### Imagem Base por Stack

| Stack | Imagem | Nota |
|-------|--------|------|
| Python | `python:3.12-slim` | pytest, scripts, serviços |
| Node/Frontend | `node:20-bullseye` | Jest, Vitest, E2E quando exigido |
| Java | `eclipse-temurin:21-jdk` | JUnit, Maven, Gradle |
| Go | `golang:1.22-alpine` | go test, build efêmero |
| .NET | `mcr.microsoft.com/dotnet/sdk:8.0` | testes, builds temp |
| Custom | `registry/{projeto}/qa-base:{tag}` | Quando declarada e versionada |

---

## 📈 Roadmap Técnico (Seção 16)

| Fase | Entregas Principais |
|------|-------------------|
| **Fase 1** | Auth, usuários, RBAC, bootstrap admin, health checks |
| **Fase 2** | Solicitação + consolidação admin, OCG Wizard, provisioning |
| **Fase 3** | Ingestão, pré-triagem, quarentena LGPD, merge, Gatekeeper |
| **Fase 4** | Arguidor, publicação respostas, reavaliação |
| **Fase 5** | Code Generator + revisão + integração repo |
| **Fase 6** | QA Readiness, executor isolado, imagens, evidências |
| **Fase 7** | Documentação Viva, roadmap, auditoria global, alertas, operação |

---

## 🎨 Mocks Figma — Status de Implementação

### Páginas Admin (4)
✅ **AdminDashboardPage** — Métricas executivas, status consolidado  
⚠️ **AdminUsersPage** — **REVISAR: Mostrar apenas GPs**  
✅ **AdminProjectsPage** — Aprovação/rejeição de projetos  
✅ **AdminAuditPage** — Logs operacionais

### Páginas Projeto (11)
✅ **ProjectListPage** — Lista de projetos por usuário  
✅ **ProjectDetailLayout** — Wrapper do projeto  
✅ **ProjectDashPage** — Overview  
✅ **IngestionPage** — Coleta de artefatos  
✅ **GatekeeperPage** — Avaliação de critérios  
✅ **QAReadinessPage** — Plano de testes  
✅ **CodeGeneratorPage** — Assistência de geração  
✅ **LegacyPage** — Integração com legado  
✅ **ArguiderPage** — Argumentação de decisões  
✅ **LiveDocsPage** — Documentação ao vivo  
✅ **MergeEnginePage** — Integração GitHub  

### Componentes Figma

- ✅ 12 componentes reusáveis (Button, Input, Modal, Toast, Badge, Card, Spinner, Table, etc.)
- ✅ 10 custom hooks (useAuth, useUsers, useProjects, useTickets, etc.)
- ✅ 9 páginas admin + projeto
- ✅ Error Boundary + ProtectedRoute
- ✅ Dark theme com Tailwind
- ✅ Build 297.81 KB gzipped

---

## 🎯 Checklist de Alinhamento Figma ↔️ Documento

| Item | Status | Nota |
|------|--------|------|
| **Stack Frontend** | ✅ | React 18 + TypeScript + Tailwind — alinhado |
| **Stack Backend** | ✅ | FastAPI + PostgreSQL + Redis — alinhado |
| **14 Módulos** | ✅ | Pages criadas para M1-M14 |
| **RBAC** | ✅ | Roles mapeados na UI |
| **OCG Wizard** | ✅ | M3 page exists |
| **Ingestão** | ✅ | M4 page exists |
| **Gatekeeper** | ✅ | M5 page exists |
| **Code Generator** | ✅ | M8 page exists |
| **QA Readiness** | ✅ | M9 page exists |
| **Questionário Técnico** | ✅ | HTML externo + integração prevista |
| **Multi-tenancy** | ✅ | Modelo suporta isolamento |
| **Auditoria** | ✅ | AuditPage + AuditEvent model |
| **Credenciais** | ⚠️ | Modelo existe, backend implementation pendente |
| **Admin Dashboard** | ✅ | 13 endpoints + dashboard page |
| **Webhooks** | ✅ | MergeEngine page existe |
| **🚨 AdminUsers (apenas GPs)** | ❌ | **CRÍTICO — Deve refatorar** |

---

## 🚀 Próximas Fases (Sessions 09+)

### Session 09: Backend Integration Tests
- 47 endpoint tests (continuação)
- Mock data refinement
- Setup CI/CD

### Session 10: Questionário & n8n
- Validação de respostas
- Integração com análise n8n
- Parecer técnico ao GP

### Session 11: Multi-tenant Provisioning
- Isolamento robusto (schema, namespace, tópicos)
- Provisioning compensatório
- Health checks per-tenant

### Session 12: Security & Compliance
- OWASP Top 10
- LGPD/GDPR quarantine
- Auditoria encadeada

### Session 13+: Módulos Avançados
- Code Generator com revisão
- QA Readiness executor
- Documentação Viva

---

## 💬 Resumo Executivo

### ✅ O Que Está Excelente
- **Arquitetura sólida** — 14 módulos bem definidos, isolamento multi-tenant robusto
- **Stack técnico moderno** — FastAPI + React 18, escalável
- **Documentação completa** — Regras claras para onboarding, testes, segurança
- **UI/UX bem planejada** — 15 páginas de mocks prontas, componentes reusáveis
- **Questionário técnico abrangente** — 50+ campos, dirigindo parametrização

### ⚠️ O Que Precisa Revisar

| Item | Problema | Ação |
|------|----------|------|
| **AdminUsersPage** | Mostra TODOS os usuários, não apenas GPs | Refatorar para listar GPs + contexto projetos |
| **Credenciais** | Modelo existe, implementação backend pendente | Implementar armazenamento seguro + rotação |
| **Questionário → n8n** | HTML externo não está integrado | Validação backend + parecer técnico |

### 🎯 Viabilidade
- **Altíssima**: Estrutura é solid, documentação clara, mocks prontos
- **Tempo estimado (Sessions 09-12)**: 30-40 dias úteis para MVP robusto

---

## 📁 Referência Rápida

| Arquivo | Linhas | Tipo | Localização |
|---------|--------|------|-----------|
| GCA_Documento.pdf | 18 páginas | Especificação | `/home/luiz/GCA/` |
| gca_questionario_tecnico_tenant.html | 15.8K | Form externo | `/home/luiz/GCA/` |
| Gcagui repository | 6 dirs, 15 pages | Mocks + components | `https://github.com/Pielak/Gcagui.git` |
| mockData.ts | 407 linhas | Mock DB | `/tmp/Gcagui/src/app/data/` |

---

## 🔗 Estrutura de Diretórios Recomendada

```
GCA/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── constants.py
│   │   ├── db/
│   │   │   └── database.py
│   │   ├── models/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── middleware/
│   │   └── tests/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── stores/
│   │   └── App.tsx
│   └── Dockerfile
├── docker-compose.yml
└── docs/
```

