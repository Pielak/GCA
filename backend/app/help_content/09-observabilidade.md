# Observabilidade

O GCA expõe 4 canais canônicos de observabilidade: healthcheck, métricas em formato Prometheus, auditoria encadeada e Flower (monitoramento da fila).

## 1. Healthcheck

### Público — `/api/v1/metrics/health`

Healthcheck sem autenticação — usado por load balancer ou k8s probe:

```bash
curl -fsS http://host:8000/api/v1/metrics/health
# {"status": "ok", "db": true}
```

Responde `degraded` se o banco falhar numa query trivial. **Não depende** de Redis ou workers — é o check mais leve possível.

### Consolidado — `/health` (autenticado, uso Admin)

Status estendido com Celery:

```json
{
  "status": "ok",
  "db": { "reachable": true },
  "celery": {
    "broker": { "reachable": true },
    "workers": {
      "workers": 1,
      "nodes": ["celery@<hostname-container>"]
    }
  }
}
```

## 2. Métricas em formato Prometheus

Endpoint: `GET /api/v1/metrics/prometheus?hours=24` — exige permissão `audit:view` (Admin).

Responde texto scrape-compatible; não exige `prometheus_client` como dependência — é texto montado pelo próprio GCA.

### Métricas disponíveis

#### Uso de IA

```
# HELP gca_ai_calls_total Chamadas de LLM agregadas
# TYPE gca_ai_calls_total counter
gca_ai_calls_total{operation="analyze",provider="anthropic"} 247
gca_ai_calls_total{operation="consolidate",provider="anthropic"} 12

# HELP gca_ai_tokens_total Tokens consumidos por direção
# TYPE gca_ai_tokens_total counter
gca_ai_tokens_total{direction="in",operation="analyze",provider="anthropic"} 124573
gca_ai_tokens_total{direction="out",operation="analyze",provider="anthropic"} 18293

# HELP gca_ai_cost_usd_total Custo agregado em USD
# TYPE gca_ai_cost_usd_total counter
gca_ai_cost_usd_total{operation="analyze",provider="anthropic"} 0.37
```

#### Auditoria

```
# HELP gca_audit_events_total Eventos de audit por tipo
# TYPE gca_audit_events_total counter
gca_audit_events_total{event_type="DOCUMENT_INGESTED"} 48
gca_audit_events_total{event_type="OCG_UPDATED"} 19
```

#### Projetos e usuários

```
# HELP gca_projects_total Projetos por status
# TYPE gca_projects_total gauge
gca_projects_total{status="active"} 3
gca_projects_total{status="completed"} 1

# HELP gca_users_total Usuários por categoria
# TYPE gca_users_total gauge
gca_users_total{category="active"} 5
gca_users_total{category="admin_active"} 1
gca_users_total{category="inactive"} 0
```

#### Celery

```
# HELP gca_celery_broker_reachable 1 se o broker respondeu, 0 caso contrário
# TYPE gca_celery_broker_reachable gauge
gca_celery_broker_reachable 1

# HELP gca_celery_workers_online Workers Celery respondendo ao inspect ping
# TYPE gca_celery_workers_online gauge
gca_celery_workers_online 1

# HELP gca_celery_dlq_entries Entradas atuais na DLQ in-memory (cap 200)
# TYPE gca_celery_dlq_entries gauge
gca_celery_dlq_entries 0
```

As métricas de Celery são **best-effort** — se o broker estiver fora, o endpoint responde mesmo assim com as gauges zeradas/unreachable; scrape externo (Prometheus, Grafana) alerta.

## 3. Auditoria encadeada

Toda ação crítica emite entrada em `audit_log_global` com:

- `event_type` — um dos tipos canônicos (ver abaixo).
- `actor_id`, `actor_email`, `resource_type`, `resource_id`.
- `details` — JSON com payload específico do evento.
- `correlation_id` — agrupa eventos relacionados (ex.: transferência de GP gera 2 eventos com o mesmo correlation).
- `previous_hash` + `current_hash` — SHA-256 encadeando o payload atual ao hash anterior.
- `created_at`.

### Tipos de evento

- **Projeto**: `project_approved`, `project_rejected`, `project_status_changed`.
- **Questionário**: `QUESTIONNAIRE_SUBMITTED`, `questionnaire_approved`, `questionnaire_rejected`.
- **Papéis**: `role_granted`, `role_revoked`, `role_transferred`.
- **OCG**: `OCG_UPDATED`, `ocg_rolled_back`, `ocg_consolidated`.
- **Ingestão**: `DOCUMENT_INGESTED`, `DOCUMENT_QUARANTINED`.
- **Pipeline**: `GATEKEEPER_EVALUATED`, `ARGUIDER_QUESTION_OPENED`, `ARGUIDER_RESPONSE_REGISTERED`, `BACKLOG_REGENERATED`, `LIVEDOCS_UPDATED`.
- **CodeGen**: `codegen_scaffold_generated`, `codegen_scaffold_applied`, `codegen_file_regenerated`, `CODEGEN_REQUESTED`, `CODEGEN_COMPLETED`, `CODE_VALIDATION_COMPLETED`.
- **QA**: `QA_EXECUTION_REQUESTED`, `QA_EXECUTION_COMPLETED`.
- **Credenciais**: `CREDENTIAL_STATUS_CHANGED`.
- **Webhooks**: `WEBHOOK_HEALTH_CHANGED`.
- **Chain**: `AUDIT_CHAIN_VERIFIED` registrado após cada run de verificação.

### Verificação de integridade

A integridade da cadeia pode ser verificada percorrendo os registros ordenados por timestamp e checando se cada `previous_hash` bate com o `current_hash` do anterior.

- **UI** — botão "Verificar chain" em `/admin/audit`.
- **Job periódico** — agendador dispara a verificação a cada X horas.
- **Evento de saúde** — cada verificação bem-sucedida gera `AUDIT_CHAIN_VERIFIED`.

## 4. Flower — monitoramento do Celery

Painel web em `http://host:5555/` mostra em tempo real:

- **Filas ativas** com contagem de tarefas pendentes.
- **Workers online** (heartbeat).
- **Histórico de tarefas** com duração, retry count, resultado.
- **DLQ** (tarefas que falharam após todos os retries) com detalhes.

Persistência: SQLite em volume `gca-flower-data` — histórico sobrevive a restart.

### Endpoints Admin relacionados

- `GET /api/v1/admin/celery/dlq` — lista de tarefas na DLQ (cap 200 entries in-memory).
- `GET /api/v1/admin/celery/workers` — status detalhado dos workers ativos.

### Tarefas que você vai ver no Flower

- `ping` — healthcheck trivial (~60ms roundtrip).
- `pipeline_ingest_task` — processamento de documento ingerido.
- `propagate_task` — propaga mudanças do OCG para os consumidores.
- `regenerate_backlog_task` — regera o backlog quando o OCG muda.
- `reevaluate_gatekeeper_task` — reavalia pilares após mudança.
- `auto_generate_task` — CodeGen automático.
- `external_repo_fallback_task` — análise de repositório legado.
- `notify_admins_submitted_task` — envia email a admins quando questionário é submetido.
- `send_analysis_email_task` — envia email ao GP após análise.
- `trigger_n8n_analysis_task` — dispara workflow externo no n8n (quando configurado).
- `generate_ocg_task` — pipeline dos 8 agentes.

## 5. Logs estruturados

O backend emite logs em JSON estruturado (via `structlog`) diretamente em stdout. Agregadores externos (Grafana Loki, ELK, Datadog) consomem direto.

Chaves canônicas:

- `event` — nome do evento (ex.: `ingestion.started`, `ocg.consolidated`).
- `project_id`, `document_id`, `user_id`, `ocg_version` — identificadores de contexto.
- `tokens_used`, `latency_ms`, `cost_usd` — telemetria de operações de IA.

**Não há PII nos logs** — nomes, emails e CPFs não aparecem em `structlog`. O audit log guarda isso com o tratamento adequado.

## Integração com ferramentas externas

- **Grafana** — scrape direto de `/api/v1/metrics/prometheus`. Dashboards são custom do operador.
- **Loki / ELK** — coletor ingere stdout dos containers.
- **Sentry / Rollbar** — opcional; configurar via env var `SENTRY_DSN` (não ativo por padrão).
- **Alertas (PagerDuty, Slack, Teams)** — via webhooks configurados em rotinas de alerta do Admin.

## Ver também

- [Solução de problemas](?section=10-troubleshooting) — diagnósticos específicos.
- [Área Administrativa](?section=06-admin) — painel de métricas.
