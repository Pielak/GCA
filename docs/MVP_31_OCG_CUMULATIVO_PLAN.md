# MVP 31 — OCG Cumulativo + CodeGen Gate

**Status:** Proposta (aguardando aprovação do GP per §7.0 do contrato canônico)
**Data proposta:** 2026-05-02
**Pré-requisito:** Pipeline n8n end-to-end funcional (entregue na sessão 37, 2026-05-02)

---

## 1. Problema canônico

Conforme reafirmado pelo GP em 2026-05-02:

> *"O OCG não sobrescreve, não contrai. Só cresce com informação útil. Informação inútil é descartada. OCG fica estático e só cresce com informação útil."*

E sobre o CodeGen, o critério de liberação é a **maturidade do OCG**: o CodeGen só é liberado para gerar código quando o OCG tem **≥95% de contexto** acumulado. Abaixo disso, o GCA não tem insumo suficiente para produzir código válido.

**Estado atual:**
- O caminho de ingestão antigo (Celery, `ingestion_service.py:1672`) **respeita** essa regra — chama `OCGUpdaterService.update_ocg_from_arguider` que tem o helper canônico `_filter_negative_score_deltas` e versionamento via `ocg_delta_log` com `hash_chain`.
- O caminho novo (n8n, handler `/ingestion-complete` em `webhooks.py:332`) **viola** essa regra — faz `UPDATE ocg SET ocg_data=..., overall_score=..., status=...` direto, sobrescrevendo a cada documento.
- As tabelas `ocg_individual` (por persona/doc), `ocg_global` (consolidado/doc) e `ocg_delta_log` (versão+hash chain) **existem** mas não são populadas pelo caminho n8n.
- O CodeGen (`module_codegen_service.py`, `codegen_prompt_builder.py`) **não consulta** `ocg.is_blocking` nem `ocg.overall_score` — gera código mesmo com OCG bloqueado ou imaturo.

## 2. Objetivo

Fazer o caminho n8n respeitar as mesmas invariantes do caminho Celery, **sem reescrever o `OCGUpdaterService`** (reusar). Adicionar gate explícito no CodeGen que recusa geração até o OCG estar maduro (`overall_score >= 95` e `is_blocking=false`), com motivo legível em cada nível de bloqueio.

## 3. Invariantes a preservar (não negociáveis)

1. **OCG só cresce.** Score de pilar nunca diminui via pipeline automático (é o que `_filter_negative_score_deltas` já faz).
2. **Não sobrescreve.** Cada doc gera **delta** que é mesclado ao estado anterior, não substitui.
3. **Histórico imutável.** Cada doc deixa rastro em `ocg_individual` (uma row por persona) e `ocg_global` (uma row consolidada). Anti-tamper via `ocg_delta_log.hash_chain`.
4. **Lixo é descartado, não armazenado.** Quando uma persona retorna PersonaOutput inválido (G4 reprova), o resultado **não entra** no OCG cumulativo. Vai para histórico marcado `status='failed'` em `ocg_individual` apenas.
5. **CodeGen liberado por maturidade do OCG.** Geração de código **só** roda quando o OCG está maduro: `ocg.is_blocking=false` E `ocg.overall_score >= 95` (limiar de maturidade — abaixo disso o contexto é insuficiente para código válido). Score `< 60` permanece hard-block via CONF (regra existente). Recusa com motivo legível em ambos os casos.
6. **Pipeline n8n permanece funcional.** Nenhuma mudança no n8n side. Toda a lógica fica no backend.

## 4. Não-objetivos (fora do escopo deste MVP)

- Refatorar `OCGUpdaterService`. Reusa como está.
- Adicionar novas personas. As 12 estão estáveis.
- Mudar formato do PersonaOutput v2.
- Implementar revogação manual de score por owner (parked).
- Migrar caminho Celery (já correto). Pipeline antigo continua funcional como fallback.

## 5. Faseamento (5 fases — agile)

### Fase 31.1 — Modelar tabelas + persistir histórico individual e consolidado (~2d, revisada pelo Gate 1)

**Achado do Gate 1 (2026-05-02):** As tabelas `ocg_individual` e `ocg_global` **existem no banco** (verificado via `\d` no postgres) **mas não têm modelo SQLAlchemy** em `backend/app/models/base.py` e **não há migration Alembic** que as crie. São dívida estrutural — foram criadas por SQL manual em algum ponto. A fase precisa fechar esse gap antes de qualquer INSERT.

**Decisão de schema para `persona_id`** (resolvido pelo Gate 1): seguir o padrão de `ocg_delta_log.persona_id` que usa `Column(String(20))` armazenando a tag canônica (`"AUD"`, `"GP"`, etc.). **Não** criar persona-pseudo-users. **Não** FK. As tabelas existentes precisam ser auditadas — se hoje têm FK para `users(id)`, virar dívida pré-MVP a corrigir ou aceitar e adaptar (decisão fica com o Arquiteto no Gate 2).

**Entrega:** Modelos ORM `OCGIndividual` e `OCGGlobal` em `base.py`, migration de stamp no Alembic, `webhooks.py:ingestion_complete` populando as 2 tabelas a cada documento via n8n.

**Tarefas (revisadas pelo Gate 3 — 2026-05-02):**

**Achado crítico do DBA**: Projeto **não usa Alembic** como toolchain ativo — usa SQL plain numerado em `backend/migrations/` (último arquivo: `065_create_pilares_vivos.sql`). Script do Gate 2 em formato Python Alembic foi reescrito como SQL plain.

1. **Migration `066_mvp31_consolidate_ocg_tables.sql`** (SQL plain, não Alembic). Tabelas vazias (0 rows) — custo zero. Inclui também CO-DB-02, CO-DB-03 e CR-DB-03 do Gate 3:
   ```sql
   -- 066_mvp31_consolidate_ocg_tables.sql
   -- MVP 31 Fase 31.1 — schema consolidation + integridade + perf

   BEGIN;

   -- 1. ocg_individual.persona_id: uuid REFERENCES users(id) → VARCHAR(20) (tag canônica)
   ALTER TABLE ocg_individual DROP CONSTRAINT ocg_individual_persona_id_fkey;
   DROP INDEX IF EXISTS idx_ocg_individual_persona;
   ALTER TABLE ocg_individual
       ALTER COLUMN persona_id TYPE VARCHAR(20) USING persona_id::text;
   CREATE INDEX idx_ocg_individual_persona ON ocg_individual(persona_id);

   -- 2. Drop índices duplicados (ORM autogen + manual): 3 em ocg_individual + 7 em ocg
   DROP INDEX IF EXISTS ix_ocg_individual_project_id;
   DROP INDEX IF EXISTS ix_ocg_individual_document_id;
   DROP INDEX IF EXISTS ix_ocg_individual_persona_id;
   DROP INDEX IF EXISTS ix_ocg_project_id;
   DROP INDEX IF EXISTS ix_ocg_questionnaire_id;
   DROP INDEX IF EXISTS ix_ocg_status;
   DROP INDEX IF EXISTS ix_ocg_is_blocking;
   DROP INDEX IF EXISTS ix_ocg_overall_score;
   DROP INDEX IF EXISTS ix_ocg_generated_at;
   DROP INDEX IF EXISTS ix_ocg_created_at;

   -- 3. Integridade do version do OCG (CO-DB-02)
   ALTER TABLE ocg ALTER COLUMN version SET NOT NULL;
   ALTER TABLE ocg ADD CONSTRAINT chk_ocg_version_positive CHECK (version > 0);

   -- 4. ON DELETE explícito em persona_follow_up_questions.answered_by (CO-DB-03)
   ALTER TABLE persona_follow_up_questions
       DROP CONSTRAINT persona_follow_up_questions_answered_by_fkey,
       ADD CONSTRAINT persona_follow_up_questions_answered_by_fkey
           FOREIGN KEY (answered_by) REFERENCES users(id) ON DELETE SET NULL;

   -- 5. Índice composto para gate de CodeGen (CR-DB-03 — index-only scan)
   CREATE INDEX idx_ocg_project_version ON ocg(project_id, version DESC);

   COMMIT;
   ```
2. **Modelos SQLAlchemy** em `backend/app/models/base.py`:
   - `OCGIndividual` com `persona_id = Column(String(20), nullable=False)` (espelhando schema pós-migration)
   - `OCGGlobal` com schema vivo
   - Stubs `OCGIndividualRefined` e `PersonaFollowUpQuestion` apenas com `__tablename__` e PK — só pra Alembic não tentar dropar (DT-080 cobre completar no futuro)
3. **Em `webhooks.py:ingestion_complete`**, antes do UPDATE atual (que será removido na Fase 31.2):
   - Para cada `(persona_tag, persona_output)` em `payload.ocg_individual`: upsert em `ocg_individual` por `(document_id, persona_id)` — `persona_id` é a tag string, não FK.
   - Upsert em `ocg_global` por `document_id`.
4. Idempotência garantida pelo unique constraint existente `uq_ocg_individual_per_document_persona`.

**Critério de aceite:**
- Modelos `OCGIndividual` e `OCGGlobal` importáveis via `from app.models.base import OCGIndividual, OCGGlobal`.
- Migration aplica sem erro em `gca_test` (banco de testes recriado do zero).
- Smoke test: upload de 1 doc → 9 rows em `ocg_individual` (8 especialistas + GP) + 1 row em `ocg_global`.
- Upload de 2 docs no mesmo projeto → 18 rows em `ocg_individual` + 2 rows em `ocg_global`. **Nenhuma row apagada/sobrescrita.**
- `pytest backend/app/tests/test_ocg_individual_persists_per_doc.py` passa em `gca_test`.

**Riscos remanescentes:**
- Schema vivo de `ocg_individual` tem `persona_id uuid REFERENCES users(id)` — incompatível com tag string. Decisão do DBA (Gate 3): alterar coluna (impactando dados eventuais já lá) ou criar pseudo-users idempotentes (12 rows) e mapear tag→uuid no service.

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

### Fase 31.4 — CodeGen Gate por maturidade do OCG (~1d, revisado pelo Gate 2)

**Entrega:** Geração de código consulta maturidade do OCG antes de gerar — em **todos os 6 entry points** identificados pelo Gate 2.

**Conceito:** CodeGen é liberado quando OCG está **maduro** (`overall_score >= 95`). Abaixo de 95, contexto insuficiente — pode rodar mais ingestões para amadurecer. Abaixo de 60 ou com `is_blocking=true` (CONF), é hard-block.

**Achado do Gate 2 (2026-05-02):** O plano original mencionava só `module_codegen_service.py`. Insuficiente. Existem 6 entry points reais de geração de código:

| # | Arquivo | Função | Linha aprox |
|---|---|---|---|
| 1 | `module_codegen_service.py` | `generate_module_from_candidate` | 111 |
| 2 | `code_generation.py` | `generate_scaffold` | 472 |
| 3 | `code_generation.py` | `generate_scaffold_plan` | 1579 |
| 4 | `code_generation.py` | `generate_scaffold_item` | 1788 |
| 5 | `code_generation.py` | `generate_project_code` | 2130 |
| 6 | `code_generation.py` | `generate_module_code` | 2203 |

`codegen_prompt_builder.py` é helper interno (chamado por `code_generation.py` linhas 562, 2485) — **não** é entry point separado.

**Tarefas:**
- Criar helper `_check_ocg_maturity_gate(project_id, db)` em `backend/app/services/ocg_gate.py` (novo arquivo) que retorna `None` se OCG ok, ou `HTTPException(409, ...)` com payload estruturado se bloqueado.
- Inserir chamada `_check_ocg_maturity_gate` no início de cada um dos 6 entry points listados acima — **antes** dos pontos de hardcode Anthropic (DT-079) para não agravar a dívida.
- 3 níveis de gate (mesma lógica nos 6 entry points):
  - `is_blocking=true` → 409 `block_level=hard_block` com motivo
  - `overall_score < 60` → 409 `block_level=insufficient` (mínimo absoluto)
  - `overall_score < 95` → 409 `block_level=immature` (orientação para amadurecer)
- Endpoints de codegen devolvem 409 com payload estruturado:
  ```json
  {
    "blocked": true,
    "block_level": "hard_block|insufficient|immature",
    "overall_score": <n>,
    "score_required": 95,
    "blocking_reason": "...",
    "personas_blocking": [...]
  }
  ```

**Critério de aceite:**
- Doc fraco (CONF blocking) → 409 com `block_level=hard_block`
- OCG com score 50 → 409 com `block_level=insufficient`
- OCG com score 80 → 409 com `block_level=immature` (mensagem orientando ingerir mais docs)
- OCG com score 96 e `is_blocking=false` → endpoint passa, código gerado
- **Cobertura nos 6 entry points**: `grep -n "is_blocking\|overall_score\|_check_ocg_maturity_gate" backend/app/routers/code_generation.py backend/app/services/module_codegen_service.py` retorna match em todas as 6 funções.

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

**~5-6 dias de implementação** (revisado pelo Gate 1 — Fase 31.1 saiu de 1d para 2d por causa da dívida ORM/migration descoberta) + 0.5d de revisão de aceite = **6d**.

## 7. Gates do fluxo Gatekeeper para este MVP

| Gate | Persona | Critério |
|---|---|---|
| 1 | gerente-projetos-ti | Aprovar escopo (este doc) e timeline |
| 2 | arquiteto-projetos | Validar reuso do `OCGUpdaterService`, decisão sobre persona_id em `ocg_individual` |
| 3 | dba | Revisar custos de leitura/escrita por doc (3 INSERTs + 1 UPDATE versionado), verificar índices em `ocg_individual` e `ocg_global` |
| 4 | dev-senior | Implementar fases 31.1-31.4 |
| 5 | tester-qa | Validar fase 31.5 |
| skill `preparar-release` | — | Checklist final antes de merge |

## 8. Riscos identificados (revisados pelo Gate 1 em 2026-05-02)

| # | Risco | Probabilidade | Mitigação |
|---|---|---|---|
| R1 | Tabelas `ocg_individual` e `ocg_global` existem no banco mas **não têm modelo ORM nem migration** — Fase 31.1 precisa fechar essa dívida estrutural primeiro | Alta | Decisão do Gate 2: stamp Alembic se schema OK, ou migration de consolidação se houver divergência |
| R2 | Schema vivo de `ocg_individual.persona_id` é `uuid REFERENCES users(id)` — incompatível com tag `String(20)` do padrão `ocg_delta_log` | Alta | Decisão do Gate 3 (DBA): alterar coluna ou criar pseudo-users idempotentes (12 rows, FK válida) e mapear tag→uuid no service |
| R3 | Formato `arguider_analysis` esperado pelo `OCGUpdaterService._build_user_prompt` (linha 813) não bate com payload do Consolidador n8n | Média | Investigar antes de codar a Fase 31.2; pode requerer adaptador de payload (não refator do updater) |
| R4 | `OCGUpdaterService` chama LLM (custa tokens). Cada doc ingerido via n8n gera 1 chamada extra. | Média | Política de criticidade §2.5 — provider de criticidade média (não premium) |
| R5 | Smoke test E2E com 3 docs precisa de 3 docs reais em projeto com LLM configurado | Baixa | Reusar projeto `24bf72c3-...` (DeepSeek validado) |
| R6 | `module_codegen_service.py:164-165` tem hardcode de provider Anthropic — viola §3.1 do contrato (`AIKeyResolver` é porta única) | Média | **NÃO corrigir neste MVP** (fora do escopo). Registrar como nova DT no `GCA_MVP_PROGRESS.md §3` para próximo MVP. Dev tocando Fase 31.4 deve **não agravar**. |
| R7 | Falta de `audit_log` no CodeGen (DT já listada em `GCA_MVP_PROGRESS.md §3.0`) | Baixa | Não bloqueia MVP 31 mas Fase 31.4 não deve fechar essa DT silenciosamente |

## 9. Compatibilidade backward

- Pipeline Celery antigo (`ingestion_service.py:1672`) não muda. Continua funcionando como fallback se `INGESTION_VIA_N8N=false`.
- Tabela `ocg` legacy continua sendo o estado mestre. Nenhuma mudança de schema.
- Tabelas `ocg_individual`, `ocg_global`, `ocg_delta_log` ganham mais rows mas mesmo schema.
- Endpoints de codegen ganham resposta 409 nova; clientes que tratam erros HTTP já caem no fluxo correto.

## 10. Refinamentos do Gate 1 (aplicados em 2026-05-02)

Veredito: **Aprovado com ressalvas** (gerente-projetos-ti, 2026-05-02). Refinamentos exigidos antes do Gate 2:

1. **Limiar 95% confirmado pelo GP em chat** (2026-05-02) como critério de negócio. Não é mais SHOULD — está consolidado.
2. **Não-regressão E2E após cada fase**: o smoke test de 135s do pipeline n8n deve continuar verde após cada fase. Critério de aceite explícito da Fase 31.5.
3. **`actor_id` fallback explícito**: se `ingested_documents.uploaded_by` for nulo ou doc não encontrado, passar `actor_id=None` ao `OCGUpdaterService` (suportado pela assinatura). Documentar como escolha intencional.
4. **§5 do contrato canônico** atualizado pela Fase 31.5 com cláusula explícita: *"no caminho n8n, handler `/ingestion-complete` delega ao `OCGUpdaterService.update_ocg_from_arguider`"* — verificar via grep no critério de aceite.
5. **R6 (hardcode Anthropic em `module_codegen_service.py`)**: registrar como nova DT em `GCA_MVP_PROGRESS.md §3` antes do dev tocar a Fase 31.4. Não corrigir neste MVP.

## 11. Refinamentos do Gate 2 (aplicados em 2026-05-02)

Veredito: **Aprovado com ressalvas** (arquiteto-projetos, 2026-05-02). Decisões arquiteturais consolidadas:

1. **Schema vivo confirmado**: `ocg_individual.persona_id = uuid REFERENCES users(id)` (divergente do padrão `ocg_delta_log = String(20)`). Tabelas vazias (0 rows). Tabelas filha `ocg_individual_refined` e `persona_follow_up_questions` também sem ORM.
2. **Decisão Fase 31.1**: migration de **consolidação** (opção b), **não** stamp. Script em §5 Fase 31.1.
3. **Adapter n8n→updater**: confirmado como caminho correto. Updater não muda. Adapter constrói `arguider_analysis` mapeando `consolidated_findings` para `gaps`/`show_stoppers`/`recommendations` (CR-2 do Arquiteto).
4. **R6 confirmado fora de escopo**: registrado como **DT-079** em `GCA_MVP_PROGRESS.md §3.2`. Diagnóstico ampliou: hardcode também em `code_generation.py:592,1693,1838,2353,2367,2498`.
5. **DT-080 aberta**: ORM ausente para `ocg_individual`, `ocg_global`, `ocg_individual_refined`, `persona_follow_up_questions`. MVP 31 endereça parcialmente (as 2 primeiras + stubs das 2 filhas).
6. **CO-1 do Gate 2 aplicado**: Fase 31.4 expandida para 6 entry points (não só `module_codegen_service.py`). Helper `ocg_gate.py` novo.
7. **CR-3**: `trigger_source = TRIGGER_N8N` constante, não literal. Sugestão acatada para Fase 31.2.
8. **CR-4**: lock `asyncio.Lock` per-project é in-process. Aceitável para uvicorn single-worker atual. DT futura quando escalar para multi-worker.

## 13. Refinamentos do Gate 3 (aplicados em 2026-05-02)

Veredito: **Aprovado com ressalvas** (DBA, 2026-05-02). Decisões críticas:

1. **Achado bloqueador**: projeto **não usa Alembic** — usa SQL plain numerado em `backend/migrations/`. Script do Gate 2 reescrito como `066_mvp31_consolidate_ocg_tables.sql` (acima na Fase 31.1).
2. **Custo de escrita** validado: 15 ops/doc viável para 50+ docs/dia/projeto. Lock per-project pode causar fila de até 25min em burst (50 docs simultâneos do mesmo projeto) — DT já aceita pelo Gate 2 (CR-4).
3. **6 índices duplicados** detectados em `ocg_individual` + 7 pares em `ocg` (ORM autogen vs SQL manual). Drop incluído na migration 066.
4. **`ocg.version`** sem NOT NULL e sem CHECK — incluído na migration 066 (CO-DB-02).
5. **`persona_follow_up_questions.answered_by`** sem `ON DELETE` declarado — incluído como `SET NULL` na migration 066 (CO-DB-03).
6. **Índice composto** `idx_ocg_project_version` para o gate de CodeGen (Fase 31.4) — incluído na migration 066 (CR-DB-03). Garante index-only scan.
7. **Retenção**: nenhuma política de archive/purge atual. Risco LGPD baixo (parecer técnico, base legal: legítimo interesse Art. 7º IX). Sugestão: prazo = vida do projeto + 5 anos. Documentar em produção, não bloqueia MVP 31.
8. **`ocg_delta_log.ocg_snapshot`** cresce sem limite — DT futura para particionamento/TTL.
9. **`ocg_individual.status`** sem CHECK constraint — DT futura (CR-DB-02).

## 14. Próximo passo

**Gate 4 — Dev Sênior** com mandato específico:

- Implementar Fases 31.1–31.4 conforme plano consolidado (Gates 1+2+3).
- Criar `backend/migrations/066_mvp31_consolidate_ocg_tables.sql` (SQL plain) e aplicar em `gca_test` antes de qualquer ORM.
- Criar modelos ORM `OCGIndividual`, `OCGGlobal` em `backend/app/models/base.py` com `persona_id = String(20)`. Stubs `OCGIndividualRefined` e `PersonaFollowUpQuestion` apenas com `__tablename__` e PK.
- Criar `backend/app/services/ocg_gate.py` com helper `_check_ocg_maturity_gate(project_id, db)` retornando `None` ou `HTTPException(409, ...)` estruturado.
- Aplicar gate nos 6 entry points listados na Fase 31.4 — **antes** dos pontos hardcoded de provider Anthropic (DT-079) para não agravar.
- Adapter n8n→updater em `webhooks.py:ingestion_complete` mapeando `consolidated_findings` → `gaps`/`show_stoppers`/`recommendations`.
- Constante `TRIGGER_N8N = "document_ingestion_n8n"` em `ocg_updater_service.py` (não literal).
- Smoke test E2E (135s) deve continuar verde após cada fase entregue (não-regressão).
- Pipeline n8n permanece intocado.
