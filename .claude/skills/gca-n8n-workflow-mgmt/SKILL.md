---
name: gca-n8n-workflow-mgmt
description: Use ao editar qualquer arquivo em n8n-workflows/*.json, ao adicionar campo novo no payload propagado entre Normalizer→Conferente→Specialists→Consolidador, ao ajustar timeout de chamada LLM, ou quando webhook responde 404 "not registered". Ensina os ritos de import/restart/ativação que evitam workflow desativado, o padrão de propagação de campo na cadeia, o accumulator Redis, e quirks específicos do n8n self-hosted v2.x.
---

# Skill: Gestão de workflows n8n no GCA

> Existe porque `import:workflow` desativa silenciosamente, o restart preserva apenas workflows que **já estavam ativos**, e o n8n não tem hot-reload — qualquer JSON editado precisa de cerimônia.

---

## 1. Workflows do GCA (16 ativos)

| ID | Função | Webhook entrada |
|---|---|---|
| `gca-normalizer-v3` | Recebe upload, extrai texto, valida G0/G1, despacha pro Conferente | `gca-normalizer` |
| `gca-conferente-v3` | LLM Classify, escolhe personas (G2), grava expected no Redis, dispatch fan-out | `gca-conferente` |
| `gca-orchestrator-gp` | Persona orquestradora (sempre +1 no expected) | `gca-orchestrator-gp` |
| `gca-specialist-{aud,arq,dba,dev,qa,ux,ui,seg,conf,lgpd,neg}` | Especialistas (11 paralelos) | `gca-specialist-<tag>` |
| `gca-consolidador-v3` | G4 valida PersonaOutput, accumulator, merge, callback ao backend | `gca-consolidador-accumulate` |
| `gca-pipeline-logger` | Error workflow (assina handlers de erro) | — |

---

## 2. Editar + reativar — rito canônico (4 passos)

```bash
# 1. Editar arquivo /home/luiz/GCA/n8n-workflows/<wf>.json (Edit tool)

# 2. Copiar pro container e importar (DESATIVA o workflow)
docker cp /home/luiz/GCA/n8n-workflows/<wf>.json n8n:/tmp/<wf>.json
docker exec n8n n8n import:workflow --input=/tmp/<wf>.json

# 3. Reativar via CLI (não tem efeito imediato — exige restart)
docker exec n8n n8n update:workflow --id=<wf-id> --active=true

# 4. Restart do container — agora reativa
docker restart n8n
until docker logs n8n 2>&1 | tail -80 | grep -q "Editor is now accessible"; do sleep 2; done
docker logs n8n --tail 30 2>&1 | grep "Activated workflow.*<wf-id>"
```

**Validação obrigatória**: o `grep` do passo 4 DEVE retornar a linha. Se vazio = ainda desativado. Curl rápido:
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST http://localhost:5678/webhook/<webhook-name> -H "Content-Type: application/json" -d '{}'
# 200 = ativo. 404 = desativado.
```

### Múltiplos workflows na mesma rodada
Faça os 3 passos 1+2 pra TODOS, depois UM `update:workflow` por workflow, depois UM restart final. Restart no meio desativa de novo.

---

## 3. Padrão de propagação de campo na cadeia

Adicionar campo novo (ex: `seed_shared_context`) que precisa chegar nas personas exige edição em **5 nodes encadeados**:

### 3.1. Backend → Normalizer
`backend/app/services/ingestion_service.py:_dispatch_to_n8n` — adicionar no `n8n_payload`:
```python
n8n_payload = {
    ...,
    "seed_shared_context": seed_shared_context,
}
```

### 3.2. Normalizer "Montar envelope normalizado"
`01-gca-normalizer.json` — incluir no `envelope`:
```js
const envelope = {
  ...,
  seed_shared_context: item.seed_shared_context || {},
};
```

### 3.3. Conferente "G1 - Validar entrada"
`02-gca-conferente.json` — destructure + retornar:
```js
const { ..., seed_shared_context } = body;
return [{ json: { ..., seed_shared_context: seed_shared_context || {} } }];
```

### 3.4. Conferente "Parse resposta e G2"
`02-gca-conferente.json` — fundir com shared_context do LLM (NÃO sobrescrever):
```js
shared_context: Object.assign({}, upstream.seed_shared_context || {}, parsed.shared_context || {}),
```

### 3.5. Specialists já leem `data.shared_context`
**Não precisa editar os 12 specialists** — eles já fazem `JSON.stringify({ normalized_text, shared_context })` no userMessage da LLM. Por isso o **fix mínimo é fundir no Conferente, não inventar campo separado**.

---

## 4. Accumulator Redis (consolidador)

Conferente grava no Redis (DB 2):
```
gca:ingestion:<id>:expected_count    → "11" ou "12"
gca:ingestion:<id>:project_id        → UUID
gca:ingestion:<id>:active_personas   → JSON list ["ARQ","DBA",...]
gca:ingestion:<id>:callback_url      → "http://gca-backend:8000/api/v1/webhooks/ingestion-complete"
gca:ingestion:<id>:shared_context    → JSON
```
TTL 3600s.

Cada specialist callback `/accumulate` faz:
- `RPUSH gca:ingestion:<id>:results <PersonaOutput-v2 JSON>`
- `INCR gca:ingestion:<id>:received_count`
- Se `received >= expected` → consolidador chama `Calcular scores e merge` → callback ao backend.

**Quirks**:
- Se persona crashou (ECONNRESET DeepSeek) o `received_count` nunca chega no `expected_count` → consolidador espera para sempre. Cleanup manual (ver `gca-pipeline-debug §3`).
- `expected_count` varia por doc (Conferente classifica e escolhe N personas relevantes — 11 ou 12 incluindo GP).

---

## 5. Quirks importantes do n8n self-hosted v2.x

| Quirk | Como evitar |
|---|---|
| `import:workflow` desativa | Sempre rodar `update:workflow --active=true` + restart depois |
| `update:workflow --active=true` SEM restart não tem efeito | Sempre restart depois |
| `restart n8n` reativa só workflows que estavam ativos pré-restart | Confirme com grep "Activated workflow" |
| Code node SEM `require()` e SEM `$env` | Use só APIs nativas JS + `Buffer` |
| `alwaysOutputData=true` em TODOS os nodes | Senão, IF + branch silencioso bloqueia execução |
| HTTP node v4.2: timeout vai em `options.timeout` (ms) | Default = 5min se omitido; LLM Vision/Classify atualmente em 300000 (5min) |
| Erro JSON com refs `["14"]` | Use `deref()` recursivo (ver `gca-pipeline-debug §1.4`) |
| n8n usa SQLite com WAL — `docker cp` precisa dos 3 arquivos | `database.sqlite + .sqlite-shm + .sqlite-wal` |
| Workflow ID ≠ name visível | Use `workflowId` (slug) nos comandos CLI, não nome |

---

## 6. Checklist de PR que toca workflow n8n

- [ ] Arquivo `n8n-workflows/<wf>.json` editado.
- [ ] Backup mental do que estava antes (commit prévio cobre).
- [ ] Passos 1-4 da §2 executados.
- [ ] Curl no webhook retornou 200.
- [ ] 1 ingestão de teste end-to-end completou (pipeline.log mostra cadeia completa).
- [ ] Se mudança propaga campo: §3 cobre os 4 elos (não só o último).
- [ ] Se mudança envolve LLM call: timeout em `options.timeout` revisitado.
- [ ] Commit do JSON inteiro (n8n não suporta diff parcial — JSON é fonte de verdade).

---

## 7. Referências cruzadas

- `gca-pipeline-debug` — quando algo deu errado.
- `gca-ingestion-pipeline-anatomy` — fluxo completo de ponta a ponta.
- `gca-personas-engine` — Conjunto B + 12 personas LLM (já existe).
- CLAUDE.md §6 (gotchas) — `docker compose up -d` vs `restart`.
