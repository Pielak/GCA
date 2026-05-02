# MVP 31 — OCG Cumulativo + CodeGen Gate

**Status:** Proposta (aguardando aprovação do GP per §7.0 do contrato canônico)
**Data proposta:** 2026-05-02
**Pré-requisito:** Pipeline n8n end-to-end funcional (entregue na sessão 37, 2026-05-02)

---

## 1. Problema canônico

Conforme reafirmado pelo GP em 2026-05-02:

> *"O OCG não sobrescreve, não contrai. Só cresce com informação útil. Informação inútil é descartada. CodeGen fica estático e só cresce com informação útil."*

**Estado atual:**
- O caminho de ingestão antigo (Celery, `ingestion_service.py:1672`) **respeita** essa regra — chama `OCGUpdaterService.update_ocg_from_arguider` que tem o helper canônico `_filter_negative_score_deltas` e versionamento via `ocg_delta_log` com `hash_chain`.
- O caminho novo (n8n, handler `/ingestion-complete` em `webhooks.py:332`) **viola** essa regra — faz `UPDATE ocg SET ocg_data=..., overall_score=..., status=...` direto, sobrescrevendo a cada documento.
- As tabelas `ocg_individual` (por persona/doc), `ocg_global` (consolidado/doc) e `ocg_delta_log` (versão+hash chain) **existem** mas não são populadas pelo caminho n8n.
- O CodeGen (`module_codegen_service.py`, `codegen_prompt_builder.py`) **não consulta** `ocg.is_blocking` — gera código mesmo com OCG bloqueado.

## 2. Objetivo

Fazer o caminho n8n respeitar as mesmas invariantes do caminho Celery, **sem reescrever o `OCGUpdaterService`** (reusar). Adicionar gate explícito no CodeGen que recusa geração quando OCG está bloqueado, com motivo legível.

## 3. Invariantes a preservar (não negociáveis)

1. **OCG só cresce.** Score de pilar nunca diminui via pipeline automático (é o que `_filter_negative_score_deltas` já faz).
2. **Não sobrescreve.** Cada doc gera **delta** que é mesclado ao estado anterior, não substitui.
3. **Histórico imutável.** Cada doc deixa rastro em `ocg_individual` (uma row por persona) e `ocg_global` (uma row consolidada). Anti-tamper via `ocg_delta_log.hash_chain`.
4. **Lixo é descartado, não armazenado.** Quando uma persona retorna PersonaOutput inválido (G4 reprova), o resultado **não entra** no OCG cumulativo. Vai para histórico marcado `status='failed'` em `ocg_individual` apenas.
5. **CodeGen é estático.** Geração de código **só** roda quando `ocg.is_blocking=false` E `ocg.overall_score >= 60` (mesmo limiar do CONF). Caso contrário, recusa com motivo.
6. **Pipeline n8n permanece funcional.** Nenhuma mudança no n8n side. Toda a lógica fica no backend.

## 4. Não-objetivos (fora do escopo deste MVP)

- Refatorar `OCGUpdaterService`. Reusa como está.
- Adicionar novas personas. As 12 estão estáveis.
- Mudar formato do PersonaOutput v2.
- Implementar revogação manual de score por owner (parked).
- Migrar caminho Celery (já correto). Pipeline antigo continua funcional como fallback.

## 5. Faseamento (5 fases — agile)

### Fase 31.1 — Persistir histórico individual e consolidado (~1d)

**Entrega:** `ocg_individual` e `ocg_global` populados corretamente a cada documento ingerido via n8n.

**Tarefas:**
- Em `webhooks.py:ingestion_complete`, antes do UPDATE atual:
  1. Para cada `(persona_tag, persona_output)` em `payload.ocg_individual`:
     - `INSERT INTO ocg_individual (project_id, document_id, persona_id, persona_name, parecer, status, ai_provider, ai_model, started_at, completed_at)` com upsert por `(document_id, persona_id)`.
  2. `INSERT INTO ocg_global (project_id, document_id, parecer_consolidated, consensus_fields, conflicting_fields, voting_results, consolidated_at)` com upsert por `document_id`.
- Persona ID precisa ser resolvido. Hoje a tabela referencia `users(id)` — verificar se há "persona pseudo-user" ou se precisa criar tabela `personas` (descobrir antes de implementar; pode ser dívida pré-existente).

**Critério de aceite:**
- Smoke test: upload de 1 doc → 9 rows em `ocg_individual` (8 especialistas + GP) + 1 row em `ocg_global`.
- Upload de 2 docs no mesmo projeto → 18 rows em `ocg_individual` + 2 rows em `ocg_global`. **Nenhuma row apagada/sobrescrita.**

**Risco:** Se `persona_id` referenciar `users(id)`, criar persona pseudo-users de uma vez ou abrir gap como dívida pré-MVP.

### Fase 31.2 — Substituir UPDATE cru por chamada ao OCGUpdaterService (~1.5d)

**Entrega:** Caminho n8n usa `OCGUpdaterService.update_ocg_from_arguider` igual ao Celery.

**Tarefas:**
- Em `webhooks.py:ingestion_complete`, **remover** o UPDATE direto na tabela `ocg`.
- Construir `arguider_analysis` payload no formato esperado pelo updater (verificar contrato em `ocg_updater_service.py:217`).
- Chamar:
  ```python
  updater = OCGUpdaterService(db)
  result = await updater.update_ocg_from_arguider(
      project_id=payload.project_id,
      arguider_analysis=arguider_analysis,
      document_id=payload.ingestion_id,
      actor_id=...,  # uploader do doc, buscar via SELECT em ingested_documents
      trigger_source="document_ingestion_n8n",  # ← distingue de Celery no log
  )
  ```
- Tratar `result["status"]=="awaiting_ocg"` (OCG legacy ausente) como warn não-fatal (igual Celery faz, ver `ingestion_service.py:1685`).
- Tratar falha do LLM no updater → mark doc como `arguider_status='ocg_pending'` em vez de `completed`.

**Critério de aceite:**
- 2º doc ingerido no mesmo projeto: `ocg.version` incrementa, `ocg_data` reflete merge (não substitui), `ocg_delta_log` ganha row com `trigger_source='document_ingestion_n8n'`, `hash_chain` válido.
- Doc com PersonaOutput tentando baixar score: delta filtrado, `ocg_delta_log.fields_changed` mostra `_reason='negative_score_blocked'`.

**Risco:** O `OCGUpdaterService` espera `arguider_analysis` num formato específico (provavelmente análise consolidada do Arguidor antigo). Pode ser preciso adaptar payload do n8n para esse formato. Investigar antes.

### Fase 31.3 — Política de "lixo descartado" (~0.5d)

**Entrega:** PersonaOutputs inválidos/falhos não contaminam o OCG cumulativo, mas ficam registrados para auditoria.

**Tarefas:**
- Em `ocg_individual`: `status='failed'` com `error_message` populado quando G4 reprovou (já vem em `payload.personas_failed`).
- No payload entregue ao `OCGUpdaterService`, **excluir** personas com `status='failed'` de `ocg_individual` consolidado e `ocg_global_delta`.
- No `ocg_global.parecer_consolidated`, excluir personas falhas de `consensus_fields`/`voting_results`.
- Quando `personas_failed >= len(personas_executed)/2` (maioria falhou), marcar doc como `arguider_status='partial'` e **não** chamar updater (sem dado confiável pra mesclar).

**Critério de aceite:**
- Doc com 1 persona falha (ex: SEG retornou JSON inválido): 8 rows OK + 1 row failed em `ocg_individual`. OCG mestre cresce só com as 8.
- Doc com 5+ personas falhas: nenhum delta aplicado ao OCG mestre. Status doc = `partial` com erro descritivo.

### Fase 31.4 — CodeGen Gate (~0.5d)

**Entrega:** Geração de código consulta `ocg.is_blocking` antes de gerar.

**Tarefas:**
- Em `module_codegen_service.py`: na entrada do método de geração, ler `ocg.is_blocking` e `ocg.overall_score` do projeto.
- Se `is_blocking=true` OU `overall_score < 60`: levantar `HTTPException(409, detail="OCG bloqueado: <motivo>. Codegen exige overall_score>=60 e is_blocking=false.")`.
- Mesma checagem em `codegen_prompt_builder.py` se houver entry point separado.
- Endpoints de codegen no router devolvem 409 com payload estruturado: `{ "blocked": true, "overall_score": ..., "blocking_reason": ..., "personas_blocking": [...] }`.

**Critério de aceite:**
- Smoke test: ingerir doc fraco que deixe CONF<60 → tentar `/code-generation/scaffold/plan` → 409 com motivo.
- Ingerir doc sólido depois (overall sobe acima de 60, is_blocking=false) → mesmo endpoint passa.

### Fase 31.5 — Testes + doc + observabilidade (~1d)

**Entrega:** Suíte de testes verde, doc atualizado, métricas de OCG cumulativo.

**Tarefas:**
- Testes unit:
  - `test_ocg_individual_persists_per_doc.py` (1 doc → 9 rows; 2 docs → 18 rows; sem sobrescrita).
  - `test_ocg_negative_delta_blocked.py` (delta tentando baixar score → bloqueado, log captura `_reason`).
  - `test_codegen_gate_respects_blocked.py` (gate retorna 409 quando bloqueado).
  - `test_failed_persona_excluded_from_ocg.py` (persona failed não entra no merge).
- Teste E2E (`test_e2e_n8n_ocg_cumulativo.py`): upload 3 docs sequenciais, verificar growth de `ocg.version` (0→3) e crescimento de findings agregados em `ocg_data.consolidated_findings`.
- Atualizar `docs/n8n-pipeline/PIPELINE_OPERACIONAL.md` removendo as dívidas resolvidas, documentando o novo fluxo.
- Atualizar `GCA_CANONICAL_CONTRACT.md` §5 (OCG) com cláusula explícita: "no caminho n8n, handler `/ingestion-complete` delega ao `OCGUpdaterService`".
- Métricas Prometheus (opcional): `gca_ocg_delta_applied_total{project,trigger_source}`, `gca_ocg_negative_delta_blocked_total`, `gca_codegen_blocked_total{reason}`.

**Critério de aceite:**
- pytest local em `gca_test`: 100% verde nos novos testes + sem regressão.
- Doc canônico (`PIPELINE_OPERACIONAL.md`) marca §6 dívidas relacionadas como **resolvidas**.

## 6. Estimativa total

**~4-4.5 dias de implementação** + 0.5d de revisão de aceite = **5d** (1 sprint pequeno).

## 7. Gates do fluxo Gatekeeper para este MVP

| Gate | Persona | Critério |
|---|---|---|
| 1 | gerente-projetos-ti | Aprovar escopo (este doc) e timeline |
| 2 | arquiteto-projetos | Validar reuso do `OCGUpdaterService`, decisão sobre persona_id em `ocg_individual` |
| 3 | dba | Revisar custos de leitura/escrita por doc (3 INSERTs + 1 UPDATE versionado), verificar índices em `ocg_individual` e `ocg_global` |
| 4 | dev-senior | Implementar fases 31.1-31.4 |
| 5 | tester-qa | Validar fase 31.5 |
| skill `preparar-release` | — | Checklist final antes de merge |

## 8. Riscos identificados

| Risco | Probabilidade | Mitigação |
|---|---|---|
| `persona_id` em `ocg_individual` referencia `users(id)` — sem persona-user, INSERT falha | Alta | Investigar na Fase 31.1 antes de codar; criar persona pseudo-users (12 rows, idempotente) ou abrir gap como dívida |
| Formato `arguider_analysis` esperado pelo `OCGUpdaterService` não bate com payload do consolidador n8n | Média | Investigar antes de codar a Fase 31.2; pode requerer adaptação de payload (não refator do updater) |
| `OCGUpdaterService` chama LLM (custa tokens). Cada doc ingerido via n8n vai gerar 1 chamada extra. | Média | Documentar custo em §8 do contrato (já tem política de criticidade); usar provider de criticidade média (não premium) na chamada do updater |
| Smoke test E2E com 3 docs precisa de 3 docs reais em projeto com LLM configurado | Baixa | Reusar projeto `24bf72c3-...` que já tem DeepSeek validado |

## 9. Compatibilidade backward

- Pipeline Celery antigo (`ingestion_service.py:1672`) não muda. Continua funcionando como fallback se `INGESTION_VIA_N8N=false`.
- Tabela `ocg` legacy continua sendo o estado mestre. Nenhuma mudança de schema.
- Tabelas `ocg_individual`, `ocg_global`, `ocg_delta_log` ganham mais rows mas mesmo schema.
- Endpoints de codegen ganham resposta 409 nova; clientes que tratam erros HTTP já caem no fluxo correto.

## 10. Próximo passo

Aprovação do GP via Gate 1 (gerente-projetos-ti) com este doc como input. Depois disso o Arquiteto investiga as 2 incertezas (persona_id, arguider_analysis format) e dá go/no-go pra Fase 31.1.
