# GCA_CANONICAL_CONTRACT.md

Versão: 1.2  
Data-base: 2026-04-17  
Status: **Canônico / soberano para implementação**

---

## 1. Objetivo deste documento

Este documento define a verdade operacional do GCA para implementação com Claude Code.

Ele existe para:
- eliminar conflito entre documentos históricos e código atual;
- congelar o modelo do produto nesta fase;
- definir o recorte do MVP ativo;
- impedir expansão de escopo antes do saneamento da base;
- padronizar o uso de IA por criticidade, custo, latência e risco.

Em caso de conflito, este documento prevalece sobre manual, tutorial, análises, mocks, README e demais documentos históricos.

### 1.1 Pipeline canônico (referência)

O fluxo de dados do pipeline está documentado em [`docs/PIPELINE_FLOW.md`](docs/PIPELINE_FLOW.md).
Este documento define:
- diagrama de fluxo canônico com dependências entre estágios;
- guardrails (DT-AUDITORIA-002) em cada serviço;
  - DT-AUDITORIA-003 removido na Simplificação Fase 2 (2026-05-01)
    junto com OCGIndividual/OCGGlobal
- race conditions conhecidas e seus comportamentos;
- logging e alertas recomendados.

O `PIPELINE_FLOW.md` é atualizado sempre que a arquitetura do pipeline muda.

---

## 2. Definição canônica do produto

O **GCA (Gestão de Codificação Assistida / Gerenciador Central de Arquiteturas)** é uma plataforma instalável por cliente para governança de projetos de TI assistida por IA.

### 2.1 Modelo de deployment
- O GCA é **instalável por cliente**.
- Não é, nesta versão, um **SaaS multi-tenant compartilhado entre clientes**.
- A instância `gca.code-auditor.com.br` deve ser tratada como **dogfood / ambiente do produto**, e não como prova de SaaS compartilhado.

### 2.2 Modelo de isolamento
- Cada cliente possui sua própria instância.
- Dentro da instância, o isolamento principal ocorre por **projeto**.
- “Tenant interno”, nesta versão, significa **isolamento por projeto**.
- Não existe compartilhamento de OCG, artefatos, credenciais ou contexto entre projetos.
- Não existe compartilhamento de contexto entre instâncias.

### 2.3 Modelo de IA
- O GCA **não impõe um único provedor de IA** ao cliente final.
- O cliente final usa suas próprias chaves, provedores e modelos, conforme objetivo, custo, latência, privacidade e compatibilidade desejados.
- O sistema deve oferecer **análise de adequação do provedor/modelo** ao objetivo do cliente antes de consolidar defaults que possam gerar decepção operacional.
- Nenhum provedor deve ser tratado como “melhor universal”.
- O GCA pode operar em **modo híbrido de IA**, com modelos diferentes por tipo de tarefa, desde que isso seja configurável e auditável.

---

## 3. Fonte soberana e precedência

Ordem de precedência para implementação:

1. `GCA_CANONICAL_CONTRACT.md`
2. `GCA_MVP_PROGRESS.md`
3. `CLAUDE.md`
4. `TASK_GCA_MASTER.md`
5. Código existente
6. Documentos históricos (manual, tutorial, análises, README, scripts de geração de docs)

### Regra dura
Se houver conflito entre documentos:
- **não reconciliar por conta própria**;
- seguir este contrato;
- registrar a divergência no `GCA_MVP_PROGRESS.md`.

---

## 4. RBAC canônico desta versão

Os únicos papéis canônicos implementáveis nesta versão são:
- **Admin**
- **GP**
- **Dev**
- **Tester**
- **QA**

### 4.1 Responsabilidades canônicas

#### Admin
- opera a instância;
- configura provedores, políticas, SMTP, thresholds e usuários administrativos;
- aprova/libera projetos;
- **não atua operacionalmente dentro dos projetos**;
- **não escreve código**.

#### GP
- conduz o projeto;
- aprova módulos, OCG e decisões-chave;
- convida time;
- mantém credenciais e parâmetros do projeto quando aplicável;
- **soberano do projeto** (emenda 2026-04-19): dentro do projeto o GP está acima dos demais papéis (Dev, Tester, QA) e tem acesso a **todas as funcionalidades** que os demais têm. A restrição anterior "GP não escreve código" fica revogada — o GP pode operar CodeGen, pipeline, testes e demais fluxos quando for necessário para destravar o projeto. A separação de responsabilidades do dia-a-dia continua (Dev escreve código como atividade principal; Tester cria testes; QA revisa), mas o GP não perde acesso por essas especializações: ele vê e opera tudo do projeto dele.
- análogo cross-escopo: **GP está para o projeto assim como Admin está para a instância**.

#### Dev
- implementa código;
- opera ingestão, Arguidor, CodeGen e commits quando liberado pela fase;
- corrige problemas técnicos;
- **não aprova módulo no Gatekeeper**.

#### Tester
- cria/edita/executa testes;
- registra evidências;
- exporta logs quando aplicável.

#### QA
- revisa/aprova resultados e execuções;
- valida qualidade final;
- **não edita conteúdo de teste**.

### 4.2 Papéis não canônicos nesta versão
Os seguintes papéis podem aparecer em documentos históricos, mas **não devem ser implementados como roles do sistema** sem alteração explícita deste contrato:
- Tech Lead
- Compliance
- Stakeholder
- Viewer
- Dev Sênior / Dev Pleno como roles distintas

Podem existir como:
- ator narrativo em documentação histórica;
- responsabilidade de negócio não modelada no RBAC;
- papel futuro.

---

## 5. OCG é obrigatório

O **OCG** é a fonte única de verdade do projeto.

Regras obrigatórias (atualizadas em 2026-04-30 — substituem versão anterior):
- o OCG nasce do questionário aprovado;
- o OCG é evolutivo e auditável;
- **o OCG só expande quando recebe informação de valor; nunca contrai**;
- ingestão ruim ou conflitante: documento vai para **quarentena** e **não afeta o OCG** (não há mais "contração de confiança" como behavior do motor);
- módulos não podem assumir defaults invisíveis quando o OCG estiver incompleto;
- toda mudança relevante deve gerar versionamento e trilha de auditoria.

Detalhe da máquina de estado, schema e propagação: skill `gca-ocg-engine` em `.claude/skills/gca-ocg-engine/SKILL.md`.

---

## 6. Política canônica de IA

### 6.1 Regra de adequação antes de fixar default
Antes de definir um provedor/modelo como padrão do cliente, o sistema deve avaliar:
1. objetivo principal do uso da IA no GCA;
2. nível de criticidade das tarefas;
3. expectativa de custo;
4. expectativa de latência;
5. necessidade de privacidade/localidade;
6. necessidade de codegen;
7. necessidade de análise documental e consolidação de contexto;
8. aderência do modelo ao idioma e ao volume de contexto esperado.

O resultado dessa análise deve classificar a IA como:
- **recomendada**;
- **aceitável com ressalvas**;
- **inadequada para o objetivo informado**.

### 6.2 Política de roteamento híbrido por criticidade

#### Baixa criticidade
Podem usar modelos locais ou mais baratos, inclusive via Ollama, quando configurados pelo cliente:
- classificação simples;
- extração de campos;
- sumarização curta;
- normalização de texto;
- pré-processamento de documentos;
- enriquecimento leve;
- transformação estrutural de conteúdo.

#### Média criticidade
Podem usar modelos locais ou remotos, com validação posterior:
- perguntas dirigidas preliminares;
- propostas iniciais de backlog;
- pré-análise de artefatos;
- agrupamento temático;
- preparação de insumos para OCG, Gatekeeper ou Arguidor.

#### Alta criticidade
Devem usar modelos de maior confiabilidade, qualidade analítica e contexto:
- consolidação final do OCG;
- arbitragem de conflitos entre documentos;
- decisões de arquitetura;
- achados críticos de compliance e segurança;
- decisões que bloqueiam ou liberam o pipeline;
- geração de backlog oficial;
- codegen crítico;
- síntese executiva oficial do projeto.

### 6.3 Diretriz prática
Regra recomendada:
- **Ollama/modelo local** = auxiliar de baixo custo para tarefas menores e repetitivas;
- **modelo premium de raciocínio** = consolidação, análise profunda, conflitos, arquitetura e decisões críticas.

### 6.4 Regras duras de IA
- Nenhum modelo local deve consolidar sozinho o OCG final sem validação da política do projeto.
- Nenhum modelo de baixa criticidade deve decidir sozinho arquitetura, compliance, segurança ou liberação de pipeline.
- O uso híbrido deve ser explícito, auditável e parametrizável.
- Cada tarefa relevante deve registrar:
  - provedor;
  - modelo;
  - motivo da escolha;
  - nível de criticidade;
  - custo estimado ou observado, quando aplicável.
- Compatibilidade com endpoint estilo OpenAI não deve ser tratada automaticamente como equivalência funcional entre modelos.

### 6.5 Relação com o OCG
O roteamento híbrido nunca substitui o OCG.
Independentemente do modelo usado:
- o OCG continua sendo a fonte única de verdade do projeto;
- toda saída relevante deve respeitar o contexto atual do OCG;
- mudanças relevantes devem atualizar o OCG conforme as regras de versionamento e auditoria.

### 6.6 Separação entre IA de desenvolvimento vs IA operacional do cliente

**Contexto A — construir o GCA** (escolha da equipe do produto; custo de desenvolvimento): permite modelo premium para maximizar qualidade analítica. Decisão aqui **não obriga** o cliente a usar a mesma IA.

**Contexto B — operar a instância do cliente** (escolha do cliente; custo operacional do cliente): o cliente escolhe provedor/modelo; GCA configura por instância e por projeto; recomenda, nunca impõe.

**Regra dura de não acoplamento:**
- IA do Contexto A **não pode virar dependência obrigatória** do Contexto B.
- Nenhuma decisão hardcoda um provedor como único caminho.
- Compatibilidade com múltiplos provedores + endpoints compatíveis preservada por config.

**Política de recomendação ao cliente (antes de fixar default):** avaliar objetivo, criticidade, custo, latência, privacidade, codegen, análise documental, idioma. Classificar cada opção como recomendada / aceitável com ressalvas / inadequada.

**Política operacional canônica (herdada de §6.2):** tarefas auxiliares podem ir a modelo local/barato; decisão crítica (OCG final, arbitragem, compliance, segurança, codegen estrutural) **não depende exclusivamente de modelo fraco**. Roteamento híbrido se aplica aos dois contextos, cada um com configuração própria.

**Relação com o OCG:** OCG é fonte única de verdade independente do provedor. Escolha de IA influencia perfil operacional; **não substitui** governança do OCG.

---

## 7. Escopo canônico por MVP

### 7.0 Protocolo de adição dinâmica de MVPs

Esta seção é **extensível por solicitação do stakeholder-soberano** (dono do produto). MVPs 1 a 5 nasceram com o produto; MVPs ≥ 6 são incorporados sob as regras abaixo.

Regras duras:
1. Somente o stakeholder-soberano autoriza a criação de novo MVP. Claude não cria MVP por conta própria, nem infere escopo a partir de pedido de feature isolado — toda solicitação de feature fora dos MVPs atuais deve ser tratada ou como nova DT dentro de um MVP existente, ou como solicitação formal de novo MVP.
2. Adição de MVP é commit **atômico** alterando simultaneamente:
   - `GCA_CANONICAL_CONTRACT.md §7` (nova subseção numerada, com **em escopo** e **fora de escopo** obrigatórios);
   - `GCA_MVP_PROGRESS.md §1` (cabeçalho com estado inicial e objetivo).
3. MVP recém-adicionado nasce com estado **"definido — não iniciado"** e só é trabalhado quando:
   - o MVP soberano anterior estiver fechado pelo gate §9;
   - o stakeholder autorizar o início explicitamente.
4. Nenhum MVP fora deste contrato soberano é implementado, mesmo que código rascunho exista em skills ou documentos históricos.
5. Em escopo e fora de escopo são obrigatórios no momento da criação — não se começa trabalho com escopo difuso.
6. Numeração é monotônica crescente. Não há renumeração retroativa.
7. Releases do produto amarram-se a uma lista de MVPs fechados e tickets (MVP 6) entregues — ver MVP 7.

## MVP Registry — histórico arquivado

MVPs 1-15 fechados. Detalhes completos em `docs/mvp_archive/`.

- **MVP 1** — Base operacional e saneamento do núcleo — FECHADO. Detalhe: [`docs/mvp_archive/MVP_01_base_operacional_e_saneamento_do_núcleo.md`](docs/mvp_archive/MVP_01_base_operacional_e_saneamento_do_núcleo.md)
- **MVP 2** — Contexto vivo e governança de conteúdo — FECHADO. Detalhe: [`docs/mvp_archive/MVP_02_contexto_vivo_e_governança_de_conteúdo.md`](docs/mvp_archive/MVP_02_contexto_vivo_e_governança_de_conteúdo.md)
- **MVP 3** — Geração assistida controlada — FECHADO. Detalhe: [`docs/mvp_archive/MVP_03_geração_assistida_controlada.md`](docs/mvp_archive/MVP_03_geração_assistida_controlada.md)
- **MVP 4** — Qualidade, documentação e entrega — FECHADO. Detalhe: [`docs/mvp_archive/MVP_04_qualidade_documentação_e_entrega.md`](docs/mvp_archive/MVP_04_qualidade_documentação_e_entrega.md)
- **MVP 5** — Hardening operacional — FECHADO. Detalhe: [`docs/mvp_archive/MVP_05_hardening_operacional.md`](docs/mvp_archive/MVP_05_hardening_operacional.md)
- **MVP 6** — Validação assistida em campo (tickets de incidente) — FECHADO. Detalhe: [`docs/mvp_archive/MVP_06_validação_assistida_em_campo_tickets_de_incidente.md`](docs/mvp_archive/MVP_06_validação_assistida_em_campo_tickets_de_incidente.md)
- **MVP 7** — Entrega versionada preservando dados do usuário — FECHADO. Detalhe: [`docs/mvp_archive/MVP_07_entrega_versionada_preservando_dados_do_usuário.md`](docs/mvp_archive/MVP_07_entrega_versionada_preservando_dados_do_usuário.md)
- **MVP 8** — Ingestão inteligente de documentos — FECHADO. Detalhe: [`docs/mvp_archive/MVP_08_ingestão_inteligente_de_documentos.md`](docs/mvp_archive/MVP_08_ingestão_inteligente_de_documentos.md)
- **MVP 9** — Roadmap multicategoria com pré-ingestão guiada — FECHADO. Detalhe: [`docs/mvp_archive/MVP_09_roadmap_multicategoria_com_pré_ingestão_guiada.md`](docs/mvp_archive/MVP_09_roadmap_multicategoria_com_pré_ingestão_guiada.md)
- **MVP 10** — Planos de Teste e Documentação Viva reativos ao OCG — FECHADO. Detalhe: [`docs/mvp_archive/MVP_10_planos_de_teste_e_documentação_viva_reativos_ao_ocg.md`](docs/mvp_archive/MVP_10_planos_de_teste_e_documentação_viva_reativos_ao_ocg.md)
- **MVP 11** — Simetria de soberania RBAC e higiene operacional residual — FECHADO. Detalhe: [`docs/mvp_archive/MVP_11_simetria_de_soberania_rbac_e_higiene_operacional_residual.md`](docs/mvp_archive/MVP_11_simetria_de_soberania_rbac_e_higiene_operacional_residual.md)
- **MVP 12** — Saneamento pós-MVP 11: hardening de fronteira, configurabilidade, higiene de schema e maturidade — FECHADO. Detalhe: [`docs/mvp_archive/MVP_12_saneamento_pós_mvp_11_hardening_de_fronteira_configurabilida.md`](docs/mvp_archive/MVP_12_saneamento_pós_mvp_11_hardening_de_fronteira_configurabilida.md)
- **MVP 13** — Robustez estrutural: fila persistente + cobertura completa de auditoria — FECHADO. Detalhe: [`docs/mvp_archive/MVP_13_robustez_estrutural_fila_persistente_cobertura_completa_de_a.md`](docs/mvp_archive/MVP_13_robustez_estrutural_fila_persistente_cobertura_completa_de_a.md)
## 8. MVP ativo (definição atual)

### MVP ativo inferido
**MVP 1 — Base operacional e saneamento do núcleo**

### Justificativa
O projeto já possui base funcional relevante (auth, projects, questionnaire, OCG, evaluation, codegen básico, dashboard, audit e rotas ativas), mas ainda há conflitos estruturais entre:
- contrato documental e RBAC;
- material histórico e implementação;
- estado “beta pronto” e gaps operacionais/documentais pendentes.

Portanto, a fase ativa não deve ser tratada como “expandir produto”, mas como:
1. consolidar a verdade do núcleo;
2. eliminar ambiguidade de RBAC e escopo;
3. fechar blockers/criticals da base;
4. só então avançar em ingestão profunda / CodeGen / entrega final.

---

- **MVP 14** — Saneamento de follow-up pós-MVP 13 + OCG maturity + type safety + observabilidade Celery — FECHADO. Detalhe: [`docs/mvp_archive/MVP_14_saneamento_de_follow_up_pós_mvp_13_ocg_maturity_type_safety.md`](docs/mvp_archive/MVP_14_saneamento_de_follow_up_pós_mvp_13_ocg_maturity_type_safety.md)
- **MVP 15** — Limpeza do backlog parked pós-MVP 14 — FECHADO. Detalhe: [`docs/mvp_archive/MVP_15_limpeza_do_backlog_parked_pós_mvp_14.md`](docs/mvp_archive/MVP_15_limpeza_do_backlog_parked_pós_mvp_14.md)
### MVP 16 — C++ fundacional + saneamento final do baseline frontend + dogfood validation

**Motivação:** pós-fechamento do MVP 15, o diagnóstico binário de OCG (memória `gca_session_23_2026_04_20_21.md` + `gca_cpp_codegen_gap.md`) mostrou que o OCG atual está estruturalmente completo (12 seções com fallback determinístico — agent_service.py:680-737). Os gaps reais são de **propagação + linguagem-awareness**, não de modelagem. Três entregas combinam num MVP de ≈1.5 semanas: (a) suporte fundacional a C++ no codegen (Cluster A do gap — scaffolder CMake + enum backend + test spec), fechando a única linguagem de alto impacto ausente; (b) fix tsc residual do DesignShowcase que está parked desde MVP 14; (c) validação formal de dogfood dos endpoints/servers entregues em MVPs 13-15 mas nunca verificados com produto rodando. Timeline 1-2 semanas com stop-rule dura >2d por fase.

**Não entra no MVP 16 (explícito):**
- **OCG v2 / 15 seções** — rejeitado formalmente em 2026-04-21 após análise do `TASK_MELHORIAS_OCG_REALISTA_v1.1.md`: OCG atual tem 12 seções e está estruturalmente completo; gaps reais são de propagação.
- **Cluster B C++** (CI matrix gcc×clang×msvc, sanitizers, Doxygen) — MVP 17 potencial.
- **Cluster C C++** (packaging CPack, export macros ABI) — MVP 17 ou 18.
- **Cluster D C++** (embedded ARM/ESP32, GPU CUDA/SYCL) — parked indefinidamente até pedido.
- **Auto-trigger de `consolidate_ocg`** pós-eventos canônicos — deferido; hoje é manual via 14.8.
- **APPROVAL_STATUS banner UI** por aba quando BLOCKED — deferido.
- **IaC scaffolder** (Terraform/Helm/k8s manifests) — não planejado.
- **Policy-as-code** (Rego/OPA para COMPLIANCE_CHECKLIST) — não planejado.
- **NoSQL avançado** (Cassandra, DynamoDB no DATA_MODEL) — não planejado.
- **Questionário expandido** para C++ (artifact type, target platforms, package manager) — V1 usa defaults; Q-cpp-* fica para MVP 17.
- **Identity Federation / Data Federation / Federated Learning** — seguem fora.

#### Em escopo

**Fase 16.1 — Scaffolder C++ CMake (≈2-3d)**
- Novo `backend/app/services/scaffolders/cpp_cmake.py` + `cpp_cmake` em `dispatch.py`.
- Emite: `CMakeLists.txt` mínimo (C++17, target executable), `src/main.cpp`, `include/<project>/` vazio pronto, `tests/test_main.cpp` (GoogleTest), `.clang-format`, `.clang-tidy`, `.gitignore`, `Dockerfile` multi-stage (builder + runner), `README.md`.
- Artefato V1: executável apenas (library/header-only ficam para V2).
- Teste: scaffolder roda + projeto gerado compila `cmake -B build && cmake --build build` dentro de container docker em CI.

**Fase 16.2 — Estender `LinguagemBackend` enum + OCG STACK (≈1d)**
- `schemas/questionnaire.py`: adiciona `CPP = "C++"` ao enum `LinguagemBackend`.
- `OCG.STACK_RECOMMENDATION.backend` aceita campo novo `cpp_standard` com default `"17"`.
- `dispatch.py`: branch `if language in ("c++", "cpp", "cplusplus")` → `scaffold_cpp_cmake(spec)`.
- Sem nova pergunta no questionário (V1 usa defaults; Q-cpp-* vira MVP 17).
- Analyzer (agente 0) aceita "C++" no texto livre Q27 "Outra" e normaliza para o enum.

**Fase 16.3 — Test spec generator C++-aware (≈1d)**
- `test_spec_generator_service.py`: quando `backend.language == "c++"`, emite specs em formato `TEST(Suite, Case)` (GoogleTest).
- Cobertura: unit, integration, e2e com idioms canônicos (EXPECT_EQ, EXPECT_THAT, GTEST_SKIP, fixtures com TEST_F).
- `provenance_json` marca `test_framework: "googletest"`.

**Fase 16.4 — DesignShowcasePage tsc fix (≈0.5d)**
- `frontend/src/pages/DesignShowcasePage.tsx:37` — `NodeJS.Timeout` → `ReturnType<typeof setInterval>`.
- Baseline tsc chega a **0 errors** (pela primeira vez desde MVP 14).

**Fase 16.5 — Dogfood validation (≈0.5d)**
- Validação binária sim/não por item contra instância dogfood:
  - Flower `:5555` responde (`curl -fsS http://localhost:5555/` HTTP 200).
  - Celery worker processa task (enfileirar `ping.delay()`, medir tempo até conclusão < 5s).
  - `POST /projects/:id/ocg/rollback/:v` contra DB real retorna 200 + versão incrementada.
  - `POST /projects/:id/ocg/consolidate` contra DB real retorna 200 + `changed` boolean.
  - CI e2e lane executa com sucesso em trigger de PR dummy (ou nota explícita que não foi possível validar).
- Falhas viram DTs novas (não bloqueiam fechamento do MVP 16).
- Registra resultado em `GCA_MVP_PROGRESS.md §3` como DTs ou ✅.

#### Regras duras

- Cada fase exige revalidação §9 antes de passar para a próxima.
- **Stop-rule dura >2d** por fase (exceto 16.4 e 16.5 que são limites já <1d).
- Nenhuma feature nova além do escopo das 5 fases.
- §10 aplicável: zero refactor vizinho, zero melhoria não-solicitada.
- **16.5 é validação binária**, não implementação — falhas vão para backlog.
- Nenhuma fase escreve teste contra DB de produção (§11.3 — usar `gca_test` via `TEST_DATABASE_URL`).
- RBAC imutável (§4) — C++ não introduz papel novo.
- **16.2 é pré-requisito de 16.3** (test spec precisa saber que C++ é linguagem canônica).

#### RBAC preservado (§4.1)

- Nenhuma mudança em papéis canônicos.
- Scaffolder C++ disparado pelo CodeGen existente; RBAC `code:write` já gate (MVP 3).

#### Baseline de entrada (2026-04-21)

- Suite backend: **1506 passing, 5 skipped**.
- Frontend tsc: **1 error residual** (DesignShowcase — alvo da 16.4).
- `any` frontend: 20 (meta ≤20 atingida em 15.4).
- MVP 15 fechado (`0751c0a`).
- Sem blockers/criticals abertos.
- Shadcn `src/components/ui/`: só 4 componentes próprios (15.1 limpo).

---

### MVP 17 — Saneamento operacional Celery (DT-077 + DT-078)

**Motivação:** pós-fechamento do MVP 16 (5/5 fases entregues), restam **2 DTs minor abertas em §3.3** descobertas na Fase 16.5 (dogfood validation): DT-077 (Flower não auto-start após update do docker-compose.yml) e DT-078 (worker healthcheck usa hostname literal causando flag `unhealthy` mesmo com worker respondendo ping em 58ms). Ambas sem impacto funcional, mas fecham o gate §9 em todos os 10 critérios. MVP pequeno (~1h total) para zerar o backlog de DTs.

**Não entra no MVP 17 (explícito):**
- Nenhum item parked em outro MVP ou §10.
- Refactor de docker-compose.yml além dos 2 fixes.
- Migração de healthcheck engine (ex: para script externo).
- Melhoria em Flower (auth, plugins, dashboards custom).

#### Em escopo

**Fase 17.1 — Fix healthcheck hostname (DT-078) (≈30min)**
- `docker-compose.yml` serviço `celery-worker`: substituir `celery -A app.celery_app inspect ping -d celery@gca-celery-worker` por `celery -A app.celery_app inspect ping -d celery@$$HOSTNAME`.
- `$$HOSTNAME` (com `$$` escapando interpolação do compose) resolve no runtime pro hostname real do container (ID curto do docker).
- Validação binária: após `docker compose up -d --force-recreate celery-worker`, container reporta `Up (healthy)` em até 40s (start_period).
- Teste: nenhum — é configuração de infra, validada empiricamente.

**Fase 17.2 — Documentar rotina operacional pós-compose (DT-077) (≈30min)**
- DT-077 não tem bug técnico: `gca-celery-flower` está correto no docker-compose.yml. O problema foi que `docker compose up -d` não foi re-executado após o commit de 14.10. Fix é **documentação operacional**, não código.
- Adicionar em `CLAUDE.md §12` (Convenções técnicas → Backend) uma regra dura:
  - "Toda vez que `docker-compose.yml` muda (serviço novo, porta, env, volume, healthcheck), executar `docker compose up -d` sem argumentos antes de declarar a mudança visível ao user. O up sem flags sincroniza todos os serviços declarados — sem isso, serviços novos ficam declarados mas não rodando."
- Sem mudança de código no GCA core (só CLAUDE.md).

#### Regras duras

- Cada fase exige revalidação §9 antes de passar para a próxima.
- **Stop-rule dura >2d** por fase (ambas são <1h).
- Nenhuma feature nova além dos 2 fixes.
- §10 aplicável: zero refactor vizinho.
- Validação binária: 17.1 ok se healthcheck vira `healthy`; 17.2 ok se `CLAUDE.md §12` cobre a rotina.
- RBAC imutável (§4).

#### Baseline de entrada (2026-04-21)

- Suite backend: **1506 passing, 5 skipped**.
- Frontend tsc: **0 errors** (primeira vez desde MVP 14, entregue em 16.4).
- `any` frontend: 20 (meta).
- DTs abertas: 2 (DT-077 + DT-078 — alvos deste MVP).
- MVP 16 fechado (`3b21758`).
- Sem blockers/criticals.

---

### MVP 18 — Sistema de Ajuda integrado (infraestrutura + conteúdo)

**Motivação:** Admin e GP não têm documentação operacional embutida no produto. `docs/gca_total.md` (criado 2026-04-21) enumera as 31 sub-seções de Admin+GP+infra mas vive fora da UI. Acrônimos (OCG, RBAC, GP, DT, P1-P7, DLQ, DDL, FK, etc) não têm glossário consultável em runtime. User pediu aba "Ajuda" tanto no sidebar Admin quanto no sidebar de projeto com documentação completa navegável + busca full-text + screenshots onde aplicável.

**Escopo autorizado nesta onda:** apenas **Fases 18.1 + 18.2 (infraestrutura)**. Fases 18.3-18.5 (conteúdo + busca + integração final) exigem autorização adicional após review de 18.1+18.2 (§7.0 regra 3).

**Não entra no MVP 18 (explícito):**
- **Screenshots** — requer dogfood piloto + captura manual ou Playwright automação. MVP 19 potencial.
- **Editor inline no Admin** para editar docs sem commit — parked.
- **Versionamento do help** (diff entre versões) — docs vivem no git, suficiente.
- **Tradução pt-BR → EN** — `feedback_portuguese_br` mantém pt-BR canônico.
- **Export PDF do help completo** — parked.
- **Help segmentado por papel** (Dev vs Tester vs QA) — MVP 18 entrega versão única com capítulos gerais; segmentação fica para iteração futura.
- **Chamadas LLM no caminho crítico do help** — proibido; performance + compartimentalização.

#### Em escopo (ONDA 1 — autorizada)

**Fase 18.1 — Rotas + HelpPage skeleton + sidebar item (≈1d)**
- 2 rotas novas: `/admin/help` (guard `RequireAdmin`) e `/projects/:id/help` (guard `ProjectMember` já existente via `ProjectDetailLayout`).
- Componente `HelpPage.tsx` com layout 3 colunas: TOC navegável (esquerda) + conteúdo renderizado (centro) + campo de busca (topo, placeholder em 18.1 sem backend ainda).
- Sidebar Admin ganha entrada "Ajuda" apontando para `/admin/help`.
- `ProjectDetailLayout` nav ganha entrada "Ajuda" apontando para `/projects/:id/help`.
- Skeleton: sem conteúdo real ainda — apenas 10 capítulos stub hardcoded no TOC para validar navegação. Clicar em capítulo exibe `<h1>` do capítulo + "Conteúdo em construção (MVP 18 Fase 18.3)".
- Testes: navegação admin, navegação GP, guard RBAC (outros papéis 403).

**Fase 18.2 — Backend /help endpoints + storage MD (≈1d)**
- 3 endpoints novos em `help_router.py`:
  - `GET /api/v1/help/toc` — retorna `{ chapters: [{ id, title, order, children?: [...] }] }` a partir de `help_content/toc.json`.
  - `GET /api/v1/help/section/{section_id}` — retorna `{ id, title, markdown }` lendo `help_content/{section_id}.md`.
  - `GET /api/v1/help/search?q=...` — **stub em 18.2** retornando lista vazia + header `X-Search-Backend: stub`. Implementação FTS5 vem em 18.4 (fora desta onda).
- Storage canônico: `backend/app/help_content/toc.json` + `backend/app/help_content/*.md`.
- Autorização: os 3 endpoints exigem usuário autenticado (qualquer papel). Conteúdo do help não é segmentado por papel em V1.
- Serviço `help_service.py` abstrai I/O (facilita test + mock).
- Conteúdo inicial V1: TOC com 10 capítulos stub (título + id) e 1 MD de exemplo (`help_content/01-visao-geral.md` com 3 parágrafos placeholder). Conteúdo real vem em 18.3.
- Testes: 8+ unit cobrindo leitura TOC, leitura seção válida/inexistente (404), search stub retornando vazio, autorização, serialização.

#### Fora do escopo desta onda (depende de nova autorização)

- **Fase 18.3** Conteúdo real 10 capítulos (≈2d) — trabalhoso; merece review de tom/estrutura antes.
- **Fase 18.4** Busca full-text SQLite FTS5 (≈1d).
- **Fase 18.5** Renderer markdown frontend + testes e2e + integração final (≈0.5d).

#### Regras duras

- Cada fase exige revalidação §9 antes de passar para a próxima.
- **Stop-rule dura >2d** por fase (especialmente 18.3 que tem inflação natural de texto).
- §10 aplicável: zero refactor vizinho em `HelpTooltip`, `AppLayout`, `ProjectDetailLayout` além do necessário para inserir a entrada no sidebar.
- Conteúdo em **pt-BR obrigatório** (`feedback_portuguese_br`).
- RBAC imutável (§4) — nenhum novo papel.
- Sem chamadas LLM no caminho crítico do help.
- Help não acessa DB de outros projetos além do que o user já tem permissão (compartimentalização §2.2 preservada; conteúdo help é estático).
- Storage do help NÃO é versionado por projeto — é global da instância (docs canônicas do produto).

#### RBAC preservado (§4.1)

- `/admin/help`: `RequireAdmin`.
- `/projects/:id/help`: mesmo guard do `ProjectDetailLayout` (membro ativo aceito do projeto OR admin).
- Endpoints `/api/v1/help/*`: usuário autenticado (qualquer papel); conteúdo idêntico para todos.

#### Baseline de entrada (2026-04-21)

- Suite backend: **1506 passing, 5 skipped**.
- Frontend tsc: **0 errors**.
- `any` frontend: 20.
- DTs abertas: 0 (todas quitadas no MVP 17).
- MVP 17 fechado (`a95a9f2`).
- Gate §9 todos os 10 critérios SIM.

---

### MVP 19 — ERS Vivo (Especificação de Requisitos de Software — IEEE 830 Foundation)

**Motivação:** a Doc Viva do GCA hoje regera documentação descritiva a cada commit do pipeline, mas **não produz um documento de Especificação de Requisitos de Software (ERS / SRS)** no padrão IEEE 830-1998. Os dados necessários para compor o ERS vivo **já existem** dispersos pelas seções do OCG, pelos `module_candidates`, pelos `test_specs`, pela auditoria de CodeGen e pelos `external_repos` — falta consolidá-los num documento estruturado com os 6 elementos essenciais de manutenção que o stakeholder listou: histórico de revisão, matriz de rastreabilidade, glossário, requisitos funcionais/não-funcionais categorizados, protótipos de interface, restrições e regras de negócio. **5 desses 6 elementos cabem neste MVP**; protótipos de interface ficam fora (MVP 20 potencial).

**Emenda 2026-04-21 — ERS como arquivo versionado no repositório do projeto (`docs/ERS.md`):** a proposta original guardava snapshots em tabela `live_doc_revisions` no banco. O stakeholder apontou que **o Git do próprio projeto já resolve versionamento nativamente** com menor custo operacional, maior portabilidade e aderência ao padrão "docs as code". Revisão aceita: ERS passa a ser gerado como `docs/ERS.md` no repositório do projeto, commitado via `git_service` existente. Elimina-se a tabela `live_doc_revisions`; a Fase 19.5 é removida (`git log -p docs/ERS.md` resolve o histórico). Escopo do MVP passa de 5 fases (~7d) para **4 fases (~5-6d)**. Pré-requisito operacional reforçado: o projeto precisa ter repositório Git conectado (já exigência canônica em instalação; o botão "Regenerar ERS" fica desabilitado sem repo).

**Escopo autorizado nesta onda:** 4 fases sequenciais. Execução de cada fase exige autorização adicional explícita (§7.0 regra 3). Estado inicial: **definido — não iniciado**.

**Não entra no MVP 19 (explícito):**
- **Protótipos de Interface** — upload de imagens/links, integração Figma, geração de wireframes. MVP 20 potencial; decisão de escopo pendente.
- **Edição inline do ERS na UI do GCA** — GP editar o documento gerado sem commit. Parked (GP pode editar direto no repo via PR se quiser override manual).
- **Tradução pt-BR → EN** do ERS. Parked.
- **Export PDF automatizado** do ERS. Parked. Nota arquitetural: o formato markdown escolhido **não impede** conversão via Pandoc, WeasyPrint, mdpdf ou print-to-PDF do GitHub — fica como operação opcional do cliente sem necessidade de código novo.
- **Classificação automática** de requisitos funcional/não-funcional via agente — decisão explícita: classificação é manual pelo GP.
- **Materialização de view** da matriz de rastreabilidade. Parked (query sob demanda em V1).
- **Ingestão de ERS existente** como entrada do projeto. Parked.
- **Diff visual entre versões** via UI do GCA além do que o Git já oferece. Parked (`git diff` do repo do projeto resolve).
- **Auto-regeneração** em background disparada por eventos do pipeline. Parked — em V1 o GP clica "Regenerar ERS" quando julga o momento; o sistema só marca como stale.

#### Decisões binárias travadas para esta onda

1. **Classificação de requisitos**: manual pelo GP. Cada `module_candidate` ganha campo `requirement_category ∈ {functional, non_functional, business_rule, null}`; default null; GP marca via UI no `/projects/:id/backlog` ou `/projects/:id/roadmap`. Agentes não classificam automaticamente em V1.
2. **Regras de negócio**: nova seção `BUSINESS_RULES` no OCG (não campo livre em `PROJECT_PROFILE`). Fallback determinístico do Consolidator devolve `[]` quando agente não popula — preserva compatibilidade com OCGs pré-19.
3. **Glossário vivo**: extração automática de termos candidatos a partir de documentos ingeridos + respostas do Arguidor. GP aprova, edita ou descarta antes do termo entrar no ERS. Termos do help global (cap. 1) **não** são duplicados — o ERS referencia o help para acrônimos canônicos do produto, só adiciona termos específicos do projeto.
4. **Matriz de rastreabilidade**: query SQL consolidada sob demanda no momento da geração do ERS. Sem view materializada; sem triggers. Performance aceitável em projetos até ~500 módulos.
5. **Persistência do ERS**: arquivo `docs/ERS.md` no repositório Git do projeto, commitado via `git_service`. **Sem tabela** `live_doc_revisions`. Histórico = `git log -p docs/ERS.md`. Portabilidade total; ERS viaja junto do projeto.
6. **Regeneração é manual**: sistema detecta stale automaticamente (via eventos do pipeline), mostra badge no GCA, mas **não regenera sozinho**. GP clica "Regenerar ERS" quando faz sentido. Razões: evitar commits ruidosos, preservar governança do GP, prevenir conflitos desnecessários no Git.

#### Eventos que marcam o ERS como stale

O GCA monitora e sinaliza (sem regenerar):

| Evento | Seções impactadas | Motivo exibido |
|---|---|---|
| `OCG_UPDATED` (ingestão, Arguidor) | 1.1-1.2, 2.x, 3.1-3.2, 3.4 | "OCG mudou (versão N → N+1)" |
| `OCG_ROLLED_BACK` | Todas | "OCG revertido para versão N" |
| `OCG_CONSOLIDATED` | 3.2, 2.1 | "Scores consolidados" |
| Novo `module_candidate` criado ou categorizado | 3.1–3.3 conforme `requirement_category` | "Requisito novo/alterado" |
| `test_spec` aprovado/rejeitado | 4 | "Testes atualizados" |
| `CODEGEN_SCAFFOLD_APPLIED` / `CODEGEN_FILE_REGENERATED` | 4 | "Código gerado" |
| Termo de glossário aprovado/rejeitado | 1.3 | "Glossário atualizado" |
| `BUSINESS_RULES` editado pelo GP | 3.3 | "Regras de negócio editadas" |
| External repo adicionado/removido | 2.5, 3.4 | "Integrações externas atualizadas" |

Implementação canônica: serviço `ers_freshness_tracker` mantém, por projeto, `{ is_stale, stale_since, stale_reasons[], last_commit_sha }`. Banner aparece em `/projects/:id/docs` quando stale.

#### Em escopo — 4 fases sequenciais

**Fase 19.1 — Schema expansion (≈1d)**
- Migration: adiciona `requirement_category VARCHAR(20) NULL` em `module_candidates`. Whitelist aplicação-level: `{functional, non_functional, business_rule, null}`.
- Schema `OCGResponse` ganha seção opcional `BUSINESS_RULES: list[dict]` (default `[]`). Fallback em `agent_service.consolidate_ocg` preserva comportamento pré-19 (LLM não é obrigado a popular).
- **Não cria `live_doc_revisions`** (emenda 2026-04-21 removeu).
- Testes: migration idempotente, whitelist respeitada, OCG sem BUSINESS_RULES continua serializando com default `[]`.

**Fase 19.2 — Generator IEEE 830 + commit no Git do projeto (≈2d)**
- Novo `ers_doc_generator_service.py`. Função canônica: `generate_and_commit_ers(project_id, actor_id) -> { commit_sha, path: 'docs/ERS.md' }`.
- Consome: `OCG` (12 seções), `module_candidates` filtrados por `requirement_category`, `external_repos`, glossário aprovado (quando Fase 19.3 estiver entregue; placeholder antes), matriz de rastreabilidade (idem, Fase 19.4).
- **Escreve `docs/ERS.md`** no repositório do projeto via `git_service.commit_files` existente.
- Mensagem de commit canônica: `docs(ers): regen a partir do OCG v{N} — {summary-stale-reasons}`.
- Emite audit `LIVEDOCS_UPDATED` com `details={ doc_type: 'ers', commit_sha, version_from, version_to, stale_reasons }`.
- Em 19.2 isolado: seções 1.3 (glossário) e 4 (matriz) saem com placeholder "A ser populado na próxima fase" (garante que 19.2 compila mesmo antes de 19.3 e 19.4).
- Novo botão "Regenerar ERS" em `/projects/:id/docs` — desabilitado quando projeto não tem repo Git conectado, com mensagem explicativa.
- Serviço `ers_freshness_tracker` (trigger de stale) implementado junto.
- Testes: `generate_and_commit_ers` produz markdown IEEE 830 bem-formado; OCG vazio produz ERS com placeholders em vez de erro; projeto sem repo retorna erro explícito; freshness tracker marca stale nos 9 eventos canônicos; commit é criado no repo do projeto (teste integra com `git_service` via mock + repo de teste real no container).

**Fase 19.3 — Glossário vivo por projeto (≈2d)**
- Nova entidade `project_glossary_terms` (id, project_id, term, definition, source ∈ {ingested_doc, arguider_response, manual}, status ∈ {candidate, approved, rejected}, created_at, approved_by, approved_at).
- Serviço de extração: detecta termos candidatos a partir do corpus do projeto (documentos ingeridos extraídos + `arguider_responses`). Heurísticas simples: siglas em maiúsculas (ex: SRS, ERP, OMS), termos entre aspas/negrito, definições explícitas (padrão "X é Y", "X significa Y").
- UI: aba "Glossário" em `/projects/:id/docs`. Lista termos candidatos + aprovados + rejeitados. Botões aprovar/rejeitar/editar.
- Integração com 19.2: seção 1.3 do `ERS.md` gerado lista termos aprovados + referência ao help global para acrônimos canônicos.
- Testes: extração idempotente, aprovação muda status + grava audit, termos rejeitados não vão ao ERS, ERS regerado inclui termos aprovados na seção 1.3.

**Fase 19.4 — Matriz de rastreabilidade (≈1,5d)**
- Novo endpoint `GET /api/v1/projects/:id/traceability` — retorna JSON com cada `module_candidate` e lista de `test_specs` + arquivos/commits associados do `CodeGenAudit`.
- Query SQL sob demanda: `LEFT JOIN module_candidates → test_specs (via test_spec.module_id quando disponível) → audit_log_global (via resource_id=project_id + event_type=codegen_scaffold_applied/regenerated)`.
- UI: nova aba "Rastreabilidade" em `/projects/:id/qa` ou `/projects/:id/audit`. Tabela com módulos × testes × arquivos + filtros por categoria de requisito.
- Integração com 19.2: seção 4 do `ERS.md` embute versão markdown da matriz ao regenerar.
- Testes: projeto vazio retorna matriz vazia sem erro; módulo sem teste → "sem teste associado"; módulo sem commit → "sem código gerado"; performance ≤500ms para até 200 módulos.

#### Regras duras

- Cada fase exige revalidação §9 antes de passar para a próxima.
- **Stop-rule dura >2d** por fase.
- §10 aplicável: zero refactor vizinho em `LiveDocsPage.tsx`, `Doc Viva` generator atual, schema do OCG além da seção BUSINESS_RULES nova, `module_candidates` além do campo novo.
- Conteúdo do ERS em **pt-BR** (`feedback_portuguese_br`).
- RBAC imutável (§4). Classificação de requisito: Admin + GP. Aprovação de glossário: Admin + GP. Regenerar ERS: Admin + GP.
- Sem LLM no caminho crítico do generator ERS — consolidação determinística de dados já gerados pelo pipeline.
- Compartimentalização §2.2 preservada: ERS de projeto A só consome dados de A e só é commitado no repo de A; glossário de A não vaza pra B.
- 19.1 é pré-requisito de 19.2 (schema novo precisa existir antes do generator consumir).
- 19.3 e 19.4 são pré-requisitos da **versão completa** do ERS — sem elas, 19.2 gera ERS com placeholders nas seções 1.3 e 4.
- **Pré-requisito operacional**: projeto com repositório Git conectado. Sem repo, o botão "Regenerar ERS" fica desabilitado com mensagem apontando para `/projects/:id/settings` → aba Repositório Git.

#### RBAC preservado (§4.1)

- `GET /traceability`, `GET /glossary`: membro aceito do projeto OR Admin.
- `POST /generate-ers`, `POST /glossary/:termId/approve`, `PATCH /module_candidates/:id/category`, `PUT /ocg/business-rules`: GP do projeto OR Admin.
- Endpoints novos não introduzem papel nem permissão nova — só reaproveitam guards existentes.

#### Baseline de entrada (2026-04-21)

- Suite backend: **1617 passing, 5 skipped**.
- Frontend tsc: **0 errors**.
- `any` frontend: 20.
- DTs abertas: 0.
- MVP 18 fechado (`5790617`).

---

### MVP 23 — RNF_CONTRACTS no OCG + CodeGen contract-aware

**Motivação:** hoje P2 (compliance), P4 (performance) e P7 (segurança) ficam no OCG como texto livre e achados de pilar — o CodeGen lê o OCG mas **não tem contratos estruturados** que obrigatoriamente entram no prompt e na validação. Resultado: RNFs viram tickets separados ("adicione rate limit", "parametrize query") em vez de sair no código gerado de primeira.

**Tese:** RNFs estruturados como contrato no OCG → consumidos no prompt de codegen → validados estaticamente pós-geração → testados via test specs. Fecha o elo `requisito não-funcional → código que atende`.

**Escopo autorizado:** 6 fases sequenciais (~6-7d nominais, ~4-5d com pair programming). Execução em bloco autorizada com abertura (padrão MVP 17/22).

**6 decisões binárias travadas:**

1. `RNF_CONTRACTS` é **seção nova do OCG**, não campo livre em `STACK_RECOMMENDATION`.
2. Todos os campos aceitam **null** — OCGs pré-23 seguem funcionando (fallback determinístico).
3. Validação pós-geração é **estática em V1** (grep estruturado por middleware/decorator presente). Validação semântica via LLM fica em MVP futuro.
4. `enforcement: "runtime"|"static"|"both"` é metadata canônica — determina se vira middleware em runtime ou check de lint/SAST.
5. Arguidor **só pergunta RNF quando faltar**; GP pode preencher direto via endpoint PUT sem passar pelo Arguidor.
6. UI rica (aba "Contratos RNF") fica pra Fase 23.5; V1 funcional até lá via endpoint PUT + JSON editável.

**Não entra no MVP 23 (explícito):**
- ❌ Validação semântica via LLM ("este código realmente mitiga CWE-89?") → MVP 25+
- ❌ Geração de perfis de carga (Locust, k6) → sob demanda
- ❌ Integração com APM (Datadog, New Relic, Sentry) → MVP 26+
- ❌ Reescrita retroativa de módulos existentes → só aplica a novos ou regenerados

**6 fases canônicas:**

**Fase 23.1 — Schema `RNF_CONTRACTS` no OCG + migration** (~1d)
- Nova sub-seção em `OCGResponse` com 4 blocos: `performance`, `security`, `compliance`, `availability`.
- Default `{}`; fallback zero-impact em OCGs antigos.
- Migration (se schema SQL precisar coluna dedicada) OU apenas campo JSON do `OCGResponse` (preferível — segue padrão BUSINESS_RULES).
- Testes: schema aceita None, dict vazio, dict parcial, dict completo; OCG pré-23 desserializa sem quebra.

**Fase 23.2 — Arguidor dirigido** (~1d)
- Template canônico de perguntas dispara quando `RNF_CONTRACTS` vazio + módulo crítico em fila.
- Perguntas canônicas: SLA latência P95, rate limits público/autenticado, CWEs obrigatórios, regulações (LGPD/GDPR), disponibilidade.
- Resposta alimenta `RNF_CONTRACTS` via `ocg_updater`.

**Fase 23.3 — `codegen_prompt_builder` consome RNF** (~1.5d)
- Prompt de codegen injeta bloco estruturado: *"este módulo DEVE atender latency_p95 ≤ X, rate_limit Y, CWE-89 via ORM, CWE-798 via vault"*.
- Stack-aware: Python/FastAPI → `slowapi`; Node/Express → `express-rate-limit`; Java/Spring → `@RateLimiter(name)`.
- Docstring do código gerado documenta qual contrato RNF está atendendo (rastreabilidade inline).

**Fase 23.4 — Test spec + validação estática** (~1.5d)
- `test_spec_generator` inclui cenários RNF: asserções de latency, testes de rate limit (expected 429), regressão de segurança por CWE declarado.
- `code_validation_service` novo check: grep estruturado verifica middleware/decorator declarado no contrato está presente.
- Falha → status `rnf_contract_violation` no `CodeGenAudit`.

**Fase 23.5 — UI GP edita `RNF_CONTRACTS`** (~1d)
- Aba "Contratos RNF" em `/projects/:id/ocg` (ou painel novo no backlog).
- JSON schema validado via Pydantic; GP edita, salva, sistema re-trigger codegen dos módulos afetados.

**Fase 23.6 — Dogfood + Ajuda + release** (~0.5d)
- Smoke live em projeto dogfood.
- Novo capítulo na Ajuda (provável cap 13) ou expansão em cap 05 OCG documentando RNF_CONTRACTS.
- `toc.json` versão 23.0 (pula 22 por consistência com numeração de MVP).

**Regras duras:**
- Stop-rule >1.5d por fase.
- §10 aplicável: zero refactor vizinho em `ocg_service`, `codegen_service`, `arguider_service` além dos pontos de extensão necessários.
- Sem LLM no caminho crítico da validação estática (grep determinístico).
- Compartimentalização §2.2 preservada.
- RBAC imutável: escrita em `RNF_CONTRACTS` exige GP + Admin; leitura é membro aceito.
- Rastreabilidade: toda alteração em `RNF_CONTRACTS` emite `OCG_UPDATED` canônico.

**Baseline de entrada (pós-MVP 22, pós-reforma documental):** 245+ backend passing, tsc frontend = 0, DTs abertas = 0, MVP 22 fechado (`f3ab38b`), docs reformados (`544f00a`).

---

### MVP 22 — Teams Notifier uni-direcional (extensão do NotifierPort)

**Motivação:** cliente mid-market pedindo Microsoft Teams agora. Padrão Adapter-Port canônico (MVP 20) já absorvia outros notifiers — extensão natural é adicionar `TeamsAdapter` implementando o mesmo `NotifierPort` existente.

**Escopo autorizado:** fase única (pequena). Execução autorizada em bloco com abertura.

**Não entra no MVP 22 (explícito):**
- Interatividade bi-direcional (ChatOps): aprovar módulo via botão no Teams → MVP 24 potencial, pré-requisito SSO.
- Bot Framework registrado no Azure AD com identidade própria: V1 usa Incoming Webhook (caminho pragmático).
- Parsing de respostas ou comandos `@gca` no Teams — MVP 24.
- Adaptive Card Extensions, Teams Tabs, integração profunda com Teams apps.

**Decisões binárias:**
1. Incoming Webhook via Power Automate Workflow (substituto canônico do Office 365 Connector deprecated em Dez/2024) OR Connector legado — adapter aceita ambos; cliente escolhe.
2. Adaptive Card v1.4 (TextBlock + FactSet + Action.OpenUrl) — idioma canônico do Teams moderno.
3. Mapeamento severity → Adaptive Card color: info=default, success=good, warning=warning, danger=attention.
4. Modo `link_only_mode` degrada pra card minimalista sem FactSet (mesma política do Slack).

**Fase única — TeamsAdapter (~3-5d com pair programming)**
- `backend/app/services/adapters/teams_adapter.py` implementando `NotifierPort`.
- `register_builtin_notifiers` inclui `TeamsAdapter`.
- `_REQUIRED_CREDENTIALS` do `notifier_service` aceita `teams: ('webhook_url',)`.
- 10+ testes unit com `httpx.MockTransport` cobrindo: sem webhook, evento fora de opt-in, sucesso 200 (Workflow) e 202 (legacy), body Adaptive Card canônico, link-only sem actions, link-only não vaza fields, 429/5xx retryable, 4xx non-retryable, timeout retryable, severity→color mapping.
- Dogfood pelo endpoint de config existente (PUT `/integrations/issue-tracker/credentials/...` aceita o secret_type de notifier_credentials com a mesma plumbing).

**Regras duras:**
- Zero novo endpoint. Zero migração. Zero mudança em porta.
- Stop-rule >1d (é extensão trivial; se ficar difícil algum teste, stop).
- Preservar todo o contrato do `NotifierPort` MVP 20.3 sem mudanças.

**Baseline de entrada:** 245 passing + 38 help + MVP 21 commits. tsc=0. MVP 21 fechado (`dd10bc8`).

---

### MVP 21 — Ajuda refresh (sincroniza conteúdo com MVPs 14-20)

**Motivação:** MVP 18 entregou a infraestrutura de Ajuda (capítulos + FTS5 + renderer) em 2026-04-21. Desde então MVP 19 (ERS Vivo IEEE 830 + glossário + matriz) e MVP 20 (3 integrações externas + hooks + P7 determinístico) entregaram features visíveis ao GP que **não aparecem** na Ajuda. Stakeholder sinalizou: conteúdo desatualizado é produto desatualizado; comprador percebe e perde confiança.

**Escopo autorizado:** 3 fases sequenciais em conteúdo (zero código novo). Execução de cada fase exige revalidação.

**Não entra no MVP 21 (explícito):**
- Vídeos / capturas animadas — requer gravação manual
- Tradução EN — parked desde MVP 18
- Casos por vertical (fintech, legaltech, healthtech) — MVP 22 potencial
- Editor inline de Ajuda — parked
- Novos capítulos temáticos além do refresh dos existentes

#### Decisões binárias travadas

1. Screenshots reaproveitados do `docs/screenshots/` existente (7 imagens já capturadas no MVP 20). **Sem** novas capturas.
2. Sem mudança estrutural do `toc.json` além do bump de versão (v20.4 → v21.0). Ordem dos capítulos preservada.
3. Alteração em `test_mvp18_fase182_help.py` permitida apenas em assertions que não refletem mais o conteúdo (count de chapters já ajustado na 20.4; só linha de "primeiro chapter id" pode aparecer se a UI mudar ordem).
4. Capítulo 11 (Integrações) **não** sofre refresh — foi entregue novo na 20.4 e está atualizado.

#### Em escopo — 3 fases sequenciais

**Fase 21.1 — Saneamento de capítulos técnicos (~3-4h)**
- `01-visao-geral.md`: adiciona glossário de termos do MVP 19+20 (OCG delta, BUSINESS_RULES, requirement_category, ExternalIssue, SecurityFinding, IssueTrackerPort, SecurityScannerPort, NotifierPort, matriz de rastreabilidade, glossário vivo).
- `04-pipeline.md`: documenta hooks canônicos de eventos (MODULE_APPROVED → Slack; ERS_REGENERATED; SECURITY_FINDING_HIGH) e fluxo "approve → issue Jira → status sync webhook".
- `05-ocg.md`: adiciona seção `BUSINESS_RULES`; documenta `requirement_category` em module_candidates (whitelist functional/non_functional/business_rule); documenta fórmula determinística de P7 quando scanner configurado.
- `08-codegen.md`: confirma 8 linguagens canônicas (Python, Node Express, Node NestJS, Java Spring, Java Quarkus, Kotlin Spring, C# ASP.NET, Go, PHP Laravel, C++ CMake) com matriz de scaffolder.
- `09-observabilidade.md`: adiciona eventos canônicos novos de audit: EXTERNAL_ISSUE_CREATED, EXTERNAL_ISSUE_STATUS_SYNCED, LIVEDOCS_UPDATED (doc_type=ers), OCG_ROLLED_BACK, OCG_CONSOLIDATED.
- `10-troubleshooting.md`: adiciona 4-5 entradas: ERS sem repo conectado, webhook signature inválida, credencial de integração faltando no vault, P7 não recalcula (scanner não configurado), Slack notification não chegou (opted_in_events/link_only).

**Fase 21.2 — Capítulo 07 (GP) expandido (~3-4h)**
- Nova sub-seção "Documentação Viva" dentro do 07 documentando 3 abas: LiveDocs, ERS Vivo, Glossário do Projeto, Rastreabilidade.
- Nova sub-seção "Integrações" dentro do 07 apontando pro capítulo 11 + quando usar.
- Nova sub-seção "Métricas" (custo de IA) + "Backups" (automático diário + manual + rollback) — reaproveitando as imagens do `docs/screenshots/metricas.png` e `backup.png`.
- Pequeno update na sub-seção "Aprovação de módulo" citando que integração de tracker cria issue automaticamente quando configurada.

**Fase 21.3 — Screenshots + release + smoke (~2-3h)**
- Referências `![](/images/help/X.png)` nos capítulos relevantes usando os 7 screenshots já em `docs/screenshots/`.
- `toc.json` versão → "21.0".
- Smoke live em `/help` (admin e projeto) confirmando que capítulos renderizam e busca encontra termos novos (ex: "BUSINESS_RULES", "P7 findings", "issue tracker").
- Release note no `GCA_MVP_PROGRESS.md`.

#### Regras duras

- Zero código novo — apenas conteúdo markdown + `toc.json` + ajustes de testes de help.
- Stop-rule >1d por fase.
- §10 aplicável: nenhuma refatoração de `help_service.py`, `help_router.py` ou renderer frontend.
- Sem LLM no caminho crítico — conteúdo escrito deterministicamente a partir do contrato canônico + código existente.
- RBAC imutável.
- Busca FTS5 deve continuar encontrando termos canônicos novos após rebuild automático por mtime (MVP 18 Fase 18.4 — sem ação extra).

#### Baseline de entrada

- Suite backend: **245 passing** (68 MVP 19 + 157 MVP 20 + 20 MVP 18).
- Frontend tsc: 0 errors.
- DTs abertas: 0.
- MVP 20 fechado (`494db2f`).

---

### MVP 20 — Integrações externas do ecossistema corporativo (Issue Tracker + Security Scanners + Slack Notifier)

**Motivação:** hoje o GCA é uma ilha em relação ao ecossistema corporativo do cliente. Três dores concretas bloqueiam adoção em mid-market e enterprise:

1. **Backlog do GCA ↔ ticket oficial (Jira/Trello) desincronizado** — PMs e devs perguntam "onde aparece isso no meu Jira?" e a resposta hoje é "não aparece". Reintroduzir manualmente cada módulo aprovado do GCA como ticket no tracker é atrito recorrente; divergência entre os dois estados é inevitável.
2. **Segurança do cliente já roda em Sonar / Snyk / GitHub Advanced Security / gitleaks** — o CISO exige relatório de segurança com rastreabilidade. Hoje o P7 do OCG é avaliado por LLM sobre texto, não por findings reais da ferramenta que o cliente já paga. Reimplementar SAST internamente seria concorrer com ferramentas commodity maduras — caminho errado. **Adapters que consomem findings existentes e mapeiam para P7** preservam o moat do GCA (governança) sem competir com o que o cliente já tem.
3. **Visibilidade distribuída** — eventos importantes do pipeline (módulo aprovado, OCG consolidado, CodeGen completo, ERS regenerado, finding HIGH) ficam presos na UI do GCA. Time híbrido/remoto perde o ritmo e não desenvolve hábito diário com o produto.

Os três temas compartilham a mesma tese arquitetural — **"GCA como hub que consome ferramentas externas via adapter pattern, não como produto que reimplementa cada uma"** — e a mesma plumbing (porta canônica + múltiplos adapters + `ProjectSecret` vault + config UI por projeto). Por isso cabem num único MVP coeso, mesmo cobrindo três tipos de integração distintos.

**Escopo autorizado nesta onda:** 4 fases sequenciais. Execução de cada fase exige autorização adicional explícita (§7.0 regra 3). Estado inicial: **definido — não iniciado**.

**Não entra no MVP 20 (explícito):**
- **ChatOps bi-direcional** (aprovar/rejeitar módulos via botões no Slack/Teams) — MVP 23 potencial, após SSO canônico pronto e primeiro cliente externo validar o uso uni-direcional.
- **Microsoft Teams notifier** — MVP 23 potencial. Teams Bot Framework custa ~2x o Slack; justificado quando cliente específico exigir.
- **Linear, Asana, GitHub Issues, Monday, ClickUp** — adapters sob demanda (~1.5-2d cada), disparados por pedido explícito de cliente pagante.
- **Reimplementação de SAST interno** — rejeitado por design. GCA consome, não reimplementa.
- **Custom Semgrep rules GCA-específicas** — parked até haver corpus de findings real em dogfood.
- **DAST** (OWASP ZAP, runtime scan em staging) — parked. Depende de ambiente staging disciplinado; volta no roadmap após 3 clientes em produção.
- **Dependabot/Renovate integration além do OSV-Scanner** — parked.
- **Figma MCP** — MVP 22 potencial (tema distinto: entrada UX/UI, não integração corporativa genérica).
- **Onboarding polish / expansão de Ajuda** — MVP 22 potencial (tema distinto).
- **SSO corporativo (LDAP/SAML/OIDC)** — pré-requisito do ChatOps, mas entra em MVP próprio futuro.

#### Decisões binárias travadas para esta onda

1. **Config é por projeto, não instância-wide.** Cada projeto escolhe seu tracker, seus scanners e seu canal Slack. Compartimentalização §2.2 preservada.
2. **Status mapping é configurável por projeto.** Cliente Jira com workflow customizado mapeia seu estado ("Em análise pelo jurídico" → canonical `review`) via UI do `/settings` — GCA não força naming.
3. **Security adapters consomem, não reimplementam.** `SonarAdapter` chama SonarCloud/SonarQube API, `SnykAdapter` chama Snyk API, `GitleaksAdapter` roda gitleaks local ou consome findings já gerados pelo cliente. GCA nunca gera finding próprio em V1.
4. **Slack é uni-direcional em V1.** Mensagens vão, reações/comandos não voltam. Bi-direcional (ChatOps) é MVP 23 separado por mudar perfil de segurança do produto.
5. **Webhooks recebidos pelo GCA exigem signing secret + idempotência por `message_id`.** Zero endpoint público sem validação de assinatura. Replay prevention por nonce/timestamp obrigatória.
6. **Modo "link-only" disponível por projeto.** Cliente regulado (BACEN, ANS, órgãos públicos) que não aceita payload do projeto trafegando por Slack configura modo onde a mensagem só diz "evento X no módulo Y, clique para ver" sem conteúdo sensível. Default é payload rico.
7. **P7 do OCG passa a consumir `security_findings` reais quando existirem.** Quando o projeto não tem scanner configurado, P7 mantém heurística LLM atual (comportamento pré-20 preservado). Quando scanner configurado e findings existem, P7 recalcula com base em `count(HIGH) / count(MEDIUM) / count(LOW)` ponderado — regra binária publicada no release notes.
8. **Primeira resposta de reação vale.** Não se aplica a V1 (uni-direcional), mas fica documentada como regra pro futuro ChatOps: 3 GPs reagem no canal → primeira vale, demais viram comentário.

#### Em escopo — 4 fases sequenciais

**Fase 20.1 — Issue Tracker Bridge (porta canônica + Jira + Trello) (~4-5d)**
- Porta canônica `IssueTrackerPort` com operações mínimas: `create_issue(module_candidate_id) → external_id`, `update_status(external_id, canonical_status)`, `link_commit(external_id, commit_sha)`, `add_comment(external_id, markdown)`, `webhook_handler(payload) → IssueEvent`.
- Modelo `ExternalIssue` + migration 035: `(id, project_id, module_candidate_id, provider ∈ {jira, trello}, external_id, status_canonical ∈ {todo, in_progress, review, done}, url, synced_at, provider_specific jsonb)`.
- `JiraAdapter` completo: auth (API token + email, OAuth2 deixado pra fase futura), CRUD issue, webhook signed, status mapping configurável por projeto, escape de pipe/markdown na descrição.
- `TrelloAdapter` minimalista: cards em lista canônica, movimentação entre listas como status, labels para priority, webhook com validação HMAC.
- UI: painel de config em `/projects/:id/settings` → nova aba "Issue Tracker", seguindo padrão visual dos Provedores de IA (imagem #7 do carrossel LinkedIn). Campos: provider, credencial (via `ProjectSecret` vault), status mapping JSON editável, canal default.
- Integração com backlog: quando módulo aprovado pelo GP (`ModuleCandidate.status = 'aprovado'`), dispara `IssueTrackerPort.create_issue` se config existir. Status `completed` do `GeneratedModule` → `done` no tracker. Webhook de volta do tracker sincroniza status canonical.
- Audit: cada criação/sync vira `GlobalAuditLog` com `event_type ∈ {EXTERNAL_ISSUE_CREATED, EXTERNAL_ISSUE_STATUS_SYNCED}` + `details.external_id` + `details.provider`.
- Testes: porta absorve Jira-isms (Trello força a abstração correta); status mapping configurável por projeto funciona; webhook duplicado é idempotente; auth inválido retorna erro claro; compartimentalização — issue do projeto A nunca aparece em Jira do projeto B.

**Fase 20.2 — Security Adapters (Sonar + Snyk + gitleaks) (~1.5-2d)**
- Porta canônica `SecurityScannerPort` com operações: `fetch_findings(project_config) → list[SecurityFinding]`, `normalize_severity(raw) → {HIGH, MEDIUM, LOW, INFO}`.
- Modelo `SecurityFinding` + migration 036: `(id, project_id, source_scanner ∈ {sonar, snyk, gitleaks}, external_id, file_path, line_start, line_end, rule_id, cwe_id, severity, title, description, status ∈ {open, fixed, accepted_risk}, accepted_risk_justification, first_seen_at, last_seen_at)`.
- `SonarAdapter`: consome SonarCloud Web API (`/api/issues/search`) ou SonarQube on-prem. Credencial via `ProjectSecret`. Normaliza severidade Sonar (BLOCKER/CRITICAL/MAJOR/MINOR/INFO) para canonical.
- `SnykAdapter`: consome Snyk REST API (`/orgs/:id/projects/:pid/issues`). Normaliza severidade Snyk (critical/high/medium/low).
- `GitleaksAdapter`: duas modalidades — (a) roda `gitleaks detect --report-format json` no repo do projeto durante CodeGen; (b) consome relatório já gerado pelo CI do cliente.
- UI: `SecurityFindingsPanel` no `/projects/:id/docs` (aba Security) ou integrado no `/projects/:id/gatekeeper`. Agrupa por severidade; botão "Marcar como risco aceito" com modal de justificativa obrigatória.
- Recálculo de P7 do OCG: serviço `p7_updater` lê `security_findings` com `status='open'`, aplica fórmula canônica (`score = 100 - 20*count_HIGH - 5*count_MEDIUM - 1*count_LOW, clamp 0..100`), atualiza pilar P7 via pipeline normal de OCG update (preserva delta-log).
- Quando findings HIGH existem e P7 < 70, regra canônica §7 pilares-1 entra em ação (OCG status → BLOCKED).
- Testes: Sonar mock retorna findings, adapter normaliza, P7 recalcula; fórmula clamp respeitada; accepted_risk não conta pra score; gitleaks no repo dummy detecta secret fake; compartimentalização — findings do projeto A nunca aparecem no dashboard do B.

**Fase 20.3 — Slack Notifier uni-direcional (~1-1.5d)**
- Porta canônica `NotifierPort` com operação única: `send(event_type, payload, project_config) → delivery_id`.
- `SlackAdapter` via Incoming Webhook URL (simples; OAuth fica pra V2).
- Eventos canônicos disparadores: `MODULE_APPROVED`, `OCG_CONSOLIDATED`, `CODEGEN_COMPLETED`, `ERS_REGENERATED`, `SECURITY_FINDING_HIGH` (novo, disparado pela 20.2), `BACKUP_FAILED`.
- Config por projeto: canal destino + set de events opt-in (default = todos).
- Formatação: Block Kit com header + campos estruturados + botão link profundo pra tela do GCA.
- **Modo "link-only"** por config: quando ativo, mensagem só diz "evento X, ver detalhes em <link>" sem payload sensível. Para cliente regulado.
- Fallback: se Slack retorna erro ou timeout, evento vai pra `user_notifications` (tabela já existente) com flag `delivery_failed`, retry via Celery em 1min / 5min / 15min com backoff.
- Testes: cada evento dispara adapter; modo link-only não vaza payload; retry funciona; compartimentalização — evento do projeto A nunca cai em canal configurado no B.

**Fase 20.4 — Dogfood + release notes + atualização da Ajuda (~0.5-1d)**
- Smoke live em projeto dogfood do próprio GCA: criar módulo, aprovar, ver issue aparecer no Jira (sandbox); subir finding manual em Sonar dummy, ver P7 atualizar; regenerar ERS, ver mensagem chegar no Slack.
- Atualizar `backend/app/help_content/` com novo capítulo **"Integrações Externas"** cobrindo: como conectar Jira, como conectar Trello, como conectar Sonar, como conectar Snyk, como configurar Slack notifier, como usar modo link-only. Screenshots reais do dogfood (conforme `docs/screenshots/` pattern).
- Atualizar slide 15 do `GCA_LinkedIn_Landscape.pptx` marcando Jira/Trello/Sonar/Snyk/Slack como ✅ (saem de "AMANHÃ" pra "HOJE").
- Suite de testes total deve permanecer ≥1617 passing; tsc frontend = 0; zero DTs abertas no fim do MVP.

#### Regras duras

- Cada fase exige revalidação §9 antes de passar para a próxima.
- **Stop-rule dura >2d** por fase.
- §10 aplicável: **zero refactor** em Gatekeeper, OCG updater, backlog service, CodeGen dispatch além dos pontos de extensão estritamente necessários para as 3 integrações. Nenhuma feature antecipada de MVP futuro.
- Conteúdo pt-BR (`feedback_portuguese_br`).
- RBAC imutável (§4). Config de integração: Admin + GP. Aceitar risco de segurança: GP + Admin (dupla assinatura canônica).
- **Sem LLM no caminho crítico** das 3 integrações — adapter pattern determinístico. LLM não decide quando criar issue, não decide severidade de finding, não formata mensagem Slack (template fixo).
- Compartimentalização §2.2 preservada: config de um projeto nunca vaza para outro; webhook recebido sem `project_id` resolvível é rejeitado; canal Slack que recebe evento do projeto A nunca recebe evento do projeto B sem config explícita.
- 20.1 é pré-requisito de 20.2 apenas para reuso do padrão de adapter; 20.2 e 20.3 são independentes entre si tecnicamente, mas a ordem de entrega é fixa para preservar revisão incremental.
- **ChatOps bi-direcional (Slack/Teams) é explicitamente fora de escopo** — qualquer "só uma reaçãozinha" durante a Fase 20.3 é inflação que requer autorização nova.

#### RBAC preservado (§4.1)

- `POST /projects/:id/integrations/{issue-tracker|security|notifier}`: GP do projeto OR Admin.
- `GET /projects/:id/external-issues`, `GET /projects/:id/security/findings`: membro aceito do projeto OR Admin.
- `PATCH /security/findings/:id/accept-risk`: GP + Admin dupla assinatura (implementação via 2-phase commit no backend; UI já orientada para isso).
- Endpoints de webhook (recebidos): públicos com signing secret obrigatório; resolvem `project_id` do payload + valida HMAC antes de qualquer escrita.

#### Baseline de entrada (2026-04-21)

- Suite backend: **1617 passing, 5 skipped** + 68 testes MVP 19 (1685 total).
- Frontend tsc: **0 errors**.
- `any` frontend: 20.
- DTs abertas: 0.
- MVP 19 fechado (`01c03ff`).

---

## 9. Regras duras de implementação

- Não antecipar feature de MVP futuro.
- Não expandir RBAC além de 5 papéis.
- Não promover documento histórico a contrato de implementação.
- Não reescrever arquitetura inteira quando correção cirúrgica resolver.
- Não hardcodar um único provedor de IA no produto.
- Não assumir que todo fluxo precisa usar a mesma IA.
- Não permitir que modelo barato/local tome decisão oficial crítica sozinho.
- Não avançar para o próximo MVP enquanto o gate da fase atual estiver fechado.

### MVP 26 — AI Governance Moat: Rastreabilidade LLM + Detecção de Prompt Injection + Validação Semântica de Código

**Data de abertura:** 2026-04-28  
**Duração estimada:** 6-8 dias úteis (4 fases, ~2d cada)  
**Pré-requisitos:** MVP 29 fechado (Celery idempotente para audit confiável)

#### Em escopo

1. **Fase 26.1 — Rastreabilidade de Decisão LLM (~2d)**
   - Estender `AIUsageLog` com campos novos: `temperature NUMERIC(4,2)`, `prompt_version VARCHAR(255)`, `decision_type` ∈ {ARGUIDER_ANALYSIS, CODEGEN_GENERATION, OCG_CONSOLIDATION, ERS_GENERATION}. (Campos `input_hash`/`output_hash` já existem em `OCGAnalysisLog`; Arguider usa mesmo padrão.)
   - Audit automático em `arguider_service.py` quando LLM é chamado: registra qual modelo, temperatura, versão de prompt via nova entrada em `AIUsageLog`.
   - Audit em `code_generation.py` quando CodeGen executa: registra qual modelo/provider, qual linguagem, quantos módulos gerados em `AIUsageLog`.
   - Audit em `ocg_consolidation.py` quando OCG é consolidado: registra qual modelo usou pra arbitragem em `AIUsageLog`.
   - Endpoint novo: `GET /api/audit/llm-decisions?project_id=X&start_date=Y&end_date=Z` → lista de decisões LLM via join `AIUsageLog ⟵ GlobalAuditLog` com filtro por `project_id`.
   - **Regra dura:** sem escrita na auditoria = sem chamada de LLM (fail-closed). NFR: latência de `log_llm_decision()` ≤ 50ms p95 em DB normal; se >200ms, LLM call falha com erro explícito.

2. **Fase 26.2 — Detecção de Prompt Injection (~2d)**
   - Integração com **heurísticas proprietárias** (decisão registrada: opção 2, controle total vs lib commodity).
   - Detector determinístico integrado em `arguider_service.py` **antes** da chamada ao LLM: se input é detectado como injeção, loga flag `prompt_injection_detected=true` e muda comportamento para um de:
     - **Modo restritivo** (padrão): bloqueia ingestão, retorna erro claro "Input contém padrões suspeitos"; evento vai para `GlobalAuditLog` com `event_type=PROMPT_INJECTION_BLOCKED`.
     - **Modo permissivo** (config por projeto): processa mas marca flag de risco em tudo que sair (código gerado recebe comentário `// Generated with prompt injection risk flag`).
   - Testes: payload de injeção fake é detectado; payload limpo passa; comutação de modo funciona; compartimentalização preservada.

3. **Fase 26.3 — Validação Semântica de Código Gerado (~2d)**
   - Extensão de `rnf_validation_service.py` (MVP 23.4 existente, função pura): novo método `validate_business_rules(generated_code, business_rules: list[dict]) → RnfValidationReport`.
   - Validação: código gerado respeita `BUSINESS_RULES` (MVP 23 já entregue) e `RNF_CONTRACTS` (MVP 23 já entregue)?
   - Exemplos de violações detectáveis:
     - Função gerada sem tratamento de erro, mas `RNF_CONTRACTS` exige error-handling obrigatório.
     - Módulo gerado sem logs estruturados, mas `BUSINESS_RULES` exige auditoria em cada transação.
     - Variable naming gerado não segue convenção (ex: camelCase quando `BUSINESS_RULES` exige snake_case).
   - Nível de severidade: HIGH (bloqueia merge), MEDIUM (aviso, permite merge), LOW (info apenas).
   - Integração: após CodeGen completar, dispara validação automática. Se HIGH: status `generated_module.status=REVIEW_REQUIRED` + notificação GP. Se MEDIUM/LOW: log só.
   - Comportamento gracioso: se `business_rules=[]` ou `ocg.business_rules` vazio, retorna `[]` (sem violações, sem erro).
   - Testes: violação real é detectada; code pass validation não gera falso-positivo; compartimentalização preservada.

4. **Fase 26.4 — Endpoint de Observabilidade + Dogfood (~1-2d)**
   - Novo endpoint: `GET /api/metrics/ai-governance?project_id=X` → JSON com:
     ```json
     {
       "status": "ok",
       "timestamp": "ISO-8601",
       "metrics": {
         "total_llm_decisions": N,
         "decisions_by_model": {"gpt-4": M, "claude-3": K, ...},
         "prompt_injections_detected": N,
         "prompt_injections_blocked": N,
         "code_validation_violations": {"HIGH": N, "MEDIUM": K, "LOW": L},
         "audit_entries_last_24h": N
       }
     }
     ```
   - RBAC: Admin + GP do projeto.
   - Smoke live: rodar Arguider, ver LLM decision no audit; tentar injetar prompt, ver bloqueio ou flag; gerar código, validar contra BUSINESS_RULES, ver resultado.
   - Atualizar Ajuda: capítulo novo **"Governança de IA"** cobrindo: como ler audit de decisões LLM, como interpretar detecção de injection, como validar código semanticamente, como usar endpoint de métricas.

#### Fora de escopo

- **Prompt versioning avançado** (ex: git-like diffs de prompts) — fica para MVP 27+.
- **Remediation automática** (ex: regenerar código com constraint novo) — manual primeiro, automação depois.
- **Modelos proprietários de injection detection** — usar lib commodity.
- **Fine-tuning de modelo Arguider** — fora de escopo.
- **Compliance automation** (ex: gerar relatórios LGPD automáticos) — separate MVP.

#### Regras duras de 26

- **Decisão registrada (2026-04-28):** heurísticas proprietárias (opção 2). Integração determinística em lugar de lib commodity. Controle total, customização para RNF_CONTRACTS GCA.
- **NFRs numéricos obrigatórios:**
  - Latência `log_llm_decision()` síncrona: ≤ 50ms p95 em DB normal; >200ms → LLM call falha com erro explícito.
  - Latência `GET /api/metrics/ai-governance?project_id=X`: ≤ 300ms p95 para projetos com ≤50k audit entries.
  - False-positive rate em injection detection: < 5% em fixture canônica de 40+ payloads (20+ clean, 20+ injection).
  - Cobertura de padrões de injeção: mínimo 8 categorias (prompt override, role injection, jailbreak, context poisoning, indirect, SQL, code, etc).
- **Stop-rule dura: ≤2d por fase**. Se qualquer fase passar de 2d, pausar e reportar blocker.
- §10 aplicável: zero refactor em Arguidor/CodeGen/OCG updater além da integração estrita de audit.
- Sem LLM no caminho crítico da validação — detector de injection é determinístico (heurísticas proprietárias).
- Compartimentalização §2.2 preservada: audit de projeto A nunca vaza em audit de projeto B.
- **Cada fase exige revalidação §9 (gate) antes da próxima.**

#### Critério de aceite (quando 26 completo)

- ✅ Audit estendido funciona: `AIUsageLog` persiste `temperature`, `prompt_version`, `decision_type` em Arguider/CodeGen/OCG updater.
- ✅ Prompt injection detector integrado e operacional (modo restritivo ou permissivo configurável). False-positive rate < 5% em fixture canônica.
- ✅ Validação semântica funciona contra BUSINESS_RULES + RNF_CONTRACTS via `rnf_validation_service.validate_business_rules()`.
- ✅ Endpoint `/api/metrics/ai-governance` retorna JSON válido, latência ≤ 300ms p95.
- ✅ Testes: suite baseline ~1800+ tests + 40+ novos, 100% cobertura de métodos novos, distribuídos por fase (26.1 ≥10, 26.2 ≥12, 26.3 ≥12, 26.4 ≥8).
- ✅ Zero regressão: suite existente ≥ baseline sem degradação.
- ✅ tsc frontend = 0.
- ✅ Ajuda atualizada com novo capítulo "Governança de IA", indexado em FTS5.
- ✅ Zero DTs abertas no fim do MVP.

#### Próximos candidatos após 26

- **MVP 27 potencial — SSO corporativo** (OIDC + SAML). NÃO é prioridade agora (DevOps não está previsto).
- **MVP 28 potencial — ChatOps bi-direcional** (Slack/Teams aprovação de módulos). Pré-req: MVP 27.

---

## 10. Constraint de escopo e anti-alucinação

Regras duras válidas em TODA sessão de Claude no GCA, em adição a §9.
Precedência máxima entre regras de trabalho — sobrescrevem conveniência
e "melhorias óbvias".

### 10.1 Constraint de escopo

- Faça EXATAMENTE o solicitado, nada mais.
- Se vir oportunidade de melhoria não-solicitada, liste em comentário
  TODO, não implemente.
- Antes de criar arquivo >150 linhas: peça confirmação do escopo.
- Pergunte se precisa de X, Y, Z antes de assumir.

### 10.2 Alucinação = bloqueado

- Não adicione logs estruturados sem solicitação explícita.
- Não crie fixtures que não foram pedidas.
- Não refatore código vizinho.
- Não assume "melhorias óbvias" — diga que viu a oportunidade.

### 10.3 Aplicação

- §10 aplica a TODO ciclo de trabalho, dentro ou fora de MVP ativo.
- Violação caracteriza implementação silenciosa (proibida por §9).
- Em caso de dúvida entre "faz" e "pergunta": pergunta.
