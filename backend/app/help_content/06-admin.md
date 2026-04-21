# Área Administrativa

Entrada: `/admin` — acesso exclusivo de Admin.

O Admin **não atua operacionalmente dentro dos projetos** — isso é papel do GP. O Admin governa a instância: usuários, projetos pendentes, auditoria, métricas, backups, provedores de IA, releases.

## Dashboard (`/admin`)

Visão consolidada da instância:

- **Métricas agregadas**: total de projetos, ativos, degradados, arquivados; usuários ativos, admins, inativos.
- **Gráfico de distribuição** dos projetos por status.
- **5 projetos mais recentes** com status, fase e perfil de output.
- **Auditoria recente** — últimos 5 eventos da instância.
- **Pesos dos 7 pilares** — sliders editáveis que ajustam o peso relativo de cada pilar no cálculo do score composto.
- **Thresholds** — valores de corte editáveis: quando bloquear por P7/P2, quando é READY, quando é NEEDS_REVIEW, quando é AT_RISK.

## Gestão de Usuários (`/admin/users`)

Escopo: todos os usuários da instância (não só admins).

- **Lista** com filtro por ativos/inativos/todos.
- **Convidar Administrador** — envia convite por email com token de 5 dias.
- **Bloquear** e **desbloquear** usuário — respeita a regra dura de "não deixar o último Admin sem acesso".
- **Excluir usuário** — mesma proteção.
- **Promover/rebaixar Admin** — seta ou remove o flag `is_admin`.

Convite externo de GP vem pelo fluxo de aprovação de projeto (ver próxima seção), não por aqui.

## Gestão de Projetos (`/admin/projects`)

- **Pendentes** — projetos que chegaram pela página pública `/solicitar-projeto`.
- **Aprovar** um pendente provisiona: organização + projeto + convite ao GP por email.
- **Rejeitar** exige motivo obrigatório (fica no histórico).
- **Alterar status** de projeto já existente: active, completed, archived, degraded.
- **Adicionar novo GP** a projeto existente (co-gestão).
- **Remover GP** de projeto (com proteção de último GP).
- `/admin/projects/:id` — visão somente-leitura do projeto: scores dos 7 pilares, overall score, status.

## Auditoria Global (`/admin/audit`)

Trilha de tudo que acontece na instância, com hash encadeado (cada entrada referencia o hash da anterior — qualquer alteração quebra a cadeia).

### Eventos que são rastreados

- **Projeto**: aprovação, rejeição, mudança de status.
- **Questionário**: submissão, aprovação, rejeição.
- **Ingestão**: documento ingerido, documento quarentenado.
- **Pipeline**: Gatekeeper avaliou, Arguidor abriu pergunta, Arguidor resposta registrada, backlog regenerado, doc viva atualizada.
- **OCG**: atualizado, revertido (rollback), consolidado.
- **CodeGen**: scaffold gerado, scaffold aplicado, arquivo regenerado.
- **QA**: execução requisitada, execução concluída.
- **Papéis**: concedido, revogado, transferido.
- **Outros**: credencial alterada, webhook com problema de saúde.

### Ferramentas

- **Filtros**: por tipo de evento, ator, recurso, janela temporal.
- **Verificar chain** — botão que percorre a cadeia e reporta se alguma entrada tem hash inconsistente.

## Métricas Operacionais (`/admin/metrics`)

Dashboard JSON com janela configurável (1 hora a 720 horas):

- **Uso de IA por provedor e operação**: chamadas, tokens de entrada/saída, custo em USD.
- **Uso de IA por projeto** — breakdown ordenado por custo.
- **Eventos de auditoria agregados por tipo**.

### Endpoint Prometheus

`GET /api/v1/metrics/prometheus` — texto no formato scrape-compatible para Grafana, Datadog, etc.

Métricas expostas:

- `gca_ai_calls_total` — contador de chamadas de IA por `provider` e `operation`.
- `gca_ai_tokens_total` — tokens por direção (in/out), provider, operation.
- `gca_ai_cost_usd_total` — custo agregado em USD.
- `gca_audit_events_total` — eventos de auditoria por tipo.
- `gca_projects_total` — gauge por status.
- `gca_users_total` — gauge por categoria (active, admin_active, inactive).
- `gca_celery_broker_reachable` — 0 ou 1.
- `gca_celery_workers_online` — workers ativos.
- `gca_celery_dlq_entries` — tarefas na DLQ.

### Healthcheck público

`GET /api/v1/metrics/health` responde sem autenticação — usado por load balancer ou k8s probe.

## Backups (`/admin/backups`)

Visão agregada de backups de **todos** os projetos (Admin vê global; GP vê apenas do próprio projeto em `/projects/:id/backups`).

- **Agendamento** configurável por timezone (env `BACKUP_TIMEZONE`).
- **Retenção** e **rotação** automáticas.
- **Download** direto de snapshot individual.
- **Restore** a partir de snapshot selecionado.

## Incidentes (`/admin/incidents`)

Tickets de incidente cross-instância:

- Filtro por severidade (BAIXO, MÉDIO, ALTO, CRÍTICO), status, projeto.
- Detalhe com comentários, histórico e roteamento automático por papel.
- Fechamento com auditoria.

## Sustentação (`/admin/support`)

Equipe de Sustentação — usuários com flag `is_support`:

- Lista dos membros da equipe.
- Promover/rebaixar papel de Support.
- Admin herda automaticamente a flag Support. A UI de Sustentação **não** promove ninguém a Admin — isso é exclusivo da gestão de usuários.

## Releases (`/admin/releases`)

- Lista agregada de releases por projeto.
- Detalhe em `/admin/releases/:releaseId`: status (pending, applied, rolled_back), bundle markdown, commits incluídos, evidência de testes.
- **Rollback** de release aplicado, com trilha de auditoria.

## Provedores de IA — configuração da instância

Em `/admin` → aba **"Provedores de IA"**:

- **Adicionar** Anthropic, OpenAI, DeepSeek ou Ollama (local).
- **Validar** a chave com o botão "Testar" antes de salvar.
- **Definir o padrão** da instância (usado pelo pipeline administrativo).
- **Remover** ou **substituir** chave.

Chaves ficam criptografadas no Vault (AES-GCM via Fernet com a `VAULT_MASTER_KEY` do ambiente).

### Separação entre instância e projeto

- **Chaves da instância (Admin)** — custo fica com a instância. Usadas pelo pipeline administrativo (geração inicial do OCG, reconsolidação, análises globais).
- **Chaves do projeto (GP)** — custo fica com o projeto. Usadas pelo dia-a-dia do projeto (Arguidor, ingestão, CodeGen).

GP configura as do projeto em `/projects/:id/settings` → aba IA. Se o projeto não tiver chave própria, operações do projeto caem em erro explícito — não usam a chave global silenciosamente.

## Rotinas de sistema

- **Limpeza de uploads antigos** — agendador periódico remove arquivos temporários.
- **Verificação de integridade da cadeia de auditoria** — job periódico percorre a chain.
- **Healthcheck completo** em `/health` mostra status do banco, broker Redis e workers Celery.

## Ver também

- [RBAC e papéis](?section=03-rbac) — os 5 papéis e permissões.
- [Observabilidade](?section=09-observabilidade) — endpoints de diagnóstico.
- [Solução de problemas](?section=10-troubleshooting) — FAQs operacionais.
