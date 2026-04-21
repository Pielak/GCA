# OCG — Objeto de Contexto Global

O **OCG** é a fonte única de verdade de um projeto no GCA. Não é documento estático: é **objeto de estado evolutivo orientado a eventos**. Cada ingestão, resposta do Arguidor, reconsolidation ou rollback altera o OCG e gera um delta auditável.

Princípio fundamental do contrato §5:

> Nenhum módulo do pipeline (Gatekeeper, Arguidor, Backlog, Roadmap, CodeGen, QA, LiveDocs) pode operar ignorando o OCG atual. Se o OCG está incompleto, o módulo **não assume defaults invisíveis** — ou pede ao GP, ou bloqueia.

## 12 seções canônicas

| Seção | Propósito |
|---|---|
| `PROJECT_PROFILE` | Metadados do projeto (nome, slug, tipo, criticidade, classificação), derivados do questionário. |
| `PILLAR_SCORES` | Os 7 pilares (P1–P7) com score 0-100 + adherence_level + is_blocking + findings_count. |
| `COMPOSITE_SCORE` | Score composto `{ overall, is_blocking, status }` — READY / NEEDS_REVIEW / AT_RISK / BLOCKED. |
| `STACK_RECOMMENDATION` | Stack recomendada por camada: backend (language + framework + type), frontend (stack + language), database (engine + profile), cache, messaging, deployment. **Mais consumida** do OCG (21 consumidores no código). |
| `CRITICAL_FINDINGS` | Achados críticos (severity='critical') extraídos das análises dos pilares. |
| `TESTING_REQUIREMENTS` | Tipos de teste + cobertura alvo + ferramentas (fonte dos specs e do Tester Review). |
| `COMPLIANCE_CHECKLIST` | LGPD, GDPR, setoriais. Alimenta geração de módulos compliance. |
| `DELIVERABLES` | Entregáveis esperados por categoria (doc, code, test, process, config, other). Alimenta Definition of Done. |
| `ARCHITECTURE_OVERVIEW` | Estilo + componentes + fluxo de dados + execution_model (Cloud, On-premises, Híbrido). |
| `RISK_ANALYSIS` | Riscos alto/médio/baixo com mitigações. |
| `APPROVAL_STATUS` | Status consolidado binário: APPROVED / NEEDS_REVIEW / AT_RISK / BLOCKED. |
| `DATA_MODEL` | Modelo de dados derivado (DT-076): engine, tabelas, FKs, seed data, warnings. Alimenta o DDL generator. |

Além disso, o OCG carrega `context_health` — `{ depth (0-1), confidence (0-1), quality }` — que flui junto com operações de expand/contract.

## Versionamento

Cada OCG é single-row em `ocg` (PK único por `questionnaire_id`), mas **cada mudança cria linha em `ocg_delta_log`** com:

- `project_id`
- `ocg_version_from` / `ocg_version_to`
- `fields_changed` (JSON descrevendo as mudanças)
- `change_summary`
- `changed_by` (user UUID)
- `trigger_source` (`document_ingestion`, `arguider_response`, `consolidation`, `rollback`, `manual_edit`, `pillar_agent`)
- `ocg_snapshot` (JSON completo da versão — fonte do rollback)
- `created_at`

A versão atual do OCG é incrementada in-place; o histórico vive no delta_log.

## Expand / Contract — regras canônicas §5

| Qualidade da entrada | Efeito no OCG |
|---|---|
| Documento válido + complementar | **EXPAND** — enriquece seção, sobe `context_health.confidence` |
| Documento parcial | **UPDATE** — atualiza com lacunas marcadas em `CRITICAL_FINDINGS` |
| Documento conflitante com estado atual | **CONTRACT** — reduz confidence, marca conflito explícito |
| Documento com PII | **BLOCK** — quarentena; OCG não é tocado enquanto o doc fica retido |
| Documento que invalida stack | **CONTRACT** — P5/P6 caem + `CRITICAL_FINDING` novo |
| Segurança mal definida (P7 < 70) | **BLOCK** — status BLOCKED; pipeline para |
| Compliance ausente (P2 < 70) | **BLOCK** — idem |

Por que a contração é necessária: sem ela, o sistema ficaria otimista demais — aceitaria documentos conflitantes, geraria código baseado em premissas erradas, testes errados, 80% do código precisaria ser refeito. Com contração, o sistema é **honesto**: se a base está ruim, ele para e exige correção.

## Operações canônicas

### Visualização

`/projects/:id/ocg` mostra todas as 12 seções renderizadas + versão atual + health. GP pode inspecionar snapshots antigos (`GET /ocg/snapshot/{version}` — retorna apenas o snapshot, não muta).

### Rollback (MVP 14 Fase 14.7)

Reverte o OCG para uma versão anterior. **Não destrói histórico**: cria uma nova versão com `trigger_source='rollback'` copiando o snapshot da versão alvo.

- Endpoint: `POST /projects/{id}/ocg/rollback/{version_to}`.
- Implementação: `OCGService.rollback_to_version(project_id, version_to, actor_id)`.
- Emite `OCG_ROLLED_BACK` com `{ version_from, version_to, restored_from }`.
- Requer snapshot disponível em `ocg_delta_log.ocg_snapshot`.

### Consolidate (MVP 14 Fase 14.8)

Recalcula `COMPOSITE_SCORE` + `status` + `is_blocking` a partir de `PILLAR_SCORES`, aplicando regras §5 (thresholds). Idempotente: se nada muda, retorna `changed=False`.

- Endpoint: `POST /projects/{id}/ocg/consolidate`.
- Implementação: `OCGService.consolidate_ocg(project_id, actor_id)`.
- Emite `OCG_CONSOLIDATED` com `{ version_from, version_to, composite_before/after, status_before/after }`.
- Útil após edições manuais de pilares ou importação de scores externos.

### Histórico

`GET /projects/:id/ocg/history` lista as versões com `trigger_source` + `changed_by` + `created_at` + `fields_changed` resumido. UI renderiza como timeline.

## Propagação automática

Quando o OCG muda relevantemente, os módulos consumidores são acionados:

- **Stack mudou** → `regenerate_backlog_task` regera backlog categoria "modules"; marca CodeGen desatualizado.
- **Compliance mudou** → `regenerate_backlog_task` regera "compliance"; reavalia quarentena.
- **Testes mudaram** → regera `test_specs` marca QA desatualizado.
- **Qualquer mudança** → `BACKLOG_REGENERATED` + incremento LiveDocs + evento `audit_log_global`.
- **Gatekeeper** reavalia scores automaticamente via `reevaluate_gatekeeper_task`.

Tudo é enfileirado em Celery (MVP 13) — não bloqueia a request que disparou a mudança.

## Regras duras sobre o OCG

- **Compartimentalização**: cada projeto tem seu OCG próprio; projetos não interferem entre si.
- **Separação Admin vs projeto**: chaves IA do pipeline OCG global (Admin) são distintas das chaves do projeto (GP) — §6.5.
- **Alta criticidade exige premium**: consolidação final, arbitragem de conflitos, decisões arquiteturais não podem rodar só com LLM local.
- **OCG nunca fica corrompido**: se o LLM falha no meio do pipeline, o documento fica em `pending`, o OCG não é tocado.
- **Nenhum módulo assume defaults invisíveis**: se falta dado, o módulo dispara Arguidor ou bloqueia.

## Billing por operação

Cada chamada LLM durante operações do OCG registra em `ai_usage_log`: provider, model, operation, tokens_input, tokens_output, cost_usd, project_id. GP vê o consumo do próprio projeto em `/projects/:id/metrics`; Admin vê agregado em `/admin/metrics`.

## Inventário de propagação (MVP 13 Fase 13.5)

Todos os 12 seções + operações emitem evento canônico no audit:

| Operação | Evento |
|---|---|
| OCG inicial gerado | `OCG_UPDATED` (com `trigger_source='initial_generation'`) |
| Ingestão impacta OCG | `OCG_UPDATED` (com `trigger_source='document_ingestion'`) |
| Resposta do Arguidor | `OCG_UPDATED` (com `trigger_source='arguider_response'`) |
| Rollback | `OCG_ROLLED_BACK` |
| Consolidate explícito | `OCG_CONSOLIDATED` |

## Ver também

- [Pipeline canônico](?section=04-pipeline) — onde o OCG nasce.
- [Codegen](?section=08-codegen) — principal consumidor do `STACK_RECOMMENDATION` + `DATA_MODEL`.
- [Solução de problemas](?section=10-troubleshooting) — troubleshooting de OCG travado.
