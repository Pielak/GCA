# MVP 35 — Validação canônica do Questionário Técnico

**Status:** ✅ FECHADO 2026-05-03. 3 Gates aprovados, 6 fases entregues, 90/90 testes Fase verdes, 110/110 suite ampla (zero regressão), smoke E2E real validado.
**Branch:** `feat/mvp35-questionnaire-validation`
**Origem:** GP identificou 4 lacunas no fluxo Salvar/Validar/Submeter + necessidade de validação técnica de itens (combos válidos/inválidos) + validação cruzada entre respostas + UI inline com sugestões + Q13 multi-select com "outros". Pós-decisões iniciais GP adicionou regra 5: deletar questionnaire na Ingestão = projeto volta a setup.

## Resumo de entrega

| Fase | Status | Commit |
|---|---|---|
| 35.1 — RulesEvaluator + 30 regras seed + GET /rules | ✅ | `a2801a2` |
| 35.2 — Migration 069 + validate endpoint + persist validated_at + guard save | ✅ | (este branch) |
| 35.3 — Frontend validate-on-blur + UI inline + Submeter condicional + modal questionnaire | ✅ | (este branch) |
| 35.4 — Q13 textarea condicional 'Outros' | ✅ | (este branch) |
| 35.5 — LLM camada 2 + IngestedDocument sintético + índice parcial | ✅ | (este branch) |
| 35.6 — DocumentRevertService cascata + filtro `_questionnaire_state` + smoke E2E + CLAUDE.md | ✅ | (este commit) |

**Smoke E2E real (AJA project):**
- Doc sintético criado com `file_type='questionnaire'`, hash idempotente
- Revert via DocumentRevertService → `questionnaire_reverted=True`
- TechnicalQuestionnaire → `archived`
- Questionnaire (legacy) → `approved=False`
- `setup_status.ready_to_activate` → `False` (gate fechado)
- Audit `DOCUMENT_REVERTED` emitido com hash chain íntegro

**Bônus do MVP 35:** corrigiu bug latente no `_check_setup_status` que liberava pipeline mesmo com `questionnaire_approved=False`. Agora gate exige `approved AND submitted` (alinha decisão GP "questionário aprovado e submetido").

## Decisões binárias (autorizadas pelo GP)

1. **Estado canônico** — enum `draft → validated → submitted`. Submeter exige `validated`.
2. **Submit cria `IngestedDocument`** tipo `questionnaire` — aparece na aba Ingestão.
3. **Ordem dos gates UX-guiada** — frontend libera aba Questionário só após repo+LLM ok.
4. **Validar obrigatório** — botão Submeter desabilitado se nunca validou OU validação falhou.
5. **Deletar questionário na Ingestão = volta a fase configuração** (decisão GP 2026-05-03 pós-confirmação inicial). Quando GP soft-deleta `IngestedDocument` tipo `questionnaire`:
   - `TechnicalQuestionnaire.status` reverte de `submitted` → `archived` (não `draft` — preserva histórico, força novo)
   - `Questionnaire.approved` → `False` (FK do OCG marcada como não-aprovada)
   - `_check_setup_status.questionnaire_submitted` → `False`
   - `_check_setup_status.ready_to_activate` → `False`
   - Projeto volta a fase configuração: setup checklist mostra Questionário como pendente
   - Frontend redireciona próxima sessão para `/projects/{id}/settings?tab=questionario` com novo questionário em branco (não recupera o archived)
   - Pipeline n8n bloqueado até novo questionário submetido
   - Cascata canônica via DocumentRevertService (MVP 34) — não duplica lógica

## Approach de validação (autorizado)

**Híbrido em 2 camadas:**

### Camada 1 — Regras determinísticas (DSL JSON)
- Catálogo seed ~30 regras cobre matriz comum FE×BE×DB×infra×compliance.
- Engine `evaluate_rules(responses) → {conflicts[], warnings[], suggestions[]}` < 10ms.
- Espelhada frontend (TS) + backend (Python). Backend é fonte de verdade.
- Inline: validate-on-blur por campo modificado.

### Camada 2 — LLM como sanity check
- Roda 1× no submit final. Provider via `AIKeyResolver` (já configurado).
- Prompt: detectar incoerências técnicas que regras determinísticas não pegam.
- Custo: ~R$0.001/submit (DeepSeek). Latência aceitável (não-inline).

## 6 fases (~2.5d)

| Fase | Esforço | Entregável |
|---|---|---|
| 35.1 | 0.5d | DSL rules schema + 30 regras seed (catálogo FE×BE×DB) + engine `RulesEvaluator` + testes unit |
| 35.2 | 0.5d | Migration: estado `validated` no enum status. Endpoint `validate-field`. Refactor save: status nunca regride sem flag. |
| 35.3 | 0.5d | Frontend: validate-on-blur + UI inline (warning amarelo + dropdown sugestões). Botão Submeter desabilitado sem `validated`. |
| 35.4 | 0.25d | Q13 multi_select_with_other no schema + UI checkbox + outros field. Validar Q15 (LGPD) tem mesmo padrão. |
| 35.5 | 0.25d | Camada 2 LLM no submit. `IngestedDocument` tipo questionnaire criado. |
| 35.6 | 0.5d | Hook `DocumentRevertService` para tipo `questionnaire`: archive TechnicalQuestionnaire + mark Questionnaire.approved=False. Backend gate retorna `ready_to_activate=False`. Frontend redirect setup. Smoke E2E real (delete questionnaire → projeto volta a setup). |

## Schema regras DSL

```python
{
  "id": "RULE_DB_NOSQL_TRANSACTION",  # ID canônico
  "when": {                            # condições AND
    "Q9": "mongodb",
    "Q14_contains": "transaction_acid"
  },
  "verdict": "conflict",               # ok | warning | conflict
  "severity": "error",                 # info | warning | error
  "message": "MongoDB não garante ACID multi-doc...",
  "suggestions": ["postgres", "cockroachdb"]  # opções alternativas
}
```

## Não-objetivos

- Não reescreve `TECHNICAL_QUESTIONS_SCHEMA` (só estende Q13/Q15).
- Não muda fluxo de personas Celery após submit (mantém comportamento atual).
- Não bloqueia repo/LLM gates pré-existentes.
- Não cobre validação semântica de texto livre (futuro MVP).

## Critério de aceite (testável)

1. ✅ Status enum aceita `validated`
2. ✅ `POST /technical-questionnaire/validate-field?field=Qx` retorna `{conflicts, warnings, suggestions}` < 50ms
3. ✅ 30 regras seed catalogadas + 30/30 testes verdes
4. ✅ Botão Submeter desabilitado quando `status != 'validated'` ou `conflicts > 0`
5. ✅ Q13 renderiza checkbox + textarea quando "Outros" marcado
6. ✅ Submit cria `IngestedDocument` tipo questionnaire (visível na aba Ingestão)
7. ✅ LLM camada 2 chamado 1× no submit, payload coerente
8. ✅ Suite ampla 0 regressão
9. ✅ Smoke E2E real: GP preenche AJA → Validar → conflito mock → corrige → Validar OK → Submete → status `submitted` + IngestedDocument criado
10. ✅ Delete IngestedDocument tipo questionnaire → TechnicalQuestionnaire `archived` + Questionnaire.approved=False + setup_status.ready_to_activate=False
11. ✅ Smoke E2E real revert: deletar questionnaire do AJA → consultar setup-status → ready_to_activate=False + questionnaire_submitted=False
12. ✅ Frontend redireciona para `/settings?tab=questionario` quando ready_to_activate=False após delete questionnaire

## Decisões pós-Gate 1 (2026-05-03)

Gate 1 ✅ Aprovado com ressalvas. 3 MUSTs + 5 SHOULDs incorporados.

### MUSTs

**M1 — Colisão de `validated`:** falso alarme. DB hoje tem só `draft|submitted` (sem CHECK constraint). Único valor extra é `ocg_generated` em `questionnaire_service.py:717` (legacy provavelmente morto). Decisão: migration adiciona CHECK constraint canônica `status IN ('draft','validated','submitted','archived')`. Valor legacy `ocg_generated` é mapeado para `submitted` na migration (UPDATE preventivo).

**M2 — Comportamento LLM falha no submit:** **bloqueia** com erro friendly. Alinha §0 CLAUDE.md ("sem fallback silencioso"). Mensagem: "Validação automática de IA indisponível agora. Tente novamente em instantes." HTTPException 503. Botão Submeter mostra retry option.

**M3 — `file_hash`/`file_type` do IngestedDocument sintético:**
- `file_type = 'questionnaire'` (estende comentário no model — sem CHECK formal pré-existente, então sem migration de CHECK extra)
- `file_hash = sha256(json.dumps(responses, sort_keys=True))` — idempotência canônica
- `original_filename = "Questionário Técnico — {project.name}"`
- `filename = "questionnaire-{questionnaire.id}.json"` (sem arquivo físico — payload em `responses` JSONB)
- `file_size_bytes = len(json.dumps(responses).encode())`
- Re-submit com respostas idênticas: `uq_ingested_doc_hash` + filtro DBA-M1 (`WHERE deleted_at IS NULL`, MVP 34) garante dup-detection sem bloquear delete+resubmit

### SHOULDs

**S1 — Modal diferenciado de delete questionnaire:** Frontend exibe aviso explícito antes do confirm: "⚠ Deletar este questionário retornará o projeto à fase de configuração. Você precisará preencher um novo questionário, e o pipeline n8n ficará bloqueado até que o novo seja submetido. Esta ação não pode ser desfeita automaticamente. Deseja continuar?"

**S2 — 30 grupos de regras seed (5 grupos temáticos):**
1. **NoSQL × ACID** (5 regras) — MongoDB+ACID, DynamoDB+JOIN, Cassandra+transação multi-tabela, Redis-as-DB+rollback, Elasticsearch+consistência forte
2. **Stack runtime** (6 regras) — Node+IO-bound vs Python+CPU-bound, Java+microsserviços-pequenos, Go+ML, Rust+protótipo-rápido, PHP+real-time, Ruby+throughput-alto
3. **Frontend × Backend** (5 regras) — Next.js+SPA-puro, React+SSR-sem-Next, Angular+API-REST-leve, Vue+monolito-Java, Svelte+app-grande
4. **Compliance × dados pessoais** (6 regras) — LGPD+sem-criptografia, GDPR+log-IP-clear, HIPAA+cloud-pública-sem-BAA, PCI-DSS+sem-tokenização, SOC2+sem-trilha-auditoria, LGPD+armazenamento-EUA-sem-cláusulas
5. **Infra × escala/custo** (8 regras) — Kubernetes+1k-users, serverless+long-running, on-prem+escala-elástica, monolito+10-devs, microsserviços+team-de-2, SQLite+produção-multi-region, container+secret-em-env, edge+stateful-session

**S3 — OCG cascata no delete questionnaire:** DocumentRevertService (MVP 34) já cobre — service detecta `file_type='questionnaire'` e adiciona cascata extra (TechnicalQuestionnaire→archived, Questionnaire.approved=False). Aviso de regressão de maturidade já existe (MVP 34).

**S4 — Migração projetos antigos:** simples. Registros existentes com `status='submitted'` permanecem. Registros com `status='validated'` ou `status='ocg_generated'` (raros — viu-se 1 em legacy) viram `submitted` via UPDATE no script da migration. Documentado no header do SQL.

**S5 — Estimativa 3d (não 2.5d):** ajustado.

## 6 fases (~3d revisado)

| Fase | Esforço | Entregável |
|---|---|---|
| 35.1 | 0.5d | DSL rules schema + 30 regras seed agrupadas em 5 temas + engine `RulesEvaluator` + 30 testes unit |
| 35.2 | 0.5d | Migration: enum status com CHECK + UPDATE de legacy + endpoint `validate-field` |
| 35.3 | 0.75d | Frontend: validate-on-blur + UI inline + Submeter condicional + modal diferenciado de delete |
| 35.4 | 0.25d | Q13 frontend (textarea condicional) + Q15 verificação (não muda) |
| 35.5 | 0.5d | Camada 2 LLM no submit (bloqueio em falha) + criar IngestedDocument sintético + idempotência via hash |
| 35.6 | 0.5d | Hook DocumentRevertService p/ tipo questionnaire + smoke E2E real |

## Critério de aceite (16 itens, ampliado pelo Gate 1)

13. ✅ Migration: CHECK constraint canônica em `technical_questionnaires.status`. UPDATE preventivo de legacy `ocg_generated`/`validated`(antigo) → `submitted`. 0 registros corrompidos.
14. ✅ Submit com provider LLM indisponível: bloqueia com 503 + mensagem friendly. UI mostra opção de retry.
15. ✅ Delete IngestedDocument tipo questionnaire na UI exibe modal explícito (não o genérico).
16. ✅ `uq_ingested_doc_hash` + DBA-M1 (filtro `deleted_at IS NULL`) permite re-submit pós-delete sem violação. Hash idêntico para respostas idênticas (idempotência).

## Decisões pós-Gate 2 (2026-05-03)

Gate 2 ✅ Aprovado com ressalvas. 3 MUSTs (A-M) + 4 SHOULDs (A-S) + 7 critérios técnicos.

### MUSTs Arquiteto

**A-M1 — Guard pipeline n8n para `file_type='questionnaire'`** (CRÍTICO):
- `IngestionService._dispatch_to_n8n` + `pipeline_ingest_task.delay` ganham guard `if file_type == 'questionnaire': return`
- IngestedDocument do questionário criado **direto no router de submit** com `arguider_status='completed'` + `arguider_stage='questionnaire_synthetic'` — NÃO passa por `IngestionService.upload_document` (sem dispatch automático)
- Comentário no model `base.py:1015` lista `questionnaire` no enum de file_type

**A-M2 — Hash canônico com normalização de listas** (idempotência GP):
```python
def _canonical_responses(responses: dict) -> dict:
    return {k: sorted(v) if isinstance(v, list) else v
            for k, v in responses.items()}

file_hash = hashlib.sha256(
    json.dumps(_canonical_responses(responses), sort_keys=True).encode()
).hexdigest()
```
Sem isso, multiselect com ordens diferentes gera hashes diferentes (viola critério 16).

**A-M3 — TypeScript union inclui `archived`**:
`useTechnicalQuestionnaire.ts:13` → `'draft' | 'validated' | 'submitted' | 'archived'`. Sem isso, compilador TS não detecta erros de guard.

### SHOULDs Arquiteto

**A-S1** — Endpoint `GET /technical-questionnaire/rules` expõe catálogo (single source of truth). Frontend carrega 1× no mount. Elimina bundle TS duplicado.

**A-S2** — NFR mensurável Camada 2 LLM: latência p95 ≤ 8s; custo/submit ≤ R$0,005; timeout 15s. Adicionado ao critério de aceite.

**A-S3** — `_questionnaire_state` em `project_setup_router.py:68` filtra `status != 'archived'` explicitamente. Blindagem contra ORDER BY DESC retornar archived acima de draft.

**A-S4** — `validated_at` populado ao entrar em `validated`. Migration 055 já tem CHECK `status='validated' → validated_at IS NOT NULL`. Sem populated, INSERT falha silenciosamente.

### DSL refinado

`when` operadores canônicos:
- `"Qx": "valor"` — igualdade scalar
- `"Qx_contains": "valor"` — inclusão em lista (multiselect)
- `"when_any": [{...},{...}]` — OR opcional (só se 4+ regras seed precisarem)

`RulesEvaluator` em `backend/app/services/questionnaire_validation/rules_evaluator.py`. Stateless. Regras como constante Python (lista importada). Sem hot-reload — restart canônico do worker.

### Endpoint validate-field refinado

Recebe `responses` completo (não single field) — evita N+1. Retorna conflicts de TODOS os campos afetados pela mudança. Payload:
```json
{
  "conflicts": [{"rule_id", "field", "severity", "message", "suggestions"}],
  "warnings": [...],
  "evaluated_at_ms": 12
}
```

### Camada 2 LLM — prompt canônico

Não passa as 30 regras (Camada 1 já aplicou). Payload mínimo:
```json
{
  "responses": {...},
  "conflicts_detected": [...],
  "context": "questionário técnico GCA"
}
```
Pede ao LLM detectar incoerências semânticas (ex: equipe-2 + microsserviços + K8s + ACID).

## 7 critérios técnicos extra (Gate 2)

A1-A7 — ver doc Gate 2. Foco: guard n8n, hash canônico, CHECK constraint, IngestedDocument com `arguider_status='completed'`, revert task → archived.

## 6 fases revisadas (~3d ainda)

Sem mudança de fases — apenas escopo das fases existentes ganha:
- 35.1: + endpoint `GET /rules` (A-S1)
- 35.2: + CHECK constraint canônica + UPDATE preventivo + populate `validated_at` (A-S4)
- 35.3: + TS union `archived` (A-M3)
- 35.5: + guard n8n (A-M1) + hash canônico (A-M2) + IngestedDocument direto no router
- 35.6: + filtro `status != 'archived'` em `_questionnaire_state` (A-S3) + cascata extra para `file_type='questionnaire'` no DocumentRevertService

## Decisões pós-Gate 3 (2026-05-03)

Gate 3 (DBA) ✅ Aprovado com ressalvas. 6 MUSTs (DBA-M) + 4 SHOULDs (DBA-S).

### MUSTs DBA

**DBA-M1 — Dup-check no router de submit (NÃO migration):** `uq_ingested_doc_hash` é UNIQUE regular (não parcial). Router de submit Fase 35.5 deve fazer:
```python
existing = await db.execute(select(IngestedDocument).where(
    IngestedDocument.project_id == pid,
    IngestedDocument.file_hash == hash,
    IngestedDocument.deleted_at.is_(None),  # CRÍTICO
))
if existing: return existing.id  # idempotente
# else INSERT new
```
Sem isso: delete+resubmit com hash idêntico → `UniqueViolationError` em produção.

**DBA-M2 — Migration 069 estrutura canônica idempotente:**
```sql
BEGIN;

-- 1. UPDATE preventivo ANTES de instalar CHECK
UPDATE technical_questionnaires
   SET status = 'submitted'
 WHERE status IN ('ocg_generated', 'validated');
-- 'validated' aqui = valor LEGACY (pós-personas), antes de MVP 35 redefinir

-- 2. CHECK enum status
ALTER TABLE technical_questionnaires DROP CONSTRAINT IF EXISTS chk_tq_status;
ALTER TABLE technical_questionnaires ADD CONSTRAINT chk_tq_status
    CHECK (status IN ('draft','validated','submitted','archived'));

-- 3. CHECK submitted_at obrigatório quando submitted/archived
ALTER TABLE technical_questionnaires DROP CONSTRAINT IF EXISTS chk_tq_submitted_at;
ALTER TABLE technical_questionnaires ADD CONSTRAINT chk_tq_submitted_at
    CHECK (status NOT IN ('submitted','archived') OR submitted_at IS NOT NULL);

-- 4. CHECK validated_at obrigatório quando validated
ALTER TABLE technical_questionnaires DROP CONSTRAINT IF EXISTS chk_tq_validated_at;
ALTER TABLE technical_questionnaires ADD CONSTRAINT chk_tq_validated_at
    CHECK (status != 'validated' OR validated_at IS NOT NULL);

COMMIT;
```

**DBA-M3 — `validated_at` populado no validate-field:** Router seta `validated_at = NOW()` + `validated_by = current_user.id` na transição para `validated`. Sem isso: UPDATE rejeitado por CHECK constraint.

**DBA-M4 — Código corrigido ANTES (ou atomicamente com) migration:** `questionnaire_service.py:717` + `webhooks.py:259` ainda escrevem `status='ocg_generated'`. Após migration, esses UPDATEs falham com CheckViolationError. Sequência canônica: corrigir código → deploy → migration. Adicionado à Fase 35.2.

**DBA-M5 — Guard contra regressão status no save:** Router save (linha 216) faz `status='draft'` incondicional quando `submit=False`. Auto-save no campo de validated regrediria para draft, invalidando Submeter. Fix:
```python
if questionnaire.status not in ('submitted','archived'):
    questionnaire.status = 'draft'
```
Auto-save NUNCA sobrescreve submitted/archived; pode regredir validated→draft (intencional — usuário editou após validar, precisa revalidar).

**DBA-M6 — DocumentRevertService cascata para file_type='questionnaire':** Service atual NÃO importa TechnicalQuestionnaire. Adicionar branch:
```python
if doc.file_type == 'questionnaire':
    # archive TechnicalQuestionnaire + Questionnaire.approved=False
    await db.execute(update(TechnicalQuestionnaire)
        .where(TechnicalQuestionnaire.project_id == project_id,
               TechnicalQuestionnaire.status == 'submitted')
        .values(status='archived'))
    await db.execute(update(Questionnaire)
        .where(Questionnaire.project_id == project_id, Questionnaire.approved == True)
        .values(approved=False))
```

### SHOULDs DBA

**DBA-S1** — Sem índice extra para validate-field (operação stateless em payload).
**DBA-S2** — `COMMENT ON TABLE technical_questionnaires` atualizado com novo enum.
**DBA-S3** — `_questionnaire_state` deve reconhecer `validated` como "em progresso" (não retorna `submitted=False` erroneamente). Refinamento da A-S3 do Gate 2.
**DBA-S4** — IngestedDocument tipo `questionnaire` com `deleted_reason='lgpd'` entra no escopo do DT-086 (purge físico futuro).

### LGPD

`technical_questionnaires.responses` JSONB clear-text é **OK**. Q1-Q15 são técnicas (escopo, stack, prazo, compliance flags) — sem PII. Sob LGPD Art. 5º I, não são dados pessoais.

### Critérios DBA (8 itens, somam aos 16 já definidos)

D1. Migration 069 aplica em <3s.
D2. `SELECT conname FROM pg_constraint WHERE conrelid='technical_questionnaires'::regclass AND contype='c'` = 3 rows (chk_tq_status, chk_tq_submitted_at, chk_tq_validated_at).
D3. `SELECT COUNT(*) WHERE status NOT IN (...)` = 0 após migration.
D4. INSERT com `status='ocg_generated'` rejeitado com CheckViolationError.
D5. Soft-delete + resubmit com hash idêntico → sem IntegrityError.
D6. UPDATE `status='validated'` sem `validated_at` rejeitado.
D7. `validated_at` é TIMESTAMPTZ (mantém padrão drift histórico).
D8. `status='ocg_generated'` retorna 0 rows pós-migration.

## Próxima ação

**Gate 4 — Dev Sênior.** Implementação canônica:

1. **Pré-migration (M4):** corrigir `questionnaire_service.py:717` + `webhooks.py:259` (`'ocg_generated'` → `'submitted'`). Commit isolado primeiro.
2. **Fase 35.1:** RulesEvaluator + 30 regras seed + endpoint `GET /rules`.
3. **Fase 35.2:** migration 069 + endpoint validate-field + populate validated_at + guard status no save.
4. **Fase 35.3:** Frontend validate-on-blur + UI inline + TS union archived + modal delete diferenciado.
5. **Fase 35.4:** Q13 frontend (textarea condicional).
6. **Fase 35.5:** Camada 2 LLM submit + IngestedDocument sintético com dup-check + hash canônico.
7. **Fase 35.6:** DocumentRevertService cascata file_type='questionnaire' + filtro `status != 'archived'` em `_questionnaire_state` + smoke E2E real.

Aguarda autorização explícita do GP humano (CLAUDE.md §2.6) antes de iniciar Fase pré-migration.
