# GCA — Funcionalidades Completas

**Versão**: baseline pós-MVP 15 (2026-04-21)
**Base**: 1506 testes passing · tsc frontend 1 error residual · 15 MVPs fechados

Este documento enumera todas as funcionalidades do GCA organizadas em:
- **Área Administrativa** — operada por usuário com papel `Admin` (instância)
- **Área de Gestão de Projeto** — operada por usuário com papel `GP` (projeto)
- **Áreas Compartilhadas** — acessíveis por ambos conforme RBAC

RBAC canônico: 5 papéis (`Admin`, `GP`, `Dev`, `Tester`, `QA`). Admin opera a instância; GP é soberano do projeto (§4.1 emenda 2026-04-19).

---

## 1. Área Administrativa

Entrada: `/admin` · Guard: `RequireAdmin` · Escopo: instância inteira

### 1.1 Dashboard Admin (`/admin`)

- **Métricas agregadas da instância**: total de projetos, projetos ativos, projetos degradados, usuários ativos/admin/inativos.
- **Gráfico de distribuição de projetos por status** (Ativo/Concluído/Arquivado/Rascunho/Degradado).
- **Lista dos 5 projetos mais recentes** com status + fase + perfil de output.
- **Auditoria recente** (últimos 5 eventos de `audit_log_global`).
- **Pesos dos 7 pilares** (P1 Conformidade, P2 Arquitetura, P3 Segurança, P4 Performance, P5 Testabilidade, P6 Manutenção, P7 Documentação) editáveis pelo admin.
- **Thresholds de aprovação**: P7 bloqueante, Ready, Needs Review, At Risk — configuráveis.

### 1.2 Gestão de Usuários (`/admin/users`)

- **Lista de usuários** da instância com filtro por ativos/inativos/todos.
- **Convidar Administrador** — email + papel; envia convite com link de onboarding.
- **Convidar GP** — cria convite escopado a projeto específico (delegado no fluxo de projetos).
- **Bloquear / desbloquear usuário** — respeita guard de "último Admin ativo" (MVP 11 Fase 11.3).
- **Excluir usuário** — respeita guard de "último Admin"; exige confirmação.
- **Promover / rebaixar Admin** — `set_admin_flag(True|False)`; guard de último Admin ativo.
- **Audit dos eventos de papel** — cada ação emite `role_granted` / `role_revoked` em `audit_log_global` (MVP 11 Fase 11.4).

### 1.3 Gestão de Projetos (`/admin/projects`)

- **Lista de projetos pendentes de aprovação** (provindos de requisições externas `/solicitar-projeto`).
- **Aprovar projeto** — provisiona organization + project + convida GP; emite `PROJECT_APPROVED` no audit.
- **Rejeitar projeto** — com motivo obrigatório; emite `PROJECT_REJECTED`.
- **Alterar status de projeto** (`active` → `archived`/`completed`/`degraded`) com emissão de `PROJECT_STATUS_CHANGED`.
- **Adicionar novo GP a projeto existente** — para transferência ou co-gestão.
- **Remover GP antigo** — com guard de "último GP do projeto".
- **Visualizar projeto individual** (`/admin/projects/:id`) — scores por pilar + overall, overview somente leitura do projeto do GP.

### 1.4 Auditoria Global (`/admin/audit`)

- **Trilha encadeada com hash chain SHA-256** — cada evento tem `previous_hash` + `current_hash`.
- **Eventos canônicos cobertos** (MVPs 11.4, 13.5-13.7, 14.7, 14.8):
  - Projeto: `PROJECT_APPROVED` · `PROJECT_REJECTED` · `PROJECT_STATUS_CHANGED`
  - Questionário: `QUESTIONNAIRE_SUBMITTED` · `QUESTIONNAIRE_APPROVED` · `QUESTIONNAIRE_REJECTED`
  - CodeGen: `CODEGEN_SCAFFOLD_GENERATED` · `CODEGEN_SCAFFOLD_APPLIED` · `CODEGEN_FILE_REGENERATED`
  - OCG: `OCG_UPDATED` · `OCG_ROLLED_BACK` · `OCG_CONSOLIDATED`
  - Papéis: `ROLE_GRANTED` · `ROLE_REVOKED` · `ROLE_TRANSFERRED`
  - Pipeline: `DOCUMENT_INGESTED` · `DOCUMENT_QUARANTINED` · `GATEKEEPER_EVALUATED` · `ARGUIDER_RESPONSE_REGISTERED` · `BACKLOG_REGENERATED`
  - Outros: `CREDENTIAL_STATUS_CHANGED` · `WEBHOOK_HEALTH_CHANGED` · `AUDIT_CHAIN_VERIFIED`
- **Filtro por tipo de evento, ator, recurso, janela temporal**.
- **Verificação de integridade da cadeia** (`verify_chain`).

### 1.5 Métricas Operacionais (`/admin/metrics`)

- **Dashboard JSON agregado** com janela configurável (1h a 720h).
- **Uso de IA por provider × operation**: calls, tokens_in, tokens_out, cost_usd.
- **Uso de IA por projeto** (breakdown com ordenação por custo desc).
- **Eventos de audit agregados por tipo**.
- **Endpoint Prometheus** (`/metrics/prometheus`) — texto em formato scrape-compatível com gauges e counters:
  - `gca_ai_calls_total` · `gca_ai_tokens_total` · `gca_ai_cost_usd_total`
  - `gca_audit_events_total`
  - `gca_projects_total` · `gca_users_total`
  - **MVP 14.10**: `gca_celery_broker_reachable` · `gca_celery_workers_online` · `gca_celery_dlq_entries`
- **Healthcheck público** (`/metrics/health`) sem autenticação — usado por load balancer/k8s probe.

### 1.6 Backups (`/admin/backups`)

- **Visão agregada de todos os backups por projeto** (complementa visão por projeto do GP).
- **Agendamento configurável por timezone** (env `BACKUP_TIMEZONE`, fallback em valor inválido — MVP 12.2).
- **Retenção e rotação**: políticas definidas pelo admin.
- **Download direto** de snapshot específico.

### 1.7 Incidentes (`/admin/incidents`)

- **Lista cross-instância de incident tickets** abertos e resolvidos.
- **Filtro por severidade, status, projeto**.
- **Detalhe do incidente** com comentários + histórico + roteamento automático por papel.
- **Resolução / fechamento** com auditoria.

### 1.8 Sustentação (`/admin/support`)

- **Lista da equipe de Sustentação** (`is_support=true`) — flag cross-instância; Admin herda automaticamente (MVP 6 emenda).
- **Promoção / rebaixamento** do papel Support.
- **Regra dura**: UI de Sustentação **não** promove Support a Admin.

### 1.9 Releases (`/admin/releases`)

- **Lista de releases agregadas por projeto**.
- **Detalhe de release** (`/admin/releases/:releaseId`): status (pending/applied/rolled_back), bundle, notas, commits.
- **Rollback** de release aplicada.
- **Bundle markdown** com: OCG version no momento, commits incluídos, artefatos gerados (schema.sql/seed.sql/migration), evidência de testes.

### 1.10 Provedores de IA (configuração de instância)

- **Configuração global de provedores** (Anthropic, OpenAI, DeepSeek, Qwen/Ollama local).
- **Chaves de API por provedor** criptografadas (AES-GCM com master key rotacionável).
- **Validação** — endpoint de teste que valida chave antes de salvar.
- **Definição de provedor padrão** para pipeline OCG.
- **Separação**: chaves globais do pipeline OCG (Admin) são distintas das chaves do projeto (GP) — compartimentalização §6.5.

### 1.11 Rotinas de sistema

- **Limpeza de uploads antigos** (agendador).
- **Verificação de integridade da cadeia de audit** (job periódico).
- **Healthcheck completo** (`/health`) com bloco `celery.broker.reachable` + `celery.workers.workers/nodes` (MVP 13.2).

---

## 2. Área de Gestão de Projeto (GP)

Entrada: `/projects` → `/projects/:id` · Guard: `ProjectMember` aceito + `RequireProjectSetup` em rotas pipeline
GP é soberano do projeto (§4.1 emenda 2026-04-19): tem acesso a **todas** as funcionalidades, inclusive CodeGen, testes e QA — a separação com Dev/Tester/QA é de dia-a-dia, não de permissão.

### 2.1 Meus Projetos (`/projects`)

- **Lista de projetos** onde o usuário é membro ativo (status, papel, progresso).
- **Indicador de pendências** por projeto.
- **Navegação direta** para o dashboard do projeto.

### 2.2 Dashboard do Projeto (`/projects/:id`)

- **Scores OCG** em radar chart pelos 7 pilares (P1-P7).
- **Distribuição detalhada de scores por pilar** com adherence_level.
- **Status do projeto** (READY/NEEDS_REVIEW/AT_RISK/BLOCKED) + versão do OCG.
- **Stack recomendada** resumida por camada (backend, frontend, database, cache, messaging).
- **Billing de IA do projeto**: total_cost_usd, total_tokens, calls, breakdown por operação e provedor.
- **Equipe do projeto** com papel de cada membro.
- **Atalhos** para todas as abas do pipeline.

### 2.3 Configurações do Projeto (`/projects/:id/settings`)

Abas internas:
- **Questionário Técnico** — lista questionário externo submetido + análise + correções.
- **Repositório Git** — conexão (GitHub/GitLab/Bitbucket), PAT criptografado, branch default.
- **Repos Externos** — sub-aba para legados (atalho para `/external-repos`).
- **Provedor IA do projeto** — chaves próprias independentes das globais (§6.5 compartimentalização):
  - Adicionar/remover provedor
  - Validar chave em tempo real
  - Definir padrão do projeto
- **Gestão de Equipe**:
  - Convidar membros com papel (Dev, Tester, QA, GP)
  - **GP convida outro GP** do mesmo projeto (MVP 11.1)
  - **Transferir soberania** (GP → GP) — MVP 11.2
  - Revogar convite pendente
  - Remover membro
  - Guard de "último GP" na remoção

### 2.4 OCG — Objeto de Contexto Global (`/projects/:id/ocg`)

- **Visualização completa do OCG atual**: PROJECT_PROFILE, PILLAR_SCORES, COMPOSITE_SCORE, STACK_RECOMMENDATION, CRITICAL_FINDINGS, TESTING_REQUIREMENTS, COMPLIANCE_CHECKLIST, DELIVERABLES, ARCHITECTURE_OVERVIEW, RISK_ANALYSIS, APPROVAL_STATUS, DATA_MODEL.
- **Versão + schema_version + change_type + context_health** (depth/confidence/quality).
- **Histórico de versões** com delta por versão (fields_changed, trigger_source, changed_by).
- **Snapshot de versão anterior** (`GET /ocg/snapshot/:version`).
- **Rollback formal** (`POST /ocg/rollback/:version`) — cria nova versão, emite `OCG_ROLLED_BACK` (MVP 14.7).
- **Consolidação explícita** (`POST /ocg/consolidate`) — recalcula COMPOSITE_SCORE a partir de PILLAR_SCORES aplicando regras §5; idempotente; emite `OCG_CONSOLIDATED` (MVP 14.8).
- **Health do contexto** (`/ocg/health`) — depth, confidence, quality.
- **Reconsolidação forçada** (trigger manual para refazer consolidação).
- **Regeneração do OCG** (com confirmação — descarta delta e recomeça do questionário).
- **Tabela DATA_MODEL** com tabelas + índices declarados (MVP 10 DT-076 F1).

### 2.5 Repositórios Externos (`/projects/:id/external-repos`)

- **Adicionar repositório legado** (URL + credenciais).
- **Análise automática** ao adicionar: stack detectado, vulnerabilidades, compatibilidade GCA.
- **3 abas de output**:
  - **Stack Detectado**: linguagem, frameworks, arquivos totais, Docker, CI/CD, testes.
  - **Segurança**: nível de risco (low/medium/high) + vulnerabilidades identificadas (severidade + descrição + versão recomendada).
  - **Compatibilidade GCA**: status geral (compatível/requer_adaptacao/incompativel), esforço estimado, breakdown por área (backend/frontend/database).
- **Roadmap de adaptação** do legado passo-a-passo.
- **Disparo de Arguidor** — a análise de legado alimenta o Arguidor com perguntas específicas (MVP 14).

### 2.6 Ingestão de Documentos (`/projects/:id/ingestion`)

- **Drop zone** para upload de documentos (PDF, DOCX, XLSX, PNG, JPG, MD — máx 50 MB).
- **Vinculação a módulo do Roadmap** (opcional via `target_module_id`; auto-detecta PDF de template GCA).
- **Pipeline assíncrono de análise** (Celery):
  - Estágios: `queued` → `extracting_text` → `analyzing` → `updating_ocg` → `regenerating_backlog` → `completed`/`failed`
  - Barra de progresso com `arguider_progress_percent`
- **Extração rica por tipo**:
  - **DOCX**: tabelas estruturadas + parágrafos + headers/footers
  - **PDF**: AcroForm + texto pesquisável + OCR via LLM Vision (MVP 8 Fase 3)
  - **Heurísticas de seções implícitas** (MVP 8 Fase 4)
- **Relatório de extração** read-only (chars, paragraphs, tables_detected, text_boxes, pdf_layers, requirements detectados, module_hints, warnings).
- **Quarentena PII** — documento com PII detectado é bloqueado até GP liberar.
- **Deletar documento** com cascata no OCG (regra canônica: delete reduz confidence).
- **Detalhe do documento** com análise completa do Arguidor + gaps + show_stoppers + poor_definitions + improvement_suggestions + module_candidates + ocg_fields_to_update.
- **Polling adaptativo**: 2s enquanto há doc processando; 15s caso contrário.

### 2.7 Gatekeeper (`/projects/:id/gatekeeper`)

- **Avaliação dos 7 pilares** com score + status (ok/warning/blocker).
- **Items rastreados**: gaps, show_stoppers, poor_definitions, improvement_suggestions.
- **Módulos candidatos** (derivados da ingestão) com status de aprovação.
- **Summary**: total de gaps/show_stoppers/poor_definitions/suggestions + módulos pendentes/aprovados/rejeitados.
- **Indicador de bloqueadores ativos**.
- **Health do OCG** (confidence, depth).

### 2.8 Arguidor (`/projects/:id/arguider`)

- **Lista de perguntas dirigidas** geradas a partir da ingestão e da análise de legado.
- **Resposta do GP** a cada pergunta (texto + evidência opcional).
- **Ignorar item** com motivo (não conta como resolução).
- **Resolver item** — alimenta de volta o OCG (expand ou update).
- **Contexto OCG visível**: score atual, status, versão, confiança.
- **Disparo automático** após ingestão de documento / análise de repo externo.

### 2.9 Geração de Código (`/projects/:id/codegen`)

- **IDE-like com sidebar Git** — árvore de arquivos do repositório.
- **Sidebar colapsável** (toggle).
- **Geração de scaffold** a partir do `OCG.STACK_RECOMMENDATION`:
  - 8 scaffolders determinísticos: `java_spring`, `java_quarkus`, `kotlin_spring`, `go_app`, `csharp_aspnet`, `php_laravel`, `nodejs_nestjs`, `nodejs_express`
  - Python e outras linguagens: fallback LLM-only
  - Injeção automática de DDL do `OCG.DATA_MODEL` (5 dialetos SQL: PostgreSQL/MySQL/SQLite/SQL Server/Oracle + MongoDB)
  - 7 frameworks de migration (Alembic/Flyway/Knex/TypeORM/Laravel/EFCore/go-migrate)
- **Preview do scaffold antes de commit** (diff completo).
- **Apply scaffold** — commit no Git do projeto com mensagem canônica; emite `CODEGEN_SCAFFOLD_APPLIED`.
- **Regeneração granular por arquivo** — emite `CODEGEN_FILE_REGENERATED`.
- **Docstrings obrigatórias** em todo código gerado (§CODEGEN_RULES).
- **Validação pós-geração**: pyflakes / esprima / ast.parse conforme linguagem.
- **Contexto OCG usado** visível no prompt.

### 2.10 QA Readiness (`/projects/:id/qa`)

- **Requisitos de Testes** derivados do OCG.TESTING_REQUIREMENTS.
- **Cobertura de tests**: unit, integration, e2e, regression, load, security.
- **Execução de testes** com timeout configurável + registro de execução.
- **Logs JSONL por execução** armazenados.
- **Gate de qualidade** (quality_gate) configurado no questionário Q46.
- **QA formal** (formal_qa) opcional conforme Q47.

### 2.11 Revisão de Testes / Tester Review (`/projects/:id/tester-review`)

- **Abas por tipo de teste**: Specs (planos), Unit, Integration, E2E, Regression, Load, Security.
- **TestArtifactCard**: título, tipo, status, conteúdo, ações (editar/aprovar/rejeitar/executar) — MVP 14.6.
- **Specs tab**:
  - Geração automática de planos via Ollama (local) para unit/integration/e2e
  - Geração via Premium para security/compliance (MVP 10 Fase 10.3)
  - Aprovação / rejeição do plano
- **Modal de detalhe da spec** com visualização + edição + histórico + rejeição.
- **Logs de execução** toggleable por teste.
- **Stale detection** on-the-fly com banner (MVP 10 Fase 10.4).

### 2.12 Backlog (`/projects/:id/backlog`)

- **Backlog Vivo** derivado automaticamente do OCG (BACKLOG_REGENERATED a cada mudança relevante).
- **Itens categorizados** por `source_version` (rastreia de qual versão do OCG veio).
- **Filtros** por categoria/status/prioridade.
- **Regeneração forçada** quando OCG muda.

### 2.13 Roadmap (`/projects/:id/roadmap`)

- **Módulos categorizados** em 8 categorias canônicas (Foundation, Auth, Data, Business, Infra, UI, Integration, Compliance).
- **Progresso geral** do projeto.
- **Detalhamento on-demand** de cada módulo via Ollama (local).
- **Curadoria Premium** (readiness + DAG) com WebFetch curado (MVP 9 Fase 9.2.ext).
- **Plano de deploy** com export Markdown.
- **Ciclo reativo**: GP responde Arguidor → ingestão → módulo marcado `adicionado` → deliverable automático (MVP 9.5).

### 2.14 Documentação Viva (`/projects/:id/docs`)

- **Documentação completa do projeto** gerada automaticamente.
- **Geração por módulo** via Ollama (local).
- **Consolidação geral** via Premium.
- **Regeneração granular por tipo** (MVP 10.8).
- **Incremento automático** em cada commit do pipeline (BACKLOG_REGENERATED → LiveDocs).
- **Seção Modelo de Dados** (DT-076 Fase 5) com DDL inline.
- **Stale detection** com banner quando OCG mudou depois da última geração.
- **Viewer read-only** de documentos originais ingeridos (MVP 20).

### 2.15 Definition of Done / Readiness (`/projects/:id/readiness`)

- **Lista de deliverables** por categoria (doc, code, test, process, config, other).
- **Status por deliverable**: verified, present, declared, generating, manual_only, missing, waived, error.
- **Readiness % por categoria**.
- **Registry + geração automática** (Fases A-D do MVP 21): 7 generators cobrem os deliverables canônicos.

### 2.16 Auditoria do Pipeline (`/projects/:id/audit`)

- **Lista de fases executadas** no pipeline do projeto (ingestão, gatekeeper, arguider, codegen, qa) com duração + status + context JSON.
- **Filtro por fase e janela temporal**.
- **Drill-down por evento**.

### 2.17 Backups do Projeto (`/projects/:id/backups`)

- **Snapshots do projeto** (OCG + artefatos + DB metadata do projeto).
- **Criar backup manual**.
- **Restore** a partir de snapshot selecionado.
- **Retenção configurável** pelo GP.

### 2.18 Incidentes do Projeto (`/projects/:id/incidents`)

- **Lista de tickets do projeto** (escopo compartimentalizado).
- **Criar novo ticket** com severidade (BAIXO/MÉDIO/ALTO/CRÍTICO) + descrição + anexos (até 5 arquivos / 10 MB / 9 extensões).
- **Detalhe do ticket** com comentários + resolução.
- **Roteamento automático por papel**: Dev → bugs técnicos; GP → mudança de escopo; Support → sustentação.
- **Contexto obrigatório**: section_reference (autopreenchido) + flow_description (bloqueante).
- **Regra dura**: Admin sobrepõe Support; UI de Sustentação não promove.

### 2.19 Métricas do Projeto (`/projects/:id/metrics`)

- **AI usage** do projeto (mesmo formato do admin mas filtrado por `project_id`).
- **Eventos de audit** com `resource_id=project_id`.
- **Autorização**: Admin, Support ou membro aceito do projeto (guard `_require_project_access`).

### 2.20 Configurações do pipeline (implícito)

- **Polling intervals** configuráveis.
- **Timeout de análise** por tipo de documento.
- **Rate limits** em endpoints públicos (MVP 12.1 — slowapi).

---

## 3. Áreas Públicas / Externas

Entrada: não autenticada · Acesso: qualquer um com link/token

### 3.1 Solicitação Externa de Projeto (`/solicitar-projeto`)

- **Wizard de 2 passos** (refatorado na Sessão 22).
- **49 perguntas** em 7 blocos (A.1-A.7: Identidade, Escopo, Frontend, Backend, Dados, IA/Segurança, Testes).
- **Questionário com tooltips e N/A** em cada pergunta.
- **Link com expiração de 5 dias** (InvitationToken — RF-001).
- **PDF editável do questionário** (checkboxes + dropdown + Outros) para preenchimento offline + upload.
- **Validação server-side** antes de submeter.
- **Email ao Admin** quando submetido.

### 3.2 Login Separado por Contexto

- **Login Admin/usuário geral** (`/login`) — email + senha + verificação de primeiro acesso.
- **Login do Projeto** (`/p/:slug`) — GP entra direto no contexto do projeto (MVP 19 — sessão 19).
- **Reset de senha** (`/reset-password?token=...`) com validação de token.
- **Primeiro acesso** — troca de senha temporária obrigatória.
- **Aceitar convite** (`/accept-invitation?token=...`).

### 3.3 Wizard de Setup Inicial (`/setup`)

- **Bloqueado** após existir usuário na instância (idempotente).
- **Criação do primeiro Admin** + organização inicial.
- **Configuração inicial de provedor de IA** (opcional).
- **Status público** (`/setup/status`) — healthcheck para CI e2e + needs_setup boolean.

---

## 4. Infraestrutura Compartilhada

Acessível via backend; transversal a Admin e GP.

### 4.1 Fila assíncrona (Celery + Redis)

- **Broker Redis DB 1**, result DB 2.
- **Worker service** `gca-celery-worker` (concurrency=2, ACK late, retry bounded).
- **Signal handlers**: `task_failure` / `task_retry` / `task_success`.
- **DLQ in-memory** (cap 200 entries) com endpoints admin:
  - `GET /admin/celery/dlq` — inspeção
  - `GET /admin/celery/workers` — status dos workers
- **Tasks canônicas** (MVPs 13.3 e 14.1):
  - `pipeline_ingest_task`, `propagate_task`, `regenerate_backlog_task`
  - `reevaluate_gatekeeper_task`, `auto_generate_task`, `external_repo_fallback_task`
  - `notify_admins_submitted_task`, `send_analysis_email_task`
  - `trigger_n8n_analysis_task`, `generate_ocg_task`
- **Retry max bounded** + ACK late (tasks re-enfileiradas se worker cair).

### 4.2 Flower (Celery Monitoring)

- **Serviço `gca-celery-flower`** na porta `:5555` (MVP 14.10).
- **Persistência SQLite** (volume `gca-flower-data`) — histórico entre restarts.
- **UI**: filas, workers ativos, DLQ visual, task history, retry history.

### 4.3 Pipeline OCG

- **8-agent system**: Analyzer → 7 Pillar Specialists (P1-P7 em paralelo) → Consolidator.
- **OCG reativo** (delta-only): expande com boa ingestão, contrai com documento ruim/conflitante.
- **Propagação automática** quando OCG muda: regenera backlog, marca CodeGen/LiveDocs desatualizados, reavalia Gatekeeper, emite evento de audit.
- **context_health**: depth (0-1), confidence (0-1), quality.
- **Schema versionado** (`schema_version` no OCG).
- **Compartimentalização**: projetos nunca interferem entre si.

### 4.4 Hash chain de auditoria

- **SHA-256** encadeado em `audit_log_global`.
- **Verificação periódica** (`verify_chain`).
- **Eventos canônicos** em 26+ tipos (ver §1.4 Admin).
- **Helpers de emissão** (`log_event`, `log_role_event`, `log_project_event`, `log_questionnaire_event`, `log_codegen_event`, `log_ocg_event`).

### 4.5 Backup & Restore

- **Projeto** (`project_backup_service`) — snapshot inclui OCG + deliverables + artefatos.
- **Agendador global** com timezone configurável (MVP 12.2).
- **Rotação automática** com retenção por política.
- **Restore** com validação de integridade.

### 4.6 Vault (segredos e PATs)

- **AES-GCM** com master key rotacionável (Fernet).
- **Criptografia de PATs** (GitHub/GitLab/Bitbucket).
- **Criptografia de API keys** de provedores de IA.
- **Separação global vs projeto** (§6.5 compartimentalização).
- **Rotação de master key** sem perda de acesso.

### 4.7 RBAC Engine

- **5 papéis canônicos**: Admin · GP · Dev · Tester · QA.
- **Flag cross-instância** `is_support` (Admin herda).
- **Ações**: `require_action('nome')` + `require_admin`.
- **Guard de último Admin / último GP** em ações destrutivas.
- **Compartimentalização §2.2**: toda query com `project_id` no predicado.

### 4.8 Schema generator (DDL)

- **5 dialetos SQL**: PostgreSQL, MySQL, SQLite, SQL Server, Oracle.
- **MongoDB** como engine NoSQL suportado.
- **Idempotência** via dialeto específico (`ON CONFLICT`, `INSERT IGNORE`, `IF NOT EXISTS`, etc).
- **7 frameworks de migration** com output canônico:
  - Alembic · Flyway · Knex · TypeORM · Laravel · EFCore · go-migrate.
- **Matriz framework × dialeto** com skips explícitos (ex: Laravel pula Oracle; TypeORM/EFCore emitem stubs para Mongo).

### 4.9 Webhooks (n8n, Slack, Teams, Email)

- **Integração n8n** para orquestração externa.
- **Alertas de sistema** (criticidade: critical/warning/info).
- **Envio por canal**: Teams, Slack, email.
- **Health check de webhooks** com auditoria (`WEBHOOK_HEALTH_CHANGED`).

### 4.10 Observabilidade

- **Endpoint `/health`** consolidado (DB + broker + workers).
- **Endpoint `/metrics/prometheus`** (scrape externo).
- **Endpoint `/metrics/dashboard`** (JSON agregado, Admin-only).
- **Endpoint `/metrics/per-project`** (breakdown Admin-only).
- **Logs estruturados** (structlog) em JSON para agregação externa.

---

## 5. Regras Canônicas Aplicáveis a Ambas Áreas

- **Idioma**: PT-BR em comunicação, commits, comentários, docs.
- **Linguagem binária no GCA**: sim/não, deve/não deve — zero ambiguidade.
- **Dogfood**: instância atual é produto instalável por cliente, não SaaS.
- **Isolamento**: por projeto dentro da instância; nunca entre projetos.
- **Chave de IA**: cliente final escolhe; configurável por instância e/ou projeto.
- **Nenhum modelo local consolida OCG final sozinho** — §6.3 regra dura.
- **Alta criticidade exige modelo premium** de raciocínio.
- **Roteamento híbrido** (baixa/média/alta criticidade) auditável.
- **Docstrings obrigatórias** em código gerado.
- **Teste funcional + massa de dados** por arquivo gerado.
- **Sem feature nova sem MVP autorizado** (§7.0).
- **Stop-rule em fases > 2 dias** — parar e re-escopar.

---

## 6. Baseline técnico (2026-04-21)

- Backend: FastAPI + Python 3.11, SQLAlchemy async, Alembic, Celery[redis], slowapi.
- Frontend: React + TypeScript estrito, Zustand, TanStack Query, Tailwind CSS.
- DB: PostgreSQL (prod) + SQLite/MySQL/MSSQL/Oracle/Mongo (targets DDL para codegen).
- Fila: Redis 7 (broker DB 1, result DB 2).
- Orquestração externa: n8n.
- Observabilidade: Flower + Prometheus + structlog.
- **Suite**: 1506 testes backend passing (5 skipped).
- **Frontend**: tsc 1 error residual (DesignShowcase — backlog).
- **Any**: 20 ocorrências (baseline ≤20 atingido).
- **MVPs fechados**: 1-15.
