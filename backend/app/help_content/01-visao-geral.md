# Visão geral & Glossário

O **GCA** (Gestão de Codificação Assistida / Gerenciador Central de Arquiteturas) é uma plataforma **instalável por cliente** para governança de projetos de TI assistida por IA. Cada cliente roda a própria instância; o isolamento principal é **por projeto** dentro da instância. O GCA não é SaaS compartilhado.

## Problema que o GCA resolve

Equipes iniciam projetos sem governança técnica formal. O resultado: escopo mal delimitado, arquitetura reativa, código gerado por IA sem rastreabilidade, documentação desatualizada antes de entrar em produção. O GCA conduz o projeto do questionário inicial até a geração de código assistida + documentação viva, mantendo em cada etapa:

- um objeto único de contexto (OCG) que evolui com cada ingestão;
- avaliação automática pelos 7 pilares (Gatekeeper);
- trilha de auditoria com hash chain SHA-256 encadeado;
- roteamento híbrido de IA por criticidade (baixa → modelo local; alta → modelo premium);
- compartimentalização estrita entre projetos.

## Fluxo canônico ponta-a-ponta

```
Questionário externo (49 perguntas)
    ↓ aprovação Admin
OCG gerado (8 agentes: Analyzer + 7 Specialists + Consolidator)
    ↓
Gatekeeper avalia 7 pilares → status READY / NEEDS_REVIEW / AT_RISK / BLOCKED
    ↓
Ingestão de documentos complementares (PDF, DOCX, XLSX, etc)
    ↓ Arguidor gera perguntas dirigidas
Resposta do GP → OCG expande ou contrai
    ↓
Backlog + Roadmap derivados do OCG
    ↓
CodeGen scaffold por linguagem (9 linguagens suportadas)
    ↓
QA Readiness + Tester Review
    ↓
Documentação Viva + Release Bundle
```

Detalhamento em [cap. 4 — Pipeline canônico](?section=04-pipeline).

## Glossário canônico (acrônimos mais usados no produto)

| Termo | Significado |
|---|---|
| **GCA** | Gestão de Codificação Assistida / Gerenciador Central de Arquiteturas |
| **OCG** | Objeto de Contexto Global — fonte única de verdade do projeto, com 12 seções canônicas, versionado |
| **RBAC** | Role-Based Access Control — 5 papéis canônicos no GCA (Admin, GP, Dev, Tester, QA) |
| **GP** | Gerente de Projeto — papel soberano do projeto no GCA |
| **DT** | Dívida Técnica — item rastreado formalmente no progress, classificado em Blocker/Critical/Major/Minor |
| **MVP** | Minimum Viable Product — ciclo canônico de entrega no GCA (§7.0 do contrato) |
| **P1-P7** | Os 7 pilares de avaliação do Gatekeeper: Conformidade, Arquitetura, Segurança, Performance, Testabilidade, Manutenção, Documentação |
| **DDL** | Data Definition Language — SQL que cria tabelas/índices; o GCA gera em 5 dialetos + Mongo |
| **FK** | Foreign Key — chave estrangeira entre tabelas |
| **PII** | Personally Identifiable Information — CPF/CNPJ/telefone/email detectados em documentos; quarentena obrigatória |
| **LLM** | Large Language Model — Anthropic Claude, OpenAI GPT, DeepSeek, Qwen local via Ollama, etc |
| **DLQ** | Dead Letter Queue — fila de tasks que falharam após todos os retries (Celery) |
| **ACK late** | Acknowledge late — worker só confirma a task após sucesso; se cai antes, Redis reenfileira |
| **CI / CD** | Continuous Integration / Continuous Delivery |
| **RFC** | Request For Comments / requisito funcional do questionário |
| **BRD** | Business Requirements Document |
| **ETL** | Extract / Transform / Load |
| **IaC** | Infrastructure as Code |
| **FTS5** | Full-Text Search v5 do SQLite — motor de busca do help (Fase 18.4) |
| **CMake** | Meta build system usado no scaffolder C++ (MVP 16) |
| **FetchContent** | Mecanismo do CMake que baixa dependências em build-time (usado para GoogleTest) |
| **GoogleTest** | Framework de testes canônico para C++ no GCA |
| **Celery** | Framework de fila assíncrona distribuída; broker Redis |
| **Flower** | UI de monitoramento do Celery (porta 5555) |
| **Prometheus** | Formato canônico de métricas scrape; endpoint `/api/v1/metrics/prometheus` |
| **Alembic, Flyway, Knex, TypeORM, EF Core, go-migrate, Laravel** | Frameworks de migration SQL gerados pelo DDL generator conforme a stack |
| **Fernet / AES-GCM** | Algoritmos de criptografia simétrica usados no Vault de secrets |

## Capítulos deste help

1. [Visão geral & Glossário](?section=01-visao-geral) — este capítulo.
2. [Instalação & primeiro setup](?section=02-instalacao)
3. [RBAC e papéis](?section=03-rbac)
4. [Pipeline canônico do GCA](?section=04-pipeline)
5. [OCG — Objeto de Contexto Global](?section=05-ocg)
6. [Área Administrativa](?section=06-admin)
7. [Área de Gestão de Projeto](?section=07-gp)
8. [Codegen e linguagens suportadas](?section=08-codegen)
9. [Observabilidade](?section=09-observabilidade)
10. [Solução de problemas](?section=10-troubleshooting)

## Princípios que governam o produto

- **Contrato canônico soberano**: `GCA_CANONICAL_CONTRACT.md` prevalece sobre qualquer outro documento. Toda implementação respeita §7.0 (MVP iterativo com autorização explícita), §10 (constraint de escopo e anti-alucinação), §4.1 (RBAC imutável).
- **OCG é a fonte única**: módulos do pipeline leem o OCG antes, operam sobre ele, atualizam depois. Nenhum módulo assume defaults invisíveis quando o OCG está incompleto.
- **Compartimentalização por projeto**: dados, credenciais, contexto — nada cruza entre projetos da mesma instância sem autorização explícita no contrato.
- **Roteamento híbrido de IA**: tarefa baixa criticidade aceita modelo local; alta criticidade exige modelo premium. Audit registra provider/model/motivo em cada chamada relevante.
- **Auditoria encadeada**: `audit_log_global` com hash chain SHA-256. Cada evento canônico (role, projeto, questionário, OCG, CodeGen) emite entrada com `previous_hash` + `current_hash` verificáveis.
