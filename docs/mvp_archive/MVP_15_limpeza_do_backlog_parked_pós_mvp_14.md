# Arquivo — Limpeza do backlog parked pós-MVP 14

MVP 15. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 15 — Limpeza do backlog parked pós-MVP 14

**Motivação:** pós-fechamento do MVP 14 (10/11 entregues + 1 N/A + 1 parcial), o stakeholder-soberano autorizou em 2026-04-20 o encerramento dos 4 itens parked: (a) 33 arquivos shadcn/ui órfãos remanescentes em `src/components/ui/*`; (b) 1 error tsc em `AdminMetricsPage.tsx` (prop `hint` inexistente no HintCard); (c) rewrite dos tests e2e 02-14 contra rotas/UUIDs atuais; (d) remainder dos 76 `any` da stop-rule da 14.9. Itens já diagnosticados e parked no §10 do progress pós-MVP 14 — MVP 15 os converte em ciclo canônico.

**Não entra no MVP 15 (explícito):**
- Identity Federation, Data Federation, Federated Learning — seguem fora per contrato §7 MVP 14.
- Bootstrap/auto-upgrade/multi-instância (GCA Futura Visão) — parked em outro backlog.
- Feature nova de qualquer tipo — este MVP é estritamente limpeza.

#### Em escopo

- **Fase 15.1** **shadcn pass 2**: remover os 33 arquivos órfãos em `src/components/ui/*.tsx` (todos 34 tsc errors remanescentes desmontam ~30). Critério: `grep -r "@/components/ui/<nome>"` em `src/` retorna zero. Preservar apenas os 4 componentes próprios do GCA (`HelpTooltip`, `PipelineProgress`, `ReadOnlyBanner`, `StatusBadge`).
- **Fase 15.2** **AdminMetrics HintCard**: corrigir 1 error tsc em `AdminMetricsPage.tsx:253` — prop `hint` não existe no componente `HintCard`. Opções: adicionar `hint?: string` à interface do componente OU remover o uso.
- **Fase 15.3** **e2e tests 02-14 rewrite**: ajustar seletores + rotas + UUIDs em `test_fluxo_completo.py` tests 02-14 contra o frontend atual (canônico pós-MVP 14). Test 01 + infra já validados na 14.4. Objetivo: toda lane e2e passa no CI sem regressão.
- **Fase 15.4** **any remainder**: reduzir os 76 `any` restantes com refactor cross-file onde necessário. Meta: ≤ 20 (mesma do 14.9). Regra de parada: se diagnóstico inicial revelar > 2 dias, sub-dividir e parar.

#### Regras duras

- Cada fase exige revalidação §9 antes da próxima.
- Escopo fechado; nenhuma feature nova.
- Fase 15.4 com regra de parada se diagnóstico revelar > 2 dias.
- RBAC imutável (§4).
- §10 (anti-alucinação) aplicável: sem refactor vizinho não-solicitado.
- Status inicial: **autorizado — em execução** (stakeholder autorizou abertura + execução em mensagem única).

#### Fora de escopo

- Qualquer coisa fora dos 4 itens acima.
- Refactor de componentes próprios (HelpTooltip etc.) fora de bug corrigindo tsc.

---
