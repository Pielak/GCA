# Visão geral & Glossário

O **GCA** (Gestão de Codificação Assistida) conduz um projeto de TI do questionário inicial até a geração de código assistida por IA, mantendo em cada etapa um contexto único do projeto (o OCG), avaliação automática de qualidade, trilha de auditoria e compartimentalização estrita entre projetos.

## O que o GCA faz por você

- **Transforma um questionário técnico em um objeto de contexto (OCG)** que descreve o projeto em 12 dimensões: perfil, pilares de qualidade, stack recomendada, achados críticos, requisitos de teste, compliance, entregáveis, arquitetura, riscos, status de aprovação, modelo de dados.
- **Avalia a qualidade do contexto pelos 7 pilares** (Gatekeeper) e bloqueia o pipeline quando segurança ou compliance estão abaixo do limite mínimo.
- **Aceita ingestão de documentos complementares** (PDF, DOCX, XLSX, imagens) com extração rica + quarentena automática de PII.
- **Gera perguntas dirigidas** (Arguidor) quando detecta gaps ou conflitos no contexto, e usa as respostas para enriquecer o OCG.
- **Deriva backlog e roadmap** automaticamente a partir do OCG.
- **Gera código inicial (scaffold)** em 8 linguagens canônicas com DDL de banco incluído.
- **Produz planos de teste, executa, registra evidência**, com gate de aprovação pelo QA.
- **Mantém documentação viva** que se atualiza a cada mudança relevante — inclui ERS IEEE 830 regenerado no Git do projeto (`docs/ERS.md`) com matriz de rastreabilidade e glossário vivo.
- **Integra com ferramentas corporativas externas** (Jira/Trello pra tracker, Sonar/Snyk/gitleaks pra security, Slack pra notificação) via adapter pattern — GCA consome, não reimplementa.
- **Registra tudo em auditoria encadeada** verificável.

## Fluxo ponta-a-ponta

```
Questionário externo (49 perguntas)
   ↓ aprovação Admin
OCG gerado (8 agentes de IA trabalhando em paralelo)
   ↓
Gatekeeper avalia 7 pilares → READY | NEEDS_REVIEW | AT_RISK | BLOCKED
   ↓
Ingestão de documentos complementares
   ↓ Arguidor gera perguntas dirigidas
Resposta do GP → OCG expande ou contrai
   ↓
Backlog + Roadmap derivados automaticamente
   ↓
CodeGen scaffold por linguagem (8 linguagens canônicas)
   ↓
QA Readiness + Tester Review (gate qa:approve)
   ↓
Documentação Viva + ERS IEEE 830 + Release Bundle
   ↓
Integrações externas: Jira/Trello issue automática ·
Sonar/Snyk findings em P7 · Slack notifica eventos canônicos
```

Detalhamento em [cap. 4 — Pipeline](?section=04-pipeline).

## Modelo de deployment

O GCA é **instalável por cliente** — cada cliente roda a própria instância. Não é SaaS compartilhado. Dentro da instância, o isolamento principal é por projeto: dados, credenciais, contexto e documentos de um projeto nunca cruzam para outro.

## Quem usa o GCA

| Papel | Escopo | Responsabilidade principal |
|---|---|---|
| **Admin** | Instância inteira | Configurar a instância, governar usuários, aprovar projetos externos, ver auditoria global, gerenciar provedores de IA globais, backups, releases |
| **GP (Gerente de Projeto)** | Um projeto | Conduzir o projeto do questionário até o release, aprovar OCG e ingestões, convidar equipe, configurar IA do projeto. Tem acesso a todas as funcionalidades do projeto. |
| **Dev** | Um projeto | Implementar, rodar CodeGen, operar o repositório Git do projeto. Não aprova módulos. |
| **Tester** | Um projeto | Editar, executar e registrar testes. Não aprova execução (isso é QA). |
| **QA** | Um projeto | Revisar e aprovar execução de testes. Não edita conteúdo de teste. |

Detalhes dos papéis em [cap. 3 — RBAC](?section=03-rbac).

## Glossário de termos e acrônimos

### Conceitos centrais do GCA

| Termo | Significado |
|---|---|
| **OCG** | Objeto de Contexto Global — fonte única de verdade do projeto, com 12 seções, evoluindo conforme o projeto avança. |
| **GP** | Gerente de Projeto — papel soberano do projeto. |
| **RBAC** | Controle de acesso por papéis — 5 papéis canônicos (Admin, GP, Dev, Tester, QA). |
| **Pilares P1–P7** | Sete dimensões de avaliação da qualidade do contexto do projeto: Conformidade, Arquitetura, Segurança, Performance, Testabilidade, Manutenção, Documentação. |
| **Gatekeeper** | Sistema que avalia o OCG contra os 7 pilares e decide se o projeto está pronto, precisa revisão, está em risco ou bloqueado. |
| **Arguidor** | Agente que gera perguntas dirigidas quando detecta lacunas no contexto; alimenta o OCG com as respostas. |
| **Scaffold** | Estrutura inicial de projeto gerada automaticamente (CMakeLists, pom.xml, go.mod, etc) a partir do OCG. |
| **CodeGen** | Módulo que gera código (scaffold e arquivos individuais). |
| **Backlog vivo** | Lista de itens de trabalho derivada do OCG; regenera quando o OCG muda. |
| **Doc Viva** | Documentação do projeto atualizada a cada mudança relevante. |
| **Release Bundle** | Pacote de entrega com OCG version, commits, artefatos (schema.sql, seed.sql, migrations) e evidência de testes. |

### PII e quarentena

| Termo | Significado |
|---|---|
| **PII** | Informação pessoalmente identificável — CPF, CNPJ, cartão de crédito, telefone, email. Detectado automaticamente em documentos. |
| **Quarentena** | Estado de um documento com PII detectado: retido, não processado, até decisão do GP. |

### Banco de dados e código

| Termo | Significado |
|---|---|
| **DDL** | Data Definition Language — SQL que cria tabelas e índices. O GCA gera DDL automaticamente em 5 dialetos (PostgreSQL, MySQL, SQLite, SQL Server, Oracle) + MongoDB. |
| **FK** | Foreign Key — chave estrangeira que referencia outra tabela. |
| **Migration** | Script que evolui o schema do banco. O GCA gera em 7 formatos: Alembic, Flyway, Knex, TypeORM, Laravel, EF Core, go-migrate. |
| **Seed** | Dados mínimos inseridos na primeira carga do banco (usuário admin inicial, configurações padrão). |

### IA e processamento

| Termo | Significado |
|---|---|
| **LLM** | Large Language Model — modelo de linguagem (Claude, GPT, DeepSeek, Qwen, etc). |
| **Provedor de IA** | Empresa/serviço que fornece o LLM: Anthropic, OpenAI, DeepSeek, Ollama (local). |
| **Roteamento híbrido** | Política do GCA de usar modelo barato/local para tarefas simples e modelo premium para decisões críticas. |
| **Criticidade baixa/média/alta** | Classificação da tarefa de IA. Alta criticidade (consolidação de OCG, arquitetura, compliance) exige provedor premium. |
| **Fallback de IA** | Quando o provedor configurado falha (rate limit, 401, timeout), o sistema tenta o próximo da cadeia automaticamente. |

### Operação e infraestrutura

| Termo | Significado |
|---|---|
| **Celery** | Sistema de tarefas assíncronas — processa ingestões, gerações e reavaliações em segundo plano. |
| **Worker** | Processo que consome tarefas da fila. |
| **Flower** | Painel web em `localhost:5555` para ver estado da fila, workers ativos e tarefas que falharam. |
| **DLQ** | Dead Letter Queue — fila de tarefas que falharam após todos os retries. |
| **Prometheus** | Formato de métricas em texto; o GCA expõe em `/api/v1/metrics/prometheus` para integração com Grafana e similares. |

### ERS, glossário e rastreabilidade (MVP 19)

| Termo | Significado |
|---|---|
| **ERS** | Especificação de Requisitos de Software — documento IEEE 830-1998 regenerado automaticamente como `docs/ERS.md` no repositório Git do projeto. Versionamento nativo via `git log -p docs/ERS.md`. |
| **IEEE 830** | Norma da IEEE para estrutura canônica de ERS em 4 seções: Introdução, Descrição Geral, Requisitos Específicos, Matriz de Rastreabilidade. O GCA segue a versão 1998. |
| **BUSINESS_RULES** | Nova seção do OCG com regras de negócio do projeto (ex: "nota fiscal até 24h pós-venda"). Populada por agentes IA durante ingestão ou manualmente pelo GP. |
| **requirement_category** | Classificação canônica de cada `module_candidate`: `functional` (RF), `non_functional` (RNF) ou `business_rule` (BR). Manual pelo GP — agentes não classificam em V1. |
| **RF / RNF / BR** | Siglas canônicas para requisitos: Funcional, Não-Funcional, Regra de Negócio. Aparecem no ERS numerados (RF-001, RNF-014, BR-009). |
| **Glossário vivo** | Termos específicos do projeto (siglas, produtos, entidades) extraídos automaticamente por 4 heurísticas regex do corpus já persistido (módulos + Arguidor + OCG profile). GP aprova ou rejeita antes do termo entrar no ERS. |
| **Matriz de rastreabilidade** | Seção 4 do ERS cruzando cada requisito × test_spec × arquivo de código gerado. Query determinística sob demanda — sem view materializada. |

### Integrações externas (MVP 20)

| Termo | Significado |
|---|---|
| **Adapter-Port pattern** | Padrão arquitetural do MVP 20+: toda integração externa expõe uma porta ABC (`IssueTrackerPort`, `SecurityScannerPort`, `NotifierPort`) e adapters concretos implementam o contrato. GCA consome, não reimplementa. |
| **IssueTrackerPort** | Porta canônica que define o contrato pra trackers (Jira, Trello, futuro Linear/Asana). 6 operações: create_issue, update_status, get_issue, add_comment, verify_webhook, parse_webhook. |
| **SecurityScannerPort** | Porta canônica pra scanners (Sonar, Snyk, gitleaks). Duas operações: fetch_findings + normalize_severity. |
| **NotifierPort** | Porta canônica pra canais de notificação (Slack, futuro MS Teams). Operação única: send. Uni-direcional em V1. |
| **ExternalIssue** | Tabela que vincula módulos aprovados do GCA a issues no tracker externo configurado. UNIQUE (project_id, provider, external_id) garante idempotência de webhook. |
| **SecurityFinding** | Tabela que guarda findings consumidos de scanners externos. Status canônico: `open` / `fixed` / `accepted_risk`. |
| **Modo link-only** | Configuração por projeto (regulado BACEN/ANS) que faz o notifier Slack enviar só link pro GCA, sem payload sensível. |
| **accepted_risk** | Status que um finding de segurança recebe quando GP marca formalmente como risco aceito (justificativa mínima 10 caracteres). Não conta no cálculo determinístico de P7. |

### Auditoria e segurança

| Termo | Significado |
|---|---|
| **Hash chain SHA-256** | Cada evento de auditoria carrega o hash do evento anterior, criando uma cadeia verificável — qualquer alteração quebra a cadeia. |
| **Audit log global** | Trilha canônica de todos os eventos críticos: aprovações, mudanças de papel, mudanças no OCG, geração de código, EXTERNAL_ISSUE_CREATED, EXTERNAL_ISSUE_STATUS_SYNCED, LIVEDOCS_UPDATED (doc_type=ers), OCG_ROLLED_BACK, OCG_CONSOLIDATED. |
| **Vault** | Armazenamento criptografado de segredos (chaves de IA, tokens Git, credenciais de integração). Usa pgcrypto (pgp_sym_encrypt/decrypt). |

## Capítulos deste help

1. [Visão geral & Glossário](?section=01-visao-geral) — você está aqui.
2. [Instalação & primeiro setup](?section=02-instalacao) — do docker até o primeiro login.
3. [RBAC e papéis](?section=03-rbac) — os 5 papéis e o que cada um faz.
4. [Pipeline canônico do GCA](?section=04-pipeline) — fluxo ponta-a-ponta detalhado.
5. [OCG — Objeto de Contexto Global](?section=05-ocg) — a peça central do produto.
6. [Área Administrativa](?section=06-admin) — tour do que Admin acessa.
7. [Área de Gestão de Projeto](?section=07-gp) — tour do que GP acessa.
8. [Codegen e linguagens suportadas](?section=08-codegen) — as 8 linguagens e o DDL generator.
9. [Observabilidade](?section=09-observabilidade) — saúde, métricas, auditoria, monitoramento.
10. [Solução de problemas](?section=10-troubleshooting) — FAQs com diagnósticos práticos.
11. [Integrações Externas](?section=11-integracoes) — Jira/Trello, Sonar/Snyk/gitleaks, Slack.
