---
name: gca-ingestion-pipeline-anatomy
description: Use ao adicionar feature que toca o ciclo de vida de um documento — pré-processamento de novo file_type, mudança no payload das personas, novo gate de validação, alteração na fila sequencial, ou debug do "porque o doc não chegou na persona X". Ensina o fluxo completo upload → dispatcher (advisory lock) → pré-extrator backend → n8n (Normalizer→Conferente→Specialists→Consolidador) → /ingestion-complete → próximo da fila.
---

# Skill: Anatomia do pipeline de ingestão GCA

> Mapa canônico ponta-a-ponta. Use sempre que precisar entender ONDE inserir lógica nova ou ONDE um dado é perdido.

---

## 1. Visão de alto nível

```
GP faz upload (UI ou CLI)
        │
        ▼
upload_document() → INSERT pending
        │
        ▼
dispatch_first_pending_for_project(project_id)  ← advisory lock por project_id
        │  (se algo já em processing → no-op, fica pending)
        │  (se nada → vira processing + dispatch)
        ▼
_dispatch_to_n8n() → pré-extrator (DOCX/PDF) + monta n8n_payload
        │
        ▼
[n8n pipeline — 5 workflows encadeados]
   01 Normalizer → 02 Conferente → 03 GP + (04..14) 11 Specialists → 15 Consolidador
        │
        ▼
POST /api/v1/webhooks/ingestion-complete
        │
        ├─ UPSERT ocg_individual (parecer = PersonaOutput-v2 inteiro)
        ├─ Extrai questions[] → INSERT persona_follow_up_questions (HITL)
        ├─ Atualiza ingested_documents.arguider_status='completed'
        ├─ Roda OCGUpdaterService (LLM ou fallback MAX-por-persona)
        └─ dispatch_first_pending_for_project() → próximo da fila
```

---

## 2. Backend — entry-points e estado

### 2.1. `upload_document(project_id, file_bytes, ...)`
**Local**: `backend/app/services/ingestion_service.py`

- Valida tipo, tamanho, PII (`_extract_text_for_pii_scan`).
- INSERT `IngestedDocument` com `arguider_status='pending'` (ou `quarantined` se PII).
- Retorna `{document_id, status, message}`.
- **NÃO dispatcha sozinho** — chama `dispatch_first_pending_for_project`.

### 2.2. `dispatch_first_pending_for_project(db, project_id)` *(canônico, módulo-level)*
**Local**: `backend/app/services/ingestion_service.py`

- `pg_advisory_xact_lock(hashtextextended(project_id, 0))` — atômico contra race.
- Se algum doc do projeto está `processing` AND `deleted_at IS NULL` → no-op.
- Senão pega o `pending` mais antigo (excluindo `file_type='questionnaire'`), seta `processing` + `arguider_stage='queued'` e despacha:
  - `INGESTION_VIA_N8N=true` → chama `IngestionService(db)._dispatch_to_n8n()`.
  - Senão → `pipeline_ingest_task.delay(...)` (Celery legacy).

**Chamado em 2 lugares**:
- `upload_document` (puxa o que acabou de chegar).
- Webhook `/ingestion-complete` (puxa o próximo quando o anterior termina).

### 2.3. `_dispatch_to_n8n()`
**Local**: `backend/app/services/ingestion_service.py`

Etapas:
1. Resolve `provider_chain` via `AIKeyResolver` (skill `gca-llm-resolver`).
2. **Pré-extrator backend** — converte arquivo em texto plain antes de mandar:
   - `docx` → `rich_docx_extractor.extract_rich_text` → `text/plain`.
   - `pdf` → `pdfplumber` (texto nativo) + `pytesseract` (Camada 2 OCR para páginas com `< 50 chars`) → `text/plain`.
3. Carrega `TechnicalQuestionnaire` mais recente com `status='submitted'` → monta `seed_shared_context = {questionnaire_responses, questionnaire_submitted_at}`.
4. Monta `n8n_payload` (com persona_prompts + provider_chain + callback_url + seed_shared_context).
5. Marca `arguider_status='processing'` + `arguider_stage='n8n_pipeline'`, commit.
6. POST HMAC-assinado para `http://n8n:5678/webhook/gca-normalizer`.

---

## 3. Pipeline n8n — fluxo de campo

| Workflow | Entrada | Faz | Saída |
|---|---|---|---|
| **01 Normalizer** | `n8n_payload` | G0 (mime+UUID+size), extrai texto (passthrough/pdf-heurístico/Vision OCR), monta envelope + `seed_shared_context` | POST → Conferente |
| **02 Conferente** | envelope | G1 valida, LLM Classify (escolhe N personas + `summary`), G2 valida resposta, **funde** `Object.assign({}, seed_shared_context, parsed.shared_context)`, grava Redis | Fan-out paralelo: dispatch para N specialists + GP orchestrator |
| **03..14 Specialists/GP** | payload por persona (com `shared_context` + `normalized_text` + `systemPrompt`) | LLM Call → parse PersonaOutput-v2 | POST → `/webhook/gca-consolidador-accumulate` |
| **15 Consolidador** | PersonaOutput-v2 (1 por persona) | G4 valida, accumulator Redis, quando `received >= expected` → `Calcular scores e merge` (MAX-por-persona, peso CONF=1.5 etc) | POST → backend `/ingestion-complete` |

Detalhe da propagação de campo: ver `gca-n8n-workflow-mgmt §3`.

---

## 4. `/ingestion-complete` — destino final

**Local**: `backend/app/routers/webhooks.py`

Recebe `IngestionCompletePayload` (com `ocg_individual` + `consolidated_findings` etc). Se `status in ('completed','partial')`:

1. **UPSERT `ocg_individual`** com `RETURNING id`. `parecer` = PersonaOutput-v2 inteiro (questions, findings, recommendations, scores).
2. **Extrai HITL questions** — para cada persona OK:
   - DELETE `persona_follow_up_questions WHERE document_id+persona_id AND status='pending'` (preserva `answered`).
   - INSERT 1 row por question (`question_text`, `context`, `question_order`, FK `ocg_individual_id`).
3. UPSERT `ocg_global` (parecer consolidado, conflicts, voting).
4. UPDATE `ingested_documents.arguider_status='completed'`, `arguider_progress_percent=100`.
5. **Roda `OCGUpdaterService.update_ocg_from_arguider`** (LLM ou fallback) — atualiza `ocg.pX_*_score` + `overall_score`, grava `ocg_delta_log`.
6. **`dispatch_first_pending_for_project(db, project_id)`** → puxa próximo da fila. Falha aqui é silenciosa (log warning).

Detalhe do HITL: ver `gca-hitl-questions-flow`. Detalhe do OCG update: ver `gca-ocg-monotonicity`.

---

## 5. Pontos de extensão (onde adicionar feature)

| Quero adicionar... | Edite |
|---|---|
| Novo `file_type` que precisa pré-extração | `_dispatch_to_n8n` (branch após DOCX/PDF) |
| Novo gate de validação no upload | `upload_document` antes do INSERT |
| Novo campo no contexto que personas precisam ver | `seed_shared_context` em `_dispatch_to_n8n` + `gca-n8n-workflow-mgmt §3` |
| Persona LLM nova (12ª, 13ª) | Conferente prompt (PERSONAS DISPONÍVEIS) + novo workflow specialist + `PERSONA_TO_PILLAR` em `ocg_consolidator_service.py` + `expected_count` lógica + persona_prompts |
| Novo `arguider_stage` na máquina de estado | `webhooks.py` `/ingestion-complete` + `IngestionPage.tsx` STATUS_MAP + filtros |
| Novo tipo de saída sintética (file_type sem pipeline) | `dispatch_first_pending_for_project` (filtro `_IngDoc.file_type != 'questionnaire'`) — adicionar exclusão similar |

---

## 6. Tipos sintéticos — NÃO entram no pipeline

| `file_type` | Origem | `arguider_status` ao criar | Por quê |
|---|---|---|---|
| `questionnaire` | Submit do TechnicalQuestionnaire | `completed` + `arguider_stage='questionnaire_synthetic'` | Já contém info estruturada — análise por personas redundante |
| `persona_followup` | Submit HITL por persona | `completed` + `arguider_stage='followup_synthetic'` | Q&A já é evidência humana validada |

Ambos têm `extraction-report` com branch dedicada em `ingestion_router.py` (lê do storage JSON, não do n8n).

---

## 7. Idempotência canônica

- **Hash sha256 canônico** de `responses` (questionnaire) ou `qa` (followup) + filtro `deleted_at IS NULL` evitam duplicatas pós-soft-delete.
- INSERT em `ocg_individual` usa `ON CONFLICT (document_id, persona_id) DO UPDATE` — re-tentativas seguras.
- Webhook `/accumulate` usa `RPUSH` em Redis — mesma persona dispara múltiplas vezes só duplica entry, mas `received_count` segue `INCR` então o `>=expected` ainda dispara.
- Watchdog DT-073 reconcilia docs órfãos (sem callback há > N min).

---

## 8. Referências cruzadas

- `gca-pipeline-debug` — quando algo dá errado.
- `gca-n8n-workflow-mgmt` — para mexer nos workflows.
- `gca-ocg-monotonicity` — invariante de score depois do `/ingestion-complete`.
- `gca-hitl-questions-flow` — extração de `questions[]` em detalhe.
- `gca-llm-resolver` — provider chain.
- `gca-personas-engine` — Conjunto B + 12 personas.
- CLAUDE.md §2.4 (OCG), §3.4 (gate canônico), §6 (gotchas operacionais).
