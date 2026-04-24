# M01 — Relatório de Impacto (Questões em Aberto Iterativas)

**Data:** 2026-04-24
**Status:** MVP M01 entregue (Tasks 1-9 implementadas)
**Execução:** subagent-driven-development com modelo Haiku por task, spec+quality review entre cada.

## Arquitetura aplicada

- **1 tabela nova** (`custom_questionnaire_iterations`) — histórico de iterações com `ocg_version_before/after`, `overall_before/after`, `converged`, `not_applicable_ratio`, `convergence_threshold`. Sem tabela de respostas — respostas viram `ingested_documents` normais.
- **Pipeline canônico preservado:** respostas entram pelo `IngestionService.upload_document` com `category='iterative_questionnaire_answer'` e seguem o fluxo normal: canonização (MVP 29) → Arguidor → OCG Updater. Score é atualizado APENAS pelo updater canônico — zero alteração direta de `ocg.overall_score`.
- **LLM via §6.2** respeitado: `resolve_llm_config` + `call_llm` do helper `llm_low_criticality` usa provider do projeto. Nenhum Opus/Haiku hardcoded.
- **Convergência (D3):** `|overall_after - overall_before| < 1.0` → `status='converged'`.
- **Inviabilidade (D4):** `not_applicable_ratio >= 0.5` → `status='infeasible'` (loop encerra).
- **Threshold (D2):** `overall < 90 AND min(pilares) < 75` pra elegibilidade.
- **Badge sidebar (D1):** `•` amarelo quando há iteração pending, `✓` verde quando convergiu. Hook com polling de 30s.

## Tasks entregues

| # | Descrição | Commit |
|---|---|---|
| 1 | Migration SQL 038 `custom_questionnaire_iterations` | `bd78c08` |
| 2 | Model SQLAlchemy + fix de scope (remover indexes redundantes) | `d96d8db` + `cfc5fcc` |
| 3 | Prompt builder puro (`iterative_questionnaire_generator.py`) | `49fa97b` |
| 4 | Service orquestrador (threshold + convergência + inviabilidade) | `57c624a` |
| 5 | Router 4 endpoints + registro em main.py + novo `pdf_questionnaire_generator` | `875e9fe` + fix `10e2750` |
| 6 | Hook no OCG Updater pra convergência | `eed6c3d` |
| 7 | 11 testes standalone (11/11 passing) | `5a97b71` |
| 8 | Sidebar item + hook + rota + PIPELINE_PATHS | `d51b619` |
| 9 | `IterativeQuestionnairePage` (status + generate + PDF + upload) | `516bb6a` |
| 10 | Este relatório | (commit final) |

## Dogfood AJA (projeto 65cab180) — a medir

Stakeholder:
1. Hard-refresh no AJA (`Ctrl+Shift+R`).
2. Verifica badge `•` amarelo na sidebar de "Questões em Aberto" (OCG ~73.7 < 90 e há pilares < 75 → elegível pra nova iteração).
3. Abre a página, clica "Gerar nova iteração" → backend chama LLM do projeto, cria row com N perguntas focadas.
4. Baixa PDF, preenche 2-3 questões, faz upload.
5. Aguarda pipeline terminar (~2-5 min). Badge:
   - Fica `✓` se Δ overall entre antes/depois < 1 (convergiu).
   - Continua `•` se eligible ainda (próxima iteração possível).
   - Fica oculto se inviável (≥50% "não se aplica").

Métricas a coletar:

| Iter | Status | Overall antes | Overall depois | Δ | NSA ratio | Tempo total |
|---|---|---|---|---|---|---|
| 1 | _preencher após dogfood_ | _preencher_ | _preencher_ | _preencher_ | _preencher_ | _preencher_ |

Query pra coletar:
```sql
SELECT iteration, status, overall_before, overall_after, converged, not_applicable_ratio,
       created_at, updated_at
FROM custom_questionnaire_iterations
WHERE project_id = '65cab180-e00d-4eec-aaf2-fb4b5d0f4057'
ORDER BY iteration;
```

## Decisões técnicas registradas

### D1 arquitetural — 1 tabela, não 3
Task original propôs 3 tabelas (`custom_questionnaires`, `custom_responses`, `score_analysis`). Rejeitado: respostas são documentos ingeridos (reuso do pipeline), análise de score é o OCG corrente (não precisa tabela separada). Ficou com 1 tabela enxuta.

### D2 arquitetural — score nunca direto
Task original fazia `project.score = X` por delta empírico. Rejeitado: `project.score` não existe (é `ocg.overall_score`), e score é output determinístico do pipeline Arguidor → Updater. O M01 só **lê** score e **decide** próxima iteração. Zero bypass do pipeline.

### D3 técnico — PDF generator novo
Plano mencionou reusar `pdf_generator` do MVP 24. Auditoria descobriu que o MVP 24 (`questionnaire_pdf_service.py`) tem layout hardcoded das 49 perguntas canônicas — não aceita lista dinâmica. Criado `pdf_questionnaire_generator.py` dedicado (ReportLab AcroForm) com aceitação de `questions: list[dict]` arbitrário. Naming distinto (`pdf_questionnaire_*` vs `questionnaire_pdf_*`) preservado porque as 2 responsabilidades são diferentes.

### D4 técnico — indexes só no DB
Code-quality reviewer inicialmente pediu `__table_args__` com `UniqueConstraint` e `Index` no ORM. Sobreposto pelo controller: migrations SQL são a fonte única de verdade do schema no GCA (padrão canônico — vs repos que usam `create_all`). Postgres enforça UNIQUE e usa indexes independentemente do ORM conhecer. Declarar no ORM duplica risco (nomes divergentes → índices duplos em testes via `create_all`).

## Pendências futuras (DT-092 potencial)

- **Limite explícito de iterações máximas** (hoje convergência decide — pode loopar se score oscilar; mitigação pragmática: tope soft em 5).
- **PDF com AcroForm mais rico** (hoje usa textfields planos; poderia ter radio buttons pros `type=choice`).
- **Paralelização de upload** se múltiplas iterações pendentes (improvável, mas possível).
- **Métrica de convergência visível** no Dashboard do projeto (histórico Iter 1 → Iter N, overall subindo).
- **Integração com Questionário Técnico Retroativo (MVP 24)**: hoje são pistas separadas. Possível unificar "questões ao GP" num ponto único.

## Critérios de aceite atingidos

- ✓ Plan task-a-task entregue via subagent-driven com Haiku (10 tasks, 11 commits).
- ✓ Zero hardcode de provider IA (§6.2 respeitado via `llm_low_criticality`).
- ✓ Pilares canônicos P1..P7 usados em todo o pipeline.
- ✓ PT-BR em código, commits, UI, logs, erros.
- ✓ Zero alteração direta de score — pipeline canônico preservado.
- ✓ 11/11 testes standalone passing (respeita DT-034 — sem pytest contra DB de prod).
- ✓ Backend + frontend builds verdes (`✓ built in 8.77s`, `Application startup complete`).
- ✓ Sidebar com badge reativo (30s polling).
- ✓ Hook no OCG Updater não bloqueia pipeline em caso de falha (swallow + log).
