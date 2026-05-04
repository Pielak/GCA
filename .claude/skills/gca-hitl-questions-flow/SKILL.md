---
name: gca-hitl-questions-flow
description: Use ao tocar o fluxo Human-In-The-Loop das personas — questions[] do PersonaOutput-v2, tabela persona_follow_up_questions, sub-abas por persona em "Questões em Aberto", botões Salvar/Validar Escopo/Submeter, IngestedDocument file_type='persona_followup'. Define a cadeia completa origem (LLM persona) → persistência (FK ocg_individual_id) → UI (sub-abas com gating parcial) → submit (cria evidência + DELETE só answered).
---

# Skill: HITL — fluxo das perguntas das personas

> Filosofia "Assistida" (CLAUDE.md §3.5): persona LLM tem permissão explícita de **não saber** e perguntar ao humano. Esta skill mapeia ponta-a-ponta o que essa pergunta vira: Redis temporário → row no banco → UI sub-aba → resposta do GP → documento de evidência permanente.

---

## 1. Cadeia origem → destino

```
LLM persona emite PersonaOutput-v2 com questions[]
        │
        ▼
Specialist n8n → POST /webhook/gca-consolidador-accumulate
        │
        ▼
Backend /accumulate (webhooks.py) → RPUSH Redis (PersonaOutput inteiro)
        │  (espera received >= expected)
        ▼
Consolidador n8n "Calcular scores e merge" → POST /ingestion-complete
        │  (preserva PersonaOutput inteiro em ocg_individual via Object.assign — vide gca-n8n-workflow-mgmt §3)
        ▼
Backend /ingestion-complete (webhooks.py)
   ├─ UPSERT ocg_individual com RETURNING id
   ├─ DELETE persona_follow_up_questions WHERE doc+persona AND status='pending'
   │  (preserva 'answered' que humano já respondeu)
   └─ INSERT 1 row por question (FK ocg_individual_id)
        │
        ▼
GET /api/v1/projects/{pid}/pipeline-questions
        │  (JOIN ingested_documents WHERE deleted_at IS NULL)
        ▼
Frontend: PersonaFollowUpTabs (aba "Questões em Aberto")
   ├─ sub-abas por persona com badge de contagem
   ├─ textarea por pergunta (drafts em estado local)
   └─ 3 botões: Salvar / Validar Escopo / Submeter
        │
        ▼
POST /pipeline-questions/personas/{persona_id}/submit
   modes: save | validate | submit
```

---

## 2. Schema canônico

### 2.1. Tabela `persona_follow_up_questions`
**Local**: `backend/app/models/base.py:PersonaFollowUpQuestion`

```python
id: UUID (PK)
project_id: UUID  → FK projects.id ON DELETE CASCADE
document_id: UUID → FK ingested_documents.id ON DELETE CASCADE
ocg_individual_id: UUID → FK ocg_individual.id ON DELETE CASCADE  ← exige doc+persona já persistidos
persona_id: VARCHAR(20)  → tag canônica do Conjunto B ('AUD','GP','ARQ',...)
persona_name: VARCHAR(100)
question_text: Text
context: VARCHAR(500)  → rationale curta da persona ("por que perguntei isso")
question_order: SmallInt → ordem na lista
answer_text: Text NULL
answer_provided_at: timestamptz NULL
answered_by: UUID NULL → users.id (sem FK no schema vivo)
status: VARCHAR(20) → 'pending' | 'answered' | 'skipped' | 'expired'
created_at, updated_at: timestamptz
```

**Migration 067** corrigiu `persona_id` de UUID → VARCHAR(20) (era erradamente FK pra users.id).

### 2.2. PersonaOutput-v2 (origem das questions)
```jsonc
{
  "schema_version": "PersonaOutput-v2",
  "score": 45,
  "findings": [...],
  "recommendations": [...],
  "questions": [           // ← isto é o que vira HITL
    {"question": "Qual SGBD relacional? Postgres, MySQL, SQL Server?", "context": "Q9 disse SQL mas não especificou."},
    {"question": "Tempo de retenção dos processos pós trânsito em julgado?", "context": "Compliance LGPD exige."}
  ],
  "ocg_contributions": {"individual": {...}, "global_delta": {}},
  "persona_tag": "DBA",
  "persona_name": "DBA",
  "ingestion_id": "uuid",
  "approved": false,
  "blocking": false
}
```

Aceita 2 formatos de question (tolerância no parser):
- string: `"Qual SGBD?"` → vira `question_text` direto.
- dict: `{question|text|pergunta, context|rationale|contexto}` → mapeado.

---

## 3. Endpoint canônico de submit

**Local**: `backend/app/routers/pipeline_questions_router.py`

`POST /api/v1/projects/{pid}/pipeline-questions/personas/{persona_id}/submit`

```python
class PersonaSubmitRequest(BaseModel):
    answers: dict[str, str] = {}   # {persona_follow_up_question.id: answer_text}
    mode: Literal["save", "validate", "submit"]
```

### 3.1. Comportamento por modo

| Modo | Salva drafts? | Cria IngestedDocument? | DELETE de questions? | Bloqueia? |
|---|---|---|---|---|
| `save` | sim (status=answered se ≥1 char, pending se vazio) | não | não | nunca |
| `validate` | sim | não | não | nunca (retorna `ok=false` + `missing_question_ids` se incompleto) |
| `submit` | sim | sim, `file_type='persona_followup'` | sim, **só `status='answered'`** | sim (400 se nenhuma respondida) |

### 3.2. Política canônica (decisão consolidada na sessão de 2026-05-04)

- **Submit aceita parcial** (≥1 respondida).
- DELETE atinge **só as `answered`** — perguntas em branco continuam na fila pra próximas rodadas.
- Sub-aba só some quando **todas** forem respondidas e submetidas.
- Permite ao GP salvar progresso, voltar depois, submeter em lotes.

### 3.3. IngestedDocument sintético
```python
IngestedDocument(
    file_type='persona_followup',
    filename=f"followup-{persona_id_norm.lower()}-{timestamp}.json",
    original_filename=f"Respostas HITL — {persona_name} — {project_name}",
    file_hash=sha256(payload_bytes),  # canônico, idempotente
    arguider_status='completed',      # NÃO entra no pipeline n8n
    arguider_stage='followup_synthetic',
    arguider_progress_percent=100,
    ocg_updated=False,
    pii_detected=False,
)
write_ingested(project_id, filename, payload_bytes)  # JSON em storage
```

Payload JSON serializado:
```json
{
  "persona_id": "DBA",
  "persona_name": "DBA",
  "submitted_by": "uuid",
  "submitted_at": "iso",
  "qa_count": 7,
  "qa": [
    {"question": "...", "context": "...", "answer": "...", "document_origin_id": "uuid"}
  ]
}
```

---

## 4. Endpoint de leitura

`GET /api/v1/projects/{pid}/pipeline-questions`

```python
PipelineQuestionsResponse:
    pending_questions: list[QuestionItem]
    answered_questions: list[QuestionItem]
```

**SQL canônico**:
```python
select(PersonaFollowUpQuestion, IngestedDocument.original_filename)
  .join(IngestedDocument, PersonaFollowUpQuestion.document_id == IngestedDocument.id)
  .where(
      PersonaFollowUpQuestion.project_id == project_id,
      IngestedDocument.deleted_at.is_(None),  # ← MVP 34, ignora docs soft-deleted
  )
  .order_by(persona_id, question_order, created_at)
```

`status='skipped'` e `'expired'` são omitidos da UI.

---

## 5. UI canônica

**Local**: `frontend/src/components/questionnaire/PersonaFollowUpTabs.tsx`
**Hospedagem**: `frontend/src/pages/projects/IterativeQuestionnairePage.tsx` → topbar "Questões em Aberto".

Estrutura:
- Sub-abas por persona com pendentes (uma por persona com `count > 0`).
- Estado local `drafts: Record<questionId, string>` — não persiste até clicar Salvar.
- Init dos drafts a partir de `q.answer_text` quando carrega.
- 3 botões: 💾 Salvar · 🛡️ Validar Escopo · 🚀 Submeter.
- Submeter desabilita se `answeredCurrent === 0`. Tooltip dinâmico:
  - 0 respondidas: "Preencha ao menos 1 resposta"
  - parcial: "Submete N respondida(s); M em branco continuam aqui"
  - completo: "Submete todas as N respostas e fecha esta sub-aba"

Hook: `usePipelineQuestions` (lista) + `usePersonaSubmit` (mutation save/validate/submit).

Após submit (`mode='submit'`): `qc.invalidateQueries(['pipeline-questions', projectId])` recarrega; sub-aba some se todas as PFQs daquela persona viraram `answered` (e foram deletadas pelo submit).

---

## 6. Idempotência e edge cases

| Cenário | Comportamento |
|---|---|
| GP submete, depois doc é re-ingesto (re-trigger pipeline) | Novas questions geradas; DELETE no `/ingestion-complete` só apaga `pending` antigas; respostas `answered` viraram `IngestedDocument persona_followup` separado e estão preservadas |
| GP responde, salva, fecha browser, volta depois | Drafts não persistem (estado local). `answer_text` salvo via `mode='save'` é carregado no init |
| Mesma persona aparece em 2 docs (gera 2 batches de questions) | UI mostra 2 grupos sob mesmo persona_id — agrupado por sub-aba único; submeter consolida tudo em 1 IngestedDocument |
| Doc soft-deletado | `revert_document` (DocumentRevertService) marca PFQs daquele doc como `expired` (não DELETE — auditável) |

---

## 7. Extraction-report do `persona_followup`

**Local**: `backend/app/routers/ingestion_router.py:get_extraction_report`

Branch dedicado: lê o JSON do storage (`read_ingested`), parsea `qa[]`, monta shape compatível com `ExtractionReportCard.tsx` — mesmas chaves (chars, paragraphs, ok, etc) com semântica adaptada (`paragraphs` = qa_count, `module_hints` = persona_name, `text_sample` = preview Q/A).

---

## 8. Consumidores que NÃO podem ignorar

- **Frontend "Questões em Aberto"** (sub-abas) — fonte primária.
- **GET `/pipeline-questions`** — endpoint canônico.
- **DocumentRevertService** — quando GP deleta doc, marca PFQs como `expired`.
- **Auditoria** — INSERT/UPDATE/DELETE de PFQ devem aparecer no `audit_log_global` (DT pendente — verificar antes de mexer).

---

## 9. Não invente caminhos paralelos

- **Não criar tabela paralela** (ex: `persona_questions_v2`). Use `persona_follow_up_questions`.
- **Não responder via UPDATE direto** sem passar pelo endpoint canônico — perde histórico de `answer_provided_at` e `answered_by`.
- **Não deletar PFQ no soft-delete do doc** — usar `status='expired'` (preserva auditoria).

---

## 10. Referências cruzadas

- `gca-ingestion-pipeline-anatomy` — onde HITL se encaixa no fluxo.
- `gca-personas-engine` — Conjunto B + filosofia "Assistida".
- `gca-n8n-workflow-mgmt §3` — propagação de `questions[]` no consolidador.
- `gca-pipeline-debug` — quando questions não chegam ao banco.
- CLAUDE.md §3.5 — filosofia HITL e ConflictDetector.
- DT-080 — modelo PersonaFollowUpQuestion completo (MVP 34).
