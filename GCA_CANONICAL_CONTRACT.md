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

### MVP 8 — Ingestão inteligente de documentos

**Motivação:** o dogfood 2026-04-19 expôs dois problemas operacionais que travam o usuário final:

1. **Documentos em formato técnico inadequado não alimentam o OCG.** O Arguidor usa `python-docx` lendo apenas `Document.paragraphs[].text`; tabelas de `.docx` ficam invisíveis. Na prática, cliente sobe documento aparentemente rico (RFs em tabela, diagramas, anexos), o pipeline não vê nada, OCG não evolui, backlog fica vazio, roadmap não é gerado. Cliente ficou sem saber por que "nada aconteceu". O protocolo atual (DT-064 + fallback automático) só resolve erro de provedor; não resolve a qualidade do conteúdo extraído.

2. **Ausência de feedback visível de progresso no processamento.** Frontend mostra apenas "Processando" estático. Pipelines de OCG + Gatekeeper + Arguidor podem levar minutos em IA local. Usuário comum interpreta como travado e abandona ou fica reiniciando.

Este MVP resolve ambos de forma definitiva. Pré-processamento interno é invisível ao usuário — ele sobe qualquer formato esperado (`.docx`, `.pdf`, `.md`, `.txt`) e o GCA normaliza antes de entregar ao Arguidor.

#### Em escopo

- **Fase 1 — Feedback de progresso (urgente):** colunas `arguider_stage` e `arguider_progress_percent` em `ingested_documents`; backend atualiza em cada marco (extração, análise por pilar, consolidação, backlog/roadmap); frontend com barra de progresso real, texto do estágio atual e tempo decorrido; polling adaptativo (2s enquanto processando, para ao concluir).
- **Fase 2 — Extração rica de `.docx`:** pré-parser que percorre o `Document` inteiro e transforma **tabelas em parágrafos estruturados** no formato `[Coluna1: valor] [Coluna2: valor]` legível pelo Arguidor; extrai também `<w:sdt>`, listas aninhadas, caixas de texto, notas de rodapé.
- **Fase 3 — Extração rica de `.pdf`:** pipeline em camadas — tentar AcroForm → tentar texto pesquisável → OCR (Tesseract ou provedor IA) como fallback. Deduplicar conteúdo entre camadas.
- **Fase 4 — Normalização com heurísticas:** detector automático de seções "entregáveis", "módulos", "fases", "requisitos funcionais" por sinais textuais (prefixos "RF-", "Fase N", listas numeradas). Quando o documento não declara explicitamente, o pré-processador infere e anota.
- **Fase 5 — Relatório de extração ao usuário:** ao final da extração (antes do Arguidor), a UI mostra o que foi entendido (quantos RFs, módulos, entregáveis, fases) e permite o usuário confirmar ou rejeitar antes de prosseguir com o Arguidor.
- **Fase 6 — Testes de regressão com documentos reais:** suite de fixtures com `.docx` problemáticos conhecidos (v1.0 da Automação Jurídica, PDFs escaneados, docs mistos) validando extração mínima esperada.

#### Fora de escopo

- edição in-loco do documento pelo usuário dentro do GCA (MVP futuro);
- formatos proprietários fora de `.docx/.pdf/.md/.txt` (Pages, Keynote, RTF binário antigo);
- OCR com modelo de layout (LayoutLM, Donut) — nesta fase, Tesseract ou LLM genérico bastam;
- rewrite automático de trechos ambíguos — o pré-processador **extrai e estrutura**, mas **não reescreve conteúdo do usuário**;
- tradução automática de documentos em outro idioma;
- análise de qualidade semântica do documento (isso continua no Arguidor).

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

### MVP 12 — Saneamento pós-MVP 11: hardening de fronteira, configurabilidade, higiene de schema e maturidade

**Motivação:** auditoria 2026-04-20 pós-MVP 11 identificou 6 DTs canônicas (rate limit público ausente, timezone hardcoded no backup scheduler, dual `accepted_at`/`joined_at`, `initial_password_hash` órfão, TODOs SMTP em fluxo deprecado, e2e `continue-on-error`) + 4 dívidas estruturais mais antigas que seguiam como backlog (type safety `any` no frontend, fila persistente diferida DT-075, helper de prompt CodeGen duplicado, hash chain de auditoria incompleto). O stakeholder-soberano autorizou em 2026-04-20 incluir **todas** num único MVP de saneamento, em vez de deixar as 4 últimas como backlog indefinido.

Este MVP tem caráter **majoritariamente de saneamento e hardening** — não introduz feature nova. Cada fase é independente; execução é sequencial por prioridade (A→B→C→D→E→F→G) mas fases são commitáveis isoladamente.

#### Em escopo

**Tema A — Segurança de fronteira (abuse prevention):**
- **Fase 12.1** Rate limit + mitigação anti-abuse em `POST /public/request-project`. Throttle por IP (`slowapi` ou equivalente), idempotência já existente mantida, opcional captcha simples se volume justificar. Teste cobrindo bloqueio após N requisições/min.

**Tema B — Configurabilidade operacional:**
- **Fase 12.2** Timezone configurável em `BackupScheduler`. Env var `BACKUP_TIMEZONE` (default `America/Sao_Paulo`); runtime lê e passa para APScheduler. Teste cobre 2 timezones distintos.

**Tema C — Higiene de schema + cleanup:**
- **Fase 12.3** Consolidar `ProjectMember.accepted_at` vs `joined_at`. Manter ambas colunas (backward-compat); adicionar helper canônico `is_pending_invite(member)` em `app/services/project_team_service.py`; corrigir toda query que filtra por `accepted_at IS NULL` para usar `invite_token IS NOT NULL AND joined_at IS NULL AND is_active=True`. Comentário canônico no modelo.
- **Fase 12.4** Deprecar `ProjectRequest.initial_password_hash`. Coluna não é preenchida em nenhum fluxo desde migração do onboarding — adicionar comentário `# deprecated 2026-04-20 — remove em V2 after grace period`. Sem remoção física nesta fase (evita migração destrutiva sem plano de rollback).
- **Fase 12.5** Remoção de TODOs SMTP de fluxo deprecado. Arquivos: `backend/app/routers/onboarding.py:139` e `services/onboarding_service.py:493-494`. Se os endpoints correspondentes não têm mais consumer, retornam 410 Gone; se ainda têm, ligar ao `email_service` canônico. Decisão por análise de uso.

**Tema D — CI maturity:**
- **Fase 12.6** Canário real + remoção do `continue-on-error: true` da lane `e2e` em `backend-tests.yml`. Script `backend/scripts/seed_e2e.py` cria admin canônico `admin@gca.local` + 1 projeto com `project_id=1` no ambiente de CI antes do teste rodar. Após passar consistentemente, lane vira gate real.

**Tema E — Type safety frontend:**
- **Fase 12.7** Remoção de `any` de arquivos TS do frontend — ~20 arquivos identificados em `frontend/src/lib/`, `frontend/src/pages/admin/` e `frontend/src/pages/projects/`. Substituir por tipos ou interfaces explícitas. Violação da política CLAUDE.md §12 ("Não usar `any`"). Build frontend tem que continuar íntegro.

**Tema F — Robustez estrutural:**
- **Fase 12.8** Fila persistente (ex-DT-075 reclassificada). Migração de tarefas async de `asyncio.create_task` para Celery (Redis já está no docker-compose). Cobertura: apenas pipeline `Arguidor` + `ocg_updater` + `codegen` — tarefas de ingestão mantêm `asyncio` nesta fase (watchdog DT-073 cobre). Se escopo mostrar-se excessivo em diagnóstico inicial, reportar e pedir decisão binária antes de continuar.
  - **DIFERIDA 2026-04-20** pela regra de parada: diagnóstico inicial revelou escopo estrutural (3-4 dias, 5 frentes: Celery setup + tasks, lifespan integration, refactor pipeline, migração de testes, monitoring+retry). Re-escopada para **MVP 13 — Robustez estrutural** quando autorizado. Watchdog DT-073 continua cobrindo o sintoma operacional (doc preso em `processing`).
- **Fase 12.9** Consolidação do helper de prompt do CodeGen. Hoje `/scaffold` e `/regenerate-file` duplicam lógica de build de prompt em `code_generation.py`. Extrair `_build_scaffold_prompt(project, ocg_data, scope)` compartilhado. Facilita mock em testes e garante consistência dos prompts.

**Tema G — Observabilidade compliance:**
- **Fase 12.10** Completar cobertura de `audit_log_global` na hash chain. Auditoria: identificar endpoints/ações críticas que ainda não gravam em `audit_log_global` (além do que a Fase 11.4 cobriu). Expandir cobertura para ações de projeto (aprovação, desativação, transferência), questionário (submissão, aprovação), OCG (geração, consolidação, rollback), CodeGen (scaffold/apply, regenerate-file). Validação: teste de ponta-a-ponta que verifica chain integrity pós-série-de-ações.
  - **DIFERIDA 2026-04-20** pela mesma regra de parada: cobertura e2e exige inventariar ~20+ endpoints e injetar `log_role_event`/`log_event` com payload canônico em cada, mais teste de cadeia integral. Re-escopada para **MVP 13 — Robustez estrutural** junto com 12.8. A cobertura parcial da Fase 11.4 (role events) continua operando.

#### Regras duras
- Nenhuma fase introduz feature nova além do saneamento declarado. Qualquer feature encontrada durante execução deve ser escopada em MVP futuro.
- Fases 12.8 (Celery) e 12.10 (hash chain completa) são estruturalmente maiores — se o diagnóstico inicial revelar escopo significativamente maior do que o resto, o executor **para** e pede decisão binária ao stakeholder (cortar, diferir ou continuar).
- Ordem de execução recomendada é A→B→C→D→E→F→G, mas fases são independentes; stakeholder pode reordenar.
- Gate §9 revalidado após cada fase.
- Nenhuma quebra de compat em DB/API sem plano de deprecação explícito.

#### Fora de escopo

- SSO/federação de identidade (ver MVP dedicado se solicitado).
- Nova arquitetura de auditoria (Merkle/blockchain público) — a Fase 12.10 mantém hash chain SHA-256 existente e apenas expande cobertura.
- Migração das tarefas de ingestão para Celery — watchdog DT-073 cobre e o refactor é oportunisticamente parcial na Fase 12.8.
- CAPTCHA de terceiros na Fase 12.1 (Turnstile/hCaptcha): preferir rate-limit local; captcha externo entra só se dogfood mostrar abuse real.
- Remoção física de `ProjectRequest.initial_password_hash` — só marca como deprecada; remoção em V2 com migração destrutiva planejada.
- Reescrita de testes flaky/skipped: os skips atuais têm motivo documentado (ver §3 do progresso); não reabertos nesta fase.
- Novo dialeto de DDL (Oracle V2 foi cobrido no MVP 11; não entra nada novo aqui).

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
