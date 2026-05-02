# Contratos do Pipeline n8n — GCA

Documento canônico que define o **input** e **output** esperado de cada nó do pipeline.
Cada teste em `backend/app/tests/n8n_pipeline/test_contracts.py` valida um destes contratos.

> **Regra de ouro:** se você editar um nó, atualize o contrato aqui antes — depois rode os testes para validar que o output bate.

---

## Workflow 01 — GCA Normalizer

### Fluxo

```
Webhook Trigger → Log Inicio → Verificar HMAC G0 → G0 Validar → IF G0?
  (false) → Callback erro G0 → Log Erro G0 (FIM)
  (true)  → Detectar formato → Precisa OCR? → [OCR LLM → Processar OCR] → Montar envelope → IF envelope?
            (false) → Callback erro G1 → Log Erro G1 (FIM)
            (true)  → Assinar HMAC → Despachar Conferente → Log Concluido (FIM)
```

### Nó 1 — Webhook Trigger

**Input (HTTP POST do backend):**
```json
{
  "ingestion_id": "uuid-v4",
  "project_id": "uuid",
  "document_bytes_base64": "string-base64",
  "document_metadata": {
    "filename": "string",
    "mime_type": "string",
    "size_bytes": "int"
  },
  "normalized_text": "string (opcional)",
  "provider_chain": [
    {"provider": "deepseek|anthropic|openai|gemini", "model": "string", "api_key": "string"}
  ],
  "callback_url": "string (opcional)"
}
```

**Output:**
```json
{
  "headers": {"x-gca-signature": "sha256=..."},
  "body": {<payload original>},
  "params": {},
  "query": {},
  "webhookUrl": "...",
  "executionMode": "production"
}
```

### Nó 4 — G0 - Validar entrada

**Input:** `{ valid: bool, detail: string }` (do Verificar HMAC G0)

**Output em SUCESSO:**
```json
{
  "_g0_status": "ok",
  "ingestion_id": "string",
  "project_id": "string",
  "document_bytes_base64": "string",
  "document_metadata": {...},
  "provider_chain": [...],
  "callback_url": "string|null",
  "timestamp": "string|null",
  "_received_at": "ISO-8601"
}
```

**Output em ERRO (qualquer causa):**
```json
{
  "_g0_status": "failed",
  "_g0_reason": "g0_input_invalid",
  "_g0_detail": "string descritiva do erro",
  "_http_status": 401|413|415|422,
  "ingestion_id": "string|null",
  "project_id": "string|null",
  "callback_url": "string|null"
}
```

**Validações:**
- HMAC válido (com bypass temporário)
- ingestion_id é UUID v4
- size_bytes ≤ 50MB
- mime_type ∈ ALLOWED_MIMES
- document_bytes_base64 presente
- project_id presente
- provider_chain não vazio

### Nó 12 — Assinar HMAC para Conferente

**Input (de Montar envelope normalizado):**
```json
{
  "ingestion_id": "string",
  "project_id": "string",
  "normalized_text": "string",
  "extraction_metadata": {...},
  "provider_chain": [...]
}
```

**HTTP Request body para `/internal/hmac/sign`:**
```json
{
  "body_raw": "JSON.stringify(envelope)",
  "secret_name": "NORMALIZER_SECRET"
}
```

**Output (resposta do backend):**
```json
{
  "signature": "sha256=..."
}
```

**⚠ PROBLEMA ATUAL:** O output só contém `signature`, mas o próximo nó "Despachar para Conferente" precisa do envelope completo + signature. Solução: usar `$('Montar envelope normalizado').item.json` no próximo nó.

### Nó 13 — Despachar para Conferente

**Esperado:**
- URL: `http://n8n:5678/webhook/gca-conferente` (deve apontar para webhook do Conferente)
- Header: `X-Normalizer-Signature: <signature do nó anterior>`
- Body: envelope completo (do nó "Montar envelope normalizado")

**Output esperado:** resposta do Conferente (HTTP 200 + `{message: "Workflow was started"}`)

**⚠ ERRO ATUAL:** "Workflow Webhook Error: Workflow could not be started!" — Conferente não inicia. Causas possíveis:
1. Conferente desativado (`active=false` na tabela workflow_entity)
2. Path do webhook incorreto
3. Body em formato que Conferente rejeita

---

## Workflow 02 — GCA Conferente

### Nó 1 — Webhook Trigger

**Path:** `/webhook/gca-conferente`

**Input esperado (do Normalizer):**
```json
{
  "ingestion_id": "string",
  "project_id": "string",
  "normalized_text": "string",
  "extraction_metadata": {...},
  "provider_chain": [...]
}
```

**Header:** `X-Normalizer-Signature: sha256=...`

### Demais nós: a documentar

---

## Workflows 03-14 — Especialistas

### Input padrão (do Conferente):

```json
{
  "ingestion_id": "string",
  "project_id": "string",
  "normalized_text": "string",
  "shared_context": {...},
  "provider_chain": [...]
}
```

**Header:** `X-Conferente-Signature: sha256=...`

### Output padrão (PersonaOutput v2):

```json
{
  "persona_tag": "GP|ARQ|DBA|DEV|QA|UX|UI|SEG|CONF|LGPD|NEG|AUD",
  "persona_name": "string",
  "ingestion_id": "string",
  "scores": {<5 dimensões>: 0-100},
  "avg_score": 0-100,
  "approved": "bool",
  "blocking": "bool (true só para CONF score<60)",
  "issues": [...],
  "questions": [...],
  "justification": "string",
  "metadata": {...}
}
```

---

## Workflow 15 — Consolidador

### Nó 1 — Webhook accumulate

**Path:** `/webhook/gca-consolidador-accumulate`

**Input:** PersonaOutput v2 (de qualquer especialista)

**Comportamento:** Acumula em Redis até `received_count == expected_count`, então dispara consolidação.

### Output final (callback ao GCA):

**URL:** `http://gca-backend:8000/api/v1/webhooks/ingestion-complete`

**Body (schema `IngestionCompletePayload`):**
```json
{
  "ingestion_id": "string",
  "project_id": "string",
  "status": "completed|failed|partial",
  "overall_score": "int|null",
  "blocked": "bool",
  "blocking_reason": "string|null",
  "personas_executed": ["GP", "ARQ", ...],
  "personas_failed": [],
  "ocg_individual": {...},
  "ocg_global_delta": {...},
  "conflicts_resolved": [],
  "consolidated_findings": [],
  "consolidated_recommendations": [],
  "execution_summary": {...}
}
```

**Header:** `X-N8N-Signature: sha256=...` (assinada com NORMALIZER_SECRET... CONFERIR)
