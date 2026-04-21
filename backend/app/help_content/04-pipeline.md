# Pipeline canônico do GCA

O pipeline é a sequência de etapas pela qual um projeto passa do questionário inicial até a entrega (release bundle + documentação viva). É **orientado a eventos**: cada etapa lê o OCG, opera, atualiza o OCG, emite evento em `audit_log_global`, dispara a próxima etapa (ou aguarda ação humana).

```
[Externo]                        [Admin]              [GP]                  [GP/Dev/Tester/QA]
┌───────────────┐  aprovação   ┌──────────┐  OCG  ┌─────────────┐  ingestão/dev   ┌──────────────┐
│ Questionário  │─────────────▶│ Projeto  │──────▶│ OCG/         │────────────────▶│ CodeGen/QA/  │
│ externo (49Q) │              │ criado   │       │ Gatekeeper/  │                 │ Docs/Release │
└───────────────┘              └──────────┘       │ Arguidor     │                 └──────────────┘
                                                   └─────────────┘
```

## 1. Questionário externo

- Link público com expiração de 5 dias (RF-001 / MVP 1).
- Wizard de 2 passos (pós-refactor sessão 22) + 49 perguntas técnicas em 7 blocos (A.1-A.7: Identidade, Escopo, Frontend, Backend, Dados, IA/Segurança, Testes).
- Cada pergunta tem tooltip + opção "N/A" quando aplicável.
- PDF editável alternativo para preenchimento offline + upload.
- Validação server-side antes de submeter.
- Email ao Admin quando submetido.

## 2. Aprovação pelo Admin

- `/admin/projects` → lista pendentes.
- Admin revisa → **Aprovar** ou **Rejeitar com motivo** (obrigatório).
- Aprovar: backend em transação provisiona `organization` + `project` + convida o GP (email com link de aceite). Emite `PROJECT_APPROVED`.
- Rejeitar: marca a requisição como rejeitada com motivo. Emite `PROJECT_REJECTED`.

## 3. Geração do OCG (8 agentes)

Disparada automaticamente após aprovação (via Celery task `generate_ocg_task` — MVP 14 Fase 14.1). O pipeline de 8 agentes:

```
                    Agente 0
                    Analyzer (classifica 49 respostas por pilar)
                    ↓
    ┌───────┬───────┬─────────┬────────┬────────┬────────┬────────┐
    ↓       ↓       ↓         ↓        ↓        ↓        ↓        ↓
   P1      P2      P3        P4       P5       P6       P7
   Caso    Compl.  Escopo    NFRs     Arq.     Dados    Seg.
   Neg.    Reg.                                                    (paralelo)
    ↓       ↓       ↓         ↓        ↓        ↓        ↓
    └───────┴───────┴─────────┴────────┴────────┴────────┴────────┘
                    ↓
                    Agente 8
                    Consolidator (OCG final + COMPOSITE_SCORE + status)
```

Cada agente de pilar devolve: score 0-100, adherence_level, is_blocking, findings (severity + descrição + recomendação). O Consolidator aglutina em `OCGResponse` com 12 seções (ver [cap. 5 — OCG](?section=05-ocg)).

Fallback determinístico: se o LLM não retornar um campo esperado (ex: `STACK_RECOMMENDATION`), o Consolidator usa `_stack_from_metadata(questionnaire_metadata)` para preencher com heurísticas. Nenhuma seção do OCG fica vazia por falha de LLM.

## 4. Gatekeeper

Avalia o OCG resultante contra regras canônicas do contrato §5:

- **Thresholds canônicos** (configuráveis pelo Admin em `/admin`):
  - `P7 < 70` → **BLOCKED** (segurança insuficiente).
  - `P2 < 70` → **BLOCKED** (compliance insuficiente).
  - `composite ≥ 90` → **READY**.
  - `composite ≥ 75` → **NEEDS_REVIEW**.
  - `composite < 75` → **AT_RISK**.
- **Items rastreados**: gaps, show_stoppers, poor_definitions, improvement_suggestions, module_candidates.
- GP acessa `/projects/:id/gatekeeper` para ver summary + bloqueadores ativos.

Quando OCG muda (via ingestão, Arguidor ou consolidate manual), o Gatekeeper reavalia automaticamente.

## 5. Ingestão de documentos complementares

GP pode ingerir documentos adicionais (PDF, DOCX, XLSX, PNG, JPG, MD; máx 50 MB):

- Drop zone em `/projects/:id/ingestion`.
- Pipeline assíncrono via Celery (MVP 13/14): `queued → extracting_text → analyzing → updating_ocg → regenerating_backlog → completed`.
- Extração rica por tipo (MVP 8): DOCX com tabelas estruturadas, PDF com AcroForm + texto pesquisável + OCR via LLM Vision, normalização de seções implícitas.
- **Quarentena PII obrigatória**: CPF/CNPJ/cartão (validados por mod-11/Luhn) + telefone BR (validado após DT-028, antes era regex promíscuo). Documento com PII fica retido até GP liberar.

Cada ingestão impacta o OCG:

| Qualidade | Efeito no OCG |
|---|---|
| Documento válido + complementar | **EXPAND** (enriquece seção, sobe confidence) |
| Documento parcial | **UPDATE** (atualiza com lacunas marcadas) |
| Documento conflitante | **CONTRACT** (reduz confidence, marca conflito) |
| Documento com PII | **BLOCK** (quarentena; OCG não tocado) |
| Documento que invalida stack | **CONTRACT** (P5/P6 caem + CRITICAL_FINDING) |

## 6. Arguidor

Após ingestão (ou quando Gatekeeper detecta gaps), o Arguidor emite perguntas dirigidas ao GP:

- Cada gap vira um item em `gatekeeper_items` com `status='pending'`.
- GP em `/projects/:id/arguider` responde (texto + evidência opcional) ou ignora com motivo.
- Resposta registrada como `ARGUIDER_RESPONSE_REGISTERED` no audit.
- Resposta alimenta o OCG de volta (expand/update).

## 7. Backlog e Roadmap derivados

Qualquer mudança relevante no OCG dispara:

- `BACKLOG_REGENERATED` — backlog recalculado conforme `STACK_RECOMMENDATION`, `DELIVERABLES`, `DATA_MODEL`.
- Módulos canônicos em 8 categorias (MVP 9): Foundation, Auth, Data, Business, Infra, UI, Integration, Compliance.
- Detalhamento on-demand via Ollama (local); curadoria Premium quando necessário.
- Plano de deploy com export Markdown (MVP 9 Fase 9.4).

## 8. CodeGen

- **9 linguagens scaffoldadas** canonicamente: Java Spring, Java Quarkus, Kotlin Spring, Go, C#, PHP, Node.js (NestJS + Express), **C++ (CMake + GoogleTest — MVP 16)**.
- Python fica em LLM-only (sem scaffolder determinístico).
- Scaffold a partir de `OCG.STACK_RECOMMENDATION.backend.language` + `framework`.
- DDL automaticamente injetado a partir de `OCG.DATA_MODEL` (5 dialetos SQL + Mongo; 7 frameworks de migration — MVP 10 DT-076).
- Preview antes de commit; apply cria commit no Git do projeto com mensagem canônica.
- Docstrings obrigatórias em todo código gerado.
- Validação pós-geração: pyflakes (Python), esprima (JS), ast.parse (Python), cmake+gcc (C++ via CI step `cpp-scaffold-compile`).

Detalhes em [cap. 8 — Codegen](?section=08-codegen).

## 9. QA Readiness + Tester Review

- `/projects/:id/qa` consolida cobertura de testes (unit, integration, e2e, regression, load, security).
- Specs geradas via Ollama local para unit/integration/e2e; security/compliance via Premium (MVP 10 Fase 10.3).
- Tester aprova/rejeita/edita spec; QA revisa execução (gate `qa:approve`).
- Stale detection: banner aparece quando OCG mudou depois da última geração (MVP 10 Fase 10.4).

## 10. Documentação Viva + Release Bundle

- Doc Viva regenera em cada commit de pipeline (incremento automático).
- Consolidação geral via Premium; geração por módulo via Ollama.
- Seção "Modelo de dados" com DDL inline (MVP 10 Fase 10.5 / DT-076 Fase 5).
- Viewer read-only de documentos ingeridos.
- Release Bundle (MVP 4 + evoluções): markdown + OCG version + commits incluídos + artefatos (schema.sql, seed.sql, migrations) + evidência de testes.

## Auto-trigger e propagação de eventos

Cada passo relevante emite evento em `audit_log_global`:

- `QUESTIONNAIRE_SUBMITTED` / `QUESTIONNAIRE_APPROVED` / `QUESTIONNAIRE_REJECTED`
- `PROJECT_APPROVED` / `PROJECT_REJECTED` / `PROJECT_STATUS_CHANGED`
- `DOCUMENT_INGESTED` / `DOCUMENT_QUARANTINED`
- `GATEKEEPER_EVALUATED`
- `ARGUIDER_QUESTION_OPENED` / `ARGUIDER_RESPONSE_REGISTERED`
- `OCG_UPDATED` / `OCG_ROLLED_BACK` / `OCG_CONSOLIDATED`
- `BACKLOG_REGENERATED`
- `CODEGEN_REQUESTED` / `CODEGEN_COMPLETED` / `CODEGEN_SCAFFOLD_GENERATED` / `CODEGEN_SCAFFOLD_APPLIED` / `CODEGEN_FILE_REGENERATED`
- `CODE_VALIDATION_COMPLETED`
- `QA_EXECUTION_REQUESTED` / `QA_EXECUTION_COMPLETED`
- `LIVEDOCS_UPDATED`

Cada evento tem `previous_hash` + `current_hash` (SHA-256) encadeado → trilha verificável.

## Ver também

- [OCG — Objeto de Contexto Global](?section=05-ocg)
- [Codegen e linguagens suportadas](?section=08-codegen)
- [Observabilidade](?section=09-observabilidade)
