# CLAUDE.md

Este arquivo define como Claude Code deve atuar no repositório do GCA.
Ele não substitui o contrato canônico do produto; ele operacionaliza o trabalho.

---

## 1. Identidade do projeto

GCA (Gestão de Codificação Assistida / Gerenciador Central de Arquiteturas) é uma plataforma instalável por cliente para governança de projetos de TI assistida por IA.

O GCA NÃO deve ser tratado como projeto greenfield puro.
Ele já possui base funcional, endpoints ativos, serviços existentes, testes de regressão e documentação histórica.
Claude deve evoluir e sanear o que já existe, preservando compatibilidade e evitando reescritas desnecessárias.

Idioma obrigatório:
- Comunicação: Português-BR
- Commit messages: Português-BR
- Comentários: Português-BR
- Documentação: Português-BR

---

## 2. Fonte soberana e precedência

Ordem de precedência em caso de conflito:

1. `GCA_CANONICAL_CONTRACT.md`
2. `GCA_MVP_PROGRESS.md`
3. `CLAUDE.md`
4. `TASK_GCA_MASTER.md`
5. Código existente
6. Documentos históricos, manuais, tutoriais, análises e rascunhos

Regra:
- Se houver conflito entre documentos, NÃO reconciliar por conta própria.
- Reportar a divergência e seguir a fonte soberana.
- Documentos históricos podem explicar contexto, mas não autorizam implementação automática.

---

## 3. Modo do produto

Modo canônico atual:
- Produto instalável por cliente
- Uma instância por cliente
- Isolamento principal por projeto
- Sem SaaS multi-tenant compartilhado entre clientes nesta versão
- Cada cliente usa seus próprios provedores, chaves e integrações

Interpretação obrigatória:
- “Tenant” interno no GCA significa isolamento por projeto dentro da instância do cliente
- Não assumir billing centralizado
- Não assumir compartilhamento de contexto entre instâncias
- Não assumir marketplace ou operação SaaS central como realidade atual
- IA pode operar em **modo híbrido**: modelos diferentes por tipo de tarefa, desde que configurável e auditável (detalhe em §6)

---

## 4. RBAC canônico desta versão

Papéis válidos e implementáveis nesta versão:
- Admin
- GP
- Dev
- Tester
- QA

Regras duras:
- Admin configura a instância e não atua operacionalmente em projetos
- GP conduz projeto, aprova módulos e OCG, e não escreve código
- Dev implementa, gera código, executa correções e não aprova módulos
- Tester edita, executa e registra testes
- QA revisa/aprova execução e não edita conteúdo de teste

Papéis como:
- Tech Lead
- Compliance
- Stakeholder
- Viewer
- Dev Sênior / Dev Pleno como papéis distintos de sistema

devem ser tratados como históricos, analíticos ou futuros.
Não implementar esses papéis como RBAC canônico sem atualização explícita do contrato soberano.

---

## 5. OCG é obrigatório

O OCG é a fonte única de verdade do projeto.

Regras obrigatórias:
- O OCG inicia a partir do questionário externo aprovado
- O OCG é um objeto de estado evolutivo
- O OCG expande com boa ingestão
- O OCG contrai com ingestão ruim, conflitante ou incompleta
- Nenhuma decisão arquitetural, funcional, de testes ou de geração de código pode ignorar o OCG
- Nenhum módulo deve assumir defaults invisíveis quando o OCG estiver incompleto
- Toda mudança relevante no OCG deve ser versionada e auditável

Ao trabalhar em qualquer módulo:
1. Antes: carregar o OCG atual
2. Durante: usar o OCG como contexto principal
3. Depois: atualizar/versionar o OCG quando houver impacto

---

## 6. Política obrigatória sobre IA do cliente final

Claude está construindo o GCA, mas o GCA NÃO impõe um único provedor de IA ao cliente final.

Princípios:
- O cliente final escolhe o provedor/modelo que deseja usar
- O sistema deve permitir configuração por instância e, quando aplicável, por projeto
- O comportamento do OCG, do Arguidor e do CodeGen depende do provedor escolhido
- Antes de consolidar qualquer fluxo baseado em IA, oferecer análise de aderência da IA escolhida ao objetivo do cliente

### 6.1 Regra de análise antes de fixar default de IA

Sempre que houver definição, alteração ou recomendação de provedor/modelo de IA, Claude deve:

1. Identificar o objetivo principal do cliente com o GCA, por exemplo:
   - geração de OCG com melhor qualidade analítica
   - menor custo
   - menor latência
   - maior privacidade
   - uso com modelo local/API compatível
   - melhor codegen
   - melhor capacidade de síntese documental
   - melhor desempenho em português

2. Comparar a expectativa do cliente com as características do provedor/modelo pretendido

3. Registrar riscos de frustração, tais como:
   - custo incompatível
   - latência alta
   - qualidade insuficiente para OCG complexo
   - contexto insuficiente para ingestão grande
   - compatibilidade parcial com o fluxo do GCA
   - suporte apenas via endpoint compatível, sem suporte oficial

4. Emitir recomendação clara:
   - recomendado
   - aceitável com ressalvas
   - inadequado para o objetivo informado

5. Nunca tratar uma IA como “melhor universal”
   - a recomendação deve ser contextual ao objetivo do cliente

### 6.2 Roteamento híbrido por criticidade

Referência autoritativa: `GCA_CANONICAL_CONTRACT.md §6.2`. Resumo operacional:

- **Baixa criticidade** (classificação simples, extração de campos, sumarização curta, normalização, pré-processamento, enriquecimento leve): modelo local/Ollama ou modelo barato quando configurado pelo cliente.
- **Média criticidade** (perguntas dirigidas preliminares, propostas iniciais de backlog, pré-análise de artefatos, insumos para OCG/Gatekeeper/Arguidor): local ou remoto, com validação posterior.
- **Alta criticidade** (consolidação final do OCG, arbitragem de conflitos, decisões arquiteturais, achados críticos de compliance/segurança, liberação/bloqueio de pipeline, backlog oficial, codegen crítico, síntese executiva): modelo premium de raciocínio obrigatório.

Diretriz prática: Ollama/local = auxiliar barato para tarefas menores e repetitivas; modelo premium = consolidação e decisão crítica.

### 6.3 Regras duras de IA

- Nenhum modelo local deve consolidar sozinho o OCG final sem validação da política do projeto.
- Nenhum modelo de baixa criticidade deve decidir sozinho arquitetura, compliance, segurança ou liberação de pipeline.
- Uso híbrido deve ser explícito, auditável e parametrizável.
- Cada tarefa relevante de IA deve registrar: provedor, modelo, motivo da escolha, nível de criticidade, e custo estimado/observado.
- Compatibilidade com endpoint estilo OpenAI não é equivalência funcional entre modelos.
- Roteamento híbrido **não** substitui o OCG — todo output relevante respeita o OCG atual.

### 6.4 Regras de implementação para IA

- Nunca hardcodar provedor como se fosse obrigatório do produto inteiro.
- Nunca presumir Anthropic como único caminho, mesmo se estiver presente em documentos antigos.
- Nunca misturar chave global de avaliação com chaves específicas do projeto sem regra explícita.
- Sempre externalizar provider, model, endpoint, api_key, timeouts e limites.
- Se houver suporte a endpoint compatível com OpenAI, deixar isso explícito como compatibilidade, não como suporte oficial pleno.

### 6.5 Separação obrigatória entre IA de desenvolvimento do GCA e IA operacional do cliente

Referência autoritativa: `GCA_CANONICAL_CONTRACT.md §6.6`. Aplicação obrigatória no raciocínio de Claude.

Claude deve **sempre raciocinar sob dois contextos distintos**.

#### 6.5.1 Contexto A — IA usada para construir o GCA

Cobre:
- arquitetura do produto;
- saneamento técnico;
- teste e consolidação do OCG;
- evolução dos módulos do próprio GCA;
- geração e revisão de código do produto.

Regra:
- neste contexto, pode ser usada uma IA mais forte para maximizar qualidade e reduzir risco de erro;
- isso é custo de desenvolvimento do produto;
- essa escolha **não define automaticamente** o comportamento exigido do cliente final.

#### 6.5.2 Contexto B — IA usada pelo cliente dentro da instância do GCA

Cobre:
- uso diário do GCA pelo cliente;
- OCG dos projetos do cliente;
- Gatekeeper, Arguidor, backlog, roadmap, CodeGen, QA e documentação viva;
- custos operacionais de IA da instância on-premises do cliente.

Regra:
- a escolha do provedor/modelo pertence ao cliente;
- o GCA deve suportar configuração por instância e, quando aplicável, por projeto;
- Claude **não deve transformar** a IA usada no desenvolvimento do GCA em dependência mandatória da operação do cliente.

#### 6.5.3 Regra dura de implementação

Claude **nunca** deve:
- hardcodar como obrigatório o mesmo provedor/modelo usado para construir o GCA;
- assumir que todo cliente usará Anthropic, OpenAI ou qualquer outro provedor específico;
- tratar uma escolha atual do produto como contrato obrigatório da operação do cliente;
- reduzir a arquitetura a um único provedor quando o contrato do produto exige flexibilidade configurável.

#### 6.5.4 Regra de desenho do sistema

Ao trabalhar em qualquer módulo com IA, Claude deve perguntar:
1. esta decisão pertence ao desenvolvimento do GCA ou à operação do cliente?
2. esta escolha de IA é uma decisão de engenharia do produto ou uma configuração da instância do cliente?
3. estou acidentalmente transformando uma conveniência de desenvolvimento em obrigação do produto?

#### 6.5.5 Política operacional decorrente

Claude deve preservar no sistema:
- múltiplos provedores configuráveis;
- possibilidade de recomendação por objetivo do cliente;
- possibilidade de roteamento híbrido por criticidade (§6.2);
- separação entre chaves globais do pipeline e chaves do projeto;
- registro auditável da escolha de provedor/modelo quando a tarefa for relevante.

#### 6.5.6 Frase de verificação obrigatória

Sempre que uma mudança envolver IA, Claude deve validar:

> "Esta decisão é apenas do meu ambiente de desenvolvimento do GCA ou está virando indevidamente uma obrigação da operação do cliente?"

Se a resposta indicar acoplamento indevido:
- parar;
- reportar a divergência;
- corrigir o desenho para manter o produto flexível ao cliente final.

---

## 7. Fatiamento por MVP

Claude deve trabalhar em camadas lógicas.
Nenhum MVP pode avançar enquanto o anterior tiver blocker, critical, contradição de contrato ou testes quebrados.

### MVP 1 — Base operacional mínima
Escopo:
- autenticação
- RBAC canônico de 5 papéis
- cadastro e aprovação de projeto
- questionário externo/interno
- OCG persistido básico
- Gatekeeper básico
- auditoria mínima necessária
- configuração básica de provedor de IA
- política de adequação e roteamento híbrido de IA (§6)
- vínculo obrigatório com repositório Git quando a fase exigir ingestão/codegen

Fora de escopo:
- CodeGen completo
- Documentação Viva automática
- Release Bundle
- auto-upgrade sofisticado
- billing avançado
- marketplace
- multi-instância avançada além do necessário para instalação por cliente

### MVP 2 — Contexto vivo e governança de conteúdo
Escopo:
- ingestão de documentos
- quarentena/PII
- OCG versionado com deltas
- backlog derivado do OCG
- Arguidor
- consolidação de findings
- reavaliação do Gatekeeper após ingestão

Fora de escopo:
- expansão automática para features de entrega final
- release bundle
- automações além do necessário para estabilizar contexto

### MVP 3 — Geração assistida com controle
Escopo:
- CodeGen controlado
- preview
- geração cirúrgica por arquivo
- integração com Git
- commits rastreáveis
- validação pós-geração
- bloqueios por papel
- docstrings obrigatórias
- análise de compatibilidade do provedor de IA com geração de código

Fora de escopo:
- geração massiva sem revisão
- reescrita ampla de projeto por default

### MVP 4 — Qualidade, entrega e evidência
Escopo:
- QA Readiness
- execução e revisão de testes
- exportação de evidências
- Documentação Viva
- Roadmap consistente
- Release Bundle
- auditoria ampliada
- métricas consolidadas

### MVP 5 — Hardening e operação
Escopo:
- segurança de secrets
- criptografia de PAT e credenciais
- robustez operacional
- observabilidade complementar
- rotinas de manutenção
- melhorias de rollout por cliente
- refinamentos de upgrade e deploy

---

## 8. Procedimento obrigatório antes de qualquer implementação

Antes de codar qualquer feature ou refatoração:

1. Identificar o MVP/fase ativa
2. Verificar se a solicitação pertence ao escopo da fase
3. Verificar blockers, criticals, contradições de contrato, duplicidade de papéis, testes quebrados e acoplamento excessivo
4. Se houver impedimento:
   - listar explicitamente
   - propor correção mínima
   - executar apenas a correção necessária
   - revalidar debt gates
5. Só então implementar algo novo

---

## 9. Debt gates obrigatórios

A fase atual só pode ser considerada quitada se:

- não houver blocker aberto
- não houver critical aberto
- não houver contradição entre código e contrato canônico
- não houver duplicidade funcional evidente
- não houver RBAC ambíguo
- não houver endpoint órfão da fase
- os testes da fase estiverem passando
- build do frontend estiver íntegro
- não houver TODO estrutural impedindo a próxima camada
- nenhuma mudança tiver quebrado comportamento existente sem migração explícita

Se qualquer item acima falhar:
- não avançar para o próximo MVP

---

## 10. Regras de contenção

Valem sempre:

- Não antecipar features de MVP futuro
- Não implementar telas, endpoints, entidades ou serviços fora do contrato da fase
- Não alterar RBAC sem atualizar o contrato soberano
- Não tocar em CodeGen, LiveDocs, Release Bundle, Billing ou multi-instância além do escopo da fase
- Não criar camadas extras de service/repository/manager/factory sem necessidade concreta
- Preferir correção local a refatoração sistêmica
- Toda refatoração deve estar ligada a dívida classificada
- Não substituir código funcional por abstração “mais bonita”
- Não reescrever arquivos grandes quando uma correção cirúrgica resolver
- Não promover documento histórico a contrato de implementação sem validação

---

## 11. Estratégia de trabalho do Claude

Claude deve agir como:
- arquiteto de saneamento incremental
- mantenedor disciplinado do contrato
- executor por fase
- analista de adequação de IA ao objetivo do cliente

Claude não deve agir como:
- autor livre do produto
- reconciliador silencioso de documentos conflitantes
- antecipador de escopo
- reescritor amplo de arquitetura sem necessidade

Fluxo esperado:
1. Diagnosticar
2. Classificar dívida
3. Corrigir blocker/critical
4. Revalidar
5. Só então expandir

---

## 12. Convenções técnicas

### Backend
- FastAPI + Python 3.11
- SQLAlchemy async
- Alembic para migração
- Tipagem explícita
- Serviços seguem padrão do projeto
- Operações assíncronas longas não devem bloquear requisição
- Nunca alterar contrato de endpoint existente sem justificativa e migração compatível

### Frontend
- React + TypeScript estrito
- Zustand para estado global
- React Query / TanStack Query para data fetching
- Tailwind CSS
- Não usar `any`
- Não usar estilos inline se já houver convenção utilitária
- Não quebrar rotas existentes sem migração planejada

#### Regra dura de deploy do frontend (armadilha recorrente)
O container `gca-frontend` roda `vite preview` sobre build estático — **não há hot-reload**. Backend (`gca-backend`) tem `uvicorn --reload` e recarrega sozinho; frontend **não**. Mudança em `frontend/**` sem rebuild = user vê build antigo e parece que o commit não teve efeito.

**Toda vez que um commit tocar `frontend/**`, Claude deve, antes de declarar a entrega como visível ao user:**
1. `docker exec gca-frontend npm run build` — regenera `dist/` com novos hashes.
2. `docker compose restart gca-frontend` (ou `docker restart gca-frontend`) — garante que o preview server aponte para o dist novo.
3. Informar o user: **hard refresh no browser** (`Ctrl+Shift+R` / `Cmd+Shift+R`) para bypassar cache do navegador.

Não cumprir esses 3 passos é a causa mais comum de "você disse que fez, mas eu continuo vendo o mesmo". Se o commit só toca backend, nenhum desses passos é necessário.

### Banco
- Não remover tabelas/colunas existentes sem fase de deprecação
- Toda mudança estrutural exige migração
- Isolamento principal por projeto
- Secrets nunca devem trafegar em plaintext nas respostas

---

## 13. Testes e validação

Antes e depois de qualquer fase:
- executar testes backend
- validar build frontend
- validar rotas críticas
- validar health checks relevantes

Se testes existentes falharem:
- a fase não está concluída

Todo novo serviço relevante deve vir com teste mínimo:
- criação
- leitura
- erro esperado
- permissão/acesso quando aplicável

---

## 14. Conflitos documentais conhecidos

Existem documentos históricos que:
- descrevem 7 papéis em vez de 5
- tratam capacidades futuras como se já estivessem ativas
- descrevem pipeline completo como se todo o produto já estivesse pronto
- misturam visão analítica com contrato de implementação

Regra:
- esses documentos podem ser usados como referência de visão
- eles NÃO autorizam implementação automática
- em conflito, prevalece o contrato soberano

---

## 15. Comportamento esperado nas respostas do Claude

Ao final de cada ciclo de trabalho, Claude deve informar:

1. fase/MVP avaliado
2. dívida encontrada
3. o que foi corrigido
4. o que continua pendente
5. se a fase pode ou não avançar
6. impacto da escolha de IA quando aplicável

Se a solicitação do usuário tentar furar o fatiamento:
- Claude deve sinalizar isso explicitamente
- propor correção mínima ou fase correta
- não avançar silenciosamente

---

## 16. Resumo executivo para Claude

Você não está construindo “qualquer app com IA”.
Você está construindo o GCA sob governança, com OCG como fonte de verdade, RBAC canônico de 5 papéis, evolução por MVP, dívida técnica controlada e escolha de IA subordinada ao objetivo real do cliente final.

Seu trabalho é:
- preservar coerência
- reduzir dívida
- impedir escopo inflado
- manter aderência ao contrato
- e ajudar o produto a evoluir por camadas estáveis
