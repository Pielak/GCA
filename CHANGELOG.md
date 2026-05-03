# Changelog

All notable changes to GCA will be documented in this file.

## [MVP 35 — Validação canônica do Questionário Técnico] - 2026-05-03

### Entrega principal

GP identificou 4 lacunas no fluxo Salvar/Validar/Submeter + necessidade de validação técnica de combos (FE×BE×DB×compliance×infra). MVP 35 entrega: máquina de estado canônica, validação 2 camadas (regras determinísticas + LLM), Q13 textarea condicional, IngestedDocument sintético na aba Ingestão, e cascata especial — deletar questionnaire = projeto volta à fase de configuração.

### Estado canônico

Enum `technical_questionnaires.status` ganha CHECK constraint:
- `draft` — rascunho/auto-save
- `validated` — passou Validar Escopo (Camada 1), pré-submit
- `submitted` — terminal, dispara personas + cria IngestedDocument sintético (após Camada 2 LLM)
- `archived` — deletado via Ingestão (volta projeto a setup)

### Validação 2 camadas

**Camada 1 — RulesEvaluator** (`backend/app/services/questionnaire_validation/`):
- 30 regras DSL JSON em 5 temas (NoSQL×ACID, Stack runtime, FE×BE, Compliance×PII, Infra×escala)
- Operadores: `Qx` (eq), `Qx_contains` (lista), AND implícito
- Stateless, < 50ms para 30 regras
- Endpoint `GET /api/v1/projects/technical-questionnaire/rules` (single source of truth)
- Validate-on-blur 800ms debounced no frontend (preview, sem persistir)

**Camada 2 — LLM sanity check** (apenas no submit):
- Reusa `call_codegen_llm` (porta única DT-079 + AIKeyResolver §3.1)
- Prompt mínimo: responses + conflicts_detected (não passa as 30 regras)
- Em falha, **bloqueia submit** com 503 friendly (alinha §0 CLAUDE.md "sem fallback silencioso")

### Pipeline canônico (ordem hierárquica)

`_check_setup_status` agora exige (NESTA ORDEM):
1. Repositório Git configurado
2. Chave LLM válida
3. Questionário **APROVADO E** submetido (sem `approved=True`, gate fica fechado)

### IngestedDocument sintético

Submit cria row em `ingested_documents`:
- `file_type='questionnaire'` (com guard explícito no pipeline n8n + Celery — Arq-M1)
- `file_hash = sha256(canonical(responses))` — idempotente (Arq-M2): listas com ordens diferentes geram mesmo hash
- `arguider_status='completed'` — NÃO entra no pipeline
- `filename=questionnaire-{id}.json` (sem arquivo físico)
- Aparece na aba Ingestão para o GP gerenciar

### Cascata especial: delete questionnaire = volta a setup

Quando GP soft-deleta IngestedDocument tipo `questionnaire` (via aba Ingestão):
- DocumentRevertService (MVP 34) cascata estendida (DBA-M6)
- `TechnicalQuestionnaire.status` → `archived`
- `Questionnaire.approved` → `False`
- `setup_status.questionnaire_approved` → `False` → `ready_to_activate` → `False`
- Pipeline n8n bloqueado até novo questionário submetido
- Modal de delete diferenciado na UI (S1 Gate 1) com aviso explícito

### Migration 069

- 3 CHECK constraints em `technical_questionnaires` (status enum, submitted_at NOT NULL, validated_at NOT NULL)
- UPDATE preventivo: legacy `ocg_generated`/`validated` → `submitted`
- **Índice único parcial** `uq_ingested_doc_hash_active WHERE deleted_at IS NULL` (substitui UNIQUE regular) — permite re-submit pós-soft-delete sem `UniqueViolationError`

### Q13 multi_select_with_other

Textarea condicional `<textarea rows=3>` quando opção "Outros" marcada. Multi-line, resize-y, font mono, placeholder com exemplo concreto. Schema backend `Q13` já era `multiselect_with_other` (MVP 35 só refina UX).

### Mudanças técnicas

- `backend/app/services/questionnaire_validation/` (novo módulo): rules_catalog, rules_evaluator, llm_sanity_check, synthetic_document
- `backend/app/services/document_revert_service.py`: cascata `file_type='questionnaire'` (DBA-M6)
- `backend/app/services/ingestion_service.py`: guards Arq-M1 em `_dispatch_to_n8n` + dispatch Celery
- `backend/app/routers/technical_questionnaire_router.py`: endpoint `validate` com Camada 2 + persistência `validated_at`, endpoint `GET /rules`, submit valida `status='validated'`, chama LLM, cria IngestedDocument
- `backend/app/routers/project_setup_router.py`: gate canônico exige `approved AND submitted` (MVP 35)
- `backend/migrations/069_mvp35_questionnaire_validation.sql`: CHECKs + índice único parcial
- `frontend/src/hooks/useTechnicalQuestionnaire.ts`: tipo `archived`, `validateInline`, `useRulesCatalog`
- `frontend/src/components/questionnaire/TechnicalQuestionnaireForm.tsx`: painel inline 3 níveis, Submeter condicional, Q13 textarea
- `frontend/src/pages/projects/IngestionPage.tsx`: modal delete diferenciado para questionnaire

### Decisões binárias autorizadas pelo GP

1. Estado `draft → validated → submitted | archived`
2. Submit cria IngestedDocument tipo questionnaire
3. Frontend guia ordem repo→LLM→questionário
4. Validar obrigatório antes de Submeter
5. Delete questionnaire = volta a setup

### Testes

- 90/90 verdes (29 RulesEvaluator + 16 SyntheticDoc/LLM + 16 ValidationEndpoint + 13 MVP 32 não-regressão + 16 MVP 34 não-regressão)
- 110/110 verdes na suite ampla (zero regressão MVP 32-35 + DT-079/080)
- Smoke E2E real: delete questionnaire → cascata canônica completa, ready_to_activate=False

### Sem dívidas técnicas novas

DT-086 (purge LGPD) e DT-087 (uploaded_by ON DELETE) já registradas no MVP 34. MVP 35 não abre dívidas novas.

---

## [MVP 34 — Reversão de propagação ao deletar documento] - 2026-05-03

### Entrega principal

Quando GP soft-deleta um `ingested_documents`, os efeitos cumulativos do doc no OCG, backlog e tabelas auxiliares são automaticamente revertidos. **Não viola §2.4 ("OCG não contrai por ingestão")** — complementa: deleção legítima da fonte (smoke fixture, erro humano, PII LGPD, doc obsoleto) agora tem caminho canônico de limpeza, com auditoria preservada.

### Mudanças técnicas

- **Migration 068**: 4 colunas novas em `ingested_documents` (`deleted_at`, `deleted_by`, `deleted_reason` com CHECK, `revert_metadata` JSONB com CHECK schema mínimo). `ocg.change_type` ampliado para VARCHAR(30). Índice parcial `WHERE deleted_at IS NULL`.
- **`document_revert_service.py` (novo)**: operação atômica em 12 passos — soft-delete + recompute OCG + cleanup auxiliares + auto-archive backlog + audit + payload em `revert_metadata`.
- **Celery task `revert_document_propagation_task`** com lease distribuído Redis (`gca:task:revert_document:{pid}:{did}`, TTL 120s).
- **Endpoint `DELETE /ingestion/{did}?reason=` refatorado**: retorna **202 Accepted** + `revert_job_id` (breaking change vs 200 OK síncrono pré-MVP 34).
- **Endpoint `GET /revert-jobs/{job_id}/status`** novo — polling do Celery AsyncResult.
- **12 pontos de query** com filtro `deleted_at IS NULL`: `ingestion_service` (5), `ocg_updater_service._load_persona_scores` (JOIN), 3 generators (spec global, test spec, livedoc), 3 routers (consistency, livedocs, code_generation — CRÍTICO LGPD).
- **AuditEvents.DOCUMENT_REVERTED** novo no catálogo canônico, hash chain íntegro.
- **Frontend**: hook `useDeleteDocument` aceita `{documentId, reason}`, novo hook `useRevertJobStatus` com polling 1.5s, `IngestionPage` com confirm() amigável.
- **CLAUDE.md §2.4** atualizado com a regra complementar de reversão por deleção legítima.

### Decisões binárias autorizadas pelo GP

- Soft delete (`deleted_at`) — permite undelete via API
- Recompute background (Celery) — não bloqueia UX
- Backlog auto-archive de módulos órfãos
- LGPD usa mesmo fluxo (`deleted_reason='lgpd'`)

### Testes

- 15/15 verdes em `test_mvp34_document_revert.py` (8 unit obrigatórios M1 + 5 extras + 2 guards estáticos)
- **89% cobertura** do `document_revert_service.py` (≥80% exigido pelo Gate 1 M1)
- Suite ampla: 409 passed, 0 failed
- Smoke E2E real via HTTP validado: OCG v8 → v9, `change_type=REVERT_DOCUMENT_DELETE`, `duration_ms=189`

### Dívidas técnicas registradas

- **DT-086 (Major)** — Purge físico LGPD não coberto. `pii_fields`, `ocg_individual.parecer`, `ocg_global.parecer_consolidated` permanecem após soft-delete. Compliance LGPD parcial. MVP futuro de "scheduled purge" cobre.
- **DT-087 (Minor)** — `ingested_documents.uploaded_by` sem `ON DELETE` declarado. Migration posterior declara `ON DELETE SET NULL`.

### Breaking changes

- `DELETE /api/v1/projects/{pid}/ingestion/{did}` retorna **202 Accepted** com `revert_job_id` em vez de **200 OK** síncrono. Frontend deve fazer polling via `GET /revert-jobs/{job_id}/status`. Hook `useDeleteDocument` já invalida queries `ocg`/`roadmap` automaticamente.

### Métricas

| Item | Valor |
|---|---|
| Esforço real | ~1.5d (estimativa original 3-4d) |
| Gates Gatekeeper | 3 aprovados (GP + Arquiteto + DBA) |
| MUSTs incorporados | 14 (3 GP + 5 Arq + 6 DBA) |
| Critérios de aceite | 24 testáveis |
| Pontos de query atualizados | 12 |
| Cobertura nova | 89% |
| Testes novos | 15 |
| Testes não-regressão | 409 |

### Validação E2E real

Doc 9825e89b-31dc-4ef9-ac0d-23897e1e67dc do projeto Assistente Judicial para Advogados:
- DELETE 202 → `revert_job_id`
- GET status → `state=completed`, `result.status=reverted`
- OCG v8 → v9
- `change_type=REVERT_DOCUMENT_DELETE`
- `audit_log_global` row com hash chain íntegro
- `ocg_delta_log` row com `trigger_source=document_revert`
- `maturity_warning` populado em PT-BR

---

## [MVP 33 — Expansão PERSONA_TO_PILLAR para 12 personas LLM] - 2026-05-02

### Entrega principal

`PERSONA_TO_PILLAR` (em `ocg_consolidator_service.py`) expandido de 7 para 11 entradas. Personas SEG, CONF, LGPD e NEG agora contribuem com seus scores ao OCG cumulativo — antes eram silenciosamente descartadas no fallback `_load_persona_scores`. P2 (rules) e P7 (security) agora ficam populadas mesmo no caminho de fallback (sem LLM).

### Mudanças técnicas

- `PERSONA_TO_PILLAR`: +SEG→P7, +CONF→P2, +LGPD→P2, +NEG→P1 (média com GP). AUD continua fora (router/classificador, sem score próprio).
- Comentários "MVP 33 vai mapear/expandir" removidos do `ocg_updater_service.py`.

### Testes

- 10 testes novos (mapping puro + fallback agregação por pillar).
- 24 testes não-regressão verdes (18 MVP 32 + 6 hot-fix DT-081).

### Dívidas registradas

- **DT-084 (Minor)** — 5 testes legado falhando + 4 com `ImportError: SessionLocal`, todos pré-existentes em master (independentes do MVP 33). Endereçamento em MVP cleanup futuro.

### Não impacta

- Schema (apenas dict Python).
- Migrations (nenhuma).
- E2E real (caminho de fallback validado no hot-fix DT-081 do MVP 32; MVP 33 herda).

---

## [MVP 32 — DT-081 OCG Updater funcional com payload n8n] - 2026-05-02

### Entrega principal

Fecha DT-081 descoberta no smoke E2E do MVP 31. OCG agora **acumula em produção** após pipeline n8n — `ocg.status='active'` (não mais `ocg_pending`), `ocg.version` incrementa, `ocg_delta_log` ganha row por doc ingerido.

### Mudanças técnicas

- `OCGUpdaterService._load_persona_scores` reescrito para ler de `ocg_individual` (cumulativo MVP 31), removendo dependência de `DocumentRouteMap` legacy quebrado (`AttributeError`)
- Normalização `persona_tag.lower()` antes do lookup em `PERSONA_TO_PILLAR` (case mismatch entre uppercase n8n e lowercase legacy)
- Novo módulo `arguider_compactor.py` — função `compact_arguider_for_prompt(arguider_analysis, max_findings=20)` reduz payload n8n de ~217KB para ~7.8KB (96.4%)
- Critério de prioridade: `criticidade='critica'` e CONF `score<60` SEMPRE incluídos (não truncados)
- `_build_user_prompt` chama compactor antes de serializar
- Logs distintos: `no_ocg_individual_rows` (n8n não rodou) e `conf_blocking_score` (CONF<60)

### Testes

- 18 testes unit + 1 E2E opt-in (`MVP32_REAL_LLM=1`)
- 53/53 com não-regressão MVP 31

### Dívidas registradas (fora de escopo)

- `PERSONA_TO_PILLAR` ainda tem só 7 entradas legacy — 5 personas novas (SEG/CONF/LGPD/NEG/AUD) sem mapeamento. Expansão para MVP 33.

### Plano de rollback

`git revert` dos commits MVP 32 (`506e1c0`, `80851d3`, este). Sem mudança de schema — rollback é só código. OCG volta para `ocg_pending` em ingestões n8n até MVP 32 ser reaplicado.

---

## [MVP 31 — OCG Cumulativo + CodeGen Gate] - 2026-05-02

### Entrega principal

**Caminho n8n agora respeita as invariantes canônicas do OCG**: o handler `/ingestion-complete` não faz mais `UPDATE ocg SET ocg_data=...` cru. Agora delega ao `OCGUpdaterService.update_ocg_from_arguider` (mesmo fluxo do Celery legacy) que tem `_filter_negative_score_deltas` (OCG só cresce, nunca contrai) e versionamento via `ocg_delta_log` com `hash_chain` (anti-tamper).

Histórico imutável passa a ser persistido por documento ingerido:
- `ocg_individual` (1 row por persona/doc, unique `(document_id, persona_id)`)
- `ocg_global` (1 row consolidada por doc)
- `ocg_delta_log` (versionamento + trigger_source para auditoria)

**CodeGen ganha gate de maturidade do OCG em 3 níveis**: nenhum endpoint de geração de código roda mais com OCG bloqueado/imaturo. Cobertura nos 6 entry points HTTP + 1 endpoint async (`start_scaffold_run`):
- `hard_block` (HTTP 409): `ocg.is_blocking=true` (CONF marcou bloqueante)
- `insufficient` (HTTP 409): `overall_score < 60` (mínimo absoluto)
- `immature` (HTTP 409): `overall_score < 95` (limiar de maturidade — orientação para amadurecer ingerindo mais docs)

**Política de "lixo descartado"**: PersonaOutputs falhos (G4 reprovou) ficam em `ocg_individual` com `status='failed'` para auditoria, mas **NÃO** entram no merge cumulativo. Quando ≥50% das personas falham, updater não é chamado (status do doc fica `partial`).

### Mudanças técnicas

**Backend**
- `backend/app/routers/webhooks.py` — handler `ingestion_complete` reescrito (4 commits cumulativos)
- `backend/app/services/ocg_updater_service.py` — constantes `TRIGGER_N8N` e `TRIGGER_CELERY` adicionadas
- `backend/app/services/ocg_gate.py` — novo helper `check_ocg_maturity_gate(project_id, db)` com 3 níveis
- `backend/app/services/module_codegen_service.py` + `backend/app/routers/code_generation.py` — gate adicionado em 7 entry points (antes do hardcode Anthropic — DT-079)
- `backend/app/models/base.py` — 4 modelos novos: `OCGIndividual`, `OCGGlobal`, `OCGIndividualRefined` (stub — DT-080), `PersonaFollowUpQuestion` (stub — DT-080)

**Banco**
- `backend/migrations/066_mvp31_consolidate_ocg_tables.sql` — alteração de `ocg_individual.persona_id` (uuid FK → VARCHAR(20)), drop de 13 índices duplicados (3 em `ocg_individual` + 10 em `ocg`), `NOT NULL` + `CHECK > 0` em `ocg.version`, `ON DELETE SET NULL` em `persona_follow_up_questions.answered_by`, novo índice composto `idx_ocg_project_version`
- `backend/migrations/067_mvp31_fix_persona_follow_up_questions.sql` — alteração de `persona_follow_up_questions.persona_id` (uuid FK → VARCHAR(20))

**n8n**
- 12 workflows (11 specialists + GP orchestrator) — `Parse PersonaOutput` agora produz `PersonaOutput-v2` válido (`schema_version`, `score`, `findings`, `recommendations`, `ocg_contributions`). Antes, todos os PersonaOutputs eram silenciosamente reprovados pelo Consolidador G4.

**Testes**
- 35 testes novos cobrindo as 5 fases (`test_mvp31_models_and_migration.py`, `test_mvp31_phase2_ocg_cumulative.py`, `test_mvp31_phase3_lixo_descartado.py`, `test_mvp31_phase4_codegen_gate.py`, `test_mvp31_phase5_e2e_cumulative.py`)

**Documentação canônica**
- `GCA_CANONICAL_CONTRACT.md §5.1` — cláusula formal do caminho n8n delegando ao `OCGUpdaterService`
- `GCA_CANONICAL_CONTRACT.md §7.31` — escopo formalizado (em/fora de escopo)
- `GCA_MVP_PROGRESS.md §1` — MVP 31 como ativo
- `GCA_MVP_PROGRESS.md §3` — DT-079, DT-080, DT-081, DT-082, DT-083 (todas registradas como abertas, fora do escopo)
- `docs/n8n-pipeline/PIPELINE_OPERACIONAL.md §6` — dívidas do MVP 31 marcadas como resolvidas
- `docs/MVP_31_OCG_CUMULATIVO_PLAN.md` — plano completo com 5 fases, riscos, gates Gatekeeper

### Plano de rollback (caso necessário em <15min)

Tabelas `ocg_individual` e `ocg_global` em produção têm 0 rows pré-MVP 31 — rollback de tipo de coluna é trivial.

```sql
-- Rollback migration 067 (executar antes do 066)
BEGIN;
ALTER TABLE persona_follow_up_questions
    ALTER COLUMN persona_id TYPE uuid USING persona_id::uuid,
    ADD CONSTRAINT persona_follow_up_questions_persona_id_fkey
        FOREIGN KEY (persona_id) REFERENCES users(id) ON DELETE CASCADE;
DROP INDEX IF EXISTS idx_persona_follow_up_questions_persona;
COMMIT;

-- Rollback migration 066
BEGIN;
ALTER TABLE ocg_individual
    ALTER COLUMN persona_id TYPE uuid USING persona_id::uuid,
    ADD CONSTRAINT ocg_individual_persona_id_fkey
        FOREIGN KEY (persona_id) REFERENCES users(id) ON DELETE CASCADE;
DROP INDEX IF EXISTS idx_ocg_project_version;
ALTER TABLE ocg DROP CONSTRAINT chk_ocg_version_positive;
-- Indexes ix_* duplicados e ON DELETE de answered_by ficam como estão (não regridem)
COMMIT;
```

Reverter código: `git revert` dos commits da branch `feat/mvp31-ocg-cumulativo` (12 commits) ou hard reset do master para o commit `b73fd38` (último antes do PR #2).

### Dívidas remanescentes (registradas, fora do escopo deste MVP)

- **DT-079** (Major): Hardcode `AsyncAnthropic` em `module_codegen_service.py:164,316` e `code_generation.py:592,1693,1838,2353,2367,2498` viola §3.1 (porta única é `AIKeyResolver`). MVP 31 inseriu o gate **antes** dos hardcodes — não agravou.
- **DT-080** (Major): `OCGIndividualRefined` e `PersonaFollowUpQuestion` são stubs ORM mínimos (sem 13+ colunas reais). MVP 31 endereçou parcialmente para que `alembic autogenerate` futuro não tente dropar.
- **DT-081** (Major): `OCGUpdaterService._load_persona_scores` quebrado (`AttributeError: type object 'DocumentRouteMap' has no attribute 'project_id'`) + prompt do `_build_user_prompt` não otimizado para payload n8n de ~23KB. Resultado: smoke E2E em dogfood termina com `ocg.status='ocg_pending'` (canônico — não corrompe OCG, mas updater não produz delta).
- **DT-082** (Minor): Worker Celery `execute_run` em `scaffold_run_service.py` não tem gate de maturidade próprio. Defesa em profundidade pendente — endpoint atual é o único caller, sem bypass real.
- **DT-083** (Minor): Métricas Prometheus (`gca_ocg_delta_applied_total`, `gca_ocg_negative_delta_blocked_total`, `gca_codegen_blocked_total`) parked porque projeto não tem `prometheus_client` instrumentado.

### Migração de produção

⚠️ Migrations 066 e 067 já foram aplicadas em ambos os bancos (`gca_test` e `gca`/dogfood) durante o desenvolvimento — sem perda de dados (tabelas vazias).

### Suíte de testes

35/35 verdes em 11.10s. Smoke n8n contracts: 2 passed, 7 skipped (esperado — depende de n8n ativo).

---

## [Unreleased — MVP 2 em andamento] - 2026-04-17

### Dogfood dia inteiro — 20+ DTs quitadas

**Saneamento de compartimentalização (Critical)**
- DT-026: repositório Git compartilhado entre 2 projetos era aceito pelo
  backend. Agora `connect_repository` rejeita com 400 normalizando URL
  (.git/trailing-slash/case/git@ vs https://). `git/status` retorna
  `shared_with: [...]` pro frontend mostrar banner de conflito quando
  pré-existente.

**Saneamento de findings falsos (Critical)**
- DT-024: `Q17 multi-select` causava `TypeError: unhashable type: 'list'`
  em `_check_arch_execution_compat`. Questionários ficavam zumbis em
  `pending_analysis`. Fix renomeia `exec_model` → `exec_models` (list)
  em 6 pontos de uso.
- DT-025: 13 strings hardcoded no `TechnologyVerificationService`
  descasavam com o schema real do PDF ("Criptografia em trânsito" quando
  schema tem "HTTPS", "Plano de testes" vs "Plano testes", etc).
  Resultado: bloqueadores falsos em respostas corretas. Todos alinhados
  e sugestões ("Marque 'X' em QY") citando opção exata.

**UX do questionário (DT-018/020/021/022)**
- DT-018: PDF flattened (sem AcroForm) agora rejeita com 422 orientando
  o GP a usar Adobe Reader/Foxit/Okular em vez do caminho silencioso.
- DT-022: aba Ingestão humaniza erro do Arguidor — `arguider_error_message`
  exposto na listagem com mapa 401/403/429/timeout.
- Editor inline: GP pode corrigir as perguntas bloqueadoras diretamente
  na tela (sem baixar PDF), via novo endpoint `POST /questionnaire/correct`
  que mergeia corrections com responses e re-roda análise.
- Schema Q→label espelhado no frontend em `data/questionSchema.ts`.

**Multi-provider LLM por projeto (novo)**
- Projeto suporta múltiplos provedores simultâneos, um marcado como
  padrão, com Testar/Padrão/Remover por card. Retrocompat on-read do
  formato antigo (`provider`/`model_preference`).
- Endpoints: `POST /settings/llm`, `DELETE .../providers/{p}`,
  `POST .../providers/{p}/default`, `POST .../validate?provider=X`
  (persiste `last_validated_at` e `last_validation_ok`).
- Validate ganhou suporte real a DeepSeek, Grok, Gemini (antes retornava
  `valid: True` falso-positivo). Ollama fica como DT-023 (requer schema
  de `base_url`).
- `agent_service` usa `DEFAULT_AI_MODEL` como fallback quando
  `{PROVIDER}_MODEL` específico não está setado (consistente com
  `ocg_updater_service`).

**Infra de UX (DT-017/hero/badges/DT-026 banner)**
- `/novo-projeto` redireciona para `/solicitar-projeto` (um caminho só).
- Hero âmbar em Configurações quando setup incompleto, desaparece quando
  3/3 passos concluídos + approved. Badges ✓/⚠/○ nas tabs distinguem
  "pendente" de "submetido-com-bloqueadores".
- OCG Scores por Pilar mostra nome + descrição + peso (P1 Caso de
  Negócio, P7 Segurança, etc) em vez de só "P1..P7".

**Operacional / saneamento de dados**
- DT-019: 18 admins fake (`@test.com`/`@example.com`) desativados no DB;
  16 projetos factory + 2 questionários 80% removidos. Guard RFC 2606
  + `test.com` no `EmailService` previne novos vazamentos.
- SMTP por projeto fica como DT-016 aberta, escopo MVP 5 (hardening).

**Regra de deploy (CLAUDE.md §12)**
- Frontend é `vite preview` estático — toda mudança em `frontend/**`
  exige `npm run build` + `docker restart gca-frontend` antes de pedir
  hard refresh ao user. Regra agora documentada.

### OCGs gerados (dogfood validado)
- Smoke MVP2 17abr: `9604b9f6`, score 60.9, status NEEDS_REVIEW.
- Automação Jurídica Assistida: `89b0ec95`, NEEDS_REVIEW.
- FinanceHub Pro (projeto mock): **removido** do DB por solicitação do
  owner — não tinha entregáveis reais, apenas deliverables de teste do
  dia 2026-04-09.

### Testes
- Multi-provider validate testado contra 5 provedores do admin (4
  válidos, DeepSeek do admin inválido — projeto usa chave separada).
- Reprocessamento dos 3 questionários zumbis confirmou que DT-024 +
  DT-025 eram causa 100% dos bloqueadores falsos.

---

## [MVP 1 saneamento] - 2026-04-17

### Governança documental
- Contrato canônico soberano (`GCA_CANONICAL_CONTRACT.md` v1.1) e tracker
  (`GCA_MVP_PROGRESS.md` v1.1) em vigor. Precedência documental formalizada.
- `CLAUDE.md` reescrito em 16 seções (fonte soberana, RBAC canônico, política
  híbrida de IA, debt gates, regras de contenção).
- README, ARQUITETURA e docs históricas marcadas explicitamente como
  não-contrato quando contêm visão futura.

### RBAC (DT-001 + DT-002 quitadas)
- **Breaking:** `ROLE_ACTIONS` reduzido aos 5 papéis canônicos do contrato §4:
  Admin, GP, Dev, Tester, QA (+ `admin_viewer` virtual). Removidos
  `tech_lead`, `dev_senior`, `dev_pleno`, `compliance`, `stakeholder`,
  `viewer` — DB não continha nenhum, sem migration de dados.
- GP perdeu `code:write/code:review/pipeline:execute/git:commit` (contrato
  §4.1 — GP não escreve código).
- QA ganhou `security:review` e `compliance:validate`.
- Frontend alinhado: `Sidebar`, `AdminUsersPage`, `AdminProjectViewPage`,
  `ProjectDashPage`, `ProjectListPage`, `ProjectTeamPage`,
  `RoleAssumptionPrompt`, `StatusBadge` operam apenas com os 5 canônicos.

### Governança de IA (DT-005 + DT-009 quitadas)
- `ai_key_resolver.py` com docstring de política de criticidade
  (baixa/média/alta conforme contrato §6.2).
- `agent_service.py` (camada GCA/pipeline OCG) deixa de fazer fallback
  silencioso para `ANTHROPIC_API_KEY` quando o admin escolheu outro provider
  sem a chave correspondente — `_ensure_key()` levanta `RuntimeError` claro.
- Implementação do roteamento híbrido efetivo (classificar tarefa → escolher
  provedor) permanece como escopo do MVP 3.

### Testes
- 81/81 backend integration + 44/44 unit passando ao fim desta sessão.

---

## [0.1.0-beta] - 2026-04-05

### Added

#### Backend (FastAPI)
- 13 admin endpoints (users, projects, tickets, alerts, integrations)
- JWT authentication with role-based access control
- Async PostgreSQL ORM with SQLAlchemy 2.0
- Redis caching layer
- SMTP email notifications
- Webhook testing (Teams, Slack, Discord)
- Suspicious access tracking with brute-force protection
- Support tickets with response system
- System alerts with severity levels
- Dashboard metrics endpoint
- OpenAPI/Swagger documentation

#### Frontend (React)
- 9 admin pages (Dashboard, Users, Projects, Security, Settings, Tickets, Integrations, Alerts)
- 12 reusable components (Button, Modal, Table, Badge, Card, Toast, etc)
- 10 custom hooks (useAuth, useUsers, useProjects, useTickets, etc)
- Zustand state management
- React Query data fetching & caching
- React Hook Form + Zod validation
- Error Boundary for error handling
- Protected routes with JWT validation
- Dark theme (Tailwind CSS)
- Mobile-responsive design
- Production build (297KB gzipped)

#### Infrastructure
- Docker Compose setup (4 services)
- Cloudflare Tunnel integration
- GitHub integration
- Database migrations
- Automated backups
- Health checks
- Comprehensive documentation (README, API, Architecture, Deployment, Setup)
- Production deployment configuration

#### Testing
- 12/28 backend service layer tests passing
- Test factories for database seeding
- Async test fixtures

### Changed
- Recovered 139GB NVMe space via data migration to SSD
- Optimized frontend bundle size (297KB gzipped)
- Async database operations for better performance

### Security
- bcrypt password hashing
- JWT token authentication
- CORS protection
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (React sanitization)
- RBAC (admin/user roles)

### Known Limitations
- Endpoint HTTP tests need pytest-asyncio configuration (foundation set)
- No refresh token mechanism (session dies on token expiry)
- No real-time updates (WebSocket support needed)
- No bulk operations

### Future (v0.2.0+)
- Refresh token mechanism
- WebSocket real-time updates
- Bulk user operations
- Advanced filtering (date range, text search)
- Full HTTP endpoint test coverage
- Performance monitoring dashboard

---

## [0.0.1] - 2026-03-20

Initial project setup with basic models and CLI.
