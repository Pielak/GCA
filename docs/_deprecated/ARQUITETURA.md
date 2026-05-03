> ⚠️ **DOCUMENTO HISTÓRICO / DEPRECADO — NÃO USAR COMO REFERÊNCIA OPERACIONAL.**
>
> Arquivado em 2026-04-30 pela consolidação documental do GCA (opção C — contrato + skills).
>
> Para regras vigentes, consultar:
> - `CLAUDE.md` na raiz — regras operacionais do Claude Code
> - `GCA_CANONICAL_CONTRACT.md` — contrato soberano do produto
> - `.claude/skills/gca-ocg-engine/SKILL.md` — máquina de estado do OCG (regra atual: só expande, nunca contrai)
> - `.claude/skills/gca-personas-engine/SKILL.md` — sistema de Personas v2 + HITL
> - `.claude/skills/gca-llm-resolver/SKILL.md` — porta única para invocação de LLM
>
> Este arquivo é mantido apenas para contexto histórico e auditoria. Suas regras NÃO autorizam implementação.

---

# GCA — Arquitetura do Orquestrador Global

> ⚠️ **DOCUMENTO HISTÓRICO / ANALÍTICO — NÃO É CONTRATO DE IMPLEMENTAÇÃO.**
> Descreve a visão arquitetural original. Contém elementos (papéis "Tech Lead"
> e "Manager", SaaS multi-tenant central, etc.) que **não refletem o recorte
> canônico atual**. Para o contrato vigente, consultar
> [`GCA_CANONICAL_CONTRACT.md`](GCA_CANONICAL_CONTRACT.md) e
> [`GCA_MVP_PROGRESS.md`](GCA_MVP_PROGRESS.md). Precedência documental em
> [`CLAUDE.md §2`](CLAUDE.md).

## 🏗️ Visão Geral: Camadas

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│              🌍 CAMADA GLOBAL (GCA)                            │
│          Orquestrador, Governança, Observabilidade              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ • Autenticação Global (JWT + OAuth)                    │   │
│  │ • RBAC Global (Admin, Tech Lead, Manager)              │   │
│  │ • Gestão de Credenciais Globais                        │   │
│  │ • SMTP, Slack/Teams (Global)                           │   │
│  │ • Monitoramento & Observabilidade                      │   │
│  │ • Audit Log Global (append-only)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│                    ↓                                             │
│         ┌──────────────────────────┐                           │
│         │  OCG Wizard (4 etapas)   │                           │
│         │  Criar novo Projeto/Tenant│                          │
│         └──────────────────────────┘                           │
│                    ↓                                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│           🔒 CAMADA TENANT (Projetos Isolados)                │
│                                                                 │
│  ┌────────────────────────┐  ┌────────────────────────┐        │
│  │   TENANT A (Projeto 1) │  │   TENANT B (Projeto 2) │  ...  │
│  │                        │  │                        │        │
│  │ ┌──────────────────┐   │  │ ┌──────────────────┐   │        │
│  │ │ OCG (Context)    │   │  │ │ OCG (Context)    │   │        │
│  │ │ • ProjectProfile │   │  │ │ • ProjectProfile │   │        │
│  │ │ • OutputProfile  │   │  │ │ • OutputProfile  │   │        │
│  │ │ • StackProfile   │   │  │ │ • StackProfile   │   │        │
│  │ │ • Compliance     │   │  │ │ • Compliance     │   │        │
│  │ │ • Credenciais    │   │  │ │ • Credenciais    │   │        │
│  │ └──────────────────┘   │  │ └──────────────────┘   │        │
│  │        ↓               │  │        ↓               │        │
│  │ ┌──────────────────┐   │  │ ┌──────────────────┐   │        │
│  │ │ 14 Módulos:      │   │  │ │ 14 Módulos:      │   │        │
│  │ │ M1-M14           │   │  │ │ M1-M14           │   │        │
│  │ │ (Ingestão,       │   │  │ │ (Ingestão,       │   │        │
│  │ │  Merge, GK,      │   │  │ │  Merge, GK,      │   │        │
│  │ │  CodeGen, QA)    │   │  │ │  CodeGen, QA)    │   │        │
│  │ └──────────────────┘   │  │ └──────────────────┘   │        │
│  │                        │  │                        │        │
│  │ Database Schema:       │  │ Database Schema:       │        │
│  │ proj_a_*               │  │ proj_b_*               │        │
│  │                        │  │                        │        │
│  │ Redis Namespace:       │  │ Redis Namespace:       │        │
│  │ project:a:*            │  │ project:b:*            │        │
│  └────────────────────────┘  └────────────────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│          🔧 INFRAESTRUTURA COMPARTILHADA                       │
│                                                                 │
│  • PostgreSQL (esquemas isolados: public + proj_{slug}_*)      │
│  • Redis (namespaces isolados: project:{id}:*)                 │
│  • Kafka (tópicos por tenant: project.{id}.*)                  │
│  • S3/Blob Storage (prefixos por tenant: /projects/{id}/...)   │
│  • Docker Registry (repositórios privados por tenant)          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Fluxo dos 14 Módulos (Sequência Controlada)

```
TENANT INICIALIZADO

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M1: Dashboard & Visibilidade                                    │
│ Exibe estado dos demais módulos                                 │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M2: Integração de Repositório                                   │
│ GitHub/GitLab webhook setup, validação de conectividade         │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M3: Parametrização do Projeto (Stack, Compliance)               │
│ Usuário define OutputProfile, StackProfile, ComplianceProfile   │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M4: Ingestão, Pré-triagem e Classificação de Artefatos          │
│ Upload → PII check → IA classification (P1-P7)                  │
│ Se LGPD risk → Quarentena, senão → próximo módulo               │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M5: Merge Engine                                                │
│ Consolidar artefatos por regras (específico > genérico)         │
│ Preservar mapa de origem, detectar conflitos críticos            │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M6: Gatekeeper — Avaliação dos 7 Pilares                        │
│ Score por pilar, detecção de gaps, recomendações                │
│ Se bloquear (P7 < 60) → Arguidor Técnico obrigatório            │
└─────────────────────────────────────────────────────────────────┘

   ├─→ Se BLOCKER
   │    ↓
   │   ┌────────────────────────────────────────┐
   │   │ M7: Arguidor Técnico                   │
   │   │ Perguntas formais por pilar faltante   │
   │   │ Respostas reabre ciclo (M5 → M6)       │
   │   └────────────────────────────────────────┘
   │    ↓ (volta a M5)
   │
   └─→ Se APROVADO (score >= 60)
        ↓

┌─────────────────────────────────────────────────────────────────┐
│ M8: Code Generator                                              │
│ Gera estrutura, código inicial, testes scaffold                 │
│ Cria PR ou push com estado "draft" ou "in_review"               │
│ Requer aprovação humana antes de merge                          │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M9: QA Readiness — Plano de Testes                              │
│ Define testes (Unitários, Integrados, Regressivos)              │
│ Pronto para executor isolado quando código for merged           │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M10: Executor de Testes Isolado                                 │
│ Container efêmero por projeto, timeout, limites de recurso       │
│ Executa plano QA, coleta cobertura e artefatos                  │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M11: Webhooks de Repositório & Automações                       │
│ Monitora push, PR, merge; dispara M8, M9, M10, M12 conforme OCG │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M12: Documentação Viva                                          │
│ Auto-gera API docs, README, ARCHITECTURE.md, CHANGELOG          │
│ Sincronizado com commits (git hook ou webhook)                  │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M13: Notificações & Canais (Slack/Teams)                        │
│ Alerts de cada módulo aos stakeholders apropriados               │
│ Global + escopo do projeto                                      │
└─────────────────────────────────────────────────────────────────┘

   ↓

┌─────────────────────────────────────────────────────────────────┐
│ M14: Observabilidade & Métricas                                 │
│ Prometheus, logs estruturados, trace_id, correlation_id         │
│ Monitoramento de performance dos módulos                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Ciclos de Retorno (Feedback Loops)

```
┌─────────────────────────────────┐
│  M4: Novo Artefato              │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│  M5: Merge (detecta conflito)   │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐      ┌──────────────────┐
│  M6: Gatekeeper (score baixo)   │─────→│ M7: Arguidor     │
└──────────────┬──────────────────┘      └─────────┬────────┘
               │                                   │
               │ ← respostas reabre ciclo ←─────┘
               │
               ↓
┌─────────────────────────────────┐
│  M5: Re-merge (com respostas)   │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│  M6: Re-avalia                  │
└──────────────┬──────────────────┘
               │ (se aprovado)
               ↓
         (continua M8+)
```

```
┌─────────────────────────────────┐
│  M8: Code Generator             │
│  (cria draft)                   │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│  M3: Stack atualizado           │ ← mudança propaga!
│  (mudança no ComplianceProfile) │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│  M8: Re-gera código             │ ← regenerado com novo profile
└──────────────┬──────────────────┘
               │
               ↓
         (continua)
```

---

## 🗄️ Isolamento de Dados (Tenant)

### PostgreSQL
```
public.*                    # Tabelas globais do GCA
  - users
  - organizations
  - invitations
  - audit_log_global
  - credentials (global)
  - monitoring_rules

proj_{slug}_*              # Tabelas por tenant
  - proj_slug_artifacts
  - proj_slug_ocg
  - proj_slug_ocg_history
  - proj_slug_generated_files
  - proj_slug_tests
  - proj_slug_audit_log
  - proj_slug_webhooks
```

### Redis
```
user:{id}:*                 # Sessões globais
project:{id}:*              # Namespaces por tenant
  - project:a:cache:*
  - project:a:queue:*
  - project:a:locks:*
```

### S3/Storage
```
/                           # Raiz
  /projects/{project_id}/   # Pasta por tenant
    /artifacts/
    /generated/
    /test_results/
    /documentation/
```

### Kafka
```
gca.global.*                # Tópicos globais
gca.project.{id}.*          # Tópicos por tenant
  - gca.project.a.artifacts
  - gca.project.a.merge
  - gca.project.a.codegen
```

---

## 🔐 Fluxo de Credenciais

```
GLOBAL (Orquestrador)
├── AI Provider Credentials (Claude, OpenAI)
├── SMTP Credentials
├── Slack/Teams Webhooks
└── Storage Credentials

PER-TENANT (Projeto Isolado)
├── VCS Credentials (GitHub token)
├── Docker Registry Credentials
├── External API Credentials (se aplicável)
└── AWS/Azure Credentials (se deployar próprio infra)

ISOLAMENTO:
- Chave de IA do Projeto A NÃO pode ser usada em B
- Webhook do VCS de A NÃO acessa dados de B
- Cada tenant tem seu próprio espaço de segredos
```

---

## 📈 Propagação do OCG (Context Change)

```
EVENTO: Usuário muda ComplianceProfile (M3)
   ↓
OCG atualizado em proj_{slug}_ocg
   ↓
M6 (Gatekeeper) reavalia com novo profile
   ↓
Se Compliance mais rigoroso:
   - M4 reclassifica artefatos (novas regras PII)
   - M8 regenera com menos libs externas
   - M9 adiciona mais testes de segurança
   - M12 regen docs com compliance notices
   ↓
Todos impactados sem intervenção manual
```

---

## 🎯 Primeira Implementação (MVP)

**O que você DEVE ter para começar:**

1. ✅ **Autenticação Global** (JWT + Admin bootstrap)
2. ✅ **OCG Schema** (global + per-tenant)
3. ✅ **OCG Wizard** (4 etapas de setup)
4. ✅ **Provisioning** (criar schema, redis ns, storage)
5. ✅ **M4** (upload + classificação)
6. ✅ **M5** (merge básico)
7. ✅ **M6** (gatekeeper score)
8. ✅ **API REST** (endpoints para acima)

**Depois você adiciona:**
- M7 (Arguidor)
- M8 (CodeGen)
- M9-M14 (resto)

---

## 🚀 Próximo Passo

Com base nessa arquitetura, vou criar:
- **BD Schema Detalhado** (OCG, Credentials, Audit Log)
- **Models Python** (User, Organization, Project, OCG)
- **API Endpoints** (Auth, OCG Wizard)

Avança? 🏗️
