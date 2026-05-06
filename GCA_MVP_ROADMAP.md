# GCA_MVP_ROADMAP.md — MVPs e DTs

**Versão:** 1.0  
**Data:** 2026-05-05  
**Status atual:** MVPs 1-35 fechados. Pós-saneamento, próximas features pendentes de autorização.

---

## §1. MVPs Fechados (histórico curto)

| MVP | Data | Tema |
|---|---|---|
| 1 | — | Base operacional + saneamento do núcleo |
| 2 | — | Contexto vivo + governança de conteúdo |
| 3 | — | Geração assistida controlada |
| 4 | — | Qualidade, documentação, entrega |
| 5 | — | Hardening operacional |
| 6 | — | Validação assistida em campo (tickets) |
| 7 | — | Entrega versionada preservando dados |
| 8 | — | Ingestão inteligente de documentos |
| 9 | — | Roadmap multicategoria + pré-ingestão guiada |
| 10 | — | Planos de Teste e Documentação Viva reativos ao OCG |
| 11 | — | Simetria de soberania RBAC |
| 12 | — | Saneamento pós-MVP 11 |
| 13 | — | Robustez estrutural (fila persistente + auditoria) |
| 14 | — | OCG maturity + type safety + observabilidade Celery |
| 15 | — | Limpeza do backlog parked |
| 16 | — | C++ fundacional + dogfood validation |
| 17 | — | Saneamento operacional Celery (DT-077, DT-078) |
| 18 | — | Sistema de Ajuda integrado |
| 19 | — | ERS Vivo (IEEE 830) |
| 20 | — | Integrações externas (Jira/Trello/Sonar/Snyk/Slack) |
| 21 | — | Ajuda refresh (sincronizar conteúdo) |
| 22 | — | Teams Notifier uni-direcional |
| 23 | 2026-04-22 | RNF_CONTRACTS + CodeGen contract-aware (112/112) |
| 24 | 2026-04-22 | Questionário Técnico retroativo (96/96) |
| 25 | 2026-04-22 | Design via Ingestão (129/129) |
| 26 | — | AI Governance Moat (rastreabilidade LLM + injection) |
| 27 | — | (planejado) SSO corporativo |
| 28 | — | (planejado) ChatOps bi-direcional |
| 29 | 2026-04-28 | Celery Hardening + Dramatiq (acks_late, idempotência) |
| 30 | 2026-05-02 | Pipeline n8n 12 personas (135s real) |
| 31 | 2026-05-02 | OCG Cumulativo + CodeGen Gate (35/35) |
| 32 | 2026-05-02 | OCG Updater (payload n8n, 3 bugs) |
| 33 | 2026-05-02 | Expansão 12 personas LLM (10/10) |
| 34 | 2026-05-03 | Reversão documento + recompute OCG (15/15) |
| 35 | 2026-05-03 | Validação canônica Questionário (90/90+110/110) |

**Total: 35 MVPs fechados.** Detalhes históricos em `docs/_deprecated/CONTRACT.md.OLD-*`.

---

## §2. MVPs em curso

**Nenhum.** Todos MVPs 23-35 fechados. Sistema em estado pós-saneamento.

---

## §3. DTs (Dívidas Técnicas) Abertas

### §3.1. Críticas

| DT | Severidade | Status | Descrição |
|---|---|---|---|
| **DT-084** | **CRÍTICA** | Pré-existente | 5 testes legado falhando + 4 com erro de import (independente de MVP 33) |

### §3.2. Major

| DT | Status | Descrição |
|---|---|---|
| **DT-086** | Aberta | Purge físico LGPD não coberto. `pii_fields`, `parecer` JSONB permanecem após soft-delete. Requer MVP futuro com scheduled purge |

### §3.3. Minor

| DT | Status | Descrição |
|---|---|---|
| **DT-087** | Aberta | `ingested_documents.uploaded_by` sem `ON DELETE` declarado. Cresce com soft-delete |

### §3.4. DTs Resolvidas Recentemente

| DT | Resolvida em | Tema |
|---|---|---|
| DT-076 | MVP 8 (várias fases) | Doc Viva architecture |
| DT-077 | MVP 17.2 | Documentar rotina docker compose |
| DT-078 | MVP 17.1 | Healthcheck hostname Celery |
| DT-079 | MVP 31 | Hardcode Anthropic em codegen — confirmado SEM hardcode |
| DT-080 | MVP 32 | ORM stubs |
| DT-081 | MVP 32 | OCG Updater funcional com payload n8n |

---

## §4. Próximos Candidatos (NÃO autorizados)

### §4.1. F4.2 — Chunker estrutural + sub-ingestões

**Status:** Backend-ready (migration `parent_document_id` deployed em MVP 31).  
**Pendência:** Frontend + UX para visualizar chunks.  
**Estimativa:** 3-4 dias.  
**Bloqueador:** Sem autorização explícita do GP.

### §4.2. F4.3 — Accumulator + OCG único + UX

**Status:** Definido, custo 3× estimado.  
**Estimativa:** 8-12 dias.  
**Bloqueador:** Pendente decisão arquitetural sobre escopo.

### §4.3. MVP 27 (potencial) — SSO Corporativo

**Status:** Descrito em CONTRATO antigo. Não é prioridade atual (DevOps não previsto).  
**Pré-requisito:** ChatOps bi-direcional aguarda esta entrega.

### §4.4. MVP 28 (potencial) — ChatOps bi-direcional

**Status:** Descrito em CONTRATO antigo. Pré-requisito: MVP 27.  
**Tema:** Aprovar/rejeitar módulos via botões no Slack/Teams.

---

## §5. Protocolo de adição de novos MVPs

### §5.1. Regras duras

1. Somente o **stakeholder-soberano** (dono do produto) autoriza criação de novo MVP.
2. Claude **não cria MVP por conta própria**, nem infere escopo a partir de pedido isolado.
3. Adição de MVP = commit atômico alterando:
   - `GCA_MVP_ROADMAP.md` (esta seção)
   - `GCA_MVP_PROGRESS.md` (cabeçalho com estado inicial)
4. Estado inicial: **"definido — não iniciado"**. Trabalha quando:
   - MVP soberano anterior fechado pelo gate §9 (CLAUDE.md)
   - Stakeholder autoriza início explicitamente
5. **Em escopo** e **fora de escopo** são obrigatórios no momento da criação.
6. Numeração monotônica crescente. Sem renumeração retroativa.
7. **Stop-rule >2d** por fase = pausa + report blocker (não silêncio).

### §5.2. Gate §9 — Critérios para fechar MVP

10 critérios obrigatórios (todos SIM):

1. ✅ Suite de testes passa (≥ baseline anterior)
2. ✅ Frontend tsc = 0 errors
3. ✅ DTs novas registradas em §3
4. ✅ Memória `feedback_*` atualizada quando aplicável
5. ✅ `GCA_MVP_PROGRESS.md` atualizado com estado real
6. ✅ Commit `feat:` ou `fix:` correto
7. ✅ Smoke live em dogfood (quando aplicável)
8. ✅ RBAC preservado (5 papéis canônicos)
9. ✅ Compartimentalização §2.2 preservada (project_id em queries)
10. ✅ Sem hardcode de provider IA introduzido

---

## §6. Releases (futuro)

Releases do produto amarram-se a uma lista de MVPs fechados + tickets (MVP 6) entregues. Versionamento semântico planejado para MVP 7+.

**Release 1.0 candidata:** após estabilização do dogfood + saneamento residual de DTs (DT-084, DT-086).

---

**Fim do GCA_MVP_ROADMAP.md**
