# GCA — Documento Completo de Requisitos

**Versão:** 1.0  
**Data:** 2026-04-30  
**Objetivo:** Consolidar todos os requisitos do GCA (funcionais, não-funcionais, negócios, exceções, fluxos, configuração, análise e roadmap) em um único documento para avaliação estratégica e melhoria contínua.

---

## 1. Objetivo do GCA

O **GCA (Gestão de Codificação Assistida / Gerenciador Central de Arquiteturas)** é uma plataforma **instalável por cliente** (on-premises) para governança de projetos de TI assistida por IA.

### 1.1 Propósito Principal
- Governança estruturada de decisões arquiteturais e de implementação de software
- Análise assistida por IA de documentos, requisitos e decisões
- Validação de conformidade com padrões e riscos (compliance, segurança, arquitetura)
- Geração de código assistido a partir de especificação estruturada
- Rastreabilidade completa de decisões e código gerado (auditoria)

### 1.2 Diferencial Técnico
- **OCG (Objeto de Contexto Global)** como fonte única de verdade do projeto
- **Pipeline de 5 personas LLM** (GP, Arquiteto, DBA, Dev Sr, QA) validando em paralelo
- **Gatekeeper** — arbitragem de riscos de módulos candidatos
- **CodeGen** — scaffolding e geração estruturada respeitando OCG
- **Documentação Viva** — especificação versionada reativa ao OCG

---

## 2. Definição do Produto

### 2.1 Modelo de Deployment
- **Instalável por cliente** — on-premises, não SaaS multi-tenant compartilhado
- Uma instância por cliente
- Cliente é soberano dos seus dados, credenciais e modelos de IA

### 2.2 Modelo de Isolamento
- **Isolamento principal: por projeto** dentro da instância
- Sem compartilhamento de OCG, artefatos, contexto ou credenciais entre projetos
- Sem compartilhamento entre instâncias
- Toda query de projeto inclui `project_id` no WHERE (invariante)

### 2.3 Modelo de IA
- **Não impõe provedor único** — cliente escolhe suas chaves, provedores e modelos
- Oferece análise de adequação (objetivo, custo, latência, privacidade)
- Suporta **roteamento híbrido** (modelos diferentes por criticidade/tarefa)
- Classificação de criticidade:
  - **Baixa:** Ollama, modelos locais (classificação, extração, sumarização)
  - **Média:** modelos remotos com validação (perguntas preliminares, pré-análise)
  - **Alta:** modelos premium (consolidação OCG, arbitragem, arquitetura, segurança, codegen crítico)
- Nenhum modelo de baixa criticidade decide sozinho sobre OCG final, compliance ou arquitetura

---

## 3. Papéis & Governo

### 3.1 Papéis RBAC Humanos (Conjunto A — 5 papéis)

| Papel | Sistema | Responsabilidade | Autoridade | Acesso |
|---|---|---|---|---|
| **Admin** | Sistema (user.is_admin) | Operar instância, configurar provedores/SMTP/políticas, aprovar/liberar projetos | Única no sistema | Todos os projetos + settings globais |
| **GP** | Projeto (role: gp) | Conduzir projeto, aprovar módulos/OCG/decisões, convidar time, manter credenciais | Soberano do projeto | Todas funcionalidades do projeto |
| **Dev** | Projeto (role: dev) | Implementar código, operar ingestão/Arguidor/CodeGen, corrigir problemas | Técnica | Ingestão, CodeGen, commits (quando liberado) |
| **Tester** | Projeto (role: tester) | Criar/editar/executar testes, registrar evidências | Execução | Testes, specs, logs |
| **QA** | Projeto (role: qa) | Revisar/aprovar resultados e execuções, validar qualidade final | Aprovação | Revisão, não edita testes |

**Papéis não canônicos nesta versão:** Tech Lead, Compliance, Stakeholder, Viewer, Dev Sênior/Pleno como roles — podem aparecer em documentação histórica, mas não implementar como roles do sistema.

### 3.2 Personas de Validação (Conjunto B — 8 agentes LLM)

**Nota importante:** são agentes de IA, NÃO papéis de usuário humano. Não confundir com o Conjunto A acima.

| Persona | Tag | Responsabilidade | Entrada | Saída |
|---|---|---|---|---|
| **Auditor** | AUD | Auditoria documental + roteamento + briefing inicial | Documentos crus | Roteamento para especialistas |
| **Gerente de Projetos** | GP | Escopo, viabilidade, ROI, stakeholders, riscos de negócio | Questionário, OCG parcial | Avaliação de viabilidade |
| **Arquiteto** | ARQ | Stack, padrões, integrações, NFRs, trade-offs técnicos | Requisitos, contexto técnico | Recomendações arquiteturais |
| **DBA** | DBA | Modelo de dados, retenção, LGPD, performance de query, evolução de schema | Schema candidato, requisitos de dados | Validação de modelo, riscos LGPD |
| **Dev Sr.** | DEV | Implementabilidade, dependências, debt técnico, estimativa | Especificação, arquitetura | Viabilidade técnica, riscos |
| **QA** | QA | Testes, cobertura, BDD, estratégia de teste, regras de aceitação | Especificação, módulos | Plano de testes, critérios de aceite |
| **UX** | UX | Jornada de usuário, acessibilidade, microcopy, fluxos | Requisitos funcionais | Padrões de interação, jornadas |
| **UI** | UI | Design system, responsividade, tokens de design, estados visuais | Requisitos de jornada | Componentes, tokens, espaçamento |

**Fluxo de validação:** Auditor recebe documentos → roteiam para especialistas em paralelo → consolidação de achados → OCG é atualizado → Gatekeeper arbitra riscos → aprovação de módulos.

---

## 4. Requisitos Funcionais

### 4.1 Gestão de Projetos & Membros

#### RF-001 Criar Projeto
- **Ator:** Admin
- **Entrada:** nome, descrição, tipo (backend, frontend, fullstack, etc)
- **Saída:** projeto criado com OCG vazio, questionnaire pendente
- **Validações:** nome único, não vazio
- **Regra de Negócio:** novo projeto começa com status `pending_approval` até Admin liberar; GP é o criador

#### RF-002 Listar Projetos
- **Ator:** Admin (todos), GP/Dev/Tester/QA (seus próprios)
- **Filtros:** status, tipo, data de criação, members ativos
- **Paginação:** obrigatória (padrão 20 itens)
- **Segurança:** user vê apenas seus projetos (role-based)

#### RF-003 Convidar Membro
- **Ator:** GP
- **Entrada:** email, role (dev|tester|qa)
- **Saída:** convite gerado, senha temporária enviada (RF-001: 10 chars, 1 maiúscula, 1 dígito, 1 especial)
- **Validações:** role válido, email não duplicado (ativo no projeto)
- **Regra de Negócio:** membro tem `joined_at = NULL` até aceitar convite

#### RF-004 Listar Membros Ativos
- **Ator:** Admin (todos), GP (seus), Dev/Tester/QA (seus)
- **Filtro:** `is_active AND joined_at IS NOT NULL`
- **Helper:** `is_active_integrated_member()` obrigatório
- **Segurança:** não vaza convites pendentes

#### RF-005 Alterar Role de Membro
- **Ator:** GP
- **Restrição:** não pode remover a si mesmo; não pode downgrade de role via UI (removê-lo e re-convidar é padrão)
- **Validações:** role novo válido

#### RF-006 Remover Membro
- **Ator:** GP (de si não)
- **Efeito:** `is_active = false`, dados históricos preservados
- **Auditoria:** registra quem removeu quando

### 4.2 Questionário Inicial (Estático → Dinâmico)

#### RF-010 Submeter Questionário
- **Ator:** GP (ou Dev/Tester/QA delegado)
- **Entrada:** respostas estruturadas (60+ perguntas)
- **Saída:** OCG inicial gerado, ingestão desbloqueada
- **Validações:** respostas obrigatórias preenchidas, tipos válidos
- **Fluxo:** POST `/questionnaires/` → `questionnaire_service.validate()` → `ocg_service.generate_initial()` → trigger N8N → análise de personas

#### RF-011 Visualizar Status Questionário
- **Ator:** projeto
- **Saída:** status atual (draft|submitted|under_review|approved|rejected)
- **Campos adicionais:** % completo, erros de validação, últimas respostas

#### RF-012 Gerar Perguntas Dinâmicas de Acompanhamento
- **Ator:** LLM (Auditor persona)
- **Gatilho:** após análise de personas, lacunas detectadas
- **Entrada:** OCG parcial, riscos flagged
- **Saída:** questão estruturada + contexto
- **Exemplo:** se AI_MODEL não foi respondido mas Architecture menciona "ML-heavy", gera pergunta "Qual IA será usada?"

#### RF-013 Submeter Respostas de Acompanhamento
- **Ator:** GP
- **Entrada:** resposta a pergunta dinâmica
- **Saída:** OCG atualizado, Gatekeeper recalcula riscos
- **Validação:** pergunta ainda aberta

### 4.3 Ingestão de Documentos

#### RF-020 Upload de Documento
- **Ator:** Dev/GP
- **Formatos:** PDF, DOCX, TXT, código-fonte
- **Limite:** 100 MB por arquivo, 1 GB por projeto/mês (configurável)
- **Saída:** documento armazenado, análise queued
- **Metadata:** filename, mime-type, upload_time, uploader, status

#### RF-021 Listar Documentos Ingeridos
- **Ator:** projeto
- **Filtros:** tipo, status (pending|analyzed|quarantined), data
- **Paginação:** obrigatória
- **Exibição:** preview de texto (primeiras 500 chars)

#### RF-022 Analisar Documento (Personas Paralelas)
- **Ator:** Auditor + 5 personas
- **Fluxo:**
  1. Auditor valida estrutura, detecta linguagem, classifica tipo
  2. GP valida escopo de negócio
  3. Arquiteto valida stack/padrões
  4. DBA valida dados/schema
  5. Dev Sr valida implementabilidade
  6. QA valida testabilidade
- **Saída:** análise consolidada por persona, conflitos flagged
- **Timeout:** 120s por persona (configurável)
- **Fallback:** se persona falha, questão é apresentada ao humano (HITL)

#### RF-023 Quarentena de Documento
- ** Gatilho:** análise contradiz OCG existente
- **Efeito:** documento isolado, OCG não é afetado
- **Saída:** aviso ao GP para revisão manual + esclarecimento
- **Resolução:** GP pode (a) descartar, (b) merging manual via override, (c) pedir re-análise

### 4.4 OCG (Objeto de Contexto Global)

#### RF-030 Inicializar OCG
- **Ator:** Sistema (após questionário aprovado)
- **Entrada:** respostas de questionário validadas
- **Saída:** OCG com 12 seções preenchidas conforme defaults
- **Seções:** VISION, STACK_RECOMMENDATION, DATA_MODEL, SECURITY_MODEL, COMPLIANCE_REQUIREMENTS, ARCHITECTURE_PATTERNS, DEPLOYMENT, TEAM_STRUCTURE, INTEGRATION_POINTS, MONITORING_LOGGING, ROADMAP_BACKLOG, UNRESOLVED_RISKS
- **Schema:** versionado, imutável por versão (v0, v1, v2...)
- **Auditoria:** histórico completo com timestamp, autor, delta

#### RF-031 Consultar OCG
- **Ator:** qualquer membro do projeto
- **Entrada:** project_id, versão (default: latest)
- **Saída:** OCG estruturado em JSON/YAML
- **Validação:** member ativo

#### RF-032 Atualizar OCG
- **Ator:** Sistema (automático de personas) ou GP (manual via override)
- **Regra:** OCG só expande; nunca contrai
- **Entrada:** delta (seção, campo, novo valor)
- **Saída:** nova versão criada, versionamento incremental
- **Auditoria:** quem, quando, por quê (source: persona|manual|sistema)
- **Propagação:** mudanças OCG triggam:
  1. Recalcular riscos Gatekeeper
  2. Regenerar test specs (se data model mudou)
  3. Alertar módulos candidatos dependentes

#### RF-033 Compactar OCG
- **Ator:** GP ou sistema
- **Gatilho:** >50 versões acumuladas ou manual
- **Efeito:** compacta histórico, mantém rastreabilidade via audit log
- **Saída:** versão compactada legível

#### RF-034 Rollback de OCG
- **Ator:** GP (autorizado via settings)
- **Entrada:** version_id
- **Saída:** OCG volta para versão anterior
- **Auditoria:** registra quem rollback quando
- **Validação:** só até 5 versões anteriores (default configurável)

#### RF-035 Consolidar OCG
- **Ator:** Sistema ou GP
- **Gatilho:** após análise de personas, para arbitrar conflitos
- **Entrada:** versão parcial com conflitos
- **Saída:** OCG consolidado com decisão registrada
- **Modelo:** algoritmo ConflictDetector determina
  - conflitos críticos (rejeita consolidação, enfileira para human review)
  - conflitos leves (registra como nota)
  - divergências múltiplas sobre mesmo campo (mantém histórico, toma último)

### 4.5 Gatekeeper (Aprovação de Módulos)

#### RF-040 Criar Módulos Candidatos
- **Ator:** Sistema (detecta de OCG/CodeGen) ou GP (manual)
- **Entrada:** nome, escopo, deps, riscos
- **Saída:** módulo em status `draft`
- **Métricas:** 7 pilares (Conformidade, Segurança, Performance, Integrabilidade, Testabilidade, Documentação, Viabilidade)

#### RF-041 Avaliar Módulo contra Gatekeeper
- **Ator:** Sistema (automático)
- **Gatilho:** módulo submetido para aprovação
- **Fluxo:**
  1. Auditar 7 pilares
  2. Calcular score por pilar (0-100)
  3. Aplicar thresholds (Conformidade < 60 = BLOCKER)
  4. Gerar relatório de achados
- **Saída:** status (pass|conditional|block) + itens de remediação

#### RF-042 Navegar Achados Gatekeeper
- **Ator:** GP/Dev
- **Entrada:** module_id
- **Saída:** lista de achados estruturada (categoria, severidade, ação recomendada)
- **Ações disponíveis:**
  - Resolver (marcar como feito)
  - Ignore (exceção documentada)
  - Escalar (para persona específica)
  - Defer (para próxima versão)

#### RF-043 Aprovar Módulo
- **Ator:** GP (ou QA delegado)
- **Pré-condição:** status != block (ou block tem exceção aprovada)
- **Efeito:** módulo passa para status `approved`, libera CodeGen
- **Auditoria:** registra quem aprovou quando

#### RF-044 Rejeitar Módulo
- **Ator:** GP
- **Entrada:** motivo
- **Efeito:** módulo retorna a status `draft`, dev deve remediar
- **Ciclo:** max 3 rejeições antes de escalar para Admin

### 4.6 Code Generation (Scaffolding)

#### RF-050 Gerar Plano de Scaffolding
- **Ator:** Dev/GP
- **Entrada:** módulo aprovado, target language (Python, TypeScript, Go, C++, Java), framework (Django, FastAPI, Next.js, etc)
- **Saída:** plano estruturado (arquivos a gerar, templates, dependências)
- **Detalhe:** `scaffold_planner.py` + `codegen_prompt_builder.py` = prompt engineer LLM
- **Modelo:** crítico (Opus recomendado para scaffold estrutural)

#### RF-051 Gerar Código de Item
- **Ator:** Sistema (CodeGen service)
- **Entrada:** scaffolding item spec
- **Saída:** código gerado (função, classe, arquivo estruturado)
- **Validação:** 
  - Type-safe (se TypeScript, roda tsc)
  - Imports resolvem
  - Estrutura bate com spec
- **Fallback:** se geração falha, user vê diff esperado + prompt falhado para manual fix

#### RF-052 Aplicar Scaffold no Repositório
- **Ator:** Dev/GP
- **Entrada:** scaffold_run_id, arquivos aprovados para aplicar
- **Saída:** mudanças commitadas no branch do projeto
- **Git:** automático via `git_service.commit()` com mensagem estruturada
- **Validação:**
  - Sem conflitos merge
  - Branch está atualizado com remote
  - Credenciais Git válidas

#### RF-053 Visualizar Diff
- **Ator:** Dev/QA
- **Entrada:** scaffold_run_id (ou historic commit)
- **Saída:** diff estruturado lado-a-lado
- **Opções:** whitespace ignorado, renamed files detectadas, binary files sinalizadas

### 4.7 Planos de Teste & Test Specs

#### RF-060 Gerar Test Specs
- **Ator:** Sistema (test_spec_generator_service) ou QA
- **Entrada:** módulo, cobertura alvo (unit|integration|e2e)
- **Saída:** specs estruturados em BDD (Given/When/Then) ou framework nativo
- **Detalhe por linguagem:**
  - **Python:** pytest com fixtures, parametrize
  - **TypeScript:** Jest, Vitest, supertest (e2e)
  - **Go:** testing.T, table-driven tests
  - **C++:** GoogleTest, EXPECT_EQ/EXPECT_THAT
  - **Java:** JUnit 5, fixtures, assertions
- **Cobertura alvo:** unit 80%+, integration 60%+, e2e 40%+
- **Metadata:** `provenance_json` registra gerador, modelo, data

#### RF-061 Criar Teste Manual
- **Ator:** Tester
- **Entrada:** spec, evidência (screenshot, log, resultado)
- **Saída:** teste criado com status `manual`
- **Validação:** não pode editar spec gerada (read-only)

#### RF-062 Executar Plano de Testes
- **Ator:** Tester/QA
- **Entrada:** test_plan_id, módulo, environment
- **Saída:** resultados estruturados (passed, failed, skipped, error)
- **Relatório:** cobertura, tempo, artefatos (logs, screenshots, videos quando aplicável)
- **Integração:** CI/CD pode disparar automaticamente pós-scaffold

#### RF-063 Revisar & Aprovar Teste
- **Ator:** QA (nunca edita conteúdo)
- **Entrada:** test_execution_result
- **Ações:** approve, request_retest, reject
- **Blocker:** falha em teste crítico bloqueia aprovação de módulo

### 4.8 Documentação Viva

#### RF-070 Gerar ERS (Especificação de Requisitos de Software)
- **Ator:** Sistema (após consolidação OCG)
- **Entrada:** OCG final, módulos aprovados, test specs
- **Saída:** `docs/ERS.md` no repositório do projeto
- **Conteúdo IEEE 830:**
  - Histórico de revisão
  - Matriz de rastreabilidade (requisito → módulo → teste)
  - Glossário
  - Requisitos funcionais/não-funcionais categorizados
  - Restrições e regras de negócio
  - Protótipos de interface (link para Figma, se disponível)
- **Versionamento:** comitado no git (git log -p docs/ERS.md resolve histórico)
- **Regeneração:** automática após mudança em OCG ou teste aprovado

#### RF-071 Gerar Documentação Técnica
- **Ator:** Sistema
- **Saída:** `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATABASE.md`
- **Conteúdo:**
  - Diagramas C4 (contexto, containers, componentes, código)
  - Decisões arquiteturais (ADRs)
  - APIs (OpenAPI/Swagger)
  - Schema de dados (ER diagram)
  - Padrões implementados
- **Atualização:** reativa a mudanças de módulos aprovados

#### RF-072 Gerar Documentação de Operação
- **Ator:** Sistema
- **Saída:** `docs/OPERATIONS.md`, `docs/DEPLOYMENT.md`, `docs/RUNBOOKS.md`
- **Conteúdo:**
  - Guia de deployment (Kubernetes, Docker, bare metal)
  - Runbooks de incidente
  - Métricas monitoradas
  - Alertas configurados
  - Procedimentos de backup/restore

### 4.9 Integração com Sistemas Externos

#### RF-080 Conector Jira
- **Config:** API key, base URL
- **Ações:**
  - Sincronizar requisitos → issues Jira
  - Atualizar issue quando teste falha
  - Vincular commits aos issues
- **Segurança:** credenciais em `VaultService` (Fernet-encrypted)

#### RF-081 Conector Slack
- **Config:** webhook URL
- **Eventos:**
  - Módulo aprovado / reprovado
  - Teste crítico falha
  - Rollback OCG executado
  - Novo convite gerado
- **Segurança:** não loga mensagens de erro em público

#### RF-082 Conector Git
- **Config:** PAT (personal access token), base repository URL
- **Ações:**
  - Clonar repo do projeto
  - Commit de scaffold, ERS, docs
  - Branch protection / code review automation
- **Segurança:** PAT em vault com prefixo `fernet:v1:`

#### RF-083 Scanner de Segurança (Gitleaks, Snyk, Sonar)
- **Trigger:** pós-commit (scaffold)
- **Entrada:** código gerado
- **Saída:** vulnerabilidades detectadas, severidade, remediação
- **Integração:** Gatekeeper pilar de Segurança é atualizado

### 4.10 Área de Administração

#### RF-090 Painel de Admin
- **Ator:** Admin
- **Acesso:** route guard `require_admin()`
- **Widgets:**
  - Estatísticas globais (# projetos, # usuários, # análises)
  - Atividade recente (últimos commits, análises)
  - Saúde do sistema (CPU, memória, DB, Celery workers)
  - Segurança (acessos suspeitos, failed logins)

#### RF-091 Gerenciar Usuários
- **Ator:** Admin
- **Ações:**
  - Listar usuários ativos/inativos
  - Reset password (gera temporária)
  - Lock/unlock usuário
  - Promover/rebaixar para admin
  - Ver login history

#### RF-092 Gerenciar Projetos
- **Ator:** Admin
- **Ações:**
  - Listar projetos pendentes aprovação
  - Aprovar projeto (`status = active`)
  - Rejeitar projeto (GP é notificado)
  - Ver atividade do projeto
  - Forçar reprocessamento de análise (debug)
  - Excluir projeto (soft delete)

#### RF-093 Configurar Provedores de IA
- **Ator:** Admin
- **Entrada:** tipo (Anthropic, OpenAI, DeepSeek, Ollama), API key, modelo recomendado
- **Armazenamento:** `SystemSettings` table, credenciais em vault
- **Validação:** test API call antes de salvar
- **Saída:** opção aparece em `/projects/:id/settings > IA`

#### RF-094 Configurar Política de IA por Criticidade
- **Ator:** Admin
- **Entrada:** mapeamento task_type → provider/model/criticality
- **Exemplo:**
  ```
  {
    "task.ocg.consolidate": { 
      "criticality": "high",
      "recommended_provider": "anthropic",
      "fallback": "openai"
    },
    "task.test.gen_specs": {
      "criticality": "medium",
      "recommended_provider": "openai"
    }
  }
  ```
- **Saída:** salvo em `SystemSettings.llm_policy_json`

#### RF-095 Auditar Atividades Globais
- **Ator:** Admin
- **Filtros:** usuário, projeto, tipo (login, create, update, delete), data
- **Paginação:** obrigatória
- **Exportação:** CSV, JSON
- **Retenção:** 2 anos (configurável)

#### RF-096 Configurar SMTP & Notificações
- **Ator:** Admin
- **Entrada:** host, port, auth, from_email
- **Testes:** enviar email de teste
- **Validação:** falha se SMTP indisponível
- **Templates:** convite, aprovação, falha crítica

#### RF-097 Gerenciar Secrets Globais
- **Ator:** Admin
- **Ações:** CRUD de variáveis de ambiente (não exibir valor, apenas indicador se configurado)
- **Exemplos:** API keys de scanners, webhook URLs
- **Armazenamento:** vault com FERNET

---

## 5. Requisitos Não-Funcionais

### 5.1 Performance

| Métrica | Alvo | Contexto |
|---------|------|---------|
| **Resposta questionário** | <2s | 60 perguntas, <100 caracteres cada |
| **Upload documento** | <500ms | <100 MB, transfer rate depend de rede |
| **Análise documento (5 personas)** | <120s | Timeout por persona 120s, paralelo |
| **Consolidação OCG** | <30s | <12 seções, sem I/O externo |
| **Gerar test specs** | <60s | 50 testes, LLM call incluído |
| **Geração de código** | <180s | scaffolding complexo (3+ módulos) |
| **Query projeto** | <1s | 50+ campos, com joins |
| **Render ERS** | <5s | <500 requisitos mapeados |

### 5.2 Escalabilidade

- **Concorrência:** suportar 100+ usuários simultâneos (test via load testing)
- **Armazenamento:** <1 TB por projeto (limite soft, alertado em 800 GB)
- **Revisions:** histórico OCG compactado após 50 versões
- **Fila:** Celery + Redis com dead-letter queue (DLQ)
- **Banco:** PostgreSQL 13+, com connection pooling (min 5, max 50)

### 5.3 Confiabilidade

- **Uptime:** 99.5% mensal (planejado para on-premises)
- **Backup:** diário, retenção 30 dias
- **Disaster recovery:** procedimento documentado em `docs/RUNBOOKS.md`
- **Rollback OCG:** último 5 versões sempre recuperáveis
- **Retry logic:** fail-fast vs resilience trade-off por criticidade
  - Baixa: 3 retries com jitter exponencial
  - Alta: fail-fast, enfileira para HITL

### 5.4 Segurança

- **Autenticação:** OAuth2 recomendado, fallback local (username/password com bcrypt 12 rounds)
- **Autorização:** RBAC por projeto + recurso (granularidade: operação + objeto)
- **Secrets:** Fernet AES-128 (Python cryptography)
- **Git PAT:** prefixo obrigatório `fernet:v1:`, nunca logado nem exibido
- **Senhas temporárias:** `generate_temporary_password()` — 10 chars, 1 maiúscula, 1 dígito, 1 especial
- **Auditoria:** toda ação registra user, timestamp, IP, mudança (diff se aplicável)
- **Rate limiting:** API endpoints (100 req/min por IP, bursts de 20)
- **CORS:** configurável, default restritivo (mesmo origin)
- **HTTPS:** enforced (certificado auto-signed ok em on-premises)
- **SQL injection:** prepared statements + ORM (SQLAlchemy), sem string interpolation
- **XSS:** sanitização de entrada + CSP headers
- **CSRF:** tokens CSRF em formulários, SameSite=Strict em cookies

### 5.5 Auditoria & Compliance

- **LGPD:** 
  - Campo `data_retention_days` em OCG (default 365)
  - Soft delete de usuários (preserva histórico)
  - Direito ao esquecimento: script de anonimização de dados pessoais
  - Consentimento: checkboxes no onboarding
- **Conformidade:** Gatekeeper pilar de Conformidade, threshold 60 = blocker
- **PII (Personally Identifiable Information):** não logar credenciais, senhas, tokens, emails em debug
- **Rastreabilidade:** OCG com versionamento completo, git log com commits estruturados

### 5.6 Usabilidade

- **UI Language:** pt-BR obrigatório (termos técnicos em EN)
- **Acessibilidade:** WCAG 2.1 AA (keyboard navigation, screen reader support)
- **Responsividade:** mobile-first, 320px+ (tablets 768px+, desktop 1024px+)
- **Dark mode:** optional, localStorage persisted
- **Help integrado:** `/admin/help` e `/projects/:id/help` com busca full-text (MVP 18)

---

## 6. Política de IA (Hybrid Routing by Criticality)

### 6.1 Classificação de Tarefas

| Criticidade | Exemplos | Provider Recomendado | Fallback | Obs |
|---|---|---|---|---|
| **Baixa** | Extração de campos, sumarização curta, normalização | Ollama, GPT-3.5 | — | Custo otimizado |
| **Média** | Perguntas preliminares, pré-análise, agrupamento temático | OpenAI, DeepSeek | Ollama com validação | Rápido + confiável |
| **Alta** | OCG consolidação, arbitragem, arquitetura crítica, compliance, codegen estrutural | Opus 4.7, Claude 4.6 | — | Premium obrigatório; sem fallback automático |

### 6.2 Política de Roteamento

```python
# Pseudo-código
def resolve_provider(task_type: str, project_id: int):
    """
    Resolve provider para task baseado em:
    1. Criticidade da tarefa (hardcoded)
    2. Configuração do cliente (project_settings)
    3. Disponibilidade (health check)
    """
    criticality = TASK_CRITICALITY[task_type]  # high|medium|low
    project_config = ProjectSettings.get(project_id)
    
    if criticality == 'high':
        provider = project_config.premium_provider  # Obs: recusar genérico
        if not provider:
            raise ValueError("Projeto sem provider premium configurado")
        return validate_provider(provider)
    
    elif criticality == 'medium':
        primary = project_config.primary_provider or 'openai'
        secondary = project_config.secondary_provider or 'ollama'
        return primary if healthy(primary) else secondary
    
    else:  # low
        return project_config.local_provider or 'ollama'
```

### 6.3 Registros de Uso

Toda invocação LLM registra:
- **Provider/Model:** ex "anthropic/claude-opus-4-7"
- **Task type:** ex "ocg.consolidate"
- **Criticality:** high|medium|low
- **Cost:** tokens (input+output), R$ estimado
- **Latency:** segundos
- **Status:** success|failure (+ error code)
- **Auditoria:** user, project, timestamp

---

## 7. Tratamento de Exceções

### 7.1 Erros Críticos (Falha Imediata)

| Código | Causa | Ação |
|--------|-------|------|
| **401 Unauthorized** | Token expirado, chave inválida | Retry login / regenerar PAT |
| **403 Forbidden** | Permissão insuficiente (RBAC) | Notificar GP ou Admin |
| **500 Database Unreachable** | DB offline, connection fail | PARAR. Alert oncall. Não tentar fallback. |
| **500 LLM Auth Failed** | API key inválida para provider | PARAR. User verifica settings. Não fallback automático. |
| **FileNotFoundError (tabela, migração)** | Schema não está atualizado | PARAR. Alert: rode `alembic upgrade head`. |

**Regra dura:** §0 CLAUDE.md — em caso de 401/403/não encontrado — PARAR, reportar erro literal, perguntar.

### 7.2 Erros Recuperáveis

| Código | Causa | Retry | Timeout | Fallback |
|--------|-------|-------|---------|----------|
| **429 Rate Limited** | API quota atingida | Sim (exponential backoff: 2s, 4s, 8s) | 30s | Notify user "aguarde 1 min" |
| **503 Service Unavailable** | Provider sobrecarregado | Sim (3 tentativas) | 120s | Média/Baixa: fallback provider; Alta: HITL |
| **Timeout LLM** | Resposta demorada | Sim (2 tentativas) | 120s | Baixa: cancel; Média: HITL; Alta: HITL |
| **Storage Quota Exceeded** | Project >1 GB | Não retry | — | Notificar GP, bloquear uploads até cleanup |
| **Git Merge Conflict** | Branch desatualizado | Não retry | — | Exibir diff, pedir manual resolution |

### 7.3 Quarentena & HITL (Human-in-the-Loop)

**Quando usar HITL:**
1. Análise de personas retorna conflito crítico (2+ personas divergem >50%)
2. Gatekeeper blocker sem exceção aprovada
3. Documento entra em quarentena (contradiz OCG)
4. Erro não-recuperável em crítico (arquivo gerado tem syntax error)
5. LLM timeout em alta criticidade

**Processo:**
```
1. Sistema marca recurso como "awaiting_human_review"
2. Notifica GP via email + dashboard
3. Apresenta problema estruturado + contexto
4. GP escolhe: corrigir, ignorar, escalar
5. Registra decisão em auditoria
```

### 7.4 Deadletter Queue (DLQ)

**Estrutura:**
```python
@task
def analyze_document_task(doc_id: int):
    try:
        # normal flow
    except Exception as e:
        if is_retryable(e):
            raise Retry(countdown=2**retry_count)
        else:
            # move to DLQ
            failed_task = FailedTask(
                task_id=analyze_document_task.id,
                doc_id=doc_id,
                error=str(e),
                traceback=traceback.format_exc()
            )
            db.add(failed_task)
            db.commit()
            notify_admin(failed_task)
```

**Admin pode:**
- Ver DLQ via `/admin/dead-letter-queue`
- Revisar erro + contexto
- Retry manualmente (botão "Retry")
- Mark resolved (logging da fix)
- Export para debugging

---

## 8. Glossário Técnico

| Termo | Definição | Contexto |
|-------|-----------|---------|
| **OCG** | Objeto de Contexto Global | Fonte única de verdade do projeto, 12 seções estruturadas |
| **Gatekeeper** | Sistema de aprovação de módulos | Valida 7 pilares (Conformidade, Segurança, ...), threshold blocker |
| **HITL** | Human-In-The-Loop | Decisão não-automatizável enfileirada para human review |
| **DLQ** | Dead-Letter Queue | Fila de tarefas que falharam permanentemente, requer análise |
| **Persona** | Agente LLM especialista | Auditor, GP, Arquiteto, DBA, Dev Sr, QA, UX, UI (8 tipos) |
| **Papel (Role)** | Posição humana no sistema | Admin, GP, Dev, Tester, QA (5 tipos) |
| **Scaffold** | Estrutura de código gerada | Projeto skeleton, módulo, ou arquivo padrão |
| **ERS** | Especificação de Requisitos de Software | IEEE 830, documento versionado em git |
| **Teste Spec** | Teste estruturado em formato BDD/nativo | Given/When/Then ou xUnit equivalente |
| **Quarentena** | Documento isolado do OCG | Processamento parado, espera review manual |
| **Criticidade** | Nível de confiabilidade requerido | Baixa (local), Média (remoto), Alta (premium) |
| **Versionamento OCG** | Histórico completo de mudanças | v0, v1, v2... imutável por versão, auditado |
| **Tag DT** | Data-Driven Token, número de decision/task | DT-001 a DT-0NN, linkado em issues/PRs |
| **M01** | Iteração via marker em PDF | Metadata para ingestão inteligente multi-passada |
| **Conformidade** | Pilar Gatekeeper para LGPD/reqs legais | Threshold 60 = blocker |
| **Segurança** | Pilar Gatekeeper para vulnerabilidades/PII | Threshold 60 = blocker |
| **Rastreabilidade** | Matrix req → módulo → teste | Cobertura, validação de completeness |
| **Vault** | Serviço de secrets (Fernet-encrypted) | `VaultService.store_secret()`, `get_secret()` |
| **Tenant** | Isolamento de dados | Por projeto (não multi-tenant entre clientes) |
| **Consolidação OCG** | Merge automático de múltiplas análises | ConflictDetector arbitra, critérios: prioridade, consistência |

---

## 9. Fluxo de Dados Principal

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE GCA COMPLETO                         │
└─────────────────────────────────────────────────────────────────┘

1. QUESTIONÁRIO INICIAL (Estático)
   └─→ GP submete 60+ respostas
   └─→ Validação de tipo/obrigatoriedade
   └─→ OCG inicializado com 12 seções default

2. INGESTÃO DE DOCUMENTOS (Dinâmica)
   ├─→ Dev/GP upload documento (PDF/DOCX/código)
   ├─→ Auditor analisa estrutura
   └─→ Enfileira para 5 personas (paralelo)

3. ANÁLISE POR PERSONAS (Paralelo)
   ├─→ Gerente de Projetos: escopo + viabilidade
   ├─→ Arquiteto: stack + padrões
   ├─→ DBA: schema + retenção
   ├─→ Dev Sr: implementabilidade
   ├─→ QA: testabilidade
   └─→ Consolidação de achados (ConflictDetector)

4. DETECÇÃO DE LACUNAS (Dinâmico)
   └─→ Se lacuna detectada (ex: IA_MODEL não respondido)
   └─→ Gera pergunta dinâmica
   └─→ GP submete resposta
   └─→ OCG atualizado, ciclo repete

5. CONSOLIDAÇÃO OCG
   ├─→ Arbitrar conflitos entre personas (ConflictDetector)
   ├─→ Atualizar seções affected
   ├─→ Incrementar versão (v0 → v1)
   └─→ Trigger: Gatekeeper, test specs, docs

6. GATEKEEPER (Aprovação de Módulos)
   ├─→ Detectar módulos candidatos (de OCG/CodeGen)
   ├─→ Validar contra 7 pilares
   ├─→ Gerar relatório de achados
   ├─→ Status: pass|conditional|block
   └─→ Se block: HITL ou remedy

7. CODE GENERATION (Scaffolding)
   ├─→ Dev seleciona módulo aprovado
   ├─→ Escolhe target: language + framework
   ├─→ Gera plano de scaffolding (LLM)
   ├─→ Gera código por item
   ├─→ Validação: type-safe, imports, structure
   ├─→ Diff preview
   └─→ Apply to git (commit + push)

8. QA & TESTES
   ├─→ Test specs gerados (unit|integration|e2e)
   ├─→ Tester executa (automático ou manual)
   ├─→ Relatório: cobertura, resultados
   ├─→ QA revisa (não edita)
   └─→ Aprovação gera pass/fail no módulo

9. DOCUMENTAÇÃO VIVA
   ├─→ ERS (Especificação de Requisitos)
   ├─→ Arquitetura (diagramas C4, ADRs)
   ├─→ API (OpenAPI/Swagger)
   ├─→ Database (ER diagram)
   └─→ Commited em git (versionado)

10. INTEGRAÇÃO EXTERNA
    ├─→ Sync Jira (requisitos ↔ issues)
    ├─→ Notificação Slack (eventos)
    ├─→ Commit Git (scaffold, docs)
    └─→ Scanner Segurança (Gitleaks, Snyk)

11. AUDITORÍA & COMPLIANCE
    ├─→ Auditoria global registra tudo
    ├─→ OCG versionado imutável
    ├─→ Rollback recuperável
    └─→ Gatekeeper conformidade = blocker se <60
```

### 9.1 Fluxo de Atualização OCG

```
Trigger: documento analisado | resposta pergunta dinâmica | consolidação

1. OCG.v(N) lido do banco
2. Delta calculado (seção, campo, valor novo)
3. Validar:
   - "OCG só expande": novo_valor não remove campos existentes
   - Conflito com versionamento (v(N) foi updated após leitura?)
4. Se OK:
   - Criar OCG.v(N+1)
   - Registrar delta em ocg_audit_log (quem, quando, source)
   - Propagação:
     a) Gatekeeper recalcula riscos (modules dependent on changed field)
     b) Test specs regeneradas se data_model mudou
     c) Alertar stakeholders (Dashboard update)
5. Se conflito:
   - Detectar: ConflictDetector arbitra
   - Se crítico: enfileira para HITL (awaiting_human_review)
   - Se leve: registra como nota
```

---

## 10. Configuração de Admin

### 10.1 Settings Globais

**Arquivo:** `SystemSettings` table em DB

```python
class SystemSettings(Base):
    id: int
    organization_id: int | None  # null = global
    
    # IA Configuration
    llm_policy_json: dict  # task_type → {criticality, provider, model, fallback}
    default_provider: str  # "anthropic" | "openai" | "deepseek" | "ollama"
    default_model: str     # "claude-opus-4-7" etc
    
    # Limits
    max_upload_size_mb: int = 100
    max_project_storage_gb: int = 1
    ocg_versions_before_compact: int = 50
    
    # RBAC & Security
    password_min_length: int = 12
    session_timeout_minutes: int = 480
    rate_limit_requests_per_min: int = 100
    
    # Email
    smtp_host: str
    smtp_port: int
    smtp_from_email: str
    smtp_username: str | None
    smtp_password_encrypted: str | None  # vault
    
    # Data Retention
    audit_log_retention_days: int = 730  # 2 anos
    soft_delete_retention_days: int = 90
    
    # Features
    enable_github_sync: bool = True
    enable_jira_sync: bool = True
    enable_slack_notifications: bool = True
```

### 10.2 Endpoints Admin (Route Guards)

**Middleware:** `require_admin()` em todas as rotas de admin

```python
def require_admin():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user.is_admin:
                raise HTTPException(403, "Admin access required")
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

**Rotas (prefixo `/admin`):**
- `GET /dashboard` — métricas globais
- `GET /users` — listar usuários
- `POST /users/:id/reset-password` — reset + email temporária
- `POST /users/:id/lock` — desabilitar login
- `POST /users/:id/unlock` — reabilitar
- `GET /projects/pending` — aguardando aprovação
- `POST /projects/:id/approve` — libera projeto
- `POST /projects/:id/reject` — rejeita + notifica GP
- `GET /settings` — ver configuração global
- `PATCH /settings` — editar configuração
- `POST /providers` — add LLM provider
- `GET /providers` — listar providers
- `DELETE /providers/:id` — remover provider
- `GET /audit-log` — auditoria global com filtros
- `GET /dead-letter-queue` — tarefas falhadas
- `POST /dead-letter-queue/:task_id/retry` — retry manual
- `GET /health` — status do sistema (CPU, DB, Celery)

---

## 11. Análise e Aprovação de Projetos

### 11.1 Fluxo de Criação e Aprovação

```
1. GP/Admin cria projeto
   ├─ Status: pending_approval
   ├─ OCG: vazio (aguarda questionário)
   └─ Acesso bloqueado (membros não conseguem logar)

2. GP submete questionário (60+ respostas)
   ├─ Validação de campo obrigatório/tipo
   ├─ OCG inicializado (v0) com 12 seções
   └─ Status: under_review (Admin notificado)

3. Admin avalia projeto
   ├─ Lê questionário + OCG
   ├─ Verifica: escopo legal, conformidade inicial, credibilidade
   ├─ Ação: Approve | Reject | Request More Info

4. Se Approve:
   ├─ Status: active
   ├─ Membros ganham acesso
   ├─ Ingestão desbloqueada
   ├─ Emails de welcome enviados
   └─ Dashboard disponível

5. Se Reject:
   ├─ Status: rejected
   ├─ GP notificado com motivo
   ├─ Projeto pode ser re-submetido
   └─ Histórico de rejeições registrado

6. Se Request More Info:
   ├─ Status: pending_info
   ├─ GP recebe questões específicas via email
   ├─ GP responde em formulário
   └─ Volta ao step 3
```

### 11.2 Critérios de Aprovação

**Admin avalia:**

| Critério | Validação | Status |
|----------|-----------|--------|
| **Escopo legal** | Requisitos do cliente não violam lei | PASS/FAIL |
| **Conformidade inicial** | LGPD, privacidade, segurança basics | PASS/FAIL |
| **Credibilidade de contexto** | OCG possui seções críticas (VISION, STACK) | PASS/WARN/FAIL |
| **Questionnaire completeness** | Todas respostas obrigatórias preenchidas | PASS/FAIL |
| **Team structure** | Pelo menos 1 Dev + 1 QA designados | PASS/WARN |

**Regra dura:** se algum FAIL → Reject projeto.

### 11.3 Integração com Gatekeeper

Após project aprovado, o **primeiro gate Gatekeeper é automático**:
- Lê OCG v0
- Valida pilar Conformidade (≥60 para passar)
- Se <60: gera achados estruturados
- GP deve resolver antes de iniciar ingestão

---

## 12. Funcionalidades Existentes (Status MVP 15)

**Backend:** 1506 testes passing, 5 skipped (pytest)  
**Frontend:** tsc 0 errors, 20 `any` declarations (meta atingida)  
**Database:** 20+ migrações Alembic, schema estável

### 12.1 Módulos Implementados

| Módulo | Status | Detalhe |
|--------|--------|---------|
| **Autenticação** | ✅ | OAuth2 + JWT, fallback local (bcrypt) |
| **RBAC** | ✅ | 5 papéis (Admin, GP, Dev, Tester, QA) |
| **Questionário** | ✅ | 60+ perguntas, validação, OCG init |
| **Ingestão** | ✅ | Upload PDF/DOCX/código, Auditor routing |
| **Personas** | ✅ | 5 personas paralelas (GP, ARQ, DBA, DEV, QA) |
| **OCG** | ✅ | 12 seções, versionado, audit log, consolidação ConflictDetector |
| **Gatekeeper** | ✅ | 7 pilares, scoring, relatório achados, approve/reject |
| **CodeGen (C-level)** | ✅ | Scaffolding Python/TS/Go, test specs por linguagem |
| **CodeGen (C++)** | ✅ | MVP 16 Fase 16.1-16.3 (CMake, test specs GoogleTest) |
| **Documentação Viva** | ✅ | ERS, Arquitetura, API, Database |
| **QA / Testes** | ✅ | Test exec, cobertura, revisão manual |
| **Integração Git** | ✅ | Clone, commit, push, branch protection |
| **Integração Jira** | ✅ | Sync requisitos, link commits |
| **Integração Slack** | ✅ | Notificações eventos |
| **Admin** | ✅ | Painel, gestão usuários/projetos, audit |
| **Vault** | ✅ | Secrets Fernet-encrypted (Git PAT, API keys) |
| **Observabilidade** | ✅ | Celery Flower, logs estruturados, health checks |

### 12.2 MVPs Fechados (Arquivados)

- **MVP 1-15:** Base operacional, OCG, Personas, Gatekeeper, CodeGen, QA, Hardening, Entrega, Auditoria — TODOS FECHADOS
- **MVP 16:** C++ fundacional + tsc fix + dogfood validation — EM EXECUÇÃO (4/5 fases concluídas)
- **MVP 17:** Saneamento operacional Celery (DT-077, DT-078) — PLANEJADO
- **MVP 18:** Sistema de Ajuda integrado (Fases 18.1-18.2 apenas) — AUTORIZADO (conteúdo depende nova autorização)
- **MVP 19:** ERS Vivo (IEEE 830) — PLANEJADO
- **MVP 20+:** Backlog futuro (protótipos Figma, IaC, NoSQL avançado, etc)

---

## 13. Fluxo de Ingestão, Análise, Questionários

### 13.1 Fluxo Completo de Ingestão

```
1. Upload Documento
   ├─ Dev/GP: POST /ingestion/upload (< 100 MB)
   ├─ Sistema: move arquivo para storage, gera ID
   └─ Status: pending_analysis

2. Auditor Analisa (Persona 0)
   ├─ Detecta: linguagem, tipo, estrutura
   ├─ Classifica: requisitos|arquitetura|código|teste|outro
   ├─ Extrai: texto principal, metadata
   └─ Enfileira para 5 personas

3. 5 Personas Analisam (Paralelo)
   ├─ GP: viabilidade, escopo, riscos negócio
   ├─ ARQ: stack viável, padrões, integrabilidade
   ├─ DBA: schema proposto, retenção, queries pesadas
   ├─ DEV: implementabilidade, tech debt
   ├─ QA: testabilidade, cobertura possível
   └─ Timeout: 120s cada (fail → questão para HITL)

4. Consolidação de Achados
   ├─ ConflictDetector arbitra:
     - Conflitos críticos (2+ divergem >50%) → HITL
     - Leve (anotação) → proceed
   ├─ Atualizar OCG com novas informações
   └─ Documento: status = analyzed | quarantined

5. Se Quarentena
   ├─ Documento isolado
   ├─ OCG não mudou
   ├─ GP notificado: revisar contradição
   └─ Ações: descartar | merge manual | re-análise

6. Se Sucesso
   ├─ Documento linkado ao OCG.version
   ├─ Confiança: score por persona
   ├─ Exibição: dashboard mostra "3/5 personas concordam"
   └─ Próximo: detecção de lacunas (perguntas dinâmicas)
```

### 13.2 Questionário Dinâmico (Follow-up)

**Gatilho:** após análise, se lacuna detectada

```
1. Detectar Lacuna
   ├─ Regra heurística: campo crítico do OCG vazio
   ├─ Exemplo: STACK_RECOMMENDATION.ai_model não respondido
   └─ Contexto: documento menciona "ML pipeline"

2. Gerar Pergunta
   ├─ LLM (Auditor): monta pergunta estruturada
   ├─ Entrada: OCG parcial + contexto
   ├─ Saída: "Qual será o provedor de IA recomendado?"
   └─ Tipo: múltipla escolha|texto|numérica

3. Enviar para GP
   ├─ Dashboard: "Pergunta de Acompanhamento" widget
   ├─ Email: notificação com contexto
   └─ Deadline: 3 dias (configurável)

4. GP Responde
   ├─ Submit resposta
   ├─ Validação: tipo correto, não vazio
   └─ Status pergunta: answered

5. Atualizar OCG
   ├─ Campo preenchido com resposta
   ├─ Versão incrementada
   ├─ Recalcular Gatekeeper
   └─ Alerta: "OCG updated, pilar Conformidade agora 75/100"

6. Próxima Pergunta
   ├─ Se mais lacunas: loop repete
   ├─ Se nenhuma: status = ready_for_gatekeeper
   └─ GP pode iniciar ingestão de novos documentos
```

---

## 14. Backlog, Roadmap, CodeGen, QA

### 14.1 Backlog (OCG.ROADMAP_BACKLOG)

**Armazenado em:** OCG seção `ROADMAP_BACKLOG`

```json
{
  "backlog": [
    {
      "id": "MODULE_AUTH",
      "title": "Sistema de Autenticação",
      "description": "Implemetar OAuth2 com suporte MFA",
      "priority": "high",
      "estimated_effort_days": 5,
      "dependencies": ["MODULE_CORE"],
      "status": "pending",  // pending|in_progress|completed|blocked
      "gatekeeper_status": null  // será preenchido pós-analysis
    }
  ]
}
```

### 14.2 Roadmap (Phases)

**Armazenado em:** OCG seção `ROADMAP_BACKLOG`, subseção `phases`

```json
{
  "phases": [
    {
      "phase": 1,
      "name": "MVP Básico",
      "modules": ["MODULE_AUTH", "MODULE_CORE"],
      "target_date": "2026-06-30",
      "risk_level": "low",
      "description": "Fornace funcionalidades core + auth"
    }
  ]
}
```

### 14.3 CodeGen (Scaffolding)

**Fluxo:**

```
1. Dev Seleciona Módulo Aprovado (Gatekeeper pass)
   ├─ Navegação: dashboard → Module Details → "Generate Code"
   └─ Botão desabilitado até aprovação

2. Escolher Target
   ├─ Language: Python | TypeScript | Go | C++ | Java
   ├─ Framework: Django | FastAPI | Next.js | Spring | etc
   └─ Optional: ORM, test framework, package manager

3. Gerar Plano de Scaffolding (LLM — alta criticidade)
   ├─ Input: módulo spec + stack target
   ├─ LLM: decompor em itens (classe, arquivo, util)
   ├─ Output: scaffold plan JSON
   └─ Exibição: tree view com arquivos

4. Revisar Plano (Dev)
   ├─ Pode: editar nomes, remover itens, reordenar
   ├─ Não pode: criar itens novos (requer new module)
   └─ Validate: sem conflitos nome, paths legítimas

5. Gerar Código por Item (LLM — paralelo)
   ├─ Para cada item: gerar código
   ├─ Validação post-gen:
     - Type check (tsc se TS, mypy se Py)
     - Import resolution
     - Syntax correctness
   └─ Status: generated|validating|error

6. Visualizar Diff (Dev)
   ├─ Lado a lado: gerado vs modelo
   ├─ Opciones: aceitar|editar|descartar item
   └─ Export: patch para manual review externo

7. Apply to Git (Dev)
   ├─ Commit automaticamente com scaffold-run-id
   ├─ Mensagem: "feat(scaffold): module {name} scaffolded\n\nRun: {run_id}"
   ├─ Branch: atualizado com commits
   └─ Push: automático ou manual (configurável)

8. Status Acompanhamento (Dev/QA)
   ├─ Dashboard: "Scaffold run #{id}"
   ├─ Timeline: plano → geração → validação → aplicação
   ├─ Artifacts: código gerado, logs, commit hash
   └─ Próximo: testes
```

### 14.4 QA & Execução de Testes

**Fluxo:**

```
1. Gerar Test Specs (Automático pós-scaffold)
   ├─ Sistema: lê módulo + código gerado
   ├─ LLM (QA persona — média criticidade): gera specs
   ├─ Formato: BDD (Given/When/Then) ou framework nativo
   ├─ Coverage targets: unit 80%, integration 60%, e2e 40%
   └─ Artefato: test_spec_*.md + código test_ esquelet

2. Tester Cria/Edita Testes (Iterativo)
   ├─ Pode: adicionar assertions, fixtures, parametrize
   ├─ Não pode: editar spec gerado (read-only)
   ├─ Status: draft|ready_for_review

3. Executar Testes (Manual ou CI)
   ├─ Ambiente: staging + sandbox DB (gca_test)
   ├─ Comando: pytest (Py) | jest (TS) | go test (Go) | ctest (C++)
   ├─ Reporte: JSON estruturado (junit_xml)
   └─ Resultados: passed|failed|skipped|error

4. QA Revisa Resultados
   ├─ Lê: cobertura, resultados, logs
   ├─ Não edita: conteúdo de teste
   ├─ Ações: approve|retest|reject
   └─ Decision: bloqueia ou libera módulo

5. Falha Crítica → Bloqueia Aprovação
   ├─ Status: gatekeeper.blocked_on_qa
   ├─ Dev notificado: fix required antes de re-submit
   └─ Historico: quantas vezes testou antes de passar

6. Tudo Verde → Módulo Aprovado
   ├─ Status: fully_approved
   ├─ ERS atualizada com resultado
   ├─ Test artifacts linkados em docs
   └─ Próximo: integração com outros módulos
```

---

## 15. Matriz de Rastreabilidade (Req → Módulo → Teste)

**Visualização:** Dashboard Admin / GP

```
Requisito (ERS)          │ Módulo Candidato    │ Test Spec           │ Status
────────────────────────┼─────────────────────┼─────────────────────┼────────
AUTH-001: Login OAuth2   │ MODULE_AUTH         │ test_oauth_login.py │ ✅ pass
AUTH-002: MFA            │ MODULE_AUTH         │ test_mfa_flow.py    │ ⏳ failing (retry)
CORE-001: DB Connection  │ MODULE_CORE         │ test_db_pool.py     │ ✅ pass
```

---

## 16. Deduplicação & Validação

### 16.1 Conflito de Documentos

**Cenário:** dois documentos dizem coisas diferentes sobre AUTH

```
Doc-A: "OAuth2 com GitHub"
Doc-B: "SAML com Azure"

Personas divergem:
- GP: "OAuth2 é padrão, SAML é enterprise"
- ARQ: "SAML é mais seguro para multi-tenant"
- Dev: "OAuth2 é mais rápido de implementar"

ConflictDetector:
- Score: 50/100 (conflito crítico)
- Decisão: HITL
- GP deve escolher: Doc-A | Doc-B | síntese manual
```

### 16.2 Deduplicação Automática

**Heurística:**
- Se dois documentos mencionam mesmo padrão/tool >80% similar → merge automático
- OCG não fica com duplicata (uma seção por conceito)
- Auditoria registra source: "merged docs A+B"

---

## 17. Suporte & Observabilidade

### 17.1 Logs Estruturados

**Formato:** JSON, 7 campos mínimos

```json
{
  "timestamp": "2026-04-30T14:23:45Z",
  "level": "INFO|WARN|ERROR|DEBUG",
  "service": "ocg_updater|gatekeeper|codegen",
  "project_id": 42,
  "user_id": 7,
  "action": "ocg_consolidated",
  "message": "OCG consolidated from 3 personas",
  "duration_ms": 2345,
  "extra": {
    "ocg_version_before": "v5",
    "ocg_version_after": "v6",
    "personas_agreed": 5,
    "conflicts": 0
  }
}
```

### 17.2 Alertas Críticos

| Evento | Severidade | Notificação |
|--------|-----------|-------------|
| Gatekeeper block (Conformidade <60) | Critical | Slack Admin + email GP |
| LLM timeout em alta criticidade | High | Slack Dev + HITL queue |
| DB connection pool exhausted | Critical | Slack oncall + Admin email |
| Git PAT expirado | High | Email Admin |
| Vault key rotation necessária | Medium | Email Admin (30 dias antes) |

### 17.3 Health Checks

**Endpoint:** `GET /health` (sem autenticação, 200 OK ou 503)

```json
{
  "status": "healthy|degraded|unhealthy",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "celery_worker": "ok",  // heartbeat
    "llm_provider": "ok",    // test call <1s
    "vault": "ok"
  },
  "timestamp": "2026-04-30T14:23:45Z"
}
```

---

## 18. Próximos Passos & Avaliação

Este documento consolida **todos** os requisitos do GCA para revisão por Claude web. Recomendações de melhoria:

1. **Gaps & Conflitos:** identifica contradições, ambiguidades
2. **Priorização:** quais requisitos impactam mais valor / risco
3. **Trade-offs:** custo vs qualidade, performance vs custo de IA
4. **Scalability:** está pronto para produção? 100 usuários? 10 projetos?
5. **UX:** fluxos são intuitivos? Faltam wizards / onboarding?
6. **Security:** cobertura completa de OWASP Top 10?
7. **LGPD Compliance:** está aligned com lei brasileira?

---

**Fim do Documento — Versão 1.0 (2026-04-30)**

Próximas iterações devem ser **refinadas via Claude web** para feedback estratégico antes de novas mudanças no código.
