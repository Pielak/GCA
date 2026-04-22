# Arquivo — Simetria de soberania RBAC e higiene operacional residual

MVP 11. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 11 — Simetria de soberania RBAC e higiene operacional residual

**Motivação:** a emenda §4.1 (2026-04-19) consolidou que "GP está para o projeto assim como Admin está para a instância". A auditoria 2026-04-20 pós-saneamento documental revelou que a analogia não está refletida no código:
- **Admin** pode convidar outro Admin para a instância via `POST /admin/invite-admin` com guard de último Admin ativo. Funciona.
- **GP** não pode convidar outro GP para o mesmo projeto. `ProjectTeamPage.tsx:29-33` limita o dropdown de papéis a `['dev','tester','qa']`; `project_team_service` não aceita `role='gp'`. Violação direta da analogia §4.1.

Além disso, três dívidas operacionais permanecem abertas após o fechamento do MVP 10 sem marco claro de liquidação: DT-041 (image drift), DT-076 V2 (cobertura multi-DB no `ddl_generator_service`) e a GUI E2E com Playwright (`test_fluxo_completo.py` permanente no `--ignore`). Em vez de seguirem indefinidamente como "follow-up", ganham casa num ciclo canônico.

Este MVP resolve os dois temas em sequência, sem misturá-los: simetria de soberania primeiro (11.1–11.4), higiene operacional residual depois (11.5–11.7).

#### Em escopo

**Tema 1 — Simetria de soberania RBAC (compartimentalizada):**

- **Fase 11.1 — GP convida outro GP do mesmo projeto.** `project_team_service` aceita `role='gp'` quando o convidante for GP ativo do próprio projeto. `ProjectTeamPage.tsx` adiciona "GP" ao dropdown de papéis **apenas** quando o usuário autenticado é GP do projeto aberto. Token de convite emitido com `project_id` no payload — nunca cruza projetos. Aceite do convite cria `ProjectMember` com papel `gp` rastreado em `project_member_roles`.
- **Fase 11.2 — GP transferir soberania do projeto.** Novo endpoint `POST /projects/{id}/transfer-gp/{user_id}` que promove outro membro a GP e rebaixa o chamador a Dev em transação atômica. Pré-condições: alvo é membro ativo do projeto; alvo não é GP ainda; chamador é GP atual. Auditoria obrigatória com `actor_id`, `target_user_id`, `project_id`, `old_role='gp'`, `new_role='dev'` (para o chamador) e inverso (para o alvo).
- **Fase 11.3 — Guard reforçado de último Admin ativo.** Auditar `admin_management_service.py` linha-por-linha contra o contrato: bloquear pré-ação qualquer caminho que permita a instância ficar sem Admin ativo (auto-rebaixamento de último, desativação de último, exclusão de último, rebaixamento cruzado que zere o último). Pré-check antes de autorizar a ação — nunca recuperação posterior. Teste dedicado cobrindo cada caminho.
- **Fase 11.4 — Auditoria de eventos de papel.** `audit_log_global` passa a registrar eventos canônicos `role_granted`, `role_revoked`, `role_transferred` com payload mínimo: `actor_id`, `target_user_id`, `project_id` (nullable quando for instância), `old_role`, `new_role`, `timestamp`. Cobertura: todo convite emitido, todo convite aceito, toda transferência de soberania, todo rebaixamento (admin e GP), toda desativação que afete papel ativo.

**Tema 2 — Higiene operacional residual:**

- **Fase 11.5 — DT-041 image drift.** `docker compose build --no-cache gca-backend` reprocessado com `pypdf`, `reportlab` e `esprima` persistidos na imagem. CI cobre o passo. Remove paliativo runtime. Validação: `docker exec gca-backend python -c "import pypdf, reportlab, esprima"` sem falha após rebuild limpo.
- **Fase 11.6 — DT-076 V2 cobertura multi-DB.** `ddl_generator_service` ganha implementação real para Oracle, SQL Server, SQLite e MongoDB — substitui os placeholders da V1 com dialeto correto de schema, seed e migrations. 7 frameworks de migration continuam cobertos (Alembic/Flyway/Knex/TypeORM/Laravel/EFCore/go-migrate) com dialeto-específico quando aplicável. Testes por banco cobrindo geração básica + constraint + FK.
- **Fase 11.7 — Playwright GUI E2E.** Pacote `playwright` + browsers instalados no container `gca-backend` (ou container dedicado de teste E2E); `test_fluxo_completo.py` sai do `--ignore` em CI e na baseline. Se a suite for pesada demais para o caminho default, cria-se lane separada (`pytest -m e2e`) executada em pipeline específico, mas o teste NÃO continua ignorado.

#### Regras duras

- Convites permanecem compartimentalizados: token emitido para projeto X só aceita em projeto X; nenhum caminho promove Dev/Tester/QA a Admin por atalho; GP promove GP **apenas** do próprio projeto, **nunca** de outro projeto (mesmo que seja GP de outro).
- Simetria não quebra contenção: Admin promove Admin da instância, **nunca** transfere papel para um projeto.
- Transferência de soberania do projeto é voluntária e auditada; nenhum automatismo de "substituir GP por timeout/inatividade".
- Guard do último Admin é **pré-check** antes de autorizar a ação, nunca recuperação depois.
- Toda ação de papel passa por `audit_log_global` com `project_id` preenchido quando a ação for dentro de projeto.
- Dívidas operacionais (11.5/11.6/11.7) não tocam em RBAC, fluxo de projeto ou contrato de dados — permanecem isoladas do Tema 1.
- Nenhum novo papel canônico entra — §4 continua com os 5 papéis (Admin, GP, Dev, Tester, QA).

#### RBAC preservado (§4.1)

- **Admin** (instância): convida/rebaixa Admin; continua fora dos projetos.
- **GP** (projeto): convida/rebaixa/transfere dentro do próprio projeto; nunca age em outro projeto ainda que seja GP de outro.
- **Dev/Tester/QA**: não convidam, apenas recebem convite; podem ser promovidos a GP pelo GP atual via Fase 11.2 ou convite direto de outro GP via Fase 11.1.

#### Fora de escopo

- Novos papéis além dos 5 canônicos (§4).
- Convite cross-projeto (token que valha para múltiplos projetos) ou cross-instância.
- Promoção de Support a Admin via UI (já vedado na emenda MVP 6 2026-04-19).
- Criação de "suplente de GP", "co-GP" ou "GP de backup" com políticas distintas — a simetria aqui é binária: usuário é GP do projeto ou não é.
- SSO / federação de identidade — ficará para MVP dedicado se solicitado (ver memória parked `gca_federation_roadmap.md`).
- Auto-promoção baseada em tempo, inatividade ou heurísticas.
- Integração de auditoria com SIEM externo — `audit_log_global` continua interno nesta fase.
- Expansão do `ddl_generator_service` além dos 4 bancos adicionados (ex: TimescaleDB, DynamoDB, Cassandra, Redis persistente) — fora do V2.
- GUI E2E com ferramentas além de Playwright (Cypress, Selenium, Nightwatch).

---
