# Observabilidade

O GCA expõe 4 canais canônicos de observabilidade: healthcheck, métricas Prometheus, audit log com hash chain, e Flower (Celery UI).

## 1. Healthcheck

### `/api/v1/metrics/health` — público

Healthcheck público sem autenticação — usado por load balancer / k8s probe.

```bash
curl -fsS http://host:8000/api/v1/metrics/health
# {"status": "ok", "db": true}
```

Retorna `degraded` se DB query trivial falhar. Não depende de Redis ou workers — é o check mais leve possível.

### `/health` — consolidado (admin)

Bloco estendido com Celery broker + workers (MVP 13.2):

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

## 2. Métricas Prometheus

Endpoint: `GET /api/v1/metrics/prometheus?hours=24` — requer `audit:view` (admin).

Formato texto Prometheus scrape-compatible (sem prometheus_client como dep — texto montado manualmente pra footprint pequeno).

### Métricas canônicas

#### AI usage

```
# HELP gca_ai_calls_total Chamadas de LLM agregadas
# TYPE gca_ai_calls_total counter
gca_ai_calls_total{operation="analyze",provider="anthropic"} 247
gca_ai_calls_total{operation="consolidate",provider="anthropic"} 12
```

```
# HELP gca_ai_tokens_total Tokens consumidos por direção
# TYPE gca_ai_tokens_total counter
gca_ai_tokens_total{direction="in",operation="analyze",provider="anthropic"} 124573
gca_ai_tokens_total{direction="out",operation="analyze",provider="anthropic"} 18293
```

```
# HELP gca_ai_cost_usd_total Custo agregado em USD
# TYPE gca_ai_cost_usd_total counter
gca_ai_cost_usd_total{operation="analyze",provider="anthropic"} 0.37
```

#### Audit

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

#### Celery (MVP 14.10)

```
# HELP gca_celery_broker_reachable 1 se broker Redis respondeu, 0 caso contrário
# TYPE gca_celery_broker_reachable gauge
gca_celery_broker_reachable 1

# HELP gca_celery_workers_online Workers Celery respondendo ao inspect ping
# TYPE gca_celery_workers_online gauge
gca_celery_workers_online 1

# HELP gca_celery_dlq_entries Entradas atuais na DLQ in-memory (cap 200)
# TYPE gca_celery_dlq_entries gauge
gca_celery_dlq_entries 0
```

**Best-effort**: falha no broker não derruba o endpoint — métricas caem para 0/unreachable e o scrape externo alerta.

## 3. Audit log com hash chain SHA-256

Toda ação crítica emite entrada em `audit_log_global` com:

- `event_type` — um dos 26+ tipos canônicos (ver [cap. 6 — Admin § 4](?section=06-admin)).
- `actor_id`, `actor_email`, `resource_type`, `resource_id`.
- `details` — JSON com payload específico do tipo.
- `correlation_id` — agrupa eventos relacionados (ex: transferência GP emite 2 entradas com mesmo correlation).
- `previous_hash` + `current_hash` — SHA-256 encadeando o payload atual ao hash anterior.
- `created_at`.

### Verificação da integridade

`AuditService.verify_chain(limit)` itera registros ordenados por `created_at` e checa `entry.previous_hash == entries[i-1].current_hash`. Retorna `{valid, checked, errors}`.

Disponível:
- **UI** — botão "Verificar chain" em `/admin/audit`.
- **Job** — agendador periódico (roda a cada X horas).
- **Evento de saúde** — `AUDIT_CHAIN_VERIFIED` registrado após cada run bem-sucedida.

### Helpers canônicos de emissão

Em vez de `log_event` genérico, services usam helpers tipados:

| Helper | Eventos cobertos |
|---|---|
| `log_role_event` | ROLE_GRANTED / ROLE_REVOKED / ROLE_TRANSFERRED (MVP 11.4) |
| `log_project_event` | PROJECT_APPROVED / REJECTED / STATUS_CHANGED (MVP 13.5) |
| `log_questionnaire_event` | QUESTIONNAIRE_APPROVED / REJECTED (MVP 13.5) |
| `log_codegen_event` | CODEGEN_SCAFFOLD_GENERATED / APPLIED / FILE_REGENERATED (MVP 13.5) |
| `log_ocg_event` | OCG_ROLLED_BACK / OCG_CONSOLIDATED (MVP 14.7/14.8) |

Cada helper valida whitelist de `event_type` e monta payload canônico.

## 4. Flower — Celery Monitoring

Serviço `gca-celery-flower` expõe dashboard em `http://host:5555/`:

- Filas ativas com contagem de tasks.
- Workers online (heartbeat).
- Task history com duração, retry count, resultado.
- DLQ visual com detalhes de cada entrada.
- Persistência SQLite em volume `gca-flower-data` (histórico entre restarts — MVP 14.10).
- Conectado ao broker Redis DB 1; lê eventos emitidos pelo worker.

### DLQ in-memory

Cap 200 entries no `_DLQ_LOG_ENTRIES` (MVP 13.4). Endpoints admin:

- `GET /api/v1/admin/celery/dlq` — inspeção.
- `GET /api/v1/admin/celery/workers` — status dos workers ativos.

### Tasks canônicas sob monitoramento

- `ping` — healthcheck trivial (smoke em 1 hop).
- `pipeline_ingest_task` — disparada no upload de documento.
- `propagate_task` — propaga mudanças do OCG para consumidores.
- `regenerate_backlog_task` — regera backlog quando OCG muda.
- `reevaluate_gatekeeper_task` — reavalia pilares.
- `auto_generate_task` — CodeGen automático.
- `external_repo_fallback_task` — análise de repo legado.
- `notify_admins_submitted_task` — email a admins após submissão de questionário.
- `send_analysis_email_task` — email ao GP após análise concluída.
- `trigger_n8n_analysis_task` — dispara workflow n8n externo (opcional).
- `generate_ocg_task` — pipeline OCG de 8 agentes.

## 5. Logs estruturados

`structlog` em formato JSON, stdout — agregador externo (Grafana Loki, ELK, Datadog) consome direto.

Chaves canônicas:

- `event` — nome do evento (ex: `ingestion.started`, `ocg.consolidated`).
- `project_id`, `document_id`, `user_id`, `ocg_version`.
- `tokens_used`, `latency_ms`, `cost_usd` — para operações LLM.
- Nenhum PII em logs — nomes, emails, CPFs permanecem fora de structlog.

## Integração com ferramentas externas

- **Grafana** — scrape direto de `/api/v1/metrics/prometheus`. Dashboards custom pelo operador.
- **Loki / ELK** — coletor ingere stdout dos containers.
- **Sentry / Rollbar** — opcional, configura via env var `SENTRY_DSN` (não ativo por padrão).
- **PagerDuty / Slack / Teams** — via webhooks configurados em `/admin` → rotinas de alerta.

## Ver também

- [Solução de problemas](?section=10-troubleshooting) — diagnósticos específicos.
- [Área Administrativa § 5](?section=06-admin) — painel de métricas.
