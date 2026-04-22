# Arquivo — Robustez estrutural: fila persistente + cobertura completa de auditoria

MVP 13. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 13 — Robustez estrutural: fila persistente + cobertura completa de auditoria

**Motivação:** ao fechar o MVP 12 em 2026-04-20, duas fases foram diferidas pela regra dura de parada (§7 MVP 12) — não por falta de relevância, mas por escopo estrutural incompatível com o caráter de saneamento daquele MVP. Ambas são dívidas reais de robustez:

1. **Fila persistente (ex-12.8).** Pipeline `Arguider → OCG Updater → CodeGen` hoje usa `asyncio.create_task` fire-and-forget. Se o backend cai durante uma análise, o watchdog DT-073 recupera o doc (OK operacional), mas: (a) não há retry automático; (b) concorrência sobre CPU-bound LLM calls é limitada ao event loop de um único processo; (c) auto-disparo do CodeGen após OCG pode perder-se silenciosamente. Redis já está no docker-compose; Celery é a migração canônica.

2. **Cobertura completa de `audit_log_global` (ex-12.10).** A Fase 11.4 instrumentou role events (`role_granted`/`role_revoked`/`role_transferred`) em 7 pontos. Continuam sem instrumentação canônica ~20+ ações críticas cross-domínio: aprovação/desativação/transferência de projeto, submissão/aprovação de questionário, geração/consolidação/rollback de OCG, scaffold/apply/regenerate-file em CodeGen. Isso fecha o contrato §5 (OCG como fonte única) + contrato §2.2 (compartimentalização auditável) com cadeia íntegra end-to-end.

Este MVP é explicitamente **estrutural**: não é saneamento. Cada tema é desenhado para permitir execução por fase, commit independente e revalidação §9 entre cada uma.

#### Em escopo

**Tema A — Fila persistente Celery/Redis (4 fases):**

- **Fase 13.1** Setup Celery + infraestrutura. Adicionar `celery[redis]` ao `pyproject.toml` / `requirements.txt`; criar `backend/app/celery_app.py` com broker Redis (URL vinda de env), result backend, timezone alinhado ao `BACKUP_TIMEZONE` da Fase 12.2; novo serviço `gca-celery-worker` no `docker-compose.yml` apontando para a imagem `gca-backend` + comando `celery -A app.celery_app worker --loglevel=info`; healthcheck via `celery inspect ping`. Smoke test: task trivial `ping.delay()` retorna dentro do timeout.
- **Fase 13.2** Lifespan + worker lifecycle. Integrar o `celery_app` no `main.py` lifespan do FastAPI (não iniciar worker no processo do uvicorn — worker é processo separado). Adicionar health check no endpoint `/health` que verifica conectividade do broker. Documentar `docker compose up gca-celery-worker` no README operacional.
- **Fase 13.3** Refactor pipeline Arguider + OCG Updater + auto-CodeGen. Migrar os 8 `asyncio.create_task` identificados no diagnóstico (concentrados em `ingestion_service._analyze_async`, `ocg_updater_service._auto_generate_in_background`, `ingestion_router.reanalyze`) para tasks Celery com `task.delay()` / `apply_async()`. Preservar semântica fire-and-forget vs. await quando aplicável. Manter `ingestion_service._analyze_async` como orquestrador síncrono que invoca 3 sub-tasks Celery em sequência (não migrar a orquestração inteira numa primeira passada).
- **Fase 13.4** Testes + monitoring + retry policy. `CELERY_TASK_ALWAYS_EAGER=True` em `conftest.py` para que tasks executem síncronas em pytest. Migração dos ~4 arquivos de teste que dependem de `_analyze_async`. Retry policy canônica por task (`max_retries=3`, `default_retry_delay=60s`, exponencial com jitter, DLQ em `celery_dlq` fila separada). Logs estruturados de `task_id`, `retry_count`, `duration`. Flower opcional (fora deste MVP; fica como follow-up).

**Tema B — Cobertura completa de `audit_log_global` (3 fases):**

- **Fase 13.5** Inventário + helpers de log canônico por domínio. Auditar endpoints/services que mudam estado crítico e ainda não chamam `AuditService.log_event` (spec inicial: ~20+ pontos em projeto/questionário/OCG/CodeGen). Publicar no §3 do progresso como lista binária ("tem audit" vs "falta audit"). Expandir `services/audit_service.py` com helpers específicos por domínio quando o shape canônico justificar (ex: `log_project_event`, `log_questionnaire_event`, `log_codegen_event`) — seguindo o padrão do `log_role_event` da Fase 11.4.
- **Fase 13.6** Instrumentação Tema 1 (projeto + questionário). Injetar `await audit.log_event(...)` nos pontos que Fase 13.5 inventariar: aprovação/rejeição de projeto (`admin_service.approve_project_request` / `reject_project_request`), desativação/reativação (`admin_service.lock_user` já cobre via 11.4 mas projetos não; `set_project_status` com transições active↔paused↔inactive), submissão e aprovação de questionário (`QuestionnaireService.submit_questionnaire` + analisador). Correlation_id canônico por fluxo.
- **Fase 13.7** Instrumentação Tema 2 (OCG + CodeGen) + chain integrity end-to-end. Injetar audit em `OCGUpdaterService.update_ocg_from_arguider`, `ocg_history_service.rollback_to_version`, `AgentService.consolidate_ocg` (geração), `code_generation.generate_scaffold`, `code_generation.apply_scaffold`, `code_generation.regenerate_file`. Teste E2E que dispara série de ações (approve → submit → analyze → generate_ocg → rollback → scaffold → apply) e valida `AuditService.verify_chain()` intacta ao final — sem broken links na hash chain SHA-256.

#### Regras duras

- Cada fase fechada com gate §9 atendido antes de passar para a próxima.
- Fase 13.3 (refactor pipeline) é o ponto de maior risco: se o diagnóstico revelar que as 8 `create_task` estão mais entrelaçadas do que o mapa da Fase 12.8, o executor **pode parar** e propor sub-divisão (13.3a Arguider only, 13.3b OCG only, 13.3c CodeGen only). Não forçar migração atômica.
- Infraestrutura (Fases 13.1 + 13.2) é pré-requisito de 13.3/13.4. Ordem sequencial obrigatória no Tema A.
- Tema B pode ser executado em paralelo ao Tema A depois que 13.5 produzir o inventário.
- Performance durante o refactor Celery não pode degradar vs. asyncio baseline — se medições indicarem regressão ≥20%, reportar e pedir decisão.
- Nenhuma mudança de contrato de RBAC ou escopo de papel canônico (§4). Robustez não expande permissão.
- Retry infinito é proibido — max_retries bounded, DLQ obrigatória.

#### RBAC preservado (§4.1)

- **Admin**: opera a instância Celery (logs, DLQ, flush quando necessário). Não atua em projetos.
- **GP/Dev/Tester/QA**: observam resultado do pipeline como hoje; não interagem diretamente com Celery.
- Audit events gravados têm `actor_id` fiel ao caller original da ação, não ao worker Celery.

#### Fora de escopo

- Kafka / RabbitMQ / outros brokers — Redis já está no stack, sem justificativa para trocar.
- Migração das tarefas de **ingestão** para Celery (watchdog DT-073 cobre; tema fora — spec do MVP 12 já consignou).
- Flower ou Prometheus metrics da fila — observabilidade via logs estruturados + DLQ inspection; stack de monitoring externa fica para MVP futuro se necessário.
- Reescrita do modelo de dados do `audit_log_global` — hash chain SHA-256 atual se mantém; não trocar para Merkle/blockchain.
- Exportação de audit para SIEM externo — continua interno nesta fase.
- Auto-scaling do worker Celery — número de workers fixo via docker-compose; auto-scaling com K8s é fora do produto instalável nesta versão.
- Backpressure inteligente / rate limiting interno de tasks — DLQ + timeout bounded basta; backpressure pode virar follow-up se dogfood mostrar gargalo real.

---
