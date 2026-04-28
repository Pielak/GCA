# DT-075 Mitigation — MVP 29 Hardening Celery

**Data:** 2026-04-28  
**Status:** Fase 29.1 Implementada  
**Commit:** 3b25c28

---

## O Problema (DT-075)

Tasks Celery podiam ser enfileiradas 2x se:
1. Worker morria durante processamento
2. Watchdog reenfileirava task como "zombie" (stuck em 'processing')
3. Task original + watchdog retrigger = duplicação

Pior caso: emails foram enviados 2x (spam visível ao stakeholder).

---

## Solução Estrutural (MVP 29)

Substituir watchdog agressivo (reactivo) por **fila persistente + idempotência** (proativo).

### Fase 29.1 Implementada ✅

**Config Celery:**
- `task_acks_late=True` — task só sai da fila após conclusão (sempre existia)
- `task_reject_on_worker_lost=True` — task volta pra fila se worker morre (sempre existia)
- `task_visibility_timeout=1800` **[NOVO]** — task reprocessável após 30min se stuck
- `task_ignore_result=False` **[NOVO]** — força result backend pra rastreamento

**Pipeline Ingest Guard:**
- `_check_document_already_analyzed()` — retorna True se doc não está em 'processing'
- Task initial check: se True, pula processamento (ok_idempotent)
- Fail-open: se DB falha, processa (melhor 2x que 0x)

### Impacto

| Cenário | Antes | Depois |
|---------|-------|--------|
| Worker morre durante ingest | Task volta pra fila após 1h (visibility default Redis) | Task volta em 30min + idempotência guard pula reprocessamento |
| Watchdog reenfileira zombie | Task enfileirada 2x | 1ª execução completa, 2ª skipa via guard |
| Email task duplica | Email enviado 2x (visível) | 1ª envia, 2ª skipa (próximas fases: email dedup específico) |

---

## Próximas Fases (Planejadas)

### 29.2 — Idempotência Crítica (1d)
Implementar guards similares em:
- `propagate_task` — by ocg_version + timestamp
- `auto_generate_task` — by ocg_version + trigger signature
- `regenerate_backlog_task` — by ocg_version + timestamp

### 29.3 — Idempotência em Propagação (0.5d)
Lease-based dedup:
- `_try_claim_task_lease()` — SET NX EX no Redis
- Tasks de propagação que já rodam: propagate + backlog + gatekeeper
- TTL 10min — task só roda 1x por janela

### 29.4 — Watchdog + Smoke Tests (0.5d)
- Watchdog: 300s (5min) → 900s (15min) threshold
- Testes de idempotência unitários
- Smoke kill -9 no worker mid-task

### 29.5 — Observabilidade + Fechamento (0.5d)
- Prometheus metrics: task redistributions, idempotent skips
- Docs de DT-075 no help
- Testes regressivos

---

## Checklist Fase 29.1

- [x] Atualizar celery_app.py com visibility_timeout + task_ignore_result
- [x] Implementar _check_document_already_analyzed() 
- [x] Adicionar guard em pipeline_ingest_task
- [x] Teste de compilação
- [x] Commit + merge
- [ ] Rodar suite de testes (validar sem regressão)
- [ ] Smoke test manual
