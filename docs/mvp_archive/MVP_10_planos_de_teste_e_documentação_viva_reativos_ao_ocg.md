# Arquivo — Planos de Teste e Documentação Viva reativos ao OCG

MVP 10. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 10 — Planos de Teste e Documentação Viva reativos ao OCG

**Motivação:** as abas `Testes` (QA Readiness), `Revisão de Testes` (Tester Review) e `Documentação Viva` (LiveDocs) existem mas operam **desconectadas** do OCG/Roadmap/Ingestão. Diagnóstico dogfood 2026-04-20:

- **QA Readiness**: mostra apenas metadata estática lida do OCG (`has_unit_tests: sim`, `has_integration_tests: sim`...) e placeholders "Nenhuma execução registrada". Não gera planos de teste. Não reage a evolução do OCG.
- **Tester Review**: CRUD manual de `TestArtifact` (implementação concreta de teste, código). Sem geração automática a partir dos 40 módulos do Roadmap; GP/Tester precisa criar tudo do zero.
- **LiveDocs**: gera seções hardcoded com comentário `"será gerado via LLM em produção"` — hoje não há chamada LLM real. Doc não reflete estado do OCG evolutivo.

Consequência: o Roadmap entrega 40 módulos ricos (foundation + features + orquestração Premium do MVP 9), mas o GP não tem visão de **o que testar** por módulo nem documentação técnica derivada. O ciclo Roadmap → Testes → LiveDocs fica quebrado.

Este MVP **não refaz** QA Execution (subprocess isolation + logs JSONL já existem) nem Tester Review (CRUD manual já existe) nem sobrescreve `TestArtifact`/`TestFile`. Cria **camada nova `TestSpec`** (plano/spec em plain text, granularidade módulo × tipo) + **camada nova `LiveDoc`** (doc por módulo + índice consolidado) que se conectam via `module_id` ao Roadmap do MVP 9.

#### Em escopo

- **Fase 10.1 — Schema TestSpec + LiveDoc.** Migration com 2 tabelas novas: `test_specs` (`id`, `project_id`, `module_id` NULLABLE para specs globais, `spec_type` ∈ {unit, integration, security, compliance, e2e}, `content` TEXT em markdown, `provenance_json`, `ocg_version_at_generation`, `generated_at`, `generator_provider`, `generator_model`, `status` ∈ {draft, approved, rejected, stale}) e `live_docs` (`id`, `project_id`, `module_id` NULLABLE para doc consolidada, `doc_type` ∈ {module_doc, index, architecture}, `content`, `provenance_json`, `ocg_version_at_generation`, `generated_at`, `generator_provider`, `generator_model`). `UniqueConstraint(project_id, module_id, spec_type)` em `test_specs` e `UniqueConstraint(project_id, module_id, doc_type)` em `live_docs` pra idempotência.
- **Fase 10.2 — Geração de Unitários/Integração via Ollama (baixa criticidade §6.2).** Para cada módulo `backend_service`/`feature`/`middleware`/`infrastructure` do Roadmap, Ollama gera spec markdown de testes unitários e de integração. Prompt em pt-BR: "o que testar, por quê, como, casos-limite, mocks necessários". Reusa padrão da Fase 9.2 (AIKeyResolver chain filtrado pra ollama + base_url + cache por registro).
- **Fase 10.3 — Geração de Segurança/Compliance via Premium (alta criticidade §6.2).** Specs **globais** (module_id=NULL) consolidando requisitos do OCG: LGPD (do `COMPLIANCE_CHECKLIST`), autenticação (do `ARCHITECTURE_OVERVIEW`), secrets e audit (do PROJECT_PROFILE), pillars P2 Compliance e P7 Segurança. Premium obrigatório; sem fallback local.
- **Fase 10.4 — Stale detection.** Comparar `test_spec.ocg_version_at_generation` com OCG atual; se diverge, marcar `status='stale'` + expor `reason` ("OCG avançou de v7 pra v9 após último Regenerar"). Check também em `live_docs`. Sem auto-regeneração.
- **Fase 10.5 — UI "Testes" reformada.** Aba `Testes` ganha seção nova "Plano de Testes" acima dos KPIs existentes: chips por `spec_type` com contagem + badge stale quando aplicável + filtro + click abre modal com `content` em plain text + provenance (OCG version, questionário, ingestões, LLM, timestamp). Preserva QA Execution atual (subprocess pytest).
- **Fase 10.6 — UI "Revisão de Testes" complementada.** Tabs do Tester Review ganham tab extra "Specs (planos)" mostrando `test_specs` ao lado do CRUD de `TestArtifact`. Fluxo aprovação GP/QA nos specs (approved) — Tester usa spec aprovado como insumo pra escrever `TestArtifact` concreto.
- **Fase 10.7 — UI "Documentação Viva" conectada.** Substitui placeholders por `live_docs` reais. Doc por módulo (Ollama) + índice consolidado (Premium). Seções existentes (README/ARCHITECTURE/DEPLOY) continuam vindo de Git; docs por módulo são NOVOS.
- **Fase 10.8 — Botão Regenerar granular.** Por tipo: "Regenerar Unitários", "Regenerar Compliance", "Regenerar Docs de Módulos", e "Regenerar Tudo". Stale badge + banner "X items desatualizados — clique Regenerar" no topo da aba.

#### Regras duras

- Geração é **manual** (botão Regenerar). Sem auto-disparo por delta — evita gasto de tokens descontrolado.
- Stale = comparação de versão do OCG; o sistema só **marca**, nunca regenera sozinho.
- Unit/Integration/LiveDocs-por-módulo = Ollama local. Security/Compliance/LiveDocs-consolidada = Premium obrigatório (§6.3). LLM local nunca decide política de segurança.
- Cada `test_spec` e `live_doc` grava `provenance_json` com: OCG version, questionnaire_id, ingested_doc_ids considerados, provider, model, timestamp. Click no item expõe tudo ao GP.
- Idempotência: `(project_id, module_id, spec_type)` é unique — regenerar sobrescreve in-place preservando `id` e audit log.
- Nenhum spec é promovido a `TestArtifact` automaticamente. GP/Tester aprova spec; Tester escreve `TestArtifact` usando spec como insumo.

#### Fora de escopo

- Auto-regeneração por delta — manual via Regenerar (escolha explícita do stakeholder).
- Execução de testes (já existe em `qa_service`). Gap de execução de spec-versus-TestArtifact fica fora.
- Editor WYSIWYG do conteúdo dos specs — plain markdown read-only nesta fase. GP edita regenerando via Ollama (se nova direção) ou manual no DB (apenas Admin em caso excepcional).
- Diff visual entre versões do spec — stale só mostra "mudou OCG", não detalha em quê.
- CodeGen de `TestArtifact` a partir do spec — MVP 3 cuida, 10 só produz plano.

---
