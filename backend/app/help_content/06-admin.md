# Área Administrativa

Entrada: `/admin` — Guard: `RequireAdmin` — Escopo: instância inteira.

Admin **não atua operacionalmente em projetos**. A responsabilidade é configurar a instância, governar usuários, aprovar projetos externos, ver saúde global e auditoria cruzada.

## 1. Dashboard (`/admin`)

- **Métricas agregadas**: total de projetos, ativos, degradados, arquivados; usuários ativos/admin/inativos.
- **Gráfico de distribuição** de projetos por status.
- **5 projetos mais recentes** com status + fase + perfil de output.
- **Auditoria recente** (últimos 5 eventos).
- **Pesos dos 7 pilares** (P1-P7) editáveis pelo Admin.
- **Thresholds de aprovação**: P7 bloqueante, Ready, Needs Review, At Risk.

## 2. Gestão de Usuários (`/admin/users`)

Escopo: usuários da instância (não apenas Admins).

- Lista filtrada por ativos/inativos/todos.
- **Convidar Administrador** — email + onboarding token (5 dias).
- **Bloquear/desbloquear** — respeita guard "último Admin ativo" (MVP 11.3).
- **Excluir user** — idem guard + cascata ORM (MVP 1 DT-027).
- **Promover/rebaixar Admin** — `set_admin_flag(True|False)` com guard.
- Cada ação emite `ROLE_GRANTED` ou `ROLE_REVOKED` em `audit_log_global` (MVP 11.4).

Convite externo de GP vem pelo fluxo de aprovação de projeto (item 3) ou pela aba de equipe dentro de um projeto; não por aqui.

## 3. Gestão de Projetos (`/admin/projects`)

- **Pendentes de aprovação** (vindos de `/solicitar-projeto`).
- **Aprovar** — provisiona org + project + convida GP. Emite `PROJECT_APPROVED`.
- **Rejeitar** — motivo obrigatório. Emite `PROJECT_REJECTED`.
- **Alterar status** (`active` → `archived` / `completed` / `degraded`) — emite `PROJECT_STATUS_CHANGED`.
- **Adicionar novo GP a projeto existente** (co-gestão), **remover GP** (com guard "último GP"), **transferir soberania** (disponível dentro do projeto também).
- `/admin/projects/:id` — visão read-only do projeto: scores por pilar + overall.

## 4. Auditoria Global (`/admin/audit`)

Trilha encadeada com hash chain SHA-256. Cada evento tem `previous_hash` + `current_hash`.

**Eventos canônicos cobertos** (MVPs 11.4, 13.5-13.7, 14.7, 14.8):

- **Projeto**: PROJECT_APPROVED · PROJECT_REJECTED · PROJECT_STATUS_CHANGED.
- **Questionário**: QUESTIONNAIRE_SUBMITTED · QUESTIONNAIRE_APPROVED · QUESTIONNAIRE_REJECTED.
- **CodeGen**: CODEGEN_SCAFFOLD_GENERATED · CODEGEN_SCAFFOLD_APPLIED · CODEGEN_FILE_REGENERATED.
- **OCG**: OCG_UPDATED · OCG_ROLLED_BACK · OCG_CONSOLIDATED.
- **Papéis**: ROLE_GRANTED · ROLE_REVOKED · ROLE_TRANSFERRED.
- **Pipeline**: DOCUMENT_INGESTED · DOCUMENT_QUARANTINED · GATEKEEPER_EVALUATED · ARGUIDER_RESPONSE_REGISTERED · BACKLOG_REGENERATED.
- **Outros**: CREDENTIAL_STATUS_CHANGED · WEBHOOK_HEALTH_CHANGED · AUDIT_CHAIN_VERIFIED.

Filtros: tipo de evento, ator, recurso, janela temporal. Botão **"Verificar chain"** roda `verify_chain()` e reporta se algum `previous_hash` não bate.

## 5. Métricas Operacionais (`/admin/metrics`)

Dashboard JSON agregado com janela configurável (1h–720h).

- **Uso de IA por provider × operation**: calls, tokens_in, tokens_out, cost_usd.
- **Uso de IA por projeto** — breakdown ordenado por custo desc.
- **Eventos de audit agregados por tipo**.
- **Endpoint Prometheus** (`/api/v1/metrics/prometheus`): gauges e counters scrape-ready:
  - `gca_ai_calls_total`, `gca_ai_tokens_total`, `gca_ai_cost_usd_total`.
  - `gca_audit_events_total`.
  - `gca_projects_total`, `gca_users_total`.
  - **MVP 14.10**: `gca_celery_broker_reachable`, `gca_celery_workers_online`, `gca_celery_dlq_entries`.
- **Healthcheck público** (`/api/v1/metrics/health`) sem auth — pra load balancer.

## 6. Backups (`/admin/backups`)

- Visão agregada de backups de **todos** os projetos (complementa visão por projeto do GP).
- Agendamento configurável por timezone (MVP 12.2 — env `BACKUP_TIMEZONE`).
- Retenção e rotação.
- Download direto de snapshot.

## 7. Incidentes (`/admin/incidents`)

Lista cross-instância de tickets de incidente:

- Filtro por severidade, status, projeto.
- Detalhe com comentários + histórico + roteamento automático por papel.
- Fechamento com auditoria.

## 8. Sustentação (`/admin/support`)

- Lista da equipe com flag cross-instância `is_support`.
- Promoção/rebaixamento.
- **Regra dura**: Admin herda Support automaticamente; UI de Sustentação **não** promove Support a Admin.

## 9. Releases (`/admin/releases`)

- Lista agregada por projeto.
- Detalhe em `/admin/releases/:releaseId`: status (pending/applied/rolled_back), bundle, commits incluídos, evidência de testes.
- Rollback de release aplicada com trilha.

## 10. Provedores de IA (configuração da instância)

- Anthropic Claude, OpenAI, DeepSeek, Qwen/Ollama local.
- Chaves criptografadas (AES-GCM via Fernet com `VAULT_MASTER_KEY`).
- Validação prévia — endpoint de teste confirma chave antes de salvar.
- Definir provedor padrão do pipeline Admin.
- **Separação canônica §6.5**: chaves globais do Admin **não são** usadas pelas operações de projeto — GP configura chaves próprias em `/projects/:id/settings`.

## 11. Rotinas de sistema

- **Limpeza de uploads antigos** (agendador periódico).
- **Verificação de integridade da cadeia de audit** (job periódico).
- **Healthcheck completo** em `/health` com bloco `celery.broker.reachable` + `celery.workers.workers/nodes` (MVP 13.2).

## Ver também

- [RBAC e papéis](?section=03-rbac)
- [Observabilidade](?section=09-observabilidade)
- [Solução de problemas](?section=10-troubleshooting)
