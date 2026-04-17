# GCA_CANONICAL_CONTRACT.md

Versão: 1.1  
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
