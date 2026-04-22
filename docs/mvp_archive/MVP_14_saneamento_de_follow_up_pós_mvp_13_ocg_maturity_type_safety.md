# Arquivo — Saneamento de follow-up pós-MVP 13 + OCG maturity + type safety + observabilidade Celery

MVP 14. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 14 — Saneamento de follow-up pós-MVP 13 + OCG maturity + type safety + observabilidade Celery

**Motivação:** pós-fechamento do MVP 13 (7/7 fases), permanecem dívidas residuais documentadas em §6 e §10 do progresso que o stakeholder-soberano autorizou absorver num único ciclo: (a) pontos de `asyncio.create_task` fora do escopo §7 MVP 13 Fase 13.3 (`questionnaire_service`, `gatekeeper_service`) — hoje cobertos por watchdog DT-073; (b) rebuild `--no-cache` + canário e2e real que ficaram pendentes operacionalmente; (c) baseline de tsc com erros pré-existentes em shadcn/ui e `TesterReviewPage`; (d) OCG maturity — `rollback_to_version` formal e `consolidate_ocg` explícito (§3.0 inventário N/A); (e) remoção dos 91 `any` restantes no frontend (follow-up 12.7); (f) Flower/Prometheus métricas Celery (fora de escopo 13.4 explícito); (g) refactor amplo de shadcn/ui.

**Não entra no MVP 14 (explícito):**
- **Identity Federation (SSO OIDC/SAML)**: sem cliente real para parametrizar ou testar. Fora até pedido concreto.
- **Data Federation**: exige emenda formal ao contrato §3 + 3 decisões de produto pendentes (ver `gca_federation_roadmap.md`). Fora até pedido explícito.
- **Federated Learning**: GCA consome LLM, não treina. Recusado.

#### Em escopo

**Tema A — Saneamento Celery residual (2 fases):**
- **Fase 14.1** Migrar 4 `asyncio.create_task` de `questionnaire_service.py` para Celery tasks seguindo o padrão 13.3 (`app.tasks.pipeline` ou sub-módulo próprio; retry bounded; `.delay()` nos callers; testes via `.apply()`).
- **Fase 14.2** Auditar `gatekeeper_service.py` TODO de create_task. Se houver código ativo, migrar; se for apenas comentário morto, remover o TODO e documentar.

**Tema B — CI / operacional residual (2 fases):**
- **Fase 14.3** Validar `docker compose build --no-cache backend` com `celery[redis]` + `slowapi` + demais deps persistindo na imagem final. Remover paliativos de `pip install` runtime. CI cobre com check `python -c "import celery, slowapi"` dentro do container construído.
- **Fase 14.4** Canário e2e dogfood real: rodar a lane `e2e` com stack docker local via `seed_e2e.py`, validar execução end-to-end do `test_fluxo_completo.py`, ajustar o que o dogfood revelar. Sem reintroduzir `continue-on-error`.

**Tema C — TSC baseline cleanup (2 fases):**
- **Fase 14.5** Diagnóstico + remoção dos arquivos shadcn/ui não referenciados no repositório (`calendar`, `carousel`, `command`, `drawer`, `input-otp`, `resizable`, `sidebar`, `sonner`, `switch`, `tabs`, `toggle`, `tooltip`). Para cada arquivo: se `grep` confirmar zero imports, remove; se alguma página importa, instala a dependência npm correspondente.
- **Fase 14.6** Corrigir `TesterReviewPage.tsx` (type mismatch `TestArtifact` e signature `onApprove`). Erros pré-existentes aos MVPs 11/12/13 — baseline tsc sai de 57 → 0 no caminho canônico.

**Tema D — OCG maturity (2 fases):**
- **Fase 14.7** Implementar `rollback_to_version` como fluxo formal (endpoint + service + teste + audit via `log_event` canônico). Hoje é N/A.
- **Fase 14.8** Tornar `consolidate_ocg` explícito como método separado (hoje implícito em `update_ocg_from_arguider`). Garante ponto único de observabilidade + audit.

**Tema E — Type safety frontend (1 fase):**
- **Fase 14.9** Remoção dos 91 `any` restantes no frontend (seguindo padrão `getErrorMessage`/`getErrorStatus`/`ApiError` já estabelecido na 12.7). Foco em componentes shadcn upstream + casts pontuais. Meta: 91 → ≤ 20.

**Tema F — Observabilidade Celery (1 fase):**
- **Fase 14.10** Adicionar Flower (UI de inspeção) + endpoint `/metrics` com contadores Prometheus das tasks (task_total, task_failed, task_duration_seconds). Sem alterar signal handlers existentes (Fase 13.4) — só adicionar observabilidade por cima.

**Tema G — Refactor shadcn/ui (1 fase):**
- **Fase 14.11** Refactor amplo dos shadcn/ui que **são** usados: normalizar imports, corrigir props mal tipadas, alinhar com convenção do projeto. Não remover arquivos (isso é 14.5).

#### Regras duras

- Cada fase exige revalidação §9 antes de passar para a próxima.
- Escopo fechado; qualquer item fora exige nova emenda do contrato.
- Nenhuma feature nova (tudo é saneamento/follow-up/maturity).
- Fases 14.9 (91 any) e 14.11 (refactor shadcn) têm regra de parada se diagnóstico inicial revelar escopo > 2 dias cada — aí sub-dividir.
- Watchdog DT-073 continua ativo até 14.1 + 14.2 provarem cobertura completa do pipeline.
- Identity Federation e Data Federation permanecem fora até pedido explícito com cliente real (gateway de contrato §3 mantido).

#### RBAC preservado (§4.1)

- Nenhuma mudança em papéis canônicos (§4).
- Endpoints novos (14.7 rollback, 14.10 metrics) protegidos por `require_action` apropriado (GP para rollback; admin para metrics).

#### Fora de escopo

- Identity Federation (SSO OIDC/SAML) — sem cliente real para testar.
- Data Federation — exige emenda §3 + 3 decisões pendentes.
- Federated Learning — GCA não treina modelos.
- Auto-scaling Celery (K8s) — produto instalável continua com workers fixos.
- Migração para Kafka/RabbitMQ — Redis já resolve.
- SIEM externo — audit continua interno.
- Reescrita ampla de módulos que não shadcn/ui.
- Preencher todas as 91 ocorrências de `any` (meta é ≤ 20, não zero — shadcn upstream usa `any` por design em alguns pontos).

---
