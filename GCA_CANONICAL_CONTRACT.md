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
- **não escreve código**.

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

Regras obrigatórias:
- o OCG nasce do questionário aprovado;
- o OCG é evolutivo e auditável;
- boa ingestão expande contexto;
- ingestão ruim ou conflitante contrai confiança;
- módulos não podem assumir defaults invisíveis quando o OCG estiver incompleto;
- toda mudança relevante deve gerar versionamento e trilha de auditoria.

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

### 6.6 Separação entre IA de desenvolvimento do produto e IA operacional do cliente

O GCA deve ser interpretado sob dois contextos distintos de uso de IA. Essa separação é contratual e precede qualquer decisão sobre provedor/modelo padrão.

#### 6.6.1 Contexto A — IA usada para desenvolver e evoluir o GCA

Cobre a IA utilizada pelo criador/equipe do produto para:
- desenhar arquitetura;
- testar e consolidar o OCG;
- reduzir dívida técnica;
- evoluir módulos;
- gerar ou revisar código do próprio GCA;
- criar documentação e estrutura do produto.

Regras:
- a escolha da IA é decisão de engenharia do produto;
- pode ser adotado um modelo premium/forte para maximizar qualidade analítica;
- o custo é de desenvolvimento do produto, não custo operacional do cliente;
- decisões tomadas aqui **não definem automaticamente** o padrão de IA do cliente final.

#### 6.6.2 Contexto B — IA usada pelo cliente dentro da sua instância do GCA

Cobre a IA utilizada na operação diária da instância on-premises do cliente para:
- gerar e atualizar OCGs de projetos;
- executar Gatekeeper, Arguidor, backlog, roadmap e CodeGen;
- analisar documentos, contexto e entregáveis;
- apoiar governança, testes e documentação viva.

Regras:
- o cliente escolhe o provedor/modelo que deseja utilizar;
- o cliente paga pelos custos operacionais de IA da sua instância;
- o GCA deve permitir configuração por instância e, quando aplicável, por projeto;
- o produto deve **recomendar, mas não impor**, a escolha de IA;
- a recomendação deve considerar objetivo, custo, latência, privacidade, contexto e risco de erro.

#### 6.6.3 Regra de não acoplamento entre os dois contextos

Regra dura:
- a IA usada para construir o GCA **não pode virar dependência obrigatória** da operação do cliente;
- a escolha atual de IA do produto não deve ser hardcoded como verdade universal do sistema;
- nenhuma decisão de implementação deve presumir que o cliente final usará o mesmo provedor/modelo do desenvolvedor do GCA;
- o GCA deve permanecer compatível com múltiplos provedores e modelos, inclusive por endpoint compatível quando previsto pela configuração.

#### 6.6.4 Política de recomendação de IA ao cliente

Antes de fixar um padrão de IA para a instância do cliente, o GCA deve avaliar:
1. objetivo principal do cliente com a IA;
2. nível de criticidade das tarefas;
3. expectativa de custo;
4. expectativa de latência;
5. exigência de privacidade ou localidade;
6. necessidade de codegen;
7. necessidade de análise documental e consolidação de contexto;
8. aderência do modelo ao volume de contexto e idioma esperado.

O resultado deve classificar a opção como:
- recomendada;
- aceitável com ressalvas;
- inadequada para o objetivo informado.

#### 6.6.5 Política operacional recomendada

Para clientes que desejam equilíbrio entre custo e qualidade:
- tarefas menores e auxiliares podem usar modelo local ou modelo mais barato;
- tarefas oficiais de consolidação, arbitragem e decisão crítica devem usar modelo mais forte;
- OCG final, conflitos entre artefatos, decisões de arquitetura, compliance e segurança críticos **não devem depender exclusivamente de modelo fraco**.

Essa política é consistente com §6.2 (roteamento híbrido por criticidade): Contexto B herda a taxonomia baixa/média/alta, mas aplicada à instância do cliente — nunca presumindo a mesma configuração do Contexto A.

#### 6.6.6 Relação com o OCG

Independentemente do provedor/modelo escolhido em qualquer um dos contextos:
- o OCG continua sendo a fonte única de verdade do projeto;
- nenhuma saída relevante pode ignorar o OCG;
- mudanças relevantes de contexto devem refletir no versionamento, auditoria e propagação do OCG;
- a escolha de IA influencia o perfil operacional, mas **não substitui** a governança do OCG.

#### 6.6.7 Exemplos de interpretação correta

Exemplo 1:
- durante a construção do GCA, o produto pode usar uma IA premium para amadurecer o OCG;
- isso **não obriga** o cliente a usar a mesma IA em produção.

Exemplo 2:
- o cliente pode configurar modelo local/Ollama para tarefas auxiliares;
- e modelo premium para OCG final, Gatekeeper crítico ou codegen estrutural;
- isso é comportamento **válido e desejável** quando explicitamente configurado.

---

## 7. Escopo canônico por MVP

### MVP 1 — Base operacional e saneamento do núcleo

#### Em escopo
- autenticação;
- RBAC canônico de 5 papéis;
- bootstrap/admin básico;
- cadastro e aprovação de projetos;
- questionário externo/interno;
- OCG persistido básico;
- Gatekeeper básico;
- auditoria mínima necessária;
- configuração básica de provedor de IA;
- política de adequação e roteamento de IA;
- vínculo com repositório Git quando exigido pelo fluxo da fase;
- correção de conflitos estruturais entre código e contrato.

#### Fora de escopo
- expansão livre de papéis;
- LiveDocs completa;
- Release Bundle completo;
- billing avançado;
- marketplace;
- auto-upgrade avançado;
- multi-instância avançada além do deployment por cliente;
- reescrita ampla de arquitetura.

### MVP 2 — Contexto vivo e governança de conteúdo

#### Em escopo
- ingestão de documentos;
- quarentena de PII;
- OCG versionado com deltas;
- backlog derivado do OCG;
- Arguidor;
- reavaliação do Gatekeeper após ingestão.

### MVP 3 — Geração assistida controlada

#### Em escopo
- CodeGen controlado;
- geração cirúrgica por arquivo;
- preview;
- integração com Git;
- commits rastreáveis;
- validação pós-geração;
- análise de adequação do provedor de IA ao uso pretendido no CodeGen.

### MVP 4 — Qualidade, documentação e entrega

#### Em escopo
- QA Readiness;
- execução e revisão de testes;
- Documentação Viva;
- Roadmap coerente;
- Release Bundle;
- evidências e relatórios.

### MVP 5 — Hardening operacional

#### Em escopo
- criptografia de segredos e PATs;
- hardening de produção;
- observabilidade complementar;
- rotinas de backup/restore maduras;
- melhorias de deploy/upgrade por cliente.

---

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

## 9. Regras duras de implementação

- Não antecipar feature de MVP futuro.
- Não expandir RBAC além de 5 papéis.
- Não promover documento histórico a contrato de implementação.
- Não reescrever arquitetura inteira quando correção cirúrgica resolver.
- Não hardcodar um único provedor de IA no produto.
- Não assumir que todo fluxo precisa usar a mesma IA.
- Não permitir que modelo barato/local tome decisão oficial crítica sozinho.
- Não avançar para o próximo MVP enquanto o gate da fase atual estiver fechado.
