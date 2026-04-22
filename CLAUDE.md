# CLAUDE.md

Operacional do Claude no GCA. Para contrato formal do produto, ver `GCA_CANONICAL_CONTRACT.md`.
Para estado atual do MVP, ver `GCA_MVP_PROGRESS.md`. Para histórico, ver `docs/mvp_archive/`.

---

## Gotchas operacionais — regras que se esquecer, quebra dogfood

- ❌ `pytest` do GCA sempre contra `gca_test`, nunca `gca`. Conftest já força — não passe por cima. Se schema mudar: `pg_dump /gca --schema-only | psql /gca_test` após recreate.
- ❌ Não criar dados no DB sem autorização explícita do usuário. É dogfood; dado mock vira ruído real.
- ❌ `docker-compose.yml` editado → `docker compose up -d` (não `restart <serviço>`). Restart não vê config novo.
- ❌ Frontend editado → `docker exec gca-frontend npm run build` + `docker restart gca-frontend` + informar hard-refresh. Vite preview não recarrega.
- ❌ `VaultService.store_secret` commita internamente. Testes que o chamam dentro de `session.begin()` quebram — use sessões separadas.
- ❌ `secrets.token_urlsafe(12)` não é senha canônica. Para convites, use `generate_temporary_password()` de `app.core.security` (RF-001: 10 chars, 1 maiúscula, 1 dígito, 1 especial).
- ❌ Listagem de membros filtra `is_active AND joined_at IS NOT NULL`. Filtro só `is_active` inclui convite pendente. Use helper `is_active_integrated_member()`.
- ⚠ MVP de integração entrega **backend + UI juntos**. Backend registrado sem endpoint/painel gera fix 2h depois.
- ⚠ `feedback_gca_binary_language`: escreva "tem / não tem", "deve / não deve". Nunca "pode", "poderia", "talvez". Zero ambiguidade.
- ⚠ §10 contrato canônico: correção cirúrgica > refactor amplo. Não tocar código vizinho que está funcionando.
- ⚠ PT-BR em tudo: comunicação, commits, comentários, docs, UI.
- ⚠ Compartimentalização §2.2: toda query de dado de projeto inclui `project_id`. Zero vazamento cross-tenant.

---

## Invariantes do produto (do contrato)

- **RBAC imutável**: 5 papéis canônicos — Admin · GP · Dev · Tester · QA. Não inventar outros.
- **OCG obrigatório**: toda decisão arquitetural, funcional ou de código lê o OCG antes e atualiza depois.
- **Modo on-premises**: uma instância por cliente. Sem SaaS multi-tenant. Isolamento principal por projeto.
- **IA configurável por cliente**: não hardcodar provedor. Admin e cliente escolhem — Anthropic / OpenAI / Gemini / Ollama local.
- **Criticidade em 3 níveis** (§6.2 contrato): baixa→local/barato; média→qualquer; alta→premium obrigatório (OCG consolidação, arbitragem, compliance crítico, codegen crítico).
- **Fluxo de MVP**: fase individual exige autorização explícita do stakeholder (§7.0). Nada executa em bloco sem luz verde.

---

## Antes de qualquer trabalho

1. Ler `GCA_CANONICAL_CONTRACT.md` — fonte soberana para decisões formais.
2. Ler `GCA_MVP_PROGRESS.md` — MVP ativo + próximo marco.
3. Se for fase de MVP aberto, confirmar autorização explícita antes de codar.
4. Se detectar contradição entre docs, reportar e seguir o contrato. Não reconciliar silenciosamente.

---

## Estratégia de trabalho

1. **Diagnosticar** antes de implementar.
2. **Classificar dívida** se encontrar inconsistência.
3. **Corrigir blocker/critical primeiro**, depois revalidar.
4. **Só então** expandir para feature nova.
5. Fixes descobertos no dogfood viram commit `fix:`, não MVP novo. MVP é reservado para escopo novo planejado.

---

## Ao final de cada ciclo de trabalho, reportar

- Fase/MVP avaliado.
- O que foi corrigido.
- O que continua pendente.
- Se a fase pode avançar.

Se o usuário tentar furar o fatiamento do MVP, sinalizar explicitamente e propor correção mínima. Nunca avançar silenciosamente.

---

## Precedência em caso de conflito

1. `GCA_CANONICAL_CONTRACT.md` (fonte soberana do produto)
2. `GCA_MVP_PROGRESS.md` (estado atual)
3. `CLAUDE.md` (este arquivo — operacional)
4. Código existente
5. Documentos históricos em `docs/mvp_archive/` e memórias

Documento histórico explica contexto; não autoriza implementação.
