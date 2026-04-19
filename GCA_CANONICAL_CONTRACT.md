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

### MVP 6 — Validação assistida em campo (tickets de incidente)

**Motivação:** o GCA é produto novo. Usuários reais (GPs e membros de projeto) vão encontrar bugs e necessidades não previstas. Este MVP cria o canal oficial dentro da instância para registrar, rotear e rastrear esses achados, de modo que cada incidente vire insumo rastreável para correções futuras (entregues via MVP 7).

#### Em escopo
- abertura de ticket de incidente pelo usuário, a partir do projeto em que ele atua;
- roteamento automático por papel de origem:
  - Dev / Tester / QA abre → **GPs do projeto** recebem;
  - GP abre → **Admins da instância** recebem;
  - Admin abre em um projeto → **demais Admins** recebem (tickets intra-admin);
- seção agregada na área administrativa com visão cross-projeto dos tickets escalados para Admin;
- campos mínimos: título, descrição, prioridade (baixa/média/alta/crítica), categoria (bug/dúvida/pedido de feature/incidente de pipeline), status (aberto/em andamento/resolvido/fechado);
- conversa no ticket (comentários entre autor, GP e/ou Admin), com autoria e timestamp;
- notificação in-app para os destinatários no ato da abertura e em cada evento relevante (comentário novo, mudança de status, resolução);
- auditoria compartimentalizada do ciclo de vida do ticket em `audit_log_global`;
- isolamento por projeto: ticket de um projeto nunca vaza para membros de outro projeto.

#### Fora de escopo
- SLA formal com escalonamento automático por tempo decorrido;
- integração com ferramentas externas (Jira, Linear, Zendesk, email bidirecional);
- pesquisa de satisfação pós-resolução;
- tickets transversais entre projetos (cada ticket pertence a exatamente um projeto; alternativa é abrir tickets irmãos).

#### Emenda 2026-04-19 (mesmo dia do fechamento original)

Expansão do MVP 6 solicitada pelo stakeholder-soberano logo após o fechamento. Mantém o MVP 6 como o MVP dos tickets — não gera MVP novo (protocolo §7.0.6 exige numeração monotônica).

**Adicionados ao em escopo:**
- **Área de Sustentação (papel cross-instância)**: nova flag de usuário `is_support`. Destinatários de tickets com `target_scope='admin'` passam a ser todos os usuários ativos com `is_admin=True OR is_support=True`. Admin e Sustentação veem `/admin/incidents`.
  - **Assimetria obrigatória**: `is_admin=True` **herda** os privilégios de Support automaticamente, mesmo sem `is_support=True`. Admin sobrepõe qualquer posição no GCA. Support **nunca** ganha privilégios de Admin por essa via — promoção a Admin continua fluxo separado de gestão de usuários. Conclusão prática: não existe UI que promova Support a Admin; existe UI que promove user comum a Support e que permite Admin acumular Support se quiser.
  - **Gestão**: seção nova "Equipe Sustentação" na área admin, acessível apenas a Admin, onde Admin ativa/desativa `is_support` de usuários ativos.
- **Anexos ao ticket (imagens, logs, textos)**: o autor pode anexar até 5 arquivos por ticket, 10 MB cada. Tipos aceitos: imagens (png/jpg/jpeg/webp/gif) e textos/logs/relatórios (txt/log/json/pdf). Storage no volume `gca-uploads` em `incidents/{ticket_id}/{hash}_{filename}`; tabela `incident_ticket_attachments` (id, ticket_id, uploader_id, filename, mime, size_bytes, sha256, storage_path, created_at). Sem scan de PII no V1 desta emenda — a responsabilidade pelo conteúdo anexado é do próprio autor, que é membro do projeto ou admin da instância.
- **Contexto obrigatório do incidente**: dois campos novos em `incident_tickets`:
  - `section_reference` (string, autopreenchida pela rota atual do frontend no momento da abertura — ex.: `/projects/{id}/ocg` — editável pelo autor se necessário);
  - `flow_description` (texto longo, **obrigatório**): o autor descreve passo a passo o que estava fazendo quando o erro apareceu. Modal recusa abertura se o campo vier vazio.

**Assimetria Admin↔Support — regra dura (em escopo):**
- Admin pode ver e agir em tickets escalados a admin (já existia);
- Support ativo pode ver e agir em tickets escalados a admin (nova regra);
- Admin pode promover usuário a Support (UI de "Equipe Sustentação");
- Admin pode rebaixar Support;
- Admin pode ativar `is_support` em si mesmo (Admin acumula Sustentação se quiser);
- UI de "Equipe Sustentação" **não** oferece operação de promover Support a Admin (isso fica na gestão de usuários canônica).

**Mantido fora de escopo mesmo na emenda:**
- Scan automático de PII em anexos (fora do V1; responsabilidade é do autor);
- Versionamento do anexo (substituir = upload novo, delete do anterior);
- Preview inline de PDF ou pré-visualização de vídeo (download simples);
- SLA/escalonamento automático;
- Integração externa (Jira/Linear/email bidirecional);
- Tickets cross-projeto.

### MVP 7 — Entrega versionada preservando dados do usuário

**Motivação:** quando a correção de um ticket (MVP 6) ou uma feature nova gera uma release do GCA, o usuário não pode perder os dados já inseridos (projetos, questionários, OCG, backlog, documentos, configurações). Este MVP institui o contrato de entrega: por default a release **não sobrescreve** dado persistido; quando a correção exige migração destrutiva, o usuário tem caminho explícito de recuperação e complemento.

#### Em escopo
- versionamento explícito da instância: cada release tem **tag semântica** e **changelog visível** ao usuário dentro da UI;
- cada release amarra-se à lista de **MVPs fechados** e **tickets (MVP 6) resolvidos** que a motivaram (rastreabilidade ticket → release);
- política default **não-destrutiva**: toda migração nova preserva dado existente (coluna nova é nullable ou tem default; remoção passa por janela de deprecação; mudança de tipo usa coluna paralela); o `upgrade.sh` (DT-062) roda essas migrations sem intervenção do usuário;
- quando a correção exige migração **destrutiva ou semanticamente incompatível**:
  - usuário recebe aviso explícito **antes** da aplicação com descrição do impacto;
  - snapshot pré-release é gerado automaticamente reaproveitando o backup por projeto (DT-063);
  - usuário tem botão para **restaurar o estado anterior** dos dados do projeto;
  - usuário é conduzido por um **assistente pós-release** para completar informações novas referentes ao ticket que motivou a entrega (ex.: release adiciona campo obrigatório no questionário por causa do ticket X — assistente mostra projetos afetados e solicita o novo campo);
- changelog segmentado por papel: Admin vê a release inteira; GP vê o que afeta os projetos onde atua; Dev/Tester/QA vê o que afeta os módulos em uso;
- auditoria: cada aplicação de release + cada restauração de snapshot + cada preenchimento via assistente pós-release gera evento em `audit_log_global`.

#### Fora de escopo
- downgrade da versão do aplicativo (container/imagem) — continua operação manual via DT-062 `upgrade.sh` / `restore.sh`;
- compartilhamento automático de correção entre instâncias de clientes diferentes (cada cliente recebe release pelo fluxo de instalação próprio);
- marketplace de plugins, features opt-in ou A/B testing de release;
- edição retroativa de dado de usuário fora do caminho oferecido pelo assistente pós-release (dado preservado é dado preservado — mudança arbitrária exige nova release).

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
