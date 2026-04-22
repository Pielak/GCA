# Arquivo — Saneamento pós-MVP 11: hardening de fronteira, configurabilidade, higiene de schema e maturidade

MVP 12. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 12 — Saneamento pós-MVP 11: hardening de fronteira, configurabilidade, higiene de schema e maturidade

**Motivação:** auditoria 2026-04-20 pós-MVP 11 identificou 6 DTs canônicas (rate limit público ausente, timezone hardcoded no backup scheduler, dual `accepted_at`/`joined_at`, `initial_password_hash` órfão, TODOs SMTP em fluxo deprecado, e2e `continue-on-error`) + 4 dívidas estruturais mais antigas que seguiam como backlog (type safety `any` no frontend, fila persistente diferida DT-075, helper de prompt CodeGen duplicado, hash chain de auditoria incompleto). O stakeholder-soberano autorizou em 2026-04-20 incluir **todas** num único MVP de saneamento, em vez de deixar as 4 últimas como backlog indefinido.

Este MVP tem caráter **majoritariamente de saneamento e hardening** — não introduz feature nova. Cada fase é independente; execução é sequencial por prioridade (A→B→C→D→E→F→G) mas fases são commitáveis isoladamente.

#### Em escopo

**Tema A — Segurança de fronteira (abuse prevention):**
- **Fase 12.1** Rate limit + mitigação anti-abuse em `POST /public/request-project`. Throttle por IP (`slowapi` ou equivalente), idempotência já existente mantida, opcional captcha simples se volume justificar. Teste cobrindo bloqueio após N requisições/min.

**Tema B — Configurabilidade operacional:**
- **Fase 12.2** Timezone configurável em `BackupScheduler`. Env var `BACKUP_TIMEZONE` (default `America/Sao_Paulo`); runtime lê e passa para APScheduler. Teste cobre 2 timezones distintos.

**Tema C — Higiene de schema + cleanup:**
- **Fase 12.3** Consolidar `ProjectMember.accepted_at` vs `joined_at`. Manter ambas colunas (backward-compat); adicionar helper canônico `is_pending_invite(member)` em `app/services/project_team_service.py`; corrigir toda query que filtra por `accepted_at IS NULL` para usar `invite_token IS NOT NULL AND joined_at IS NULL AND is_active=True`. Comentário canônico no modelo.
- **Fase 12.4** Deprecar `ProjectRequest.initial_password_hash`. Coluna não é preenchida em nenhum fluxo desde migração do onboarding — adicionar comentário `# deprecated 2026-04-20 — remove em V2 after grace period`. Sem remoção física nesta fase (evita migração destrutiva sem plano de rollback).
- **Fase 12.5** Remoção de TODOs SMTP de fluxo deprecado. Arquivos: `backend/app/routers/onboarding.py:139` e `services/onboarding_service.py:493-494`. Se os endpoints correspondentes não têm mais consumer, retornam 410 Gone; se ainda têm, ligar ao `email_service` canônico. Decisão por análise de uso.

**Tema D — CI maturity:**
- **Fase 12.6** Canário real + remoção do `continue-on-error: true` da lane `e2e` em `backend-tests.yml`. Script `backend/scripts/seed_e2e.py` cria admin canônico `admin@gca.local` + 1 projeto com `project_id=1` no ambiente de CI antes do teste rodar. Após passar consistentemente, lane vira gate real.

**Tema E — Type safety frontend:**
- **Fase 12.7** Remoção de `any` de arquivos TS do frontend — ~20 arquivos identificados em `frontend/src/lib/`, `frontend/src/pages/admin/` e `frontend/src/pages/projects/`. Substituir por tipos ou interfaces explícitas. Violação da política CLAUDE.md §12 ("Não usar `any`"). Build frontend tem que continuar íntegro.

**Tema F — Robustez estrutural:**
- **Fase 12.8** Fila persistente (ex-DT-075 reclassificada). Migração de tarefas async de `asyncio.create_task` para Celery (Redis já está no docker-compose). Cobertura: apenas pipeline `Arguidor` + `ocg_updater` + `codegen` — tarefas de ingestão mantêm `asyncio` nesta fase (watchdog DT-073 cobre). Se escopo mostrar-se excessivo em diagnóstico inicial, reportar e pedir decisão binária antes de continuar.
  - **DIFERIDA 2026-04-20** pela regra de parada: diagnóstico inicial revelou escopo estrutural (3-4 dias, 5 frentes: Celery setup + tasks, lifespan integration, refactor pipeline, migração de testes, monitoring+retry). Re-escopada para **MVP 13 — Robustez estrutural** quando autorizado. Watchdog DT-073 continua cobrindo o sintoma operacional (doc preso em `processing`).
- **Fase 12.9** Consolidação do helper de prompt do CodeGen. Hoje `/scaffold` e `/regenerate-file` duplicam lógica de build de prompt em `code_generation.py`. Extrair `_build_scaffold_prompt(project, ocg_data, scope)` compartilhado. Facilita mock em testes e garante consistência dos prompts.

**Tema G — Observabilidade compliance:**
- **Fase 12.10** Completar cobertura de `audit_log_global` na hash chain. Auditoria: identificar endpoints/ações críticas que ainda não gravam em `audit_log_global` (além do que a Fase 11.4 cobriu). Expandir cobertura para ações de projeto (aprovação, desativação, transferência), questionário (submissão, aprovação), OCG (geração, consolidação, rollback), CodeGen (scaffold/apply, regenerate-file). Validação: teste de ponta-a-ponta que verifica chain integrity pós-série-de-ações.
  - **DIFERIDA 2026-04-20** pela mesma regra de parada: cobertura e2e exige inventariar ~20+ endpoints e injetar `log_role_event`/`log_event` com payload canônico em cada, mais teste de cadeia integral. Re-escopada para **MVP 13 — Robustez estrutural** junto com 12.8. A cobertura parcial da Fase 11.4 (role events) continua operando.

#### Regras duras
- Nenhuma fase introduz feature nova além do saneamento declarado. Qualquer feature encontrada durante execução deve ser escopada em MVP futuro.
- Fases 12.8 (Celery) e 12.10 (hash chain completa) são estruturalmente maiores — se o diagnóstico inicial revelar escopo significativamente maior do que o resto, o executor **para** e pede decisão binária ao stakeholder (cortar, diferir ou continuar).
- Ordem de execução recomendada é A→B→C→D→E→F→G, mas fases são independentes; stakeholder pode reordenar.
- Gate §9 revalidado após cada fase.
- Nenhuma quebra de compat em DB/API sem plano de deprecação explícito.

#### Fora de escopo

- SSO/federação de identidade (ver MVP dedicado se solicitado).
- Nova arquitetura de auditoria (Merkle/blockchain público) — a Fase 12.10 mantém hash chain SHA-256 existente e apenas expande cobertura.
- Migração das tarefas de ingestão para Celery — watchdog DT-073 cobre e o refactor é oportunisticamente parcial na Fase 12.8.
- CAPTCHA de terceiros na Fase 12.1 (Turnstile/hCaptcha): preferir rate-limit local; captcha externo entra só se dogfood mostrar abuse real.
- Remoção física de `ProjectRequest.initial_password_hash` — só marca como deprecada; remoção em V2 com migração destrutiva planejada.
- Reescrita de testes flaky/skipped: os skips atuais têm motivo documentado (ver §3 do progresso); não reabertos nesta fase.
- Novo dialeto de DDL (Oracle V2 foi cobrido no MVP 11; não entra nada novo aqui).

---
