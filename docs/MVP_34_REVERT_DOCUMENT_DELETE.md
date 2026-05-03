# MVP 34 — Reversão de propagação ao deletar documento

**Status:** DEFINIDO 2026-05-03 — aguardando Gate 1 (gerente-projetos-ti)
**Branch:** `feat/mvp34-revert-document-delete`
**Origem:** GP identificou que smoke fixture do MVP 32 (doc `9825e89b` no projeto Assistente Judicial) ficou contaminando OCG sem caminho de limpeza canônico. Regra "OCG não contrai" cobre ingestão ruim, mas não cobre deleção legítima.

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
- Atualizar todas as queries de `ingested_documents` que listam para o GP/UI: filtrar `WHERE deleted_at IS NULL` (cuidado com regressão silenciosa)

### Fase 34.2 — Celery job + service (~1.5d)
- Novo `app/services/document_revert_service.py::revert_document_propagation(doc_id, actor_id, reason)`
- Lê todos os `ocg_individual` rows ATIVOS do projeto (excluindo o doc deletado)
- Re-agrega via `_load_persona_scores` (já existente, MVP 33)
- Calcula novo `PILLAR_SCORES` + `overall_score`
- Cria nova versão OCG com `change_type='REVERT_DOCUMENT_DELETE'`
- Audit event `DOCUMENT_REVERTED` (novo `AuditEvents`)
- Auto-archive `module_candidates` órfãos

### Fase 34.3 — Endpoint HTTP + UI (~0.5d)
- `DELETE /api/v1/projects/{pid}/ingestion/{doc_id}?reason=manual|lgpd|smoke_cleanup` retorna 202 Accepted com `revert_job_id`
- `GET /api/v1/projects/{pid}/revert-jobs/{job_id}/status` para polling
- UI: botão "🗑 Apagar com reversão" na tabela de Ingestão (substitui DELETE atual que é hard-delete sem reversão)

### Fase 34.4 — Testes + smoke E2E real (~0.5d)
- Unit: revert_document_propagation com fixture multi-doc
- Integração: endpoint DELETE → Celery → DB consistente
- Smoke E2E real: deletar doc 9825e89b do AJA, confirmar OCG v5 → v6 com score recalculado a partir do zero (provavelmente vai pra zero pois é o único doc analisado nesse projeto)

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
10. ✅ Suite de testes verde (unit + integração + smoke E2E real)
11. ✅ Não-regressão: pipeline n8n continua ingerindo + atualizando OCG normalmente

---

## 6. Próxima ação

**Gate 1 (gerente-projetos-ti):** validar escopo, aceite, viabilidade e dependências de negócio. Após aprovação → Gate 2 (arquiteto-projetos).
