# Arquivo — Roadmap multicategoria com pré-ingestão guiada

MVP 9. Extraído de `GCA_CANONICAL_CONTRACT.md` em 2026-04-22 como parte da reforma documental.

---

### MVP 9 — Roadmap multicategoria com pré-ingestão guiada

**Motivação:** o dogfood 2026-04-19 no projeto Automação Jurídica expôs que o Roadmap gerado hoje lista apenas **features de negócio** (29 itens, todos `module_type='feature'` — Cadastro, Triagem, Geração de Peças, Conector DataJud etc). O questionário captura stack, capacity e output_type; o OCG consolida `STACK_RECOMMENDATION` (backend/frontend/database/cache/messaging/ai), `ARCHITECTURE_OVERVIEW` (execution_model, multi_tenant, HA, async_processing) e `PROJECT_PROFILE` (initiative_type, output_formats). Mas o Arguidor nunca destilou essas informações em **itens de backend, middleware, infraestrutura, observabilidade e deploy**. Resultado: o Roadmap é um catálogo de funcionalidades, não um plano de construção. Sem esses itens, não há plano de deploy sugerido, e a Geração de Código (MVP 3) não sabe em que ordem construir ou que camadas faltam.

Este MVP resolve três lacunas em sequência:
1. **Roadmap incompleto** — só tem features, falta backend/infra/deploy.
2. **Itens opacos** — cada card traz só nome + prioridade; não explica o quê é, o que precisa, que código gera.
3. **Sem ponte item → ingestão** — se um item precisa de mais informação (API externa, diagrama, regra de negócio), GP não tem caminho para prover; item fica "suggested" para sempre.

A chegada do primeiro item no estado `ready_for_codegen` é a condição binária para o MVP 3 (CodeGen) operar em dogfood real.

#### Em escopo

- **Fase 9.1 — Categorias canônicas de módulos:** `module_candidates.module_type` aceita 6 categorias estáveis: `feature`, `backend_service`, `middleware`, `infrastructure`, `observability`, `deploy_pipeline`. Prompt do Arguidor reescrito pedindo expansão nas 6 categorias a partir do OCG. UI do Roadmap agrupa por categoria com filtro.
- **Fase 9.1.1 — Fase 1 do Roadmap nasce do OCG (não do Arguidor):** ao aprovar o questionário inicial e gerar OCG v1, um `RoadmapFoundationService` lê `STACK_RECOMMENDATION`, `ARCHITECTURE_OVERVIEW` e `PROJECT_PROFILE` e cria itens de **Fase 1 — Fundação** representando o TODO de pré-deploy: chaves de API externas, contratos de integração, certificados, ambiente de container, secrets, schema inicial de DB, primeiro pipeline de CI. Esses itens entram em `module_candidates` com `priority='high'`, `source='ocg_foundation'` (campo novo), `status='sugerido'`. Não dependem de Arguidor — Fase 1 existe **antes da primeira ingestão**.
- **Fase 9.1.2 — Status canônicos pt-BR (3 estados):** `module_candidates.status` aceita `sugerido` (criado pelo OCG/Arguidor, sem ação do GP), `aguardando_resposta` (GP iniciou questionário implícito do item mas não fechou), `adicionado` (item resolvido — todas as informações chegaram via Ingestão e o pipeline confirmou; vira deliverable e entra no escopo do CodeGen), `concluido` (CodeGen completou o item). Transições proibidas (regra dura): `concluido` não retrocede, `adicionado` só pode regredir para `sugerido` se o GP explicitamente reabrir. Labels em pt-BR sempre — o backend persiste o valor canônico em pt-BR; UI não traduz.
- **Fase 9.2 — Detalhamento on-demand por item (IA local, §6.2 baixa criticidade):** endpoint `GET /projects/{id}/modules/{mid}/details` invoca modelo local (Ollama) para gerar, sob demanda: `what_it_is` (descrição técnica curta), `prerequisites` (pré-requisitos), `missing_inputs` (informações que o Arguidor precisa ter recebido na Ingestão para este item ser elaborado), `input_examples` (exemplos de doc/trecho que viabilizam), e — quando aplicável — `implicit_questionnaire` (perguntas dirigidas ao GP cuja resposta engorda o OCG). Cache persistido em `module_candidates.details_json` para não regenerar a cada clique. Modal na UI do Roadmap ao clicar no item.
- **Fase 9.2.ext — Enriquecimento por WebFetch curado:** quando o item declara `external_reference: '<url>'` (tipicamente serviços públicos como DataJud, gov.br, APIs documentadas), o detalhamento da Fase 9.2 puxa via WebFetch o trecho relevante da documentação oficial e inclui no `what_it_is`/`prerequisites`. **Sem URL declarada, não há WebFetch automático** — o GCA não navega autonomamente. URLs são curadoria do prompt do Arguidor / Foundation generator.
- **Fase 9.3 — Orquestração premium (§6.2 alta criticidade):** job async pós-Arguidor chama provider premium do projeto para: inferir grafo de dependências entre os itens (DAG), prioridade real, e preencher campo novo `readiness_status` ∈ {`needs_input`, `partial`, `ready_for_codegen`}. Quando `needs_input`, LLM premium gera lista explícita de perguntas específicas ao item. Persistido em `module_candidates.dependencies_json` e `module_candidates.readiness_status`.
- **Fase 9.4 — Plano de deploy sugerido:** service ordena itens por camada + DAG: `infrastructure` → `observability` → `middleware` → `backend_service` → `feature` → `deploy_pipeline`. Exposto como aba/card "Plano de Deploy" no Roadmap, exportável em Markdown.
- **Fase 9.5 — Ciclo de resposta GP → ingestão → item `adicionado` → deliverable automático:** quando item está em `aguardando_resposta`, GP preenche o questionário implícito (Fase 9.2) e/ou anexa documentos adicionais marcados com `target_module_id`. **A resposta SEMPRE passa pelo pipeline normal de ingestão** (extractor → Arguidor → OCG updater) — preserva audit, evolui OCG por caminho único, sem patch direto. Quando o pipeline confirma propagação, item transita `aguardando_resposta` → `adicionado`. **Ao virar `adicionado`, o sistema cria automaticamente uma row em `DELIVERABLES` do OCG** (sem ação manual) — esse é o ponto onde o item entra no escopo do CodeGen. Botão "Gerar código" só aparece em itens `adicionado` e ainda exige aprovação explícita do GP (alinha com MVP 3 §7).

#### Roteamento híbrido Premium + Local nesta fase (§6.2 reforçado)

Cada chamada de IA desta fase declara **camada de uso** explícita:
- **Premium imediata** (alta criticidade): geração inicial do OCG no questionário aprovado, geração da Fase 1 de Fundação, orquestração da Fase 9.3 (DAG + readiness). Tem que ter feedback rápido pro GP.
- **Local imediata** (baixa criticidade): detalhamento on-demand da Fase 9.2 (Ollama no projeto) — o GP clica e espera 2-3 segundos.
- **Premium batch** e **Local batch** (jobs noturnos, refinamento incremental sobre OCG inteiro): **fora de escopo nesta iteração** do MVP 9. Ficam definidos no contrato como direção futura mas não implementados aqui.

#### Regras duras

- Nenhum item vai para CodeGen sem `status='adicionado'` E aprovação explícita do GP (binário).
- Item `adicionado` cria automaticamente row em `DELIVERABLES` do OCG. Sem exceção.
- Resposta do GP a questionário implícito sempre passa pelo pipeline de ingestão. Não existe patch direto no OCG.
- Cada chamada de IA grava provedor, modelo, camada (Premium/Local), criticidade e custo (§6.3).
- IA local nunca decide sozinha arquitetura, DAG ou readiness — texto explicativo e questionário implícito são baixa criticidade; dependências e readiness são alta criticidade e exigem premium (§6.3).
- A escolha de provedor/modelo segue a configuração do projeto (§6.5 Contexto B) — o GCA não hardcoda provedor.
- WebFetch acontece **apenas** com `external_reference` curado declarado. Sem navegação autônoma.

#### RBAC preservado (§4.1)

- **GP** aciona "Detalhar" e "Prover informações"; aprova itens para CodeGen. Não escreve código.
- **Dev** opera CodeGen depois que GP marca item como aprovado. Não aprova itens do Roadmap.
- **Tester/QA** leem o Roadmap; não mudam readiness.
- **Admin** não atua em projeto (§4.1). Pode ler o Roadmap apenas em `support` (§7 MVP 6 Emenda).

#### Fora de escopo

- Geração de diagrama arquitetural visual (DAG renderizado como grafo) — nesta fase, a DAG fica em campo relacional e a ordem sugerida vira lista textual; visualização gráfica é MVP futuro.
- Estimativa automática de esforço/tempo por item — exige calibração com histórico, fica para depois que houver N projetos com dados reais de codegen.
- Auto-edição de OCG a partir das respostas do "questionário complementar" da Fase 9.5 — as respostas entram como novo artefato ingerido, o OCG evolui pelo Updater já existente; não há caminho paralelo.
- Integração direta com Jira/Linear/GitHub Issues — o Roadmap permanece local no GCA neste MVP.

---
