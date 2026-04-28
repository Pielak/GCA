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

### Impacto MVP 29.1

| Cenário | Antes | Depois |
|---------|-------|--------|
| Worker morre durante ingest | Task volta pra fila após 1h (visibility default Redis) | Task volta em 30min + idempotência guard pula reprocessamento |
| Watchdog reenfileira zombie | Task enfileirada 2x | 1ª execução completa, 2ª skipa via guard |
| Email task duplica | Email enviado 2x (visível) | 1ª envia, 2ª skipa (próximas fases: email dedup específico) |

### Impacto MVP 29.2

| Cenário | Antes | Depois |
|---------|-------|--------|
| Worker morre durante propagation | Task redistribui, corre 2x (backlog duplo) | Lease blocks 2ª execução por 10min, 1ª termina limpo |
| Worker morre durante backlog regen | Task redistribui, items deleted/recreated 2x | Lease blocks 2ª, estado final igual a 1x |
| Worker morre durante auto_generate | Task redistribui, deliverables regenerados 2x | Lease blocks 2ª, generators skip verified items |
| Múltiplas rodadas paralelas (race) | Task A + Task B rodam simultaneamente | Apenas 1 clama lease, outro retorna ok_idempotent |

---

## Próximas Fases (Planejadas)

### 29.2 — Idempotência Crítica (1d) ✅ COMPLETA
Implementar guards similares em:
- `propagate_task` — by ocg_version + timestamp ✅
- `auto_generate_task` — by ocg_version + trigger signature ✅
- `regenerate_backlog_task` — by ocg_version + timestamp ✅

**Implementação:** Lease-based dedup via Redis SET NX EX (TTL 600s).
- Key pattern: `gca:task:{task_name}:{project_id}:{ocg_version}`
- Se lease já claimado: return `ok_idempotent` (skip execution)
- Fail-open: Redis inacessível → executa (melhor 2x que travar)
- Commit: `63d9538`

### 29.3 — Watchdog + Smoke Tests (0.5d) ✅ COMPLETA
Refinar watchdog e validar idempotência end-to-end:
- Watchdog threshold: 8/10 min → 15 min (conservador, alinhado com visibility_timeout) ✅
- Testes de idempotência: 6 smoke tests, 100% PASS ✅
- Validação: guard + lease dedup + watchdog config + TTL suficiente ✅

**Implementação:**
- Watchdog timeout aumentado em celery_app.py beat_schedule
- 6 smoke tests: arquitetura + integração + configuração
- Commit: `eec6c02`

### 29.4 — Observabilidade + Fechamento (Planejada)
- Prometheus metrics: task redistributions, idempotent skips
- Docs de DT-075 no help
- Testes regressivos
- Merge final para produção

---

**Consolidação de Fases:**
- MVP 29.2: Consolidou original 29.2+29.3 (lease-based dedup em 3 tasks)
- MVP 29.3: Consolidou original 29.4 (watchdog tuning + smoke tests)
- MVP 29.4: Consolidado (observabilidade + fechamento)

---

## Checklist Fase 29.1

- [x] Atualizar celery_app.py com visibility_timeout + task_ignore_result
- [x] Implementar _check_document_already_analyzed() 
- [x] Adicionar guard em pipeline_ingest_task
- [x] Teste de compilação
- [x] Commit + merge
- [x] Validação: Celery config + idempotency guard verificado
- [x] Smoke test: Validação estrutural completa
