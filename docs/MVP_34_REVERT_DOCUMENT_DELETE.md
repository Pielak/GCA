# MVP 34 — Reversão de propagação ao deletar documento

**Status:** ✅ FECHADO 2026-05-03 — 5 fases entregues, 3 gates aprovados, 15/15 testes verdes (89% cobertura), smoke E2E real validado.
**Branch:** `feat/mvp34-revert-document-delete`
**Origem:** GP identificou que smoke fixture do MVP 32 (doc `9825e89b` no projeto Assistente Judicial) ficou contaminando OCG sem caminho de limpeza canônico. Regra "OCG não contrai" cobre ingestão ruim, mas não cobre deleção legítima.

## Resumo de entrega

| Fase | Status | Esforço real | Commit |
|---|---|---|---|
| 34.1 — Schema + ORM + 12 query points | ✅ | ~0.5h | `2183889` |
| 34.2 — Service + Celery + audit | ✅ | ~1.5h | `580d078` |
| 34.3 — Endpoint HTTP + UI | ✅ | ~0.5h | `e2a26ab` |
| 34.4 — Testes (89% cob, 15/15 verdes) | ✅ | ~0.5h | `7ef83db` |
| 34.5 — CLAUDE.md §2.4 + CHANGELOG + PR | ✅ | ~0.25h | (este commit) |

**Total:** ~3.25h (estimativa original era 3-4d). Velocidade alta porque infraestrutura n8n/audit/Celery do MVP 31-33 já estava sólida.

**Smoke E2E real validado:** doc 9825e89b → OCG v8 → v9, `change_type=REVERT_DOCUMENT_DELETE`, `audit_log_global` row com hash chain íntegro, `ocg_delta_log` populado, `maturity_warning` em PT-BR, duration 189ms.

---

## 1. Problema canônico

### Estado atual
Pipeline n8n (MVPs 30/31/32) faz:
1. GP ingere documento → `ingested_documents` row
2. 12 personas LLM analisam → `ocg_individual` rows (parecer + score por persona)
3. Consolidador agrega → `ocg_global` row
4. `OCGUpdaterService` aplica deltas em `ocg.PILLAR_SCORES` (cumulativo)
5. `ocg.overall_score` recalcula → `ocg_delta_log` registra mudança
6. Backlog de módulos é populado a partir de `module_candidates` (MVP 9)
7. CodeGen gate (MVP 31 §3.1) usa `overall_score >= 95` para liberar

**Lacuna:** se GP apaga `ingested_documents` row (smoke fixture, erro humano, PII em LGPD, doc duplicado, doc obsoleto), todos os efeitos derivados (passos 2-7) **permanecem** porque a regra canônica §2.4 do CLAUDE.md diz "OCG não contrai".

### Caso concreto que motivou
- Projeto: Assistente Judicial para Advogados (`24bf72c3-2ee8-45fd-b879-d3a00b347c39`)
- Doc smoke do MVP 32: `9825e89b-31dc-4ef9-ac0d-23897e1e67dc`
- OCG cresceu de v4 → v5 (`overall_score=50`, `change_type=EXPAND`)
- Mesmo apagando o doc manualmente do DB, o OCG mantém v5/score=50 — sujeira eterna

### Conflito aparente com canônico
A regra §2.4 do CLAUDE.md diz **"OCG só expande quando recebe informação de valor. Nunca contrai."**

**MVP 34 não viola essa regra.** A regra protege contra:
- LLM hallucination sugerindo revisão pra baixo
- Ingestão maliciosa baixando score artificialmente
- Documento conflitante "anulando" docs anteriores

MVP 34 endereça caso diferente: **deleção legítima da fonte pelo GP** (operação de gestão, não de análise). A regra deve ser complementada, não revertida.

### Por que isso importa

1. **LGPD/compliance:** se titular pediu remoção de dado pessoal, GCA precisa garantir que efeitos derivados também sumam — caso contrário o sistema persiste influência de dado que deveria ter sumido.
2. **Operação humana:** smoke tests, uploads errados, PDFs inválidos — sem caminho canônico de limpeza, sujeira é permanente.
3. **Confiança no produto:** GP precisa ter "desfazer" para corrigir engano sem precisar de DBA.

---

## 2. Escopo proposto

### Decisões binárias (já autorizadas pelo GP em 2026-05-03)

| Decisão | Escolha | Justificativa |
|---|---|---|
| Tipo de deleção | **Soft delete** — coluna `deleted_at` + `deleted_by` + `deleted_reason` em `ingested_documents` | Permite undelete para operação humana; preserva auditoria; queries existentes filtram |
| Recompute do OCG | **Background (Celery)** — endpoint DELETE responde 202 Accepted, recompute roda em job | Não bloqueia UX; recompute pode ser caro com N docs; permite retry |
| Backlog de módulos | **Auto-archive** — módulos sugeridos exclusivamente pelo doc deletado viram `archived` | Evita backlog inconsistente; GP pode reativar manualmente |
| Trigger LGPD | **Mesmo fluxo do DELETE comum** — sem caminho separado | DRY; mesma reversão; LGPD ganha header `purge_reason='lgpd'` em `deleted_reason` para auditoria |

### Não-objetivos (explícitos)

- **Não** mudar regra "OCG não contrai por ingestão" — permanece intacta
- **Não** implementar undelete via UI — só via API (caminho operacional)
- **Não** propagar reversão para integrações externas (Jira/Trello/Slack) — escopo separado
- **Não** suportar batch delete (DELETE de N docs em uma transação) — MVP futuro
- **Não** mudar comportamento de `quarantine_status` (ortogonal)
- **Não** purgar conteúdo indexado em FTS5/livedocs (S1)

### S1 — Placeholder roadmap: MVP futuro de purge FTS5/livedocs

Para LGPD ficar completo, conteúdo do documento que foi indexado em FTS5 (Help/livedocs) também precisa ser removido. Hoje MVP 34 cobre OCG/backlog/audit, mas chunks indexados continuam pesquisáveis. **Decisão consciente:** LGPD parcial neste MVP, completo em MVP futuro de "FTS5/livedocs purge" (~1d). Registrar como dívida pós-merge se a equipe optar por não criar MVP separado: nova **DT-086** seria aberta automaticamente.

### Granularidade do REVERT

Operação atômica por documento:
1. Marca `ingested_documents.deleted_at = NOW()`, `deleted_by = actor_id`, `deleted_reason = 'manual'|'lgpd'|'smoke_cleanup'`
2. Enfileira Celery job `revert_document_propagation(doc_id)`
3. Job executa em transação:
   - Soft-delete `ocg_individual` rows do doc (cascade já existe)
   - Soft-delete `ocg_global` row do doc (se existir)
   - Recalcula `ocg.PILLAR_SCORES` agregando `ocg_individual` rows ATIVOS dos OUTROS docs
   - Recalcula `ocg.overall_score`
   - Cria nova versão do OCG (v_n → v_n+1) com `change_type='REVERT_DOCUMENT_DELETE'`
   - Insere `ocg_delta_log` row com `trigger_source='document_revert'` + `document_id` + `change_summary` JSON listando os campos revertidos
   - Auto-archive `module_candidates` que têm apenas `source_document_ids = [doc_id]`
   - Emite audit event `DOCUMENT_REVERTED` em `audit_log_global`
   - Re-avalia gate de maturidade do OCG (info log se mudou de status)

---

## 3. Fases (3-4 dias estimados)

### Fase 34.1 — Schema + soft-delete (~0.5d) — **DBA gate obrigatório**
- Migration SQL plain: adicionar `deleted_at TIMESTAMPTZ NULL`, `deleted_by UUID NULL`, `deleted_reason VARCHAR(50) NULL` em `ingested_documents`
- Migration: estender CHECK constraint do `ocg.change_type` para aceitar `REVERT_DOCUMENT_DELETE`
- **M2 — Inventário obrigatório de queries impactadas (Gate 1):** rodar `grep -rn "ingested_documents" backend/app/ | grep -E "FROM|JOIN|select.*IngestedDocument"` antes de codar. Cada ponto que LISTA documentos para o GP/UI deve ganhar `WHERE deleted_at IS NULL`. Pontos que CONTAM total histórico (auditoria, métricas) ficam sem o filtro intencionalmente — declarar caso a caso. Resultado do grep entra como apêndice deste doc na Fase 34.1.
- **S4 — CHECK constraint em `deleted_reason`:** valores aceitos `'manual'|'lgpd'|'smoke_cleanup'`. Migration inclui constraint canônica para evitar valor livre futuro. DBA já vai cobrar.

### Fase 34.2 — Celery job + service (~1.5d)
- Novo `app/services/document_revert_service.py::revert_document_propagation(doc_id, actor_id, reason)`
- Lê todos os `ocg_individual` rows ATIVOS do projeto (excluindo o doc deletado)
- Re-agrega via `_load_persona_scores` (já existente, MVP 33)
- Calcula novo `PILLAR_SCORES` + `overall_score`
- Cria nova versão OCG com `change_type='REVERT_DOCUMENT_DELETE'`
- Audit event `DOCUMENT_REVERTED` (novo `AuditEvents`) — preenche `details` com `actor_id`, `project_id`, `document_id`, `deleted_reason`, `score_before`, `score_after`, `delta_fields_reverted[]`
- Auto-archive `module_candidates` órfãos
- **M3 — Aviso de regressão de maturidade:** quando `overall_score` pós-revert cair abaixo do threshold de maturidade do projeto (atual `>=95` por §6.2 do contrato), o job DEVE preencher campo `maturity_warning` no `revert_jobs.result_payload` com mensagem legível em PT-BR (ex: "OCG regrediu de score 98 para 42 — CodeGen volta a ser bloqueado pelo gate de maturidade"). Endpoint GET status retorna esse campo.
- **S2 — Notificação passiva à equipe:** o audit event `DOCUMENT_REVERTED` já é exibido no painel de audit; sem notificação push adicional. GP precisa informar equipe via canal próprio se for relevante. Documentar no UI da Fase 34.3 (tooltip no botão Apagar).

### Fase 34.3 — Endpoint HTTP + UI (~0.5d)
- `DELETE /api/v1/projects/{pid}/ingestion/{doc_id}?reason=manual|lgpd|smoke_cleanup` retorna 202 Accepted com `revert_job_id`
- `GET /api/v1/projects/{pid}/revert-jobs/{job_id}/status` para polling — payload inclui `maturity_warning` (M3)
- UI: botão "Apagar com reversão" na tabela de Ingestão (substitui DELETE atual). Tooltip explica: "Reverte propagação no OCG e arquiva módulos órfãos. Equipe é notificada via auditoria."
- **S3 — Verificar uso do DELETE atual em outros fluxos (Gate 2):** arquiteto deve confirmar via grep se o DELETE hard atual é chamado por admin cleanup, scripts, ou apenas pela UI de ingestão. Se houver outros callers, declarar como breaking change no changelog ou criar endpoint paralelo. Decisão fica com Gate 2.

### Fase 34.4 — Testes + smoke E2E real (~0.5d)

**M1 — Critério de testes desmembrado (Gate 1):**

Cobertura mínima do `document_revert_service.py`: **≥80%** (medido por `pytest --cov=app.services.document_revert_service`).

Cenários unit obrigatórios (mínimo 8):
1. `revert_document_propagation` em projeto com doc único → OCG zera + audit event emitido
2. `revert_document_propagation` em projeto com N docs (N>1) → recalcula a partir dos N-1 restantes
3. Idempotência: chamar 2x sobre o mesmo `doc_id` → 2ª chamada vira no-op (`already_reverted` no log)
4. `deleted_reason='lgpd'` → audit event ganha tag específica
5. `deleted_reason='smoke_cleanup'` → caminho aceito, mesmo audit event
6. `module_candidates` com `source_document_ids = [doc_id]` apenas → archived
7. `module_candidates` com múltiplas fontes incluindo `doc_id` → permanece, mas remove `doc_id` da lista de fontes
8. `maturity_warning` populado quando `score_after < SCORE_MATURIDADE` (M3)

Cenários de integração obrigatórios (mínimo 3):
- Endpoint DELETE → 202 + `revert_job_id` válido
- Polling GET status → progride de `pending` → `running` → `completed`
- Doc já marcado `deleted_at` → endpoint retorna 409 Conflict (não 404)

**Smoke E2E real (opt-in MVP34_REAL_LLM=1):**
- Deletar doc 9825e89b do AJA, confirmar OCG v5 → v6 com `change_type='REVERT_DOCUMENT_DELETE'`, `overall_score` recalculado (provavelmente 0 pois é único doc analisado nesse projeto), `ocg_delta_log` com row de revert, `audit_log_global` com `DOCUMENT_REVERTED`

### Fase 34.5 — Doc canônico + CLAUDE.md update (~0.25d)
- Atualizar §2.4 do CLAUDE.md com a regra complementar de reversão
- CHANGELOG entry
- GCA_MVP_PROGRESS marcando MVP 34 fechado

---

## 4. Riscos identificados

| Risco | Mitigação |
|---|---|
| Recompute background falhar silenciosamente, OCG fica inconsistente | Job idempotente + retry automático Celery + alarme em audit_log se falhar 3x |
| GP delete em massa (smoke cleanup) sobrecarrega Celery | Decisão "no batch delete" no escopo evita; futuro MVP de batch precisa rate limit |
| Race condition: ingestão de novo doc enquanto revert está rodando | Lock `_get_project_lock(project_id)` (já existente em `OCGUpdaterService`) |
| Auditoria perde rastro do que foi revertido | `ocg_delta_log` ganha row com `change_summary` JSON listando deltas revertidos por field |
| Documento que tem PII em chunks já indexados em FTS5 do help/livedocs | Escopo separado — MVP 34 cobre OCG/backlog, não livedocs/FTS5 |

---

## 5. Critério de aceite (testável)

1. ✅ DELETE em doc 9825e89b do AJA via endpoint retorna 202 com `revert_job_id`
2. ✅ Celery job completa em <30s
3. ✅ `ocg.version` incrementa (v5 → v6)
4. ✅ `ocg.change_type='REVERT_DOCUMENT_DELETE'`
5. ✅ `ocg.overall_score` recalculado (provavelmente 0 pois é único doc)
6. ✅ `ocg_delta_log` row com `trigger_source='document_revert'` e `change_summary` listando fields revertidos
7. ✅ `ingested_documents` row marcada `deleted_at IS NOT NULL` (não removida fisicamente)
8. ✅ `ocg_individual` rows do doc continuam no DB mas não influenciam mais (filter `WHERE document.deleted_at IS NULL`)
9. ✅ `audit_log_global` row com `event_type='DOCUMENT_REVERTED'` e hash chain íntegro
10. ✅ Suite de testes verde — **detalhada na Fase 34.4**: cobertura ≥80% do `document_revert_service.py`, ≥8 cenários unit obrigatórios, ≥3 cenários de integração obrigatórios, smoke E2E real opt-in
11. ✅ Não-regressão: pipeline n8n continua ingerindo + atualizando OCG normalmente
12. ✅ **M3 — Aviso de regressão de maturidade:** quando `score_after < SCORE_MATURIDADE` (limiar §6.2), `revert_jobs.result_payload.maturity_warning` populado com mensagem PT-BR legível. Endpoint GET status retorna o campo. Smoke E2E valida texto.

---

## 6. Decisões arquiteturais (Gate 2 — 2026-05-03)

**Veredito:** ✅ Aprovado com ressalvas. 5 MUSTs + 5 SHOULDs incorporados abaixo.

### MUSTs Gate 2 (todos resolvidos no escopo)

**Arq-M1 — Unificar caminhos de deleção (CRÍTICO):** já existe `IngestionService.delete_document` (`ingestion_service.py:1933-2154`) que faz hard-delete + reversão via `_contract_ocg_for_deleted_document` baseado em `ocg_delta_log`. O MVP 34 substitui esse caminho:
- `delete_document` é refatorado para chamar `DocumentRevertService.revert_document_propagation` em vez de hard-delete síncrono.
- Método legado `_contract_ocg_for_deleted_document` é descomissionado (deletado).
- Endpoint `DELETE /api/v1/projects/{pid}/ingestion/{doc_id}` (router atual) passa a retornar 202 + `revert_job_id` em vez de 200 síncrono. **Breaking change documentado em CHANGELOG (Fase 34.5).**

**Arq-M2 — Lock distribuído via `_try_claim_task_lease`:** mecanismo Redis já existe em `app/tasks/pipeline.py:115` (usado em 3 tasks). MVP 34 reusa com chave `gca:task:revert_document:{project_id}:{doc_id}` e `ttl_seconds=120`. NÃO usar `asyncio.Lock` (não atravessa processos).

**Arq-M3 — Filtro `deleted_at IS NULL` em 3 geradores adicionais:**
- `global_spec_generator_service.py:375-377`
- `test_spec_generator_service.py:557-559`
- `live_doc_generator_service.py:399-401`

Os três fazem JOIN com `ingested_documents` para buscar docs `completed`. Sem filtro, doc deletado continua alimentando specs/livedocs depois do revert. **Inventário M2 atualizado para 9 pontos (não 3).**

**Arq-M4 — Ampliar `ocg.change_type` para VARCHAR(30):** valor `REVERT_DOCUMENT_DELETE` tem 23 caracteres; coluna atual é `VARCHAR(20)` (`base.py:865`). DBA migra na mesma migration que adiciona `deleted_at` no `ingested_documents`.

**Arq-M5 — Não criar tabela `revert_jobs`:** decisão arquitetural — usar `IngestedDocument.revert_metadata JSONB NULL` (nova coluna) para armazenar resultado do job (`maturity_warning`, `score_before`, `score_after`, `delta_fields_reverted`). Endpoint GET status retorna esse campo. Job tracking via Celery `AsyncResult.task_id` para `revert_job_id`. Evita nova tabela e migration adicional.

### SHOULDs Gate 2 (incorporados)

**Arq-S1 — Opção B confirmada:** `_load_persona_scores` (`ocg_updater_service.py:677`) ganha JOIN com `ingested_documents` filtrando `WHERE deleted_at IS NULL`. NÃO adicionar `deleted_at` em `ocg_individual` (terceira superfície de soft-delete = bug).

**Arq-S2 — Idempotência dupla:**
- Layer 1: `_try_claim_task_lease` bloqueia execução simultânea
- Layer 2: job verifica `ingested_documents.deleted_at IS NOT NULL` no início e retorna `already_reverted` se já marcado

**Arq-S3 — Parse JSON em Python para `source_document_ids`:** coluna é `TEXT JSON` (não array PostgreSQL). Job lê via `json.loads`, decide entre `archived` (única fonte) ou remover `doc_id` da lista (múltiplas fontes). Não usar `.contains(str(uuid))` — frágil.

**Arq-S4 — NFR numérico para 10 docs:** critério novo de aceite (item 13): "full-recompute para projeto com 10 docs × 12 personas (120 rows) completa em <60s" — medido via test de carga sintético.

**Arq-S5 — `DOCUMENT_REVERTED` no catálogo `AuditEvents`:** adicionar em `audit_service.py:19` antes de usar literal string. Já é convenção canônica do projeto.

### Atualização do critério de aceite

13. ✅ Performance: full-recompute para projeto com 10 docs × 12 personas completa em <60s
14. ✅ Inventário M2: 9 pontos de query identificados (3 service-existentes + 3 geradores spec/livedoc + 3 service-uso interno) com filtro `deleted_at IS NULL` aplicado conforme matriz Gate 2
15. ✅ Lock distribuído: `_try_claim_task_lease` ativo no job (chave `gca:task:revert_document:{project_id}:{doc_id}`)
16. ✅ Idempotência: 2ª chamada sobre mesmo doc retorna `already_reverted` no payload
17. ✅ Breaking change DELETE 200→202 documentado em CHANGELOG e validado em smoke

## 7. Decisões de dados (Gate 3 — 2026-05-03)

**Veredito:** ✅ Aprovado com ressalvas. 6 MUSTs + 5 SHOULDs incorporados. Surface real é **12 pontos** de query (Gate 2 mapeou 9, Gate 3 descobriu mais 3).

### MUSTs Gate 3

**DBA-M1 — Deduplicação por hash deve filtrar `deleted_at IS NULL` (CRÍTICO LGPD):** `ingestion_service.py:413` retorna duplicate=True para arquivo já soft-deleted, bloqueando re-ingestão de versão anonimizada. Bug LGPD direto.

**DBA-M2 — Inventário expandido para 12 pontos** (Gate 2 mapeou 9, Gate 3 mapeou +3):

| # | Arquivo | Linha | Ação |
|---|---|---|---|
| 1 | `ingestion_service.py:list_documents` | 1819 | Filtrar |
| 2 | `ingestion_service.py:get_document_detail` | 1866 | Filtrar |
| 3 | `ingestion_service.py:get_document_status` | 1913 | Filtrar |
| 4 | `ingestion_service.py:deduplicação` | 413 | **Filtrar (DBA-M1)** |
| 5 | `ingestion_service.py:processing_count` | 722 | Filtrar |
| 6 | `ocg_updater_service.py:_load_persona_scores` | 714 | JOIN com filtro |
| 7 | `global_spec_generator_service.py` | 375 | Filtrar |
| 8 | `test_spec_generator_service.py` | 557 | Filtrar |
| 9 | `live_doc_generator_service.py` | 399 | Filtrar |
| 10 | `consistency_router.py` | 63 | Filtrar (NOVO Gate 3) |
| 11 | `livedocs_router.py:changelog` | 122 | Filtrar (NOVO Gate 3) |
| 12 | `code_generation.py` | 514 | **Filtrar (NOVO Gate 3 — LGPD compliance)** |

**DBA-M3 — Migration idempotente:** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` em tudo. Padrão da migration 067.

**DBA-M4 — Ordem da migration:** `ALTER TABLE ocg ALTER COLUMN change_type TYPE VARCHAR(30)` ANTES de `ADD COLUMN` em `ingested_documents`. Motivo: rolling deploy não pode falhar entre passos.

**DBA-M5 — Job revert atinge tabelas adicionais:**
- `conflicts_pending_review` do doc deletado → `status='archived_doc_deleted'` ou DELETE
- `chunk_errors_pending_review` do doc deletado → idem
- `persona_follow_up_questions` pendentes do doc → `status='expired'` (DBA-S2, valor já no enum)

**DBA-M6 — Comentário explícito DT-086 no cabeçalho da migration:**
```sql
-- DT-086: purge físico de deleted_reason='lgpd' não implementado nesta migration.
-- Campos pii_fields, ocg_individual.parecer e ocg_global.parecer_consolidated
-- de docs lgpd-deletados permanecem no banco. Implementar scheduled purge em MVP futuro.
```

### SHOULDs Gate 3 (incorporados)

**DBA-S1 — Índice parcial:** `CREATE INDEX idx_ingested_docs_active ON ingested_documents(project_id, arguider_status) WHERE deleted_at IS NULL`. Evita inclusão de docs deletados no plan independente de estatísticas.

**DBA-S2 — `persona_follow_up_questions`:** já consolidado em DBA-M5.

**DBA-S3 — `uploaded_by` ON DELETE SET NULL:** abrir **DT-087** (separada) — não bloqueia MVP 34, mas vira risco com tempo.

**DBA-S4 — `ocg_global.parecer_consolidated`:** documentar no DT-086 que purge LGPD futuro inclui essa tabela também.

**DBA-S5 — CHECK schema mínimo em `revert_metadata`:**
```sql
CHECK (revert_metadata IS NULL OR (
    revert_metadata ? 'score_before' AND
    revert_metadata ? 'score_after'
))
```

### Atualização do critério de aceite

18. ✅ Migration aplica em <5s (banco limpo) e <10s (banco dogfood)
19. ✅ Migration idempotente: re-execução não falha
20. ✅ Re-ingestão de arquivo soft-deleted é aceita (não 409 — DBA-M1)
21. ✅ `consistency_router`, `livedocs_router`, `code_generation` não exibem docs deletados
22. ✅ Job revert marca `conflicts_pending_review`, `chunk_errors_pending_review`, `persona_follow_up_questions` corretamente
23. ✅ DT-086 referenciada no cabeçalho da migration
24. ✅ DT-087 (`uploaded_by` ON DELETE SET NULL) registrada em GCA_MVP_PROGRESS

### Dívidas registradas (sem MVP — só registro)

- **DT-086 (Major)** — Purge físico de docs `deleted_reason='lgpd'` não implementado. `pii_fields`, `ocg_individual.parecer`, `ocg_global.parecer_consolidated` permanecem. Compliance LGPD parcial. Endereçar em MVP futuro de "scheduled purge".
- **DT-087 (Minor)** — `ingested_documents.uploaded_by` sem `ON DELETE` declarado. Com soft-delete vivendo indefinidamente, RESTRICT implícito cresce como risco operacional.

## 8. Próxima ação

**Gate 4 — Dev Sênior:** implementar Fase 34.1 → 34.5 conforme plano. Todos os MUSTs dos 3 gates incorporados (3 GP + 5 Arq + 6 DBA = 14 MUSTs). Segue ordem:

1. **34.1** (~0.5d) Migration `068_mvp34_soft_delete_document.sql` + ORM updates
2. **34.2** (~1.5d) `document_revert_service.py` + Celery task + audit event
3. **34.3** (~0.5d) Endpoint DELETE 202 + GET status + UI
4. **34.4** (~0.5d) Testes (≥80% cobertura, 8 unit + 3 integração) + smoke E2E real
5. **34.5** (~0.25d) CHANGELOG + CLAUDE.md §2.4 update + GCA_MVP_PROGRESS

**Aguarda autorização explícita do GP humano** antes de iniciar Fase 34.1 (CLAUDE.md §2.6: "Cada fase de MVP exige autorização explícita do GP antes de codar").
