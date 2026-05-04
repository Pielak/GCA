---
name: gca-pipeline-debug
description: Use quando um doc fica preso em arguider_status='processing', quando overall_score=0 inexplicado, quando callback /ingestion-complete não chega, quando "Pipeline n8n: failed. Failed: []", quando Redis tem expected_count diferente de received_count, ou em qualquer "fui dormir e o pipeline travou". Ensina a sequência canônica de inspeção (pipeline.log → n8n sqlite com WAL → Redis → Postgres) e o cleanup canônico para desbloquear.
---

# Skill: Diagnosticar pipeline n8n travado no GCA

> Aprendizado consolidado de sessão real onde 4 docs em paralelo travaram com sintomas diferentes. Use ANTES de mexer no código — quase sempre o "bug" é workflow desativado, race no upload, ECONNRESET de LLM ou config faltante.

---

## 1. Sequência canônica de inspeção

Faça nesta ordem. Pular gera diagnóstico errado.

### 1.1. Estado do doc no Postgres
```sql
SELECT substring(id::text, 1, 8) as id,
       substring(original_filename, 1, 50) as fn,
       file_size_bytes, file_type,
       arguider_status, arguider_stage, arguider_progress_percent,
       arguider_error_message, created_at, updated_at
FROM ingested_documents
WHERE id = '<doc_id>';
```
- `processing` + `progress=0` há > 3min → travado.
- `arguider_stage='n8n_pipeline'` + sem progresso → morreu antes do callback.
- `arguider_stage='queued'` + outro doc processing → fila normal, OK.

### 1.2. Pipeline log estruturado
```bash
grep <ingestion_id_short> /home/luiz/GCA/logs/pipeline.log | tail -30
```
Procure pela cadeia esperada:
1. `01-normalizer/webhook STARTED`
2. `01-normalizer/despachar COMPLETED`
3. `02-conferente/webhook STARTED`
4. `02-conferente/dispatch COMPLETED` (×N personas)
5. `15-consolidador/webhook PERSONA_RESULT_RECEIVED [TAG]` (×N)
6. `15-consolidador/callback COMPLETED`

Onde parou = onde morreu. Faltando passo 1: backend nem despachou. Faltando 2: G0/G1 do Normalizer. Faltando 3: Normalizer não despachou pro Conferente. Faltando 4: Conferente caiu no LLM Classify. Faltando 5: persona específica caiu. Faltando 6: callback ao backend falhou.

### 1.3. n8n executions (com WAL — crítico)
```bash
rm -f /tmp/n8n.sqlite*
docker cp n8n:/home/node/.n8n/database.sqlite /tmp/n8n.sqlite
docker cp n8n:/home/node/.n8n/database.sqlite-shm /tmp/n8n.sqlite-shm
docker cp n8n:/home/node/.n8n/database.sqlite-wal /tmp/n8n.sqlite-wal
sqlite3 /tmp/n8n.sqlite "SELECT id, workflowId, status, startedAt, stoppedAt FROM execution_entity WHERE startedAt > datetime('now','-30 minutes') ORDER BY id DESC LIMIT 30;"
```
**Sem os 3 arquivos (sqlite + shm + wal) você lê snapshot velho** e pode achar que pipeline não rodou quando rodou.

### 1.4. Decodificar erro de execution n8n
A coluna `data` em `execution_data` é JSON com refs `["14"]` apontando para índices do array. Use:
```python
import sqlite3, json
conn = sqlite3.connect('/tmp/n8n.sqlite')
arr = json.loads(conn.execute("SELECT data FROM execution_data WHERE executionId='<id>'").fetchone()[0])
def deref(v):
    if isinstance(v, str) and v.isdigit():
        try: return arr[int(v)]
        except: return v
    return v
for item in arr:
    if isinstance(item, dict) and 'message' in item and 'code' in item:
        print('code:', deref(item['code']))
        print('message:', deref(item['message']))
        break
```

### 1.5. Redis state (n8n DB 2)
```bash
for k in expected_count received_count callback_url project_id active_personas; do
  echo -n "$k: "
  docker exec gca-redis redis-cli -n 2 get "gca:ingestion:<doc_id>:$k"
done
```
- `expected_count > received_count` + última atividade > 5min → persona caiu silenciosa, consolidador esperando para sempre.
- Tudo vazio → Conferente nunca executou (provável workflow desativado).

### 1.6. Logs n8n
```bash
docker logs n8n --since 10m 2>&1 | grep -iE "error|fail|aborted|conferente|consolidador|specialist" | tail -30
docker logs n8n --tail 30 2>&1 | grep "Activated workflow" | grep -iE "Normalizer|Conferente|Consolidador"
```
**Workflow não na lista de Activated** = desativado. Causa comum: `import:workflow` desativa, e restart não reativa sozinho se não foi reativado antes.

---

## 2. Causas comuns e fix imediato

| Sintoma | Causa | Fix |
|---|---|---|
| `expected_count` ausente em Redis | Conferente desativado ou crashou no LLM Classify | Reativar workflow + cleanup doc + redispatch |
| `executionTime: ~60000ms` + `ECONNRESET` em LLM | DeepSeek timeout (60s) | Subir timeout pro nó (ver `gca-n8n-workflow-mgmt`) |
| `expected=11 received=10` parado há > 5min | Persona caiu por ECONNRESET (rate limit DeepSeek em uploads paralelos) | Cleanup + dispatcher serial 1-por-vez |
| `webhook ... not registered` (404) | Workflow desativado | `n8n update:workflow --id=X --active=true` + restart |
| 4 docs subiram simultâneos, todos em `processing` | Race no `_dispatch_to_n8n` (pré-fix) | Garantir que `dispatch_first_pending_for_project` está sendo chamada (já corrigido em commit `f5ef571`) |
| OCR via LLM 404 com URL errada | PDF roteado pra Vision LLM, URL `api.openai.com/chat/completions` (sem `/v1/`) e/ou provider sem Vision | Usar pré-extrator backend (pdfplumber+Tesseract) — já implementado |
| `personas_failed=[]` mas pipeline morreu | Pipeline morreu antes do dispatch das personas (Normalizer ou Conferente) | Olhar pipeline.log — provavelmente G0/G1/envelope falhou |

---

## 3. Cleanup canônico (desbloquear sem risco)

### 3.1. Marcar doc como erro + limpar Redis + redispatch fila
```bash
# 1. Marcar erro com mensagem clara
docker exec gca-postgres psql -U gca -d gca -c "
UPDATE ingested_documents
SET arguider_status='error',
    arguider_stage='failed',
    arguider_error_message='<mensagem clara — sintoma + causa + ação sugerida>',
    updated_at=NOW()
WHERE id='<doc_id>' AND arguider_status='processing';
"

# 2. Limpar TODAS as chaves Redis daquele ingestion
docker exec gca-redis redis-cli -n 2 eval \
  "for _,k in ipairs(redis.call('keys', 'gca:ingestion:<doc_id>*')) do redis.call('del', k) end return 1" 0

# 3. Disparar próximo da fila (canônico)
docker exec gca-backend python -c "
import asyncio
from uuid import UUID
from app.db.database import AsyncSessionLocal
from app.services.ingestion_service import dispatch_first_pending_for_project
async def main():
    async with AsyncSessionLocal() as db:
        d = await dispatch_first_pending_for_project(db, UUID('<project_id>'))
        print('Despachou:', d)
asyncio.run(main())
"
```

### 3.2. Resetar doc para refazer pipeline (re-dispatch do MESMO doc)
Se quiser tentar de novo (não é re-upload):
```sql
-- ANTES limpe Redis (passo 2 acima)
UPDATE ingested_documents
SET arguider_status='pending', arguider_stage='queued',
    arguider_error_message=NULL, arguider_progress_percent=0
WHERE id='<doc_id>';
-- Depois chame dispatch_first_pending_for_project (passo 3)
```

### 3.3. NÃO faça
- Não rodar `pipeline_ingest_task.delay()` direto (bypassa fila + advisory lock).
- Não dropar `ocg_individual` rows pra "limpar": viola §2.4 OCG cumulativo.
- Não DELETE no Postgres do doc travado: hard-delete viola integridade — use soft-delete (`deleted_at=NOW()`) ou marque error.

---

## 4. Sinais de alarme (escala para humano)

- 3 docs travados consecutivos com mesmo sintoma → bug sistêmico, não trate caso a caso.
- Workflow desativando sem causa explícita → checar se `import:workflow` foi rodado em sessão recente.
- `parecer={}` em rows novas de `ocg_individual` → bug no consolidador n8n descartando dado (já fixado, mas regrediu se reapareceu).
- Overall OCG **caindo** com novos docs → contração indevida (ver `gca-ocg-monotonicity`).

---

## 5. Referências cruzadas

- `gca-n8n-workflow-mgmt` — como editar/importar/reativar workflows sem desativar.
- `gca-ingestion-pipeline-anatomy` — fluxo completo de ingestão.
- `gca-ocg-monotonicity` — invariante de score.
- `gca-hitl-questions-flow` — fluxo das `questions[]` das personas.
- CLAUDE.md §0 — antes de "fix rápido", confirme que entendeu o sintoma; não tome contorno silencioso.
