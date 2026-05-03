# Pipeline n8n GCA — Documentação Operacional

**Data**: 2026-05-02
**Status**: Funcional end-to-end com DeepSeek. Smoke test verde em 135s.
**Branch**: `feat/exception-handling-canonical` (mudanças unstaged — precisa virar branch própria + commit)

---

## 1. Topologia (16 workflows, 18 ativos no n8n)

### 1.1. Workflows GCA (15)

```
backend (FastAPI / IngestionService._dispatch_to_n8n)
    │
    │ POST /webhook/gca-normalizer  (HMAC: GCA_WEBHOOK_SECRET)
    ▼
┌─────────────────────────────┐
│ 01-gca-normalizer-v3        │ G0 (HMAC + campos) → extrai texto → G1 (envelope)
└──────────────┬──────────────┘
               │ POST /webhook/gca-conferente  (HMAC: NORMALIZER_SECRET)
               ▼
┌─────────────────────────────┐
│ 02-gca-conferente-v3        │ G1 (HMAC) → classifier LLM → G2 (active_personas, doc_class)
└──────────┬──────────────────┘
           │ Redis bulk-set (expected_count, callback_url, project_id, shared_context, active_personas)
           │
           ├── POST /webhook/gca-specialist-{tag}  ×N  (HMAC: CONFERENTE_SECRET)
           │   ├── 04-gca-specialist-aud
           │   ├── 05-gca-specialist-arq
           │   ├── 06-gca-specialist-dba
           │   ├── 07-gca-specialist-dev
           │   ├── 08-gca-specialist-qa
           │   ├── 09-gca-specialist-ux
           │   ├── 10-gca-specialist-ui
           │   ├── 11-gca-specialist-seg
           │   ├── 12-gca-specialist-conf  (BLOQUEANTE — score < 60)
           │   ├── 13-gca-specialist-lgpd
           │   └── 14-gca-specialist-neg
           │
           └── POST /webhook/gca-orchestrator-gp  (HMAC: CONFERENTE_SECRET)
               └── 03-gca-orchestrator-gp
                   └── (cada um: Verificar HMAC → Validar HMAC → Montar LLM Request → LLM Call → Parse PersonaOutput → Callback Consolidador)
                       │
                       │ POST /webhook/gca-consolidador-accumulate  (HMAC: SPECIALIST_SECRET)
                       ▼
            ┌─────────────────────────────┐
            │ 15-gca-consolidador-v3      │ G4 (validar PersonaOutput) → Accumulate (Redis) → Todos chegaram?
            └──────────────┬──────────────┘
                           │ quando all_received: Calcular scores e merge → Callback final
                           │ POST {callback_url} (= /api/v1/webhooks/ingestion-complete)  (HMAC: N8N_CALLBACK_SECRET)
                           ▼
                       backend (handler ingestion_complete)
```

### 1.2. Auxiliar (1)

- **16-gca-pipeline-logger** — Error Workflow (n8n nativo). Roda **automaticamente** quando qualquer workflow GCA falha. Captura `errorData.execution.error.message` e POSTa em `/api/v1/webhooks/internal/pipeline-log`. Não precisa ser invocado manualmente.

---

## 2. Fluxo de dados — campos críticos

### 2.1. Backend → Normalizer (entrada do pipeline)

```python
# IngestionService._dispatch_to_n8n
n8n_payload = {
    "ingestion_id": uuid_str,
    "project_id": uuid_str,
    "document_bytes_base64": base64,
    "document_metadata": {filename, mime_type, size_bytes, uploaded_by, uploaded_by_role, declared_purpose},
    "provider_chain": [{"provider", "model", "api_key"}],
    "persona_prompts": dict[tag → systemPrompt],   # ← INJETADO nesta sessão
    "callback_url": ".../api/v1/webhooks/ingestion-complete",
    "timestamp": iso_utc,
}
# HMAC: sha256=<hex> com GCA_WEBHOOK_SECRET, header X-GCA-Signature
```

**12 tags em `persona_prompts`**: AUD, GP, ARQ, DBA, DEV, QA, UX, UI, SEG, CONF, LGPD, NEG.

Origem dos prompts: `backend/app/services/personas/prompts_registry.py` → `PERSONA_PROMPTS` dict, com `get_persona_prompt(tag)` que **levanta KeyError** se tag não-canônica (proibido fallback silencioso).

### 2.2. Normalizer → Conferente

Envelope `JSON.stringify`-ado, com `persona_prompts` propagado intacto:

```js
{
  ingestion_id, project_id, normalized_text, extraction_metadata,
  provider_chain, persona_prompts, callback_url, received_at
}
```

### 2.3. Conferente → Especialista (e GP Orquestrador)

Para **cada** persona ativa, payload de dispatch:

```js
{
  ingestion_id, project_id, normalized_text, extraction_metadata,
  provider_chain, callback_url, shared_context, doc_classification,
  chunking_strategy, persona_tag, systemPrompt,    // ← persona_prompts[tag]
  dispatched_at
}
```

Se `persona_prompts[tag]` ausente → **fail-fast** com `PROMPT_AUSENTE` (proibido cair em "Você é um especialista." genérico).

### 2.4. Especialista → Consolidador (PersonaOutput v2)

Cada especialista produz e envia:

```js
{
  schema_version: "PersonaOutput-v2",
  persona_tag, persona_name, ingestion_id,
  scores: {...}, avg_score, score,
  approved, blocking, blocking_reason,
  ocg_contributions: { individual: {...}, global_delta: {...} },  // ← chave canônica
  findings: [], recommendations: [], questions: [],
  // campos persona-específicos (audit_findings, chunk_tags, etc.)
}
```

### 2.5. Consolidador → Backend (callback final)

Quando `all_received` (Redis counter), Consolidador agrega e POSTa:

```js
{
  ingestion_id, project_id, status: "completed"|"partial",
  overall_score, blocked, blocking_reason,
  personas_executed: [...], personas_failed: [...],
  ocg_individual: { TAG: {...} },        // por persona, deste doc
  ocg_global_delta: { ...merged... },    // delta consolidado deste doc
  consolidated_findings: [...],
  consolidated_recommendations: [...],
  callback_url, execution_summary, completed_at
}
```

---

## 3. Cadeia HMAC — segredos (env)

| Hop | Secret enviado | Header verificado |
|---|---|---|
| Backend → Normalizer | `GCA_WEBHOOK_SECRET` | `X-GCA-Signature` |
| Normalizer → Conferente | `NORMALIZER_SECRET` | `X-Normalizer-Signature` |
| Conferente → Especialista/GP | `CONFERENTE_SECRET` | `X-Conferente-Signature` |
| Especialista/GP → Consolidador | `SPECIALIST_SECRET` | `X-Specialist-Signature` |
| Consolidador → Backend | `N8N_CALLBACK_SECRET` | `X-N8N-Signature` |

Backend tem `/internal/hmac/sign` e `/internal/hmac/verify` (`backend/app/routers/webhooks.py:626/640`) que aceitam `secret_name` por chave acima. n8n não computa HMAC sozinho — sempre delega ao backend.

**OBS** — G0 do Normalizer está com bypass temporário (`if (false && !hmacResult.valid)`); G1 do Conferente, todos especialistas e Consolidador validam. Bypass é dívida técnica conhecida (ver §6).

---

## 4. Campos opcionais que QUEBRAM se ausentes (lições da sessão)

| Campo | Onde | Sintoma se ausente |
|---|---|---|
| `webhookId` (no JSON do workflow) | Webhook Trigger node | n8n não registra rota → HTTP 404 ao chamar |
| `sendBody: true` no httpRequest | Qualquer POST do n8n | n8n manda body vazio → backend pydantic 422 |
| `sendHeaders: true` + `Content-Type: application/json` | Qualquer POST com JSON | n8n manda como form-urlencoded → backend pydantic 422 (loc=["body"], input=null) |
| `specifyBody: "json"` (NÃO `"string"` com `contentType: "json"`) | httpRequest do n8n | Combinação `specifyBody: string + contentType: json` envia o JSON como CHAVE de form-urlencoded |
| `persona_prompts` no payload | Backend `_dispatch_to_n8n` | `PROMPT_AUSENTE` no Conferente |
| `ingestion_id`, `callback_url` no return de `/accumulate` | Backend `webhooks.py` | Consolidador monta `finalResult.ingestion_id = undefined` → callback final 500 |

---

## 5. Bugs estruturais corrigidos nesta sessão (2026-05-02)

1. **Conferente conexões apontavam pra `Montar prompt Conferente`** (nó renomeado pra `Montar LLM Request`) → "Cannot read properties of undefined (reading 'name')" no startup do n8n. Fix: rename na chave de connections + nas refs `$('...')`.

2. **`Despachar especialistas` enviava `payload_json` com `specifyBody: "string"`** → n8n virou form-encoded apesar do Content-Type. Fix: `specifyBody: "json"` + `jsonBody: JSON.parse(payload_json)`.

3. **`webhookId` ausente em todos os 12 especialistas + GP** → webhooks não registravam (404). Fix: setar `webhookId = path` para cada Webhook Trigger.

4. **Especialistas/GP sem `sendBody: true` em `Log - Inicio` / `Verificar HMAC` / `Callback Consolidador`** → POSTs vazios → 422. Fix: forçar `sendBody: true` + `sendHeaders: true` + Content-Type explícito em todo httpRequest com URL `gca-backend:*` ou consolidador.

5. **`Validar HMAC` (JS code) lia de `webhookData.X` mas dispatch agora usa `specifyBody: json` → body fica em `webhookData.body.X`**. Fix: `webhookData = $('Webhook Trigger').item.json.body || $('Webhook Trigger').item.json`.

6. **`LLM Call` lia `$json.provider.api_url` mas `Montar LLM Request` produz `$json.llmUrl`** → URL undefined. Fix: usar `$json.llmUrl`, `$json.requestHeaders`, `$json.requestBody` direto.

7. **Conferente classifier prompt usava `persona_prompts['AUD']` (Auditor)** que retornava markdown em vez de JSON estruturado. Fix: prompt classifier inline curto, exigindo JSON estrito com `active_personas/doc_classification/shared_context`.

8. **Conferente `LLM - Classificar` URL hardcoded para OpenAI** quando provider é DeepSeek → 404. Fix: usar `$json.llmUrl` (calculado em Montar LLM Request com switch por provider).

9. **`Callback erro G1` no Normalizer não incluía `project_id`** → backend pydantic 422 quando G1 falhava. Fix: adicionar `project_id`.

10. **Backend `/accumulate` não retornava `ingestion_id` nem `callback_url`** → Consolidador montava `finalResult.ingestion_id = undefined`. Fix: incluir os 2 campos no return + persistir/limpar `callback_url` no Redis.

---

## 6. Dívidas técnicas conhecidas (não bloqueantes)

| Dívida | Onde | Impacto |
|---|---|---|
| Bypass HMAC em G0 (`if (false && !hmacResult.valid)`) | `01-gca-normalizer.json` G0 | Normalizer aceita request sem HMAC válido. Implementar antes de produção. |
| Workflows v2 antigos (`gca-normalizer-v2`, `a3f7c2e1...`) deactivated mas presentes | n8n SQLite | Confunde inventário. Apagar manualmente quando seguro. |
| DOCX não tem extrator nativo no Normalizer (`extractionMethod: 'pending_external'`) | `01-gca-normalizer.json` "Detectar formato e extrair texto" | Docs `.docx` falham em G1 ("texto vazio"). Tratar via OCR fallback ou lib mammoth. |
| `Log Erro` do Pipeline Logger pode falhar silenciosamente | `16-gca-pipeline-logger.json` | Errors não logados ficam só no n8n executions. |
| ~~**Backend `/ingestion-complete` faz UPDATE cru no `ocg`, não chama `OCGUpdaterService`**~~ | — | **RESOLVIDA pelo MVP 31 Fase 31.2** (2026-05-02). Handler em `webhooks.py` agora delega obrigatoriamente ao `OCGUpdaterService.update_ocg_from_arguider`. Histórico imutável em `ocg_individual` e `ocg_global` populado a cada doc. Política OCG-só-cresce via `_filter_negative_score_deltas` em vigor. |
| ~~**CodeGen não consulta `ocg.is_blocking`**~~ | — | **RESOLVIDA pelo MVP 31 Fase 31.4** (2026-05-02). Gate de maturidade (`check_ocg_maturity_gate`) implementado em `app/services/ocg_gate.py` e aplicado nos 6 entry points HTTP + `start_scaffold_run` async. 3 níveis: `hard_block`, `insufficient`, `immature`. |
| **DT-079**: Hardcode Anthropic em CodeGen (`_call_llm`, `generate_module_code`, etc.) | `module_codegen_service.py`, `codegen_prompt_builder.py` | (Major) Viola §3.1 do contrato — cliente não pode mudar provider de CodeGen sem código. Registrada para próximo MVP. |
| **DT-080**: ORM stubs `ocg_individual_refined` e `persona_follow_up_questions` sem corpo | `backend/app/models/base.py` | (Major) Tabelas existem no banco sem modelo funcional. Persistência via estas tabelas não funciona. |
| **DT-081**: OCGUpdaterService fallback `_load_persona_scores` quebrado + prompt sub-ótimo | `ocg_updater_service.py` | (Major) Fallback busca em `gatekeeper_persona_response` (Gatekeeper v1) em vez de `ocg_individual` (pipeline n8n). LLM prompt ainda cita contração de score (removida em 2026-04-25). |
| **DT-082**: Defesa em profundidade — gate ausente no worker Celery | `ingestion_service.py`, tasks Celery | (Minor) Caminho Celery não tem gate de maturidade de CodeGen. Risco baixo (caminho legado), mas inconsistência na política. |

---

## 7. Como rodar smoke test E2E

```bash
docker compose exec backend python -c '
import asyncio
from app.db.database import AsyncSessionLocal
from app.models.base import IngestedDocument
from app.services.ingestion_service import IngestionService
from app.utils.ingested_storage import read_ingested
from uuid import UUID
DOC_ID = UUID("...")  # documento existente com bytes em storage
PROJECT_ID = UUID("...")  # projeto com LLM configurado em project_settings.llm
async def main():
    async with AsyncSessionLocal() as db:
        doc = await db.get(IngestedDocument, DOC_ID)
        doc.arguider_status = "pending"; doc.arguider_stage = "queued"
        await db.commit()
        await IngestionService(db)._dispatch_to_n8n(
            doc.id, doc.project_id, doc.file_type,
            read_ingested(doc.project_id, doc.filename)
        )
asyncio.run(main())
'

# Acompanhar progresso:
tail -f logs/pipeline.log

# Quando concluir, status do doc:
docker compose exec postgres bash -c 'psql $POSTGRES_DB -U $POSTGRES_USER -c "SELECT arguider_status, arguider_stage, arguider_progress_percent, arguider_completed_at FROM ingested_documents WHERE id=\\'<doc-id>\\';"'
```

---

## 8. Pré-requisitos para o pipeline rodar

1. Containers up: `n8n`, `gca-backend`, `gca-postgres`, `gca-redis`.
2. Env vars no backend: `INGESTION_VIA_N8N=true`, `N8N_BASE_URL=http://n8n:5678`, todos os 5 secrets HMAC.
3. n8n com 18 workflows ativos (via `docker exec n8n n8n list:workflow --active=true`). Após restart de n8n, alguns webhooks podem ficar 404 por alguns segundos (lazy registration) — basta um POST para forçar o registro.
4. Projeto com LLM configurado em `project_settings.settings_json` (setting_type=`llm`), com `provider`, `model`, `api_key`, e `is_default=true`.
5. Documento ingerido pelo upload (cria row em `ingested_documents` + bytes em storage). Sem isso, `read_ingested` retorna None.

---

## 9. Para futuro debug — onde olhar primeiro

1. **Status do doc**: `SELECT arguider_status, arguider_stage, arguider_error_message FROM ingested_documents WHERE id=...`
2. **Pipeline log humanly-readable**: `logs/pipeline.log` (nginx tail, mostra cada nó com ✓/✗/▶/←)
3. **n8n executions**: `docker cp n8n:/home/node/.n8n/database.sqlite /tmp/ && sqlite3 /tmp/database.sqlite "SELECT id,status,workflowId FROM execution_entity ORDER BY id DESC LIMIT 20"`
4. **Detalhe de exec falhada**: `SELECT data FROM execution_data WHERE executionId=<id>` — JSON com índice numérico, resolver via Python.
5. **Backend logs**: `docker compose logs backend --since=10m | grep -aE "webhook|ingestion-complete|hmac"`
6. **Redis state durante pipeline**: `docker compose exec redis redis-cli -n 2 KEYS 'gca:ingestion:*'` (db=2 é o n8n).
