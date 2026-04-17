# GCA_CANONICAL_CONTRACT.md

Versão: 1.0  
Data-base: 2026-04-17  
Status: **Canônico / soberano para implementação**

---

## 1. Objetivo deste documento

Este documento define a verdade operacional do GCA para implementação com Claude Code.

Ele existe para:
- eliminar conflito entre documentos históricos e código atual;
- congelar o modelo do produto nesta fase;
- definir o recorte do MVP ativo;
- impedir expansão de escopo antes do saneamento da base.

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

## 6. Escopo canônico por MVP

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

## 7. MVP ativo (definição atual)

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

## 8. Regras duras de implementação

Valem sempre:
- não antecipar features de MVP futuro;
- não criar papéis fora dos 5 canônicos;
- não reconciliar documentos históricos em silêncio;
- não alterar contratos existentes sem migração/compatibilidade explícita;
- não reescrever módulos inteiros se correção cirúrgica for suficiente;
- não criar novas camadas genéricas sem necessidade concreta;
- não assumir Anthropic como único caminho de IA;
- não assumir SaaS multi-cliente compartilhado;
- não avançar de MVP com blocker, critical, contradição de contrato ou testes quebrados.

---

## 9. Critérios de pronto da fase atual

O MVP 1 só pode ser considerado encerrado quando:
- RBAC de 5 papéis estiver coerente em backend, frontend e documentação ativa;
- não houver conflito estrutural aberto entre contrato e código do núcleo;
- autenticação e fluxo de projeto estiverem estáveis;
- OCG básico e Gatekeeper básico estiverem consistentes com o recorte do MVP;
- testes e validações mínimas da fase passarem;
- gaps bloqueantes forem classificados e reduzidos ao mínimo aceitável;
- o próximo MVP puder começar sem depender de “interpretação criativa” do Claude.

---

## 10. Conflitos documentais conhecidos

Conflitos já reconhecidos e não resolvidos automaticamente:
- documentos históricos com **7 papéis** versus contrato canônico com **5 papéis**;
- materiais que descrevem pipeline completo como se tudo já estivesse pronto;
- textos que tratam a instância dogfood como se provasse SaaS compartilhado;
- trechos que apontam provedores específicos de IA como padrão rígido;
- discrepâncias entre “production ready/beta” e gaps ainda documentados.

Esses conflitos devem ser tratados como **dívida de contrato/documentação**, não como autorização para novas implementações.

---

## 11. Mandato para Claude Code

Claude deve atuar como:
- saneador incremental do GCA;
- executor por MVP;
- verificador de aderência ao contrato;
- analista de adequação de IA ao objetivo do cliente.

Claude não deve atuar como:
- autor livre da plataforma;
- reconciliador silencioso de contradições;
- expansor de escopo;
- reescritor amplo de arquitetura sem necessidade demonstrada.
