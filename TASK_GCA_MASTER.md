# TASK_GCA_MASTER.md
# GCA — Gestão de Codificação Assistida
# Especificação Técnica e Funcional — Fases 0 a 5
# Versão: 1.0 | Data: 08/04/2026 | Autor: Luiz Carlos Pielak

---

## LEITURA OBRIGATÓRIA ANTES DE QUALQUER AÇÃO

Este documento é o contrato de implementação do GCA. Cada fase deve ser executada
na ordem definida. Nenhuma fase pode ser iniciada sem que a anterior esteja completa
e com todos os testes de regressão passando. Qualquer dúvida sobre comportamento
não especificado aqui deve ser reportada ANTES de implementar — nunca assuma.

---

## 0. ESTADO ATUAL DO SISTEMA (O QUE NÃO DEVE SER ALTERADO)

### 0.1 Repositório e Infraestrutura

- **Repositório:** https://github.com/Pielak/GCA.git
- **Branch produção:** master | **Branch dev:** main
- **URL produção:** https://gca.code-auditor.com.br
- **API produção:** https://api.code-auditor.com.br
- **Stack:** FastAPI 0.104 (Python 3.11), React 18.3 + TypeScript 5.6 + Vite 6.0
- **Banco:** PostgreSQL 16 (asyncpg) + Redis 7
- **Containers:** Docker Compose, 5 serviços (postgres, redis, backend, frontend, n8n)
- **Proxy:** Cloudflare Tunnel (NÃO usar Nginx ou Certbot)
- **Auto-start:** systemd gca.service

### 0.2 O Que Já Existe e Funciona em Produção

As implementações abaixo são INTOCÁVEIS. Nenhum arquivo, tabela, endpoint ou
componente listado pode ser modificado sem uma seção explícita de migração neste
documento. Qualquer alteração estrutural exige script de migração Alembic.

**Backend — Serviços implementados:**
- `auth_service.py` — JWT RS256, bootstrap-admin, first-access, refresh, logout
- `user_service.py` — CRUD, ativação/desativação, proteção self-deactivate
- `project_service.py` — CRUD, listagem por permissão
- `questionnaire_service.py` — 54 campos, 8 blocos, draft/submit, timer 5 dias
- `technology_verification_service.py` — 8 fases, 8 matrizes, 1464 linhas
- `agent_service.py` — 8 agentes Claude Opus 4.6, asyncio.gather paralelo
- `ocg_service.py` — geração, armazenamento, scores P1-P7
- `evaluation_service.py` — avaliação por 7 pilares, P7 bloqueante
- `codegen_service.py` — geração básica, 4 provedores LLM
- `email_service.py` — 11 templates SMTP
- `audit_service.py` — hash encadeado, log global imutável
- `external_project_service.py` — token 5 dias, deduplicação, timer
- `invitation_service.py` — token 2h, max 3 tentativas, 2 etapas
- `dashboard_service.py` — métricas, health check
- `n8n_service.py` — webhooks, triggers
- `password_service.py` — validação 10 chars, upper, digit, special

**Backend — Endpoints ativos (prefixo /api/v1/):**
```
POST   /auth/bootstrap-admin
POST   /auth/login
GET    /auth/me
POST   /auth/refresh
POST   /auth/change-password
POST   /auth/reset-password
POST   /auth/reset-password-confirm
POST   /auth/first-access
POST   /auth/logout
GET    /auth/validate-token/{token}
POST   /auth/accept-invite
GET    /auth/check-invite/{token}
GET    /projects/
POST   /projects/
GET    /projects/{id}
PUT    /projects/{id}
GET    /questionnaires/
POST   /questionnaires/
GET    /questionnaires/{id}
PUT    /questionnaires/{id}
POST   /questionnaires/{id}/submit
POST   /questionnaires/request-access
POST   /agents/analyze
GET    /agents/status/{job_id}
GET    /agents/result/{job_id}
POST   /agents/retry/{job_id}
POST   /evaluation/artifacts/{id}/evaluate
GET    /evaluation/artifacts/{id}/scores
GET    /evaluation/artifacts/{id}/history
POST   /evaluation/artifacts/{id}/approve
POST   /codegen/generate
GET    /codegen/status/{job_id}
GET    /codegen/result/{job_id}
POST   /codegen/preview
POST   /webhooks/questionnaire
POST   /webhooks/questionnaire-result
POST   /webhooks/external-project-result
GET    /dashboard/summary
GET    /dashboard/projects/stats
GET    /dashboard/ocg/stats
GET    /dashboard/agents/stats
GET    /dashboard/recent-activity
GET    /dashboard/alerts
GET    /dashboard/health
GET    /admin/users
POST   /admin/users
PUT    /admin/users/{id}
DELETE /admin/users/{id}
POST   /admin/invite-admin
POST   /admin/projects
GET    /admin/projects/pending
POST   /admin/projects/{id}/approve
POST   /admin/projects/{id}/reject
GET    /admin/external-requests
GET    /admin/external-requests/{id}
POST   /admin/external-requests/generate-link
POST   /admin/external-requests/{id}/approve
POST   /admin/external-requests/{id}/reject
GET    /admin/dashboard/metrics
GET    /admin/audit-log
```

**Banco de Dados — Schema público (tabelas existentes):**
- users, organizations, projects, project_requests
- access_attempts, reset_tokens, team_invites
- questionnaires, ocg, ocg_analysis_log
- audit_log_global, support_tickets, system_alerts
- artifacts, artifact_evaluations, onboarding_progress
- project_members, organization_members
- pillar_templates, pillar_configuration, company_policies
- stack_cache, ogc_versions, integration_webhooks
- piloter_queries, piloter_quota_history

**Schema por projeto (multi-tenant: proj_{slug}_*):**
- PillarConfiguration, OGCVersion, Artifact, ArtifactEvaluation, AuditLog

**Frontend — 23 páginas ativas (não modificar rotas existentes):**
```
/login              → LoginPage
/reset-password     → ResetPasswordPage
/reset-password/:token → ResetPasswordConfirmPage
/accept-invitation  → AcceptInvitationPage
/novo-projeto       → NovoProjetoPage
/dashboard          → DashboardPage
/projects           → ProjectListPage
/projects/:id       → ProjectDetailPage
/projects/:id/team  → ProjectTeamPage
/projects/:id/onboard → OnboardingWizard
/projects/:id/questionnaire → QuestionnairePage
/projects/:id/questionnaire/status → QuestionnaireStatusPage
/projects/:id/ocg   → OCGViewPage
/projects/:id/ocg/:ocg_id → OCGDetailPage
/projects/:id/artifacts → ArtifactListPage
/projects/:id/artifacts/:aid → ArtifactDetailPage
/projects/:id/codegen → CodeGenPage
/projects/:id/support → SupportPage
/admin              → AdminDashboardPage
/admin/users        → AdminUsersPage
/admin/projects     → AdminProjectsPage
/admin/external-requests → AdminExternalRequestsPage
/admin/audit-log    → AuditLogPage
```

**Frontend — 6 placeholders (serão implementados neste documento):**
```
/projects/:id/ingestion   → IngestionPage
/projects/:id/gatekeeper  → GatekeeperPage (ArguiderPage)
/projects/:id/livedocs    → LiveDocsPage
/projects/:id/roadmap     → RoadmapPage
/projects/:id/legacy      → LegacyPage
/projects/:id/merge       → MergeEnginePage
```

**Testes existentes:** 54/54 passando, 15 suítes. Localização: `/backend/tests/`.
Estes testes NÃO podem falhar após nenhuma das fases.

---

## 1. REGRAS FUNDAMENTAIS DE DESENVOLVIMENTO

### 1.1 Convenções de Código

**Backend:**
- Todos os serviços novos seguem o padrão `{nome}_service.py` com classe `{Nome}Service`
- Todos os endpoints novos são registrados no router correspondente ou em novo router incluído em `main.py`
- Toda operação de banco usa SQLAlchemy 2.0 async com `AsyncSession`
- Toda operação assíncrona longa usa `asyncio.create_task` (não bloqueia o HTTP response)
- Logs estruturados em JSON usando o logger existente do projeto
- Tipagem completa com Pydantic 2.5 — nenhum campo `Any` sem justificativa

**Frontend:**
- Todos os componentes novos em TypeScript estrito (sem `any`)
- Estado global: Zustand (já configurado). Não adicionar Redux ou Context para estado global
- Data fetching: TanStack Query v5 (já configurado). Não usar fetch direto em componentes
- Estilo: Tailwind CSS apenas. Não adicionar bibliotecas CSS externas
- Ícones: biblioteca já em uso no projeto (não adicionar nova)
- Formulários: padrão existente no projeto
- Todas as páginas novas devem usar o layout (Sidebar + Header) já existente

**Banco de dados:**
- Toda nova tabela requer script de migração Alembic (`alembic revision --autogenerate`)
- Toda coluna nova em tabela existente requer migração com valor DEFAULT para não quebrar dados existentes
- Nunca fazer DROP de coluna ou tabela sem fase de deprecação explícita
- Multi-tenant: tabelas de projeto ficam no schema `proj_{slug}_*`, não no schema público
- pgcrypto deve ser habilitado via migração, não manualmente

### 1.2 Padrão de Resposta da API

Todas as respostas da API seguem o padrão existente do projeto. Não alterar o formato
de resposta de nenhum endpoint existente. Novas rotas seguem o mesmo padrão.

### 1.3 Autenticação e Autorização

- JWT Bearer em todos os endpoints protegidos (padrão existente)
- Admin-only endpoints: usar decorator/dependency já existente `require_admin`
- Endpoints de projeto: usar `verify_project_access` (novo — ver Fase 0.3)
- Webhooks: validação HMAC com WEBHOOK_SECRET do .env

### 1.4 Variáveis de Ambiente

Novas variáveis de ambiente devem ser adicionadas ao `.env.example` com descrição.
Nunca hardcodar chaves, URLs ou segredos no código.

Novas variáveis necessárias neste documento:
```
GCA_MASTER_KEY=          # Chave mestra 256-bit para criptografia de secrets (Fase 0.2)
GCA_MASTER_KEY_SALT=     # Salt para derivação de chave (Fase 0.2)
```

---

## 2. PROTOCOLO DE TESTES DE REGRESSÃO

### 2.1 Regra de Ouro

Antes de iniciar qualquer fase e ao concluir qualquer fase, executar:
```bash
cd /home/luiz/devmachina  # ajustar para path real do GCA
cd backend
pytest tests/ -v --tb=short 2>&1 | tail -20
```
O resultado deve ser: `54 passed` (ou mais, conforme testes novos são adicionados).
Se qualquer teste falhar, a fase não está concluída.

### 2.2 Testes de Regressão por Endpoint Crítico

Para cada fase, executar os seguintes testes de fumaça manuais (ou automatizados
como parte da nova suíte de testes):

**Auth — deve continuar funcionando:**
```
POST /api/v1/auth/login         → 200 com tokens JWT válidos
GET  /api/v1/auth/me            → 200 com dados do usuário
POST /api/v1/auth/refresh       → 200 com novo access_token
GET  /api/v1/dashboard/health   → 200 com status dos serviços
```

**Admin — deve continuar funcionando:**
```
GET  /api/v1/admin/users              → 200 com lista de usuários
GET  /api/v1/admin/projects/pending   → 200
GET  /api/v1/admin/audit-log          → 200 com entradas encadeadas
GET  /api/v1/admin/dashboard/metrics  → 200
```

**Projetos — deve continuar funcionando:**
```
GET  /api/v1/projects/                    → 200
POST /api/v1/questionnaires/request-access → 200 com token
```

**Build frontend — deve continuar sem erros:**
```bash
cd frontend
npm run build
# Esperado: "2333 modules transformed" sem erros
```

### 2.3 Testes de Schema de Banco

Após qualquer migração Alembic, verificar:
```sql
-- Tabelas existentes devem permanecer com mesma estrutura
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
-- Dados existentes não devem ser perdidos
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM projects;
SELECT COUNT(*) FROM questionnaires;
```

### 2.4 Adição de Testes — Convenção

Novos arquivos de teste seguem o padrão: `tests/test_{nome_feature}.py`
Cada novo serviço deve ter ao mínimo: teste de criação, teste de leitura, teste de erro esperado.
Os testes novos são ADICIONADOS às 15 suítes existentes, nunca substituídos.

---

## 3. FASE 0 — FECHAMENTO DA BASE

**Pré-requisito:** nenhum. Esta é a fase inicial.
**Dependência das fases seguintes:** Fases 1-5 dependem de itens desta fase.
**Ordem de execução dentro da fase:** 0.1 → 0.2 → 0.3 → 0.4 → 0.5

---

### 3.1 FASE 0.1 — Conexão Git por Projeto

**Objetivo:** cada projeto deve obrigatoriamente vincular um repositório Git
(GitHub, GitLab, Bitbucket ou outro) usando Personal Access Token (PAT) fornecido
pelo GP durante o onboarding. Sem repositório vinculado, o projeto não pode
receber documentos (Fase 1) nem gerar código (Fase 3).

#### 3.1.1 Migração de Banco de Dados

Criar nova migração Alembic. Nova tabela no schema público:

```sql
CREATE TABLE project_git_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    -- valores aceitos: 'github', 'gitlab', 'bitbucket', 'azure_devops', 'other'
    repository_url VARCHAR(500) NOT NULL,
    -- ex: https://github.com/org/repo
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    pat_encrypted TEXT NOT NULL,
    -- armazenado via pgp_sym_encrypt (ver Fase 0.2)
    -- na Fase 0.1, armazenar como texto simples temporariamente
    -- será migrado para criptografado na Fase 0.2
    connection_verified BOOLEAN NOT NULL DEFAULT FALSE,
    connection_verified_at TIMESTAMP,
    last_commit_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_git UNIQUE (project_id)
);

CREATE INDEX idx_project_git_configs_project ON project_git_configs(project_id);
```

#### 3.1.2 Novo Serviço: git_service.py

Localização: `backend/services/git_service.py`

Implementar a classe `GitService` com os seguintes métodos públicos:

```python
class GitService:

    async def connect_repository(
        self,
        project_id: str,
        provider: str,         # 'github'|'gitlab'|'bitbucket'|'azure_devops'|'other'
        repository_url: str,
        pat: str,
        default_branch: str = "main"
    ) -> dict:
        """
        Valida o PAT fazendo uma chamada de teste ao provider.
        Se válido, salva em project_git_configs.
        Se inválido, retorna erro 400 com mensagem específica.
        Retorna: {success: bool, message: str, provider: str, branch: str}
        """

    async def verify_connection(self, project_id: str) -> dict:
        """
        Testa a conexão atual do projeto com o repositório.
        Retorna: {connected: bool, provider: str, repo_url: str, branch: str, last_verified: datetime}
        """

    async def commit_file(
        self,
        project_id: str,
        file_path: str,        # ex: "docs/functional/overview.md"
        content: str,          # conteúdo do arquivo (texto)
        commit_message: str    # ex: "[GCA] docs: atualiza overview funcional"
    ) -> dict:
        """
        Cria ou atualiza um arquivo no repositório do projeto.
        Se o arquivo já existir, sobrescreve (cria novo commit).
        Retorna: {success: bool, commit_sha: str, file_url: str}
        """

    async def commit_binary_file(
        self,
        project_id: str,
        file_path: str,
        content_bytes: bytes,
        commit_message: str
    ) -> dict:
        """
        Igual ao commit_file mas para arquivos binários (imagens, PDFs).
        """

    async def get_file_content(
        self,
        project_id: str,
        file_path: str
    ) -> str | None:
        """
        Lê o conteúdo de um arquivo do repositório.
        Retorna None se o arquivo não existir.
        """

    async def initialize_repository_structure(self, project_id: str) -> bool:
        """
        Chamado quando projeto é aprovado pelo Admin.
        Cria a estrutura inicial de diretórios no repositório via commits:

        /docs/
          /functional/
            overview.md       ← gerado com dados do OCG
          /technical/
            architecture.md   ← gerado com dados do OCG
            stack.md          ← gerado com dados do OCG
          /business_rules/
            rules.md          ← gerado com dados do OCG
          /modules/
            .gitkeep
          /tests/
            test_plan.md      ← gerado com estrutura inicial
          /ingested/
            .gitkeep
          ocg_current.md      ← OCG atual em formato legível
          CHANGELOG.md        ← início do histórico

        /src/
          /modules/
            .gitkeep

        /tests/
          /unit/
            .gitkeep
          /integration/
            .gitkeep
          /uat/
            .gitkeep

        README.md             ← gerado com nome e descrição do projeto

        Retorna True se bem-sucedido, False se repositório não configurado.
        """

    async def list_files(self, project_id: str, path: str = "") -> list[dict]:
        """
        Lista arquivos em um diretório do repositório.
        Retorna: [{name, path, type ('file'|'dir'), size, last_modified}]
        """
```

**Implementação do provider GitHub (prioritário):**
- Usar a API REST do GitHub v3 via `httpx` (já disponível no projeto)
- Base URL: `https://api.github.com`
- Autenticação: `Authorization: Bearer {pat}`
- Verificação: `GET /repos/{owner}/{repo}` → 200 = PAT válido
- Commit: usar API `PUT /repos/{owner}/{repo}/contents/{path}` com SHA do arquivo atual
- Parsear `repository_url` para extrair `owner` e `repo`

**Implementação dos outros providers:**
- GitLab: API v4 em `https://gitlab.com/api/v4`
- Bitbucket: API v2 em `https://api.bitbucket.org/2.0`
- Azure DevOps: API REST do Azure
- Other: retornar erro informando que conexão automática não é suportada,
  mas salvar as configurações para uso manual futuro

#### 3.1.3 Novos Endpoints

Router: `backend/routers/git_router.py` — incluir em `main.py`

```
POST   /api/v1/projects/{project_id}/git/connect
       Body: {provider, repository_url, pat, default_branch}
       Auth: Bearer (GP ou Admin com papel GP no projeto)
       Response 200: {success, message, provider, branch}
       Response 400: {error: "PAT inválido"|"Repositório não encontrado"|"URL inválida"}

GET    /api/v1/projects/{project_id}/git/status
       Auth: Bearer (qualquer membro do projeto)
       Response 200: {connected, provider, repository_url, branch, last_verified, last_commit_at}
       Response 200 (sem git): {connected: false}

POST   /api/v1/projects/{project_id}/git/verify
       Auth: Bearer (GP ou Admin com papel GP)
       Response 200: {connected, message}

DELETE /api/v1/projects/{project_id}/git/disconnect
       Auth: Bearer (Admin global apenas)
       Response 200: {success: true}
```

#### 3.1.4 Integração com OnboardingWizard (Frontend)

O OnboardingWizard existente possui 5 passos. Adicionar novo Passo (antes do passo atual 1):

**Novo Passo 0 — Configuração do Repositório Git:**

Componente: `GitConfigStep.tsx` dentro do OnboardingWizard existente.

Campos:
- Provider (select): GitHub | GitLab | Bitbucket | Azure DevOps | Outro
- URL do repositório (input text): validação de formato URL
- Branch padrão (input text): default "main"
- Personal Access Token (input password): mascarado, com botão "Testar Conexão"

Comportamento:
- Botão "Testar Conexão" chama `POST /api/v1/projects/{id}/git/connect`
- Se sucesso: exibe badge verde "✓ Repositório conectado" e habilita botão "Próximo"
- Se erro: exibe mensagem de erro específica do backend
- O PAT nunca é exibido após salvo (campo se torna somente-leitura com máscara `***`)
- Este passo é obrigatório — o Wizard não avança sem conexão verificada

Indicador visual no projeto: `ProjectDetailPage` deve exibir badge de status do Git
(verde = conectado, vermelho = não configurado, amarelo = erro de conexão).

#### 3.1.5 Integração com aprovação de projeto pelo Admin

Em `external_project_service.py` (ou `project_service.py`), no método que processa
aprovação de projeto (`approve_project` ou equivalente), adicionar chamada ASSÍNCRONA
ao final:

```python
asyncio.create_task(
    git_service.initialize_repository_structure(project_id)
)
```

Esta chamada não bloqueia a aprovação. Se o repositório não estiver configurado ainda,
a função retorna False silenciosamente (o GP configura depois no Wizard).

#### 3.1.6 Testes — Fase 0.1

Criar `backend/tests/test_git_service.py`:

```python
# Teste 1: connect_repository com PAT inválido → retorna erro 400
# Teste 2: verify_connection sem git configurado → {connected: false}
# Teste 3: commit_file em projeto sem git → retorna erro claro
# Teste 4: initialize_repository_structure cria os arquivos esperados
#           (usar repositório de teste com PAT de teste — variável TEST_GIT_PAT no .env.test)
# Teste 5: get_file_content de arquivo existente → retorna conteúdo
# Teste 6: get_file_content de arquivo inexistente → retorna None
```

---

### 3.2 FASE 0.2 — Vault de Chaves por Projeto (project_secrets)

**Objetivo:** armazenar chaves e tokens de cada projeto de forma criptografada no
banco de dados. A chave mestra (`GCA_MASTER_KEY`) fica no `.env` do GCA. Cada
projeto tem seus próprios secrets isolados.

#### 3.2.1 Habilitação do pgcrypto

Criar migração Alembic:
```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

#### 3.2.2 Migração de Banco de Dados

Nova tabela no schema público:

```sql
CREATE TABLE project_secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    secret_type VARCHAR(50) NOT NULL,
    -- valores: 'llm_api_key', 'smtp_password', 'webhook_secret',
    --          'git_pat', 'n8n_token', 'custom'
    secret_key VARCHAR(100) NOT NULL,
    -- identificador do secret dentro do tipo (ex: 'anthropic', 'openai')
    secret_value_encrypted TEXT NOT NULL,
    -- armazenado como pgp_sym_encrypt(value, master_key)
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_secret UNIQUE (project_id, secret_type, secret_key)
);

CREATE INDEX idx_project_secrets_project ON project_secrets(project_id);
CREATE INDEX idx_project_secrets_type ON project_secrets(project_id, secret_type);
```

Após criação da tabela, executar migração para criptografar o campo `pat_encrypted`
na tabela `project_git_configs` criada na Fase 0.1:

```sql
-- Migração: converter pat_encrypted para usar pgp_sym_encrypt
-- (só executar depois que GCA_MASTER_KEY estiver no .env)
UPDATE project_git_configs
SET pat_encrypted = pgp_sym_encrypt(pat_encrypted, current_setting('app.master_key'))
WHERE connection_verified = TRUE;
```

#### 3.2.3 Novo Serviço: vault_service.py

Localização: `backend/services/vault_service.py`

```python
class VaultService:

    def __init__(self):
        self.master_key = settings.GCA_MASTER_KEY
        # GCA_MASTER_KEY deve ter no mínimo 32 caracteres

    async def store_secret(
        self,
        db: AsyncSession,
        project_id: str,
        secret_type: str,
        secret_key: str,
        secret_value: str
    ) -> bool:
        """
        Criptografa e armazena um secret do projeto.
        Se já existir (project_id, secret_type, secret_key), sobrescreve.
        Usa: pgp_sym_encrypt(:value, :master_key)
        Retorna True se sucesso.
        """

    async def get_secret(
        self,
        db: AsyncSession,
        project_id: str,
        secret_type: str,
        secret_key: str
    ) -> str | None:
        """
        Recupera e descriptografa um secret.
        Usa: pgp_sym_decrypt(secret_value_encrypted::bytea, :master_key)
        Retorna None se não encontrado.
        """

    async def delete_secret(
        self,
        db: AsyncSession,
        project_id: str,
        secret_type: str,
        secret_key: str
    ) -> bool:
        """Remove um secret. Retorna True se removido, False se não existia."""

    async def list_secrets(
        self,
        db: AsyncSession,
        project_id: str
    ) -> list[dict]:
        """
        Lista secrets do projeto SEM descriptografar os valores.
        Retorna: [{secret_type, secret_key, created_at, updated_at}]
        """

    async def rotate_secret(
        self,
        db: AsyncSession,
        project_id: str,
        secret_type: str,
        secret_key: str,
        new_value: str
    ) -> bool:
        """Atualiza o valor criptografado de um secret existente."""
```

**Integração com GitService:** ao salvar o PAT na Fase 0.1, usar `VaultService.store_secret`
com `secret_type='git_pat'` e `secret_key=provider`. O campo `pat_encrypted` em
`project_git_configs` passa a armazenar o resultado do `pgp_sym_encrypt`.

#### 3.2.4 Testes — Fase 0.2

Criar `backend/tests/test_vault_service.py`:
```python
# Teste 1: store_secret → secret armazenado criptografado (valor no banco != valor original)
# Teste 2: get_secret → retorna valor original descriptografado
# Teste 3: get_secret de secret inexistente → retorna None
# Teste 4: store_secret duas vezes (mesmo project/type/key) → sobrescreve sem erro
# Teste 5: delete_secret → secret removido, get_secret retorna None
# Teste 6: list_secrets → retorna lista sem valores descriptografados
# Teste 7: rotate_secret → get_secret retorna novo valor
```

---

### 3.3 FASE 0.3 — Isolamento de Role Admin em Projeto

**Objetivo:** implementar a regra de que Admin do GCA não acessa dados funcionais
de projeto onde não tem papel cadastrado. Admin sem papel = vê apenas logs de ação.
Admin com papel = acessa apenas pelo papel, sem override.

#### 3.3.1 Nova Função de Verificação de Acesso

Localização: `backend/dependencies/project_access.py` (novo arquivo ou adição ao
arquivo de dependências existente)

```python
async def get_user_project_role(
    user_id: str,
    project_id: str,
    db: AsyncSession
) -> str | None:
    """
    Retorna o papel do usuário no projeto ('gp', 'developer', 'qa', 'tester', 'viewer')
    ou None se o usuário não tem papel no projeto.
    Consulta a tabela project_members existente.
    """

async def verify_project_access(
    project_id: str,
    current_user,        # objeto user do token JWT
    db: AsyncSession,
    required_roles: list[str] | None = None
    # None = qualquer membro pode acessar
    # ['gp'] = apenas GP pode acessar
    # ['gp', 'developer'] = GP ou Developer
):
    """
    Dependency FastAPI para endpoints de projeto.

    Lógica:
    1. Se current_user.is_admin == True:
       a. Obter papel do admin no projeto via get_user_project_role
       b. Se papel == None → levantar HTTPException 403 com mensagem:
          "Acesso negado: você não está cadastrado neste projeto.
           Como admin, você tem acesso apenas ao log de auditoria."
       c. Se papel != None → continuar como usuário com aquele papel
          (verificar required_roles se especificado)
    2. Se current_user.is_admin == False:
       a. Verificar se é membro do projeto
       b. Verificar required_roles se especificado
       c. Se não membro → HTTPException 403
       d. Se não tem o papel requerido → HTTPException 403 com mensagem específica
    3. Retorna o papel do usuário no projeto
    """
```

#### 3.3.2 Aplicação nos Endpoints de Projeto

Aplicar `verify_project_access` como dependency em todos os endpoints que recebem
`project_id` como parâmetro, exceto:
- Endpoints que já têm `require_admin` (continuam funcionando para admins)
- `GET /api/v1/projects/` (listagem — admins veem todos os projetos, sem dados funcionais)
- `GET /dashboard/health` (público)

Os endpoints de questionnaire, agents, evaluation, codegen, e os novos endpoints
das Fases 1-4 devem usar esta dependency.

#### 3.3.3 Endpoint de Auditoria de Projeto para Admin

Novo endpoint que permite ao admin ver apenas o log de ações de um projeto:

```
GET /api/v1/admin/projects/{project_id}/activity-log
Auth: Admin apenas
Response: lista de entradas do audit_log_global onde resource_id = project_id
          Campos retornados: event_type, actor_email, resource_type,
                             details (SEM dados funcionais do projeto), created_at
          Campos NÃO retornados: conteúdo de documentos, código gerado, OCG
```

#### 3.3.4 Testes — Fase 0.3

Adicionar a `backend/tests/test_auth.py` ou novo arquivo `test_project_access.py`:
```python
# Teste 1: Admin sem papel em projeto tenta acessar GET /projects/{id}/questionnaire → 403
# Teste 2: Admin com papel 'developer' em projeto acessa GET /projects/{id}/questionnaire → 200
# Teste 3: Admin sem papel acessa GET /admin/projects/{id}/activity-log → 200 (só logs)
# Teste 4: GP acessa projeto onde é GP → 200
# Teste 5: Developer tenta endpoint que requer GP → 403 com mensagem de papel
# Teste 6: Usuário sem papel no projeto tenta acessar → 403
```

---

### 3.4 FASE 0.4 — Endpoints de Settings por Projeto

**Objetivo:** permitir que GP configure SMTP, provider LLM e n8n por projeto.
Dados armazenados via VaultService (Fase 0.2).

#### 3.4.1 Migração de Banco de Dados

Nova tabela para configurações não-secretas de projeto:

```sql
CREATE TABLE project_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    setting_type VARCHAR(50) NOT NULL,
    -- 'smtp', 'llm', 'n8n', 'general'
    settings_json JSONB NOT NULL DEFAULT '{}',
    -- configurações não-secretas (ex: host, porta, provider name)
    -- valores secretos ficam em project_secrets
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_setting UNIQUE (project_id, setting_type)
);
```

#### 3.4.2 Novos Endpoints

Router: `backend/routers/settings_router.py` — incluir em `main.py`

```
GET    /api/v1/projects/{project_id}/settings
       Auth: GP do projeto
       Response: {smtp: {...}, llm: {...}, n8n: {...}, git: {connected, provider}}
       Valores secretos retornam mascarados: "***" ou {configured: true}

POST   /api/v1/projects/{project_id}/settings/smtp
       Auth: GP do projeto
       Body: {host, port, use_tls, username, password, from_email, from_name}
       Ação: salva host/port/use_tls/username/from_email/from_name em project_settings
             salva password via VaultService (secret_type='smtp_password', secret_key='main')
       Response: {success: true}

POST   /api/v1/projects/{project_id}/settings/smtp/test
       Auth: GP do projeto
       Body: {to_email}
       Ação: envia email de teste usando SMTP do projeto
       Response: {success: true} | {success: false, error: "mensagem"}

POST   /api/v1/projects/{project_id}/settings/llm
       Auth: GP do projeto
       Body: {provider, api_key, model_preference}
       -- provider: 'anthropic'|'openai'|'grok'|'deepseek'
       -- model_preference: modelo preferido (opcional, usa default do provider)
       Ação: salva provider e model_preference em project_settings
             salva api_key via VaultService (secret_type='llm_api_key', secret_key=provider)
       Response: {success: true}

POST   /api/v1/projects/{project_id}/settings/llm/validate
       Auth: GP do projeto
       Ação: faz chamada de teste ao provider LLM com a chave salva
       Response: {valid: true, model: "nome do modelo"} | {valid: false, error: "mensagem"}

POST   /api/v1/projects/{project_id}/settings/n8n
       Auth: GP do projeto
       Body: {webhook_url, api_token, workflow_id}
       Ação: salva webhook_url e workflow_id em project_settings
             salva api_token via VaultService (secret_type='n8n_token', secret_key='main')
       Response: {success: true}

PUT    /api/v1/projects/{project_id}/settings/{setting_type}
       Auth: GP do projeto
       -- setting_type: 'smtp'|'llm'|'n8n'
       Body: campos a atualizar (mesmos do POST correspondente)
       Ação: atualiza configurações não-secretas em project_settings
             atualiza secrets se fornecidos (campo não-vazio)
       Response: {success: true}
```

#### 3.4.3 Frontend — SettingsPage

Componente: `SettingsPage.tsx` na rota `/projects/:id/settings`

Abas: Git | SMTP | LLM Provider | n8n

Cada aba:
- Exibe configuração atual (valores secretos como "✓ Configurado" ou "Não configurado")
- Formulário de edição com campos específicos
- Botão "Salvar" e botão "Testar" (onde aplicável)
- Feedback visual de sucesso/erro

Adicionar link "Configurações" no menu de projeto (Sidebar) para GPs.

#### 3.4.4 Testes — Fase 0.4

Criar `backend/tests/test_settings.py`:
```python
# Teste 1: POST settings/smtp → configuração salva, password criptografado
# Teste 2: GET settings → retorna configurações com secrets mascarados
# Teste 3: PUT settings/smtp → atualiza apenas campos fornecidos
# Teste 4: Non-GP tenta configurar settings → 403
# Teste 5: POST settings/llm com provider inválido → 400
```

---

### 3.5 FASE 0.5 — Template de Email: OCG Gerado

**Objetivo:** notificar o GP por email quando o OCG do projeto é gerado.

#### 3.5.1 Novo Template

Em `email_service.py`, adicionar template 12:

**Função:** `send_ocg_generated_email(to_email, project_name, ocg_data, project_id)`

**Assunto:** `GCA — OCG Gerado: {project_name}`

**Corpo:**
```
O Objeto Contexto Global (OCG) do seu projeto foi gerado com sucesso.

Projeto: {project_name}
Score Geral: {overall_score}/100
Status: {status} (READY | NEEDS_REVIEW | AT_RISK | BLOCKED)

Scores por Pilar:
P1 Contexto de Negócio:    {p1_score}/100
P2 Regras e Conformidade:  {p2_score}/100
P3 Requisitos Funcionais:  {p3_score}/100
P4 Requisitos Não Func.:   {p4_score}/100
P5 Arquitetura:            {p5_score}/100
P6 Dados:                  {p6_score}/100
P7 Segurança:              {p7_score}/100

{if status == 'BLOCKED'}
⚠️ ATENÇÃO: O projeto está BLOQUEADO porque o score de Segurança (P7) está abaixo de 70.
A geração de código não será permitida até que as questões de segurança sejam resolvidas.
{endif}

Acesse o OCG completo: {base_url}/projects/{project_id}/ocg
```

#### 3.5.2 Integração

Em `agent_service.py`, no método do Agent 8 (Consolidator), após salvar o OCG
no banco com sucesso, adicionar chamada assíncrona:

```python
asyncio.create_task(
    email_service.send_ocg_generated_email(
        to_email=gp_email,
        project_name=project_name,
        ocg_data=ocg_result,
        project_id=project_id
    )
)
```

#### 3.5.3 Testes — Fase 0.5

Adicionar ao `backend/tests/test_email_service.py` (ou equivalente):
```python
# Teste 1: send_ocg_generated_email com status READY → email enviado sem warning
# Teste 2: send_ocg_generated_email com status BLOCKED → email contém texto de bloqueio
# Teste 3: send_ocg_generated_email com p7_score < 70 → is_blocking = True no email
```

---

**CHECKPOINT FASE 0:**
Antes de avançar para a Fase 1, verificar:
- [ ] 54+ testes passando
- [ ] Repositório Git pode ser conectado e verificado via API
- [ ] Secrets armazenados criptografados no banco
- [ ] Admin sem papel em projeto recebe 403 em endpoints funcionais
- [ ] Settings de SMTP, LLM e n8n configuráveis por projeto
- [ ] Email de OCG gerado sendo enviado
- [ ] Build do frontend sem erros

---

## 4. FASE 1 — ARGUIDOR + INGESTÃO DE DOCUMENTOS

**Pré-requisito:** Fase 0 completa.
**Descrição:** implementação do fluxo de ingestão de documentos externos ao OCG
(funcionais, técnicos, wireframes, etc.) e do Arguidor — Agente 9 —, que classifica
cada documento e identifica gaps, show-stoppers, má definição e candidatos a módulos.
O Arguidor também atualiza o OCG do projeto com a nova informação (versão evolutiva).

---

### 4.1 Migração de Banco de Dados — Fase 1

Criar migração Alembic. Todas as tabelas abaixo ficam no schema do projeto
(`proj_{slug}_*`). Devem ser criadas quando o projeto é aprovado.

```sql
-- Tabela de documentos ingeridos
CREATE TABLE ingested_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    filename VARCHAR(500) NOT NULL,
    -- nome único gerado pelo sistema (uuid + extensão)
    original_filename VARCHAR(500) NOT NULL,
    -- nome original do arquivo enviado pelo usuário
    file_type VARCHAR(20) NOT NULL,
    -- 'pdf'|'docx'|'markdown'|'image'|'wireframe'|'spreadsheet'|'code'|'other'
    document_category VARCHAR(30),
    -- preenchido pelo Arguidor após análise
    -- 'functional'|'technical'|'business_rule'|'wireframe'|
    -- 'test_plan'|'architecture'|'security'|'data'|'other'
    git_file_path VARCHAR(500),
    -- path no repositório: docs/ingested/{category}/{filename}
    git_analysis_path VARCHAR(500),
    -- path da análise: docs/ingested/{category}/{filename}.analysis.json
    file_hash VARCHAR(64) NOT NULL,
    -- SHA256 do conteúdo para deduplicação
    file_size_bytes INTEGER NOT NULL,
    uploaded_by UUID NOT NULL,
    -- FK para users (schema público)
    arguider_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- 'pending'|'processing'|'completed'|'error'
    arguider_started_at TIMESTAMP,
    arguider_completed_at TIMESTAMP,
    arguider_error_message TEXT,
    ocg_updated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ingested_docs_project ON ingested_documents(project_id);
CREATE INDEX idx_ingested_docs_status ON ingested_documents(project_id, arguider_status);
CREATE UNIQUE INDEX idx_ingested_docs_hash ON ingested_documents(project_id, file_hash);

-- Tabela de análises do Arguidor
CREATE TABLE arguider_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES ingested_documents(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    document_classification JSONB NOT NULL,
    -- {category, subcategory, confidence: 0-100, reasoning}
    gaps JSONB NOT NULL DEFAULT '[]',
    -- [{id, description, pillar, severity, related_ocg_field}]
    show_stoppers JSONB NOT NULL DEFAULT '[]',
    -- [{id, description, pillar, impact}]
    poor_definitions JSONB NOT NULL DEFAULT '[]',
    -- [{id, description, location, suggestion}]
    improvement_suggestions JSONB NOT NULL DEFAULT '[]',
    -- [{id, description, priority, category}]
    module_candidates JSONB NOT NULL DEFAULT '[]',
    -- [{name, description, module_type, priority, pillar_impact,
    --   dependencies, ready_for_codegen, reasoning}]
    ocg_fields_to_update JSONB NOT NULL DEFAULT '[]',
    -- [{field, current_value, suggested_value, reasoning}]
    llm_model VARCHAR(50) NOT NULL DEFAULT 'claude-opus-4-6',
    tokens_used INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_arguider_document UNIQUE (document_id)
);

CREATE INDEX idx_arguider_analyses_project ON arguider_analyses(project_id);

-- Tabela de candidatos a módulos (promovidos da análise do Arguidor)
CREATE TABLE module_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    arguider_analysis_id UUID NOT NULL REFERENCES arguider_analyses(id),
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    module_type VARCHAR(20) NOT NULL,
    -- 'feature'|'component' (decidido pelo Arguidor)
    priority VARCHAR(10) NOT NULL DEFAULT 'medium',
    -- 'high'|'medium'|'low'
    status VARCHAR(20) NOT NULL DEFAULT 'suggested',
    -- 'suggested'|'approved'|'rejected'|'in_progress'|'completed'
    approved_by UUID,
    -- UUID do usuário que aprovou (FK para users schema público)
    approved_at TIMESTAMP,
    rejected_by UUID,
    rejection_reason TEXT,
    dependencies JSONB NOT NULL DEFAULT '[]',
    -- lista de module_candidate ids dos quais este depende
    source_document_ids JSONB NOT NULL DEFAULT '[]',
    -- lista de ingested_document ids que originaram este módulo
    pillar_impact JSONB NOT NULL DEFAULT '{}',
    -- {p1: bool, p2: bool, p3: bool, p4: bool, p5: bool, p6: bool, p7: bool}
    ready_for_codegen BOOLEAN NOT NULL DEFAULT FALSE,
    -- true se Arguidor determinou sem dependências pendentes
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_module_candidates_project ON module_candidates(project_id);
CREATE INDEX idx_module_candidates_status ON module_candidates(project_id, status);

-- Tabela de delta do OCG (histórico de mudanças causadas por ingestão)
CREATE TABLE ocg_delta_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES ingested_documents(id),
    ocg_version_from INTEGER NOT NULL,
    ocg_version_to INTEGER NOT NULL,
    fields_changed JSONB NOT NULL,
    -- {field_name: {old_value, new_value, reasoning}}
    change_summary TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ocg_delta_project ON ocg_delta_log(project_id);
```

Estas tabelas devem ser criadas automaticamente quando o schema do projeto
(`proj_{slug}_*`) é criado na aprovação do projeto. Atualizar o método de
criação de schema no `project_service.py` ou `external_project_service.py`.

---

### 4.2 Novo Serviço: arguider_service.py

Localização: `backend/services/arguider_service.py`

Este serviço é o núcleo da Fase 1. Implementa o Agente 9 — Arguidor — usando
Claude Opus 4.6 via Anthropic SDK (mesmo padrão do `agent_service.py` existente).

#### 4.2.1 Extração de Conteúdo de Documentos

```python
class DocumentExtractor:

    async def extract_text(self, file_bytes: bytes, file_type: str) -> str:
        """
        Extrai texto de diferentes tipos de arquivo:
        - PDF: usar pypdf2 ou pdfplumber
        - DOCX: usar python-docx
        - Markdown: texto direto
        - Imagem/Wireframe: usar Claude Vision para descrever
        - Spreadsheet: usar openpyxl, extrair como CSV
        - Code: texto direto
        - Other: tentar como texto, se falhar retornar "{arquivo binário não extraível}"
        """

    async def extract_image_description(self, image_bytes: bytes) -> str:
        """
        Usa Claude claude-opus-4-6 com vision para descrever uma imagem ou wireframe.
        Prompt: "Descreva detalhadamente este wireframe/imagem de interface de usuário
                 ou diagrama de sistema. Identifique: elementos visuais, fluxos,
                 componentes, textos visíveis e funcionalidades implícitas."
        """
```

#### 4.2.2 Classe ArguiderService

```python
class ArguiderService:

    SYSTEM_PROMPT = """
    Você é o Arguidor do GCA (Gestão de Codificação Assistida).
    Seu papel é analisar documentos ingeridos em projetos de software e:

    1. Classificar o tipo e categoria do documento
    2. Identificar GAPS em relação ao OCG (Objeto Contexto Global) do projeto
    3. Identificar SHOW-STOPPERS: contradições graves que impedem implementação
    4. Identificar MÁ DEFINIÇÃO: ambiguidades que precisam ser esclarecidas antes de codificar
    5. Sugerir MELHORIAS de forma objetiva e acionável
    6. Identificar MÓDULOS CANDIDATOS: funcionalidades que podem ser implementadas
       imediatamente caso não tenham dependências de outros documentos pendentes

    Para cada módulo candidato, decida se é:
    - 'feature': funcionalidade completa de negócio (ex: módulo de autenticação,
      módulo de relatórios, módulo de pagamento)
    - 'component': componente técnico reutilizável (ex: serviço de email,
      middleware de logging, componente de tabela paginada)

    IMPORTANTE:
    - Seja específico e objetivo. Evite generalidades.
    - Cada gap, show-stopper, má-definição e sugestão deve ter ID único (G001, SS001, PD001, IS001).
    - Um módulo só é 'ready_for_codegen: true' se o documento atual fornece
      TODAS as informações necessárias para implementá-lo sem depender de outros
      documentos ainda não ingeridos.
    - Ao atualizar o OCG, sugira apenas campos que o documento DIRETAMENTE impacta.
    - Responda SOMENTE com JSON válido, sem markdown, sem explicações fora do JSON.
    """

    async def analyze_document(
        self,
        db: AsyncSession,
        document_id: str,
        project_id: str,
        document_text: str,
        current_ocg: dict,
        previous_analyses: list[dict]
    ) -> dict:
        """
        Executa a análise do Arguidor para um documento.

        Fluxo:
        1. Monta o prompt com: document_text + current_ocg + previous_analyses (resumo)
        2. Chama Claude claude-opus-4-6 com max_tokens=4096
        3. Parseia o JSON retornado (tratar erros de parsing graciosamente)
        4. Salva resultado em arguider_analyses
        5. Promove module_candidates para tabela module_candidates
        6. Se ocg_fields_to_update não vazio → atualiza OCG (ver 4.2.3)
        7. Persiste análise como JSON no repositório Git do projeto
        8. Atualiza ingested_documents.arguider_status = 'completed'
        9. Retorna resultado completo
        """

    def build_analysis_prompt(
        self,
        document_text: str,
        current_ocg: dict,
        previous_analyses: list[dict]
    ) -> str:
        """
        Monta o prompt do usuário para o Arguidor.

        Estrutura:
        === DOCUMENTO A ANALISAR ===
        {document_text}

        === OCG ATUAL DO PROJETO ===
        {json.dumps(current_ocg, ensure_ascii=False, indent=2)}

        === ANÁLISES ANTERIORES (RESUMO) ===
        {resumo das análises anteriores — apenas títulos e contadores}

        === INSTRUÇÕES ===
        Analise o documento acima em relação ao OCG do projeto.
        Retorne SOMENTE o seguinte JSON:

        {
          "document_classification": {
            "category": "functional|technical|business_rule|wireframe|test_plan|architecture|security|data|other",
            "subcategory": "string descritivo",
            "confidence": 0-100,
            "reasoning": "justificativa da classificação"
          },
          "gaps": [
            {
              "id": "G001",
              "description": "descrição objetiva do gap",
              "pillar": "P1|P2|P3|P4|P5|P6|P7",
              "severity": "BLOCKER|CRITICAL|WARNING|INFO",
              "related_ocg_field": "campo do OCG afetado (ou null)"
            }
          ],
          "show_stoppers": [
            {
              "id": "SS001",
              "description": "descrição da contradição grave",
              "pillar": "P1|P2|P3|P4|P5|P6|P7",
              "impact": "impacto se não resolvido"
            }
          ],
          "poor_definitions": [
            {
              "id": "PD001",
              "description": "o que está mal definido",
              "location": "onde no documento",
              "suggestion": "como melhorar a definição"
            }
          ],
          "improvement_suggestions": [
            {
              "id": "IS001",
              "description": "sugestão de melhoria",
              "priority": "high|medium|low",
              "category": "funcional|técnico|processo|segurança|performance"
            }
          ],
          "module_candidates": [
            {
              "name": "NomeDoModulo",
              "description": "descrição funcional e técnica do módulo",
              "module_type": "feature|component",
              "priority": "high|medium|low",
              "pillar_impact": ["P1", "P3", "P5"],
              "dependencies": [],
              "ready_for_codegen": true,
              "reasoning": "justificativa para criar este módulo agora"
            }
          ],
          "ocg_fields_to_update": [
            {
              "field": "nome_do_campo_ocg",
              "current_value": "valor atual",
              "suggested_value": "valor sugerido",
              "reasoning": "por que atualizar"
            }
          ]
        }
        """
```

#### 4.2.3 Atualização Evolutiva do OCG

Quando o Arguidor identifica `ocg_fields_to_update`, executar:

```python
async def evolve_ocg(
    self,
    db: AsyncSession,
    project_id: str,
    document_id: str,
    fields_to_update: list[dict]
) -> bool:
    """
    1. Buscar OCG atual do projeto (tabela ocg)
    2. Buscar versão atual em ogc_versions (campo version_number)
    3. Criar nova entrada em ogc_versions com os dados atuais (snapshot)
    4. Aplicar atualizações ao registro ocg (UPDATE)
    5. Registrar delta em ocg_delta_log
    6. Atualizar ocg_current.md no repositório Git com o novo OCG
    7. Retorna True se sucesso
    """
```

A tabela `ogc_versions` já existe no projeto. Usar o campo existente `version_number`
incrementando +1. O campo `ocg_data` da versão antiga é preservado. O registro `ocg`
principal é atualizado.

---

### 4.3 Novo Serviço: ingestion_service.py

Localização: `backend/services/ingestion_service.py`

```python
class IngestionService:

    async def upload_document(
        self,
        db: AsyncSession,
        project_id: str,
        uploaded_by: str,
        file_bytes: bytes,
        original_filename: str,
        content_type: str
    ) -> dict:
        """
        1. Calcular SHA256 do arquivo (deduplicação)
        2. Verificar se hash já existe em ingested_documents para este projeto
           → Se sim: retornar {duplicate: true, existing_document_id: uuid}
        3. Determinar file_type a partir do content_type e extensão
        4. Gerar filename único: {uuid4}.{extensão}
        5. Inserir registro em ingested_documents com status 'pending'
        6. Commit o arquivo bruto no repositório Git do projeto
           Path: docs/ingested/uncategorized/{filename}
        7. Disparar análise assíncrona:
           asyncio.create_task(arguider_service.analyze_document_async(document_id))
        8. Retornar {document_id, status: 'pending', message: 'Documento recebido. Análise iniciada.'}
        """

    async def list_documents(self, db: AsyncSession, project_id: str) -> list[dict]:
        """Lista todos os documentos do projeto com status e análise resumida."""

    async def get_document_detail(
        self, db: AsyncSession, project_id: str, document_id: str
    ) -> dict:
        """Retorna documento + análise completa do Arguidor se disponível."""

    async def get_document_status(
        self, db: AsyncSession, project_id: str, document_id: str
    ) -> dict:
        """Retorna apenas status para polling: {status, arguider_status, updated_at}"""

    async def delete_document(
        self, db: AsyncSession, project_id: str, document_id: str
    ) -> bool:
        """
        Remove documento do banco e do repositório Git.
        Só permite se arguider_status != 'processing'.
        Retorna False se módulos candidatos já foram aprovados a partir deste documento.
        """
```

---

### 4.4 Novos Endpoints — Fase 1

Router: `backend/routers/ingestion_router.py` — incluir em `main.py`

```
POST   /api/v1/projects/{project_id}/ingestion
       Auth: Bearer (qualquer membro com papel 'gp', 'developer', 'qa')
       Content-Type: multipart/form-data
       Body: file (UploadFile), description (str, opcional)
       Tipos aceitos: pdf, docx, doc, md, txt, png, jpg, jpeg, gif, webp,
                      xlsx, xls, csv, py, ts, js, java, cs, go, rs
       Tamanho máximo: 50MB
       Response 200: {document_id, status, message}
       Response 400: {error: "Tipo de arquivo não suportado"}
       Response 409: {duplicate: true, existing_document_id, message: "Documento já ingerido"}

GET    /api/v1/projects/{project_id}/ingestion
       Auth: Bearer (qualquer membro)
       Response: lista de documentos com {id, original_filename, file_type,
                 document_category, arguider_status, created_at, uploaded_by_name}

GET    /api/v1/projects/{project_id}/ingestion/{document_id}
       Auth: Bearer (qualquer membro)
       Response: documento completo + análise do Arguidor (se concluída)

GET    /api/v1/projects/{project_id}/ingestion/{document_id}/status
       Auth: Bearer (qualquer membro)
       Response: {document_id, arguider_status, arguider_started_at,
                  arguider_completed_at, ocg_updated}
       -- Endpoint para polling a cada 3 segundos

DELETE /api/v1/projects/{project_id}/ingestion/{document_id}
       Auth: Bearer (GP apenas)
       Response 200: {success: true}
       Response 409: {error: "Módulos aprovados dependem deste documento"}
```

---

### 4.5 Frontend — IngestionPage

Rota: `/projects/:id/ingestion`
Substituir o placeholder existente.

#### 4.5.1 Layout

```
[Header: "Ingestão de Documentos"]
[Área de upload: drag-and-drop + botão "Selecionar arquivo"]
  - Exibe tipos aceitos e tamanho máximo
  - Preview do arquivo selecionado antes de enviar
  - Botão "Enviar para análise"

[Tabela de documentos enviados]
Colunas: Nome Original | Tipo | Categoria (pós-análise) | Status | Enviado por | Data | Ações
Status badge:
  - Aguardando análise (cinza, pulsando)
  - Classificando (amarelo, pulsando)
  - Concluído (verde)
  - Erro (vermelho)
Ações: Ver análise | Excluir

[Painel de análise (expandível ao clicar em "Ver análise")]
  Abas: Classificação | Gaps | Show Stoppers | Má Definição | Sugestões | Módulos
  Cada aba mostra os items com badges de severidade/prioridade
```

#### 4.5.2 Comportamento de Polling

Após upload, iniciar polling em `GET /ingestion/{id}/status` a cada 3 segundos.
Parar polling quando `arguider_status == 'completed'` ou `'error'`.
Usar TanStack Query `refetchInterval` para implementar o polling.

#### 4.5.3 Atualização do Status do OCG

Se `ocg_updated == true` na resposta, exibir banner informativo:
"O OCG do projeto foi atualizado com base neste documento. [Ver OCG atualizado →]"

#### 4.5.4 Testes — Fase 1

Criar `backend/tests/test_ingestion.py`:
```python
# Teste 1: upload PDF → documento criado com status 'pending'
# Teste 2: upload mesmo arquivo duas vezes → retorna duplicate=true
# Teste 3: upload arquivo acima de 50MB → 413 Request Too Large
# Teste 4: upload tipo não suportado → 400
# Teste 5: status polling → retorna campos corretos
# Teste 6: delete documento sem módulos aprovados → sucesso
# Teste 7: delete documento com módulo aprovado → 409
# Teste 8: arguider_service.analyze_document com OCG mock → retorna JSON válido
# Teste 9: analyze_document com campos ocg_fields_to_update → OCG atualizado e versão criada
# Teste 10: analyze_document com module_candidates ready_for_codegen=true
#            → registros criados em module_candidates
```

---

**CHECKPOINT FASE 1:**
- [ ] 54+ testes passando
- [ ] Upload de PDF, DOCX e imagem funcionando
- [ ] Arguidor analisando documentos e retornando JSON válido
- [ ] OCG sendo atualizado quando necessário
- [ ] Módulos candidatos sendo registrados
- [ ] Repositório Git recebendo arquivos de documentos e análises

---

## 5. FASE 2 — GATEKEEPER + APROVAÇÃO DE MÓDULOS

**Pré-requisito:** Fase 1 completa.
**Descrição:** interface visual (GatekeeperPage) que consolida todos os items
identificados pelo Arguidor (gaps, show-stoppers, má-definição, sugestões e módulos
candidatos) e permite o fluxo de aprovação/rejeição de módulos por desenvolvedor humano.

---

### 5.1 Migração de Banco de Dados — Fase 2

Nova tabela para rastreamento de resolução de items do Gatekeeper:

```sql
CREATE TABLE gatekeeper_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    arguider_analysis_id UUID NOT NULL REFERENCES arguider_analyses(id),
    item_type VARCHAR(20) NOT NULL,
    -- 'gap'|'show_stopper'|'poor_definition'|'improvement'
    item_id_in_analysis VARCHAR(10) NOT NULL,
    -- ex: 'G001', 'SS002' (ID da análise do Arguidor)
    item_data JSONB NOT NULL,
    -- dados completos do item (copiados da análise)
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- 'pending'|'resolved'|'ignored'
    resolved_by UUID,
    resolution_note TEXT,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gatekeeper_project ON gatekeeper_items(project_id);
CREATE INDEX idx_gatekeeper_status ON gatekeeper_items(project_id, status);
CREATE INDEX idx_gatekeeper_type ON gatekeeper_items(project_id, item_type);
```

Nota: ao concluir a análise do Arguidor, popular automaticamente `gatekeeper_items`
com todos os gaps, show_stoppers, poor_definitions e improvement_suggestions da análise.
Adicionar esta lógica no método `analyze_document` do `ArguiderService`.

---

### 5.2 Novo Serviço: gatekeeper_service.py

Localização: `backend/services/gatekeeper_service.py`

```python
class GatekeeperService:

    async def get_project_gatekeeper(self, db: AsyncSession, project_id: str) -> dict:
        """
        Consolida todos os items de Gatekeeper do projeto (todos os documentos).
        Retorna:
        {
          summary: {
            total_gaps: int,
            open_gaps: int,
            total_show_stoppers: int,
            open_show_stoppers: int,
            total_poor_definitions: int,
            total_suggestions: int,
            total_modules: int,
            modules_pending_approval: int,
            modules_approved: int,
            modules_rejected: int,
            has_blockers: bool  -- true se há show_stoppers BLOCKER não resolvidos
          },
          gaps: [...],
          show_stoppers: [...],
          poor_definitions: [...],
          improvement_suggestions: [...],
          module_candidates: [...]
        }
        """

    async def resolve_item(
        self,
        db: AsyncSession,
        project_id: str,
        item_id: str,
        resolved_by: str,
        resolution_note: str
    ) -> bool:
        """Marca item como 'resolved'. Qualquer membro pode resolver."""

    async def ignore_item(
        self,
        db: AsyncSession,
        project_id: str,
        item_id: str,
        ignored_by: str,
        reason: str
    ) -> bool:
        """
        Marca item como 'ignored'. Reason é obrigatório.
        Apenas GP pode ignorar show_stoppers.
        """

    async def approve_module(
        self,
        db: AsyncSession,
        project_id: str,
        module_id: str,
        approved_by: str
    ) -> bool:
        """
        Aprova módulo candidato.
        Apenas usuários com papel 'developer' ou 'gp' podem aprovar.
        Muda status para 'approved'.
        Dispara asyncio.create_task para CodeGen do módulo (Fase 3).
        """

    async def reject_module(
        self,
        db: AsyncSession,
        project_id: str,
        module_id: str,
        rejected_by: str,
        reason: str
    ) -> bool:
        """
        Rejeita módulo candidato. Reason é obrigatório.
        Muda status para 'rejected'.
        """

    async def generate_gatekeeper_report(
        self,
        project_id: str,
        format: str  # 'markdown'|'pdf'
    ) -> bytes:
        """
        Gera relatório completo do Gatekeeper.
        Markdown: retorna string encodada como bytes
        PDF: usa reportlab ou weasyprint para converter markdown em PDF
        Inclui: todos os items com status, todos os módulos com decisão
        """
```

---

### 5.3 Novos Endpoints — Fase 2

Router: `backend/routers/gatekeeper_router.py` — incluir em `main.py`

```
GET    /api/v1/projects/{project_id}/gatekeeper
       Auth: Bearer (qualquer membro)
       Response: consolidado completo (ver get_project_gatekeeper)

GET    /api/v1/projects/{project_id}/gatekeeper/modules
       Auth: Bearer (qualquer membro)
       Response: lista de module_candidates com status e histórico de decisão

POST   /api/v1/projects/{project_id}/gatekeeper/items/{item_id}/resolve
       Auth: Bearer (qualquer membro)
       Body: {resolution_note: str}
       Response: {success: true}

POST   /api/v1/projects/{project_id}/gatekeeper/items/{item_id}/ignore
       Auth: Bearer (GP para show_stoppers; qualquer membro para demais)
       Body: {reason: str (obrigatório)}
       Response: {success: true}
       Response 400: {error: "Reason é obrigatório para ignorar um item"}
       Response 403: {error: "Apenas GP pode ignorar show-stoppers"}

POST   /api/v1/projects/{project_id}/gatekeeper/modules/{module_id}/approve
       Auth: Bearer (papel 'developer' ou 'gp' no projeto)
       Response: {success: true, message: "Módulo aprovado. Geração de código iniciada."}
       Response 403: {error: "Apenas Developer ou GP podem aprovar módulos"}

POST   /api/v1/projects/{project_id}/gatekeeper/modules/{module_id}/reject
       Auth: Bearer (papel 'developer' ou 'gp' no projeto)
       Body: {reason: str (obrigatório)}
       Response: {success: true}

GET    /api/v1/projects/{project_id}/gatekeeper/report
       Auth: Bearer (qualquer membro)
       Query param: format=markdown|pdf (default: markdown)
       Response: arquivo para download (Content-Disposition: attachment)
```

---

### 5.4 Frontend — GatekeeperPage (ArguiderPage)

Rota: `/projects/:id/gatekeeper`
Substituir o placeholder existente.

#### 5.4.1 Layout

```
[Header: "Gatekeeper do Projeto"]
[Barra de resumo: badges com contadores]
  Gaps: N (X abertos) | Show-Stoppers: N | Má-Definição: N |
  Sugestões: N | Módulos: N (X aguardando aprovação)

[Botão "Baixar Relatório" com dropdown: Markdown | PDF]

[Tabs: Gaps | Show Stoppers | Má Definição | Sugestões | Módulos Candidatos]
```

**Tab Gaps:**
- Tabela: ID | Descrição | Pilar | Severidade | Status | Ações
- Filtro por Severidade e Status
- Badge de severidade colorido: BLOCKER=vermelho, CRITICAL=laranja, WARNING=amarelo, INFO=azul
- Botões: "Resolver" (modal com campo resolution_note) | "Ignorar" (modal com campo reason)

**Tab Show Stoppers:**
- Mesma estrutura que Gaps
- Card de alerta vermelho no topo se há BLOCKER não resolvidos:
  "⚠️ Existem {N} show-stoppers bloqueantes não resolvidos.
   A geração de código pode ser comprometida."

**Tab Má Definição:**
- Lista cards: Descrição | Localização | Sugestão | Status | Ações

**Tab Sugestões:**
- Lista cards: Descrição | Prioridade | Categoria | Status | Ações

**Tab Módulos Candidatos:**
```
[Card por módulo]
  Nome: {NomeDoModulo}
  Tipo: feature | component (badge)
  Prioridade: high | medium | low (badge colorido)
  Descrição: {descrição}
  Pilares afetados: P1, P3, P5 (badges)
  Dependências: {lista de módulos ou "Nenhuma"}
  Status de codegen: ✓ Pronto para gerar | ⚠ Aguardando dependências

  [Botão "Aprovar"] → modal de confirmação "Confirma aprovação do módulo?"
  [Botão "Rejeitar"] → modal com campo reason obrigatório

  Se status='approved': exibe badge "Aprovado por {nome} em {data}"
  Se status='rejected': exibe badge "Rejeitado: {reason}"
  Se status='in_progress': exibe badge pulsante "Gerando código..."
  Se status='completed': exibe badge verde + link para código gerado
```

#### 5.4.2 Testes — Fase 2

Criar `backend/tests/test_gatekeeper.py`:
```python
# Teste 1: GET gatekeeper sem documentos → summary com zeros
# Teste 2: GET gatekeeper com análise → items populados corretamente
# Teste 3: resolve_item → status muda para 'resolved'
# Teste 4: ignore_item sem reason → 400
# Teste 5: ignore show_stopper por non-GP → 403
# Teste 6: approve_module por 'qa' role → 403
# Teste 7: approve_module por 'developer' → sucesso, CodeGen disparado
# Teste 8: reject_module sem reason → 400
# Teste 9: GET report?format=markdown → retorna bytes com conteúdo markdown
# Teste 10: GET report?format=pdf → retorna bytes de PDF
```

---

**CHECKPOINT FASE 2:**
- [ ] 54+ testes passando
- [ ] GatekeeperPage exibindo items de todos os documentos analisados
- [ ] Resolução e ignoração de items funcionando
- [ ] Aprovação de módulo dispara CodeGen (mesmo que Fase 3 ainda não esteja completa — pode disparar com log de "pendente")
- [ ] Download de relatório em Markdown funcionando
- [ ] PDF opcional (se reportlab disponível)

---

## 6. FASE 3 — CODEGEN POR MÓDULO + GERAÇÃO DE TESTES

**Pré-requisito:** Fases 0, 1 e 2 completas.
**Descrição:** ao aprovar um módulo no Gatekeeper, o GCA gera o código do módulo,
persiste no repositório Git do projeto, gera testes unitários, e se houver múltiplos
módulos com dependências, gera testes de integração. Para módulos com componente
de UI (detectado por wireframes ingeridos), gera testes UAT.

---

### 6.1 Migração de Banco de Dados — Fase 3

```sql
-- Tabela de módulos gerados
CREATE TABLE generated_modules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    module_candidate_id UUID NOT NULL REFERENCES module_candidates(id),
    name VARCHAR(200) NOT NULL,
    module_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'generating',
    -- 'generating'|'generated'|'error'
    git_source_path VARCHAR(500),
    -- ex: src/modules/autenticacao/
    git_unit_test_path VARCHAR(500),
    -- ex: tests/unit/autenticacao_test.py
    git_integration_test_path VARCHAR(500),
    -- null se não aplicável ainda
    git_uat_test_path VARCHAR(500),
    -- null se módulo não tem UI
    git_docs_path VARCHAR(500),
    -- ex: docs/modules/autenticacao.md
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),
    tokens_used INTEGER,
    generation_latency_ms INTEGER,
    error_message TEXT,
    generated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_generated_modules_project ON generated_modules(project_id);
CREATE INDEX idx_generated_modules_candidate ON generated_modules(module_candidate_id);

-- Tabela de arquivos de teste gerados
CREATE TABLE test_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    generated_module_id UUID NOT NULL REFERENCES generated_modules(id),
    test_type VARCHAR(20) NOT NULL,
    -- 'unit'|'integration'|'uat'
    git_path VARCHAR(500) NOT NULL,
    framework VARCHAR(50) NOT NULL,
    -- ex: 'pytest', 'jest', 'junit', 'cypress', 'playwright'
    coverage_scope VARCHAR(200),
    -- descrição do escopo coberto
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_test_files_project ON test_files(project_id);
CREATE INDEX idx_test_files_module ON test_files(generated_module_id);
```

---

### 6.2 Aprimoramento do codegen_service.py

O `codegen_service.py` existente gera código de forma genérica. Adicionar método
específico para geração de módulo aprovado no Gatekeeper:

```python
async def generate_module_from_candidate(
    self,
    db: AsyncSession,
    project_id: str,
    module_candidate_id: str
) -> str:
    """
    Orquestra a geração completa de um módulo aprovado.
    Retorna: generated_module_id

    Fluxo:
    1. Buscar module_candidate (nome, tipo, descrição, pilares, source_document_ids)
    2. Buscar OCG atual do projeto
    3. Buscar conteúdo dos source_documents do Git
    4. Buscar configurações de stack do projeto (OCG: Q47, Q48, Q49)
    5. Determinar framework de teste (ver tabela de mapeamento abaixo)
    6. Criar registro em generated_modules com status 'generating'
    7. Gerar código do módulo via LLM (ver prompt em 6.2.1)
    8. Commit do código no Git: src/modules/{module_slug}/
    9. Gerar testes unitários via LLM (ver prompt em 6.2.2)
    10. Commit dos testes: tests/unit/{module_slug}_test.{ext}
    11. Verificar se há outros módulos gerados com dependência (ver 6.2.3)
    12. Verificar se fonte inclui wireframes → gerar UAT (ver 6.2.4)
    13. Gerar documentação do módulo → commit em docs/modules/{module_slug}.md
    14. Atualizar generated_modules com status 'generated' e paths
    15. Atualizar module_candidates.status = 'completed'
    16. Disparar atualização da documentação viva (Fase 4)
    17. Retornar generated_module_id
    """
```

**Tabela de mapeamento Stack → Framework de Teste:**
```python
TEST_FRAMEWORK_MAP = {
    # Backend
    "python": {"unit": "pytest", "ext": "py"},
    "typescript": {"unit": "jest", "ext": "test.ts"},
    "javascript": {"unit": "jest", "ext": "test.js"},
    "java": {"unit": "junit5", "ext": "Test.java"},
    "csharp": {"unit": "xunit", "ext": "Tests.cs"},
    "go": {"unit": "testing", "ext": "_test.go"},
    "rust": {"unit": "cargo_test", "ext": "_test.rs"},

    # Frontend (para UAT)
    "react": {"uat": "playwright", "ext": "spec.ts"},
    "vue": {"uat": "playwright", "ext": "spec.ts"},
    "angular": {"uat": "cypress", "ext": "cy.ts"},
    "default_uat": {"uat": "playwright", "ext": "spec.ts"}
}
```

#### 6.2.1 Prompt de Geração de Código do Módulo

```python
MODULE_CODEGEN_SYSTEM = """
Você é um engenheiro de software sênior especializado em {backend_language} e {frontend_framework}.
Gere código de produção limpo, testável e bem documentado.
Siga as melhores práticas da stack ({backend_language}, {frontend_framework}, {database}).
Use os padrões de arquitetura definidos no OCG do projeto: {architecture_pattern}.
Responda SOMENTE com o código. Sem explicações. Sem markdown code blocks.
O código deve estar pronto para commit direto no repositório.
"""

MODULE_CODEGEN_USER = """
Gere o código completo para o módulo: {module_name}

Tipo: {module_type} (feature|component)
Descrição: {module_description}

OCG do Projeto (contexto):
{ocg_summary}

Documentação de referência (dos documentos ingeridos):
{source_documents_content}

Estrutura esperada de arquivos (liste todos e gere o conteúdo de cada um):
- src/modules/{module_slug}/__init__.py (se Python)
- src/modules/{module_slug}/models.py
- src/modules/{module_slug}/service.py
- src/modules/{module_slug}/router.py (se API endpoint)
- src/modules/{module_slug}/schemas.py
- src/modules/{module_slug}/README.md

Para cada arquivo, use o formato:
### ARQUIVO: src/modules/{module_slug}/models.py
{conteúdo do arquivo}
### FIM

Gere todos os arquivos necessários para o módulo funcionar completamente.
"""
```

Parsear a resposta para extrair os arquivos e commitar cada um separadamente no Git.

#### 6.2.2 Prompt de Geração de Testes Unitários

```python
UNIT_TEST_SYSTEM = """
Você é um engenheiro de QA sênior. Gere testes unitários completos usando {test_framework}.
Cubra: happy path, edge cases, erros esperados, valores limite.
Cada teste deve ser independente (sem estado compartilhado).
Mostre comentários explicando o que cada teste verifica.
Responda SOMENTE com o código de teste. Sem explicações fora do código.
"""

UNIT_TEST_USER = """
Gere testes unitários para o módulo: {module_name}

Código do módulo:
{module_code}

Framework de teste: {test_framework}
Cobertura mínima esperada: todas as funções/métodos públicos

Arquivo de saída: tests/unit/{module_slug}_test.{ext}
"""
```

#### 6.2.3 Geração de Testes de Integração

Trigger: quando um novo módulo é gerado e existem outros módulos já gerados que
têm dependência com ele (cruzando a tabela `module_candidates.dependencies`).

```python
async def generate_integration_tests(
    self,
    db: AsyncSession,
    project_id: str,
    new_module_id: str
) -> str | None:
    """
    1. Buscar todos os módulos gerados do projeto
    2. Identificar pares de módulos com dependência direta
    3. Para cada par que inclui new_module e não tem teste de integração:
       a. Buscar código de ambos os módulos do Git
       b. Gerar teste de integração via LLM
       c. Commit em tests/integration/test_{modulo_a}_{modulo_b}.{ext}
       d. Registrar em test_files
    4. Retornar path do arquivo criado ou None se não aplicável
    """

INTEGRATION_TEST_PROMPT = """
Gere testes de integração entre os módulos: {module_a_name} e {module_b_name}

Código do módulo A:
{module_a_code}

Código do módulo B:
{module_b_code}

Contexto da integração (dependência): {dependency_description}

Os testes devem verificar a interação entre os módulos, não cada módulo isoladamente.
Framework: {test_framework}
"""
```

#### 6.2.4 Geração de Testes UAT

Trigger: se algum dos `source_document_ids` do módulo tem `document_category == 'wireframe'`
ou `file_type == 'image'`.

```python
async def generate_uat_tests(
    self,
    db: AsyncSession,
    project_id: str,
    module_id: str
) -> str | None:
    """
    1. Verificar se source_documents inclui wireframes
    2. Buscar conteúdo/descrição dos wireframes (análise do Arguidor)
    3. Gerar roteiro UAT em linguagem natural + script automatizado
    4. Commit em tests/uat/{module_slug}_uat.md (roteiro) +
               tests/uat/{module_slug}.spec.ts (script Playwright)
    5. Retornar path ou None
    """

UAT_TEST_PROMPT = """
Gere testes de UAT para o módulo: {module_name}

Wireframes/Screenshots analisados:
{wireframe_descriptions}

Funcionalidades a testar (baseado no módulo):
{module_description}

Gere:
1. Roteiro UAT em Markdown (casos de teste em linguagem natural para humanos)
2. Script Playwright/Cypress em {uat_framework} (automação)

Use o formato:
### ARQUIVO: tests/uat/{module_slug}_uat.md
{roteiro em markdown}
### FIM

### ARQUIVO: tests/uat/{module_slug}.spec.ts
{script automatizado}
### FIM
"""
```

---

### 6.3 Novos Endpoints — Fase 3

Adicionar ao router existente de codegen ou criar `module_router.py`:

```
POST   /api/v1/projects/{project_id}/modules/{module_candidate_id}/generate
       Auth: Bearer (papel 'developer' ou 'gp')
       -- Normalmente disparado automaticamente pela aprovação no Gatekeeper
       -- Endpoint manual para reprocessar em caso de erro
       Response: {generated_module_id, status: 'generating'}

GET    /api/v1/projects/{project_id}/modules
       Auth: Bearer (qualquer membro)
       Response: lista de módulos gerados com status e paths

GET    /api/v1/projects/{project_id}/modules/{generated_module_id}
       Auth: Bearer (qualquer membro)
       Response: módulo completo + arquivos gerados + paths no Git

GET    /api/v1/projects/{project_id}/modules/{generated_module_id}/status
       Auth: Bearer (qualquer membro)
       Response: {status, generated_at, error_message}

GET    /api/v1/projects/{project_id}/tests
       Auth: Bearer (qualquer membro)
       Response: {
         unit: [{module_name, framework, git_path, created_at}],
         integration: [{modules, framework, git_path, created_at}],
         uat: [{module_name, framework, git_path, created_at}]
       }
```

#### 6.3.1 Testes — Fase 3

Criar `backend/tests/test_module_generation.py`:
```python
# Teste 1: generate_module_from_candidate com projeto configurado → status 'generating'
# Teste 2: geração completa (mock LLM) → status 'generated', paths preenchidos
# Teste 3: geração com LLM falhando → status 'error', error_message preenchido
# Teste 4: dois módulos com dependência → teste de integração gerado
# Teste 5: módulo com wireframe no source → teste UAT gerado
# Teste 6: módulo sem wireframe → git_uat_test_path é null
# Teste 7: GET /modules → lista módulos com status correto
# Teste 8: GET /tests → agrupa por tipo corretamente
```

---

**CHECKPOINT FASE 3:**
- [ ] 54+ testes passando
- [ ] Código de módulo sendo gerado e commitado no Git do projeto
- [ ] Testes unitários gerados para cada módulo
- [ ] Testes de integração gerados quando há dependência entre módulos
- [ ] Testes UAT gerados quando há wireframes associados
- [ ] Status de geração acessível via polling

---

## 7. FASE 4 — DOCUMENTAÇÃO VIVA

**Pré-requisito:** Fases 0, 1, 2 e 3 completas (mas pode iniciar paralelamente à Fase 3).
**Descrição:** a documentação viva é gerada e mantida automaticamente pelo GCA
no repositório Git do projeto e exibida na LiveDocsPage dentro do GCA.
Ela é atualizada em cada evento significativo do projeto.

---

### 7.1 Estrutura de Documentação no Git por Projeto

A estrutura abaixo deve existir após `initialize_repository_structure` (Fase 0.1)
e ser mantida atualizada automaticamente:

```
/docs/
  /functional/
    overview.md           ← visão geral funcional do projeto (do OCG P1/P3)
    user_stories.md       ← user stories extraídas do questionário e documentos ingeridos
    business_rules.md     ← regras de negócio (OCG P2 + documentos ingeridos)
  /technical/
    architecture.md       ← arquitetura do sistema (OCG P5)
    stack.md              ← stack tecnológica escolhida
    api_endpoints.md      ← endpoints gerados (atualizado a cada módulo)
    data_model.md         ← modelo de dados (OCG P6)
  /security/
    compliance.md         ← requisitos LGPD/GDPR e controles (OCG P2/P7)
  /modules/
    {module_slug}.md      ← documentação de cada módulo gerado
  /tests/
    test_plan.md          ← plano de testes consolidado
    unit_coverage.md      ← cobertura de testes unitários
    integration_plan.md   ← plano de testes de integração
    uat_plan.md           ← plano de testes UAT
  /ingested/
    {category}/
      {filename}          ← arquivo original
      {filename}.analysis.json ← análise do Arguidor
  ocg_current.md          ← OCG atual em formato legível (atualizado a cada versão)
  ocg_history.md          ← histórico de versões do OCG
  CHANGELOG.md            ← changelog automático do projeto

README.md                 ← visão geral do projeto
```

---

### 7.2 Novo Serviço: livedocs_service.py

Localização: `backend/services/livedocs_service.py`

```python
class LiveDocsService:

    async def generate_initial_documentation(
        self, db: AsyncSession, project_id: str
    ) -> bool:
        """
        Chamado quando OCG é gerado pela primeira vez.
        Gera todos os arquivos da estrutura /docs usando dados do OCG.
        Usa Claude claude-opus-4-6 para gerar conteúdo em Markdown.
        Retorna True se todos os arquivos foram commitados com sucesso.
        """

    async def update_on_document_ingested(
        self, db: AsyncSession, project_id: str, document_id: str
    ) -> bool:
        """
        Chamado após Arguidor completar análise.
        Atualiza: user_stories.md, business_rules.md, ocg_current.md,
                  ocg_history.md (se OCG foi atualizado), CHANGELOG.md
        """

    async def update_on_module_generated(
        self, db: AsyncSession, project_id: str, module_id: str
    ) -> bool:
        """
        Chamado após módulo ser gerado.
        Cria/atualiza: docs/modules/{module_slug}.md,
                       api_endpoints.md (se módulo tem endpoints),
                       test_plan.md, unit_coverage.md,
                       integration_plan.md (se há testes de integração),
                       uat_plan.md (se há testes UAT),
                       CHANGELOG.md
        """

    async def refresh_ocg_documentation(
        self, db: AsyncSession, project_id: str
    ) -> bool:
        """
        Regenera ocg_current.md e ocg_history.md com dados atuais do banco.
        """

    async def get_doc_section(
        self, project_id: str, section_path: str
    ) -> str | None:
        """
        Busca o conteúdo de uma seção da documentação diretamente do Git.
        Retorna o conteúdo Markdown ou None se não existir.
        """

    async def get_doc_index(self, db: AsyncSession, project_id: str) -> list[dict]:
        """
        Lista todas as seções disponíveis com metadados (última atualização).
        Busca os arquivos do Git via git_service.list_files.
        """

    def build_initial_docs_prompt(self, ocg_data: dict, project_name: str) -> dict:
        """
        Retorna um dict com prompts por seção:
        {
          'functional/overview': 'Prompt para gerar overview.md baseado no OCG...',
          'functional/user_stories': 'Prompt para gerar user_stories.md...',
          ...
        }
        Cada prompt usa dados específicos do OCG para a seção correspondente.
        """

    def generate_changelog_entry(self, event_type: str, details: dict) -> str:
        """
        Gera uma entrada para o CHANGELOG.md no formato:
        ## [data] - tipo_evento
        - detalhe
        """
```

**Commits da documentação viva:**
Toda atualização usa a convenção:
- `[GCA] docs: geração inicial após OCG aprovado`
- `[GCA] docs: atualiza overview após ingestão de {filename}`
- `[GCA] docs: adiciona módulo {module_name}`
- `[GCA] docs: atualiza plano de testes com UAT de {module_name}`

---

### 7.3 Novos Endpoints — Fase 4

Router: `backend/routers/livedocs_router.py` — incluir em `main.py`

```
GET    /api/v1/projects/{project_id}/livedocs
       Auth: Bearer (qualquer membro)
       Response: {sections: [{name, path, last_updated, size_bytes}],
                  last_sync: datetime,
                  total_sections: int}

GET    /api/v1/projects/{project_id}/livedocs/content
       Auth: Bearer (qualquer membro)
       Query param: path=docs/functional/overview.md
       Response: {content: "conteúdo markdown", path, last_updated}
       Response 404: {error: "Seção não encontrada"}

GET    /api/v1/projects/{project_id}/livedocs/ocg/history
       Auth: Bearer (qualquer membro)
       Response: lista de versões do OCG com {version, timestamp, summary_of_changes}

POST   /api/v1/projects/{project_id}/livedocs/refresh
       Auth: Bearer (GP apenas)
       Response: {success: true, sections_updated: int}
       -- Força resincronização com o repositório Git

GET    /api/v1/projects/{project_id}/livedocs/changelog
       Auth: Bearer (qualquer membro)
       Response: {content: "conteúdo do CHANGELOG.md"}
```

---

### 7.4 Frontend — LiveDocsPage

Rota: `/projects/:id/livedocs`
Substituir o placeholder existente.

#### 7.4.1 Layout

```
[Header: "Documentação Viva"]
[Botão "Sincronizar" (GP apenas) | Última sincronização: {datetime}]

[Sidebar de navegação — árvore de documentos]
  📁 Funcional
    📄 Visão Geral
    📄 User Stories
    📄 Regras de Negócio
  📁 Técnica
    📄 Arquitetura
    📄 Stack
    📄 API Endpoints
    📄 Modelo de Dados
  📁 Segurança
    📄 Compliance
  📁 Módulos
    📄 {módulo 1}
    📄 {módulo 2}
  📁 Testes
    📄 Plano de Testes
    📄 Cobertura Unitária
    📄 Plano de Integração
    📄 Plano UAT
  📄 OCG Atual
  📄 Histórico do OCG
  📄 Changelog

[Área principal: renderiza o Markdown selecionado]
  Usar biblioteca de renderização Markdown já disponível no projeto.
  Se não houver, usar react-markdown (adicionar dependência).
  Exibir última atualização do arquivo selecionado.
```

#### 7.4.2 Painel de Histórico do OCG

Ao selecionar "Histórico do OCG", exibir linha do tempo:

```
[Versão 3 — 07/04/2026] — CURRENT
  Alterações: stack atualizada, P3 score revisado
  Gatilho: ingestão de "especificacao_funcional_v2.pdf"
  [Ver diff ↓]

[Versão 2 — 05/04/2026]
  Alterações: regras LGPD detalhadas, P2 score atualizado
  Gatilho: ingestão de "politica_privacidade.docx"
  [Ver diff ↓]

[Versão 1 — 03/04/2026] — OCG Inicial
  Gerado a partir do questionário de 54 campos
```

#### 7.4.3 Testes — Fase 4

Criar `backend/tests/test_livedocs.py`:
```python
# Teste 1: generate_initial_documentation → arquivos criados no Git
# Teste 2: update_on_document_ingested → CHANGELOG atualizado
# Teste 3: update_on_module_generated → docs/modules/{slug}.md criado
# Teste 4: GET livedocs → lista de seções com metadados
# Teste 5: GET livedocs/content?path=... → conteúdo Markdown
# Teste 6: GET livedocs/content?path=inexistente → 404
# Teste 7: GET livedocs/ocg/history → histórico de versões
# Teste 8: POST livedocs/refresh por non-GP → 403
```

---

**CHECKPOINT FASE 4:**
- [ ] 54+ testes passando
- [ ] Documentação inicial gerada automaticamente após OCG
- [ ] LiveDocsPage renderizando documentação do Git
- [ ] Histórico de versões do OCG visível
- [ ] Changelog sendo atualizado automaticamente
- [ ] Sincronização manual funcionando

---

## 8. FASE 5 — FUNCIONALIDADES COMPLEMENTARES

**Pré-requisito:** Fases 0 a 4 completas.
**Descrição:** funcionalidades de suporte que completam a experiência do GCA
mas não bloqueiam as fases anteriores.

---

### 8.1 RoadmapPage

Rota: `/projects/:id/roadmap`

**Backend — novo endpoint:**
```
GET /api/v1/projects/{project_id}/roadmap
Auth: Bearer (qualquer membro)
Response: {
  phases: [
    {
      name: "Fase 1 — Fundação",
      status: "completed|in_progress|pending",
      modules: [{name, status, created_at}],
      estimated_completion: date
    }
  ],
  total_modules: int,
  completed_modules: int,
  next_action: "string descrevendo próximo passo recomendado"
}
```

**Lógica:** gerar roadmap dinamicamente a partir do estado dos `module_candidates`
e `generated_modules`. Módulos com `priority='high'` vão na Fase 1, `medium` na Fase 2, `low` na Fase 3.

**Frontend:**
- Linha do tempo visual (horizontal ou vertical)
- Cards de módulos por fase com status colorido
- Indicador de progresso geral (% concluído)

---

### 8.2 LegacyPage

Rota: `/projects/:id/legacy`

**Propósito:** ingerir um codebase existente (zip de código ou URL de repositório
legado) para análise pelo Arguidor com foco em: debt técnico, padrões existentes,
conflitos com a stack do OCG, módulos já implementados.

**Backend:**
```
POST /api/v1/projects/{project_id}/legacy/analyze
Auth: Bearer (GP apenas)
Body: {source_type: 'zip'|'git_url', source: arquivo ou URL, branch: 'main'}
Response: {job_id, status: 'analyzing'}

GET /api/v1/projects/{project_id}/legacy/status/{job_id}
Auth: Bearer (qualquer membro)
Response: {status, progress_percent, current_step}

GET /api/v1/projects/{project_id}/legacy/result/{job_id}
Auth: Bearer (qualquer membro)
Response: análise completa do Arguidor sobre o codebase legado
```

**Nota:** esta feature reusa ArguiderService com prompt específico para código legado.

---

### 8.3 MergeEnginePage

Rota: `/projects/:id/merge`

**Propósito:** quando um módulo é gerado e o repositório já tem código existente
para aquela funcionalidade, o MergeEngine compara e propõe um merge inteligente.

**Backend:**
```
POST /api/v1/projects/{project_id}/merge/compare
Auth: Bearer (Developer ou GP)
Body: {generated_module_id, existing_file_path}
Response: {diff, conflicts, merge_suggestion, confidence_score}

POST /api/v1/projects/{project_id}/merge/apply
Auth: Bearer (Developer apenas)
Body: {merge_result, target_path}
Response: {success: true, commit_sha}
```

**Frontend:**
- Diff viewer (lado a lado: código existente vs código gerado)
- Sugestão de merge com destaque de conflitos
- Botões: "Aplicar merge sugerido" | "Manter existente" | "Usar gerado"

---

### 8.4 Parametrização do Admin (Pilares e Thresholds)

**Objetivo:** permitir que o Admin do GCA ajuste os pesos dos pilares e os
thresholds de score sem alterar código.

**Tabela existente:** `pillar_configuration` (já existe no schema do projeto).

**Novos endpoints admin:**
```
GET    /api/v1/admin/gca/settings
       Response: {pillar_weights, score_thresholds, agent_config}

PUT    /api/v1/admin/gca/settings/pillar-weights
       Body: {P1: 10, P2: 15, P3: 20, P4: 20, P5: 15, P6: 10, P7: 10}
       Validação: soma deve ser exatamente 100
       Response: {success: true}

PUT    /api/v1/admin/gca/settings/thresholds
       Body: {p7_blocking_threshold: 70, ready_threshold: 90,
              needs_review_threshold: 70, at_risk_threshold: 50}
       Response: {success: true}
```

**Frontend:** nova aba na `SettingsPage` admin.

---

## 9. CRITÉRIOS DE ACEITAÇÃO GLOBAIS

Ao concluir todas as 5 fases, o sistema deve atender:

### 9.1 Funcionais

- [ ] Admin pode ver lista de todos os projetos mas não acessar dados funcionais sem papel
- [ ] Admin com papel em projeto acessa apenas pelo papel cadastrado
- [ ] Projeto sem repositório Git não aceita ingestão de documentos
- [ ] Cada projeto tem seus próprios secrets criptografados e isolados
- [ ] Ingestão de documento → Arguidor → Gatekeeper funciona end-to-end
- [ ] Aprovação de módulo → CodeGen → Git funciona end-to-end
- [ ] Documentação viva é atualizada automaticamente nos eventos corretos
- [ ] OCG evolui (nova versão) após cada ingestão que impacta seus campos
- [ ] Logs de ação do projeto são visíveis para Admin no audit log
- [ ] Testes unitários são gerados para cada módulo aprovado
- [ ] Testes de integração são gerados quando há dependência entre módulos
- [ ] Testes UAT são gerados para módulos com wireframes associados

### 9.2 Não Funcionais

- [ ] Todos os 54 testes originais continuam passando
- [ ] Build do frontend sem erros (2333+ módulos)
- [ ] Nenhum endpoint existente teve comportamento alterado
- [ ] Nenhuma tabela existente foi removida ou teve coluna removida
- [ ] Secrets nunca trafegam em plain text nas respostas da API
- [ ] Todas as operações longas (Arguidor, CodeGen, LiveDocs) são assíncronas
- [ ] Polling de status disponível para todas as operações assíncronas
- [ ] PAT do Git mascarado após salvo (exibido como "***")

### 9.3 Testes de Regressão Final

Executar antes de marcar o projeto como concluído:

```bash
# 1. Todos os testes backend
cd backend && pytest tests/ -v --tb=short
# Esperado: N passed, 0 failed (N >= 54)

# 2. Build frontend
cd frontend && npm run build
# Esperado: 0 errors

# 3. Health check de produção
curl https://api.code-auditor.com.br/api/v1/dashboard/health
# Esperado: {"status": "healthy", ...}

# 4. Teste de login
curl -X POST https://api.code-auditor.com.br/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@test.com", "password": "senha_teste"}'
# Esperado: access_token presente na resposta

# 5. Docker compose up sem erros
docker-compose up -d && sleep 10 && docker-compose ps
# Esperado: todos os 5 serviços "Up (healthy)"
```

---

## 10. ORDEM DE EXECUÇÃO RECOMENDADA PARA CLAUDE CODE

Execute as fases na seguinte ordem, confirmando o checkpoint de cada fase antes de avançar:

```
1. FASE 0.1 → testes → checkpoint
2. FASE 0.2 → testes → checkpoint
3. FASE 0.3 → testes → checkpoint
4. FASE 0.4 → testes → checkpoint
5. FASE 0.5 → testes → checkpoint
6. CHECKPOINT FASE 0 completo → avançar
7. FASE 1 (banco + ArguiderService + IngestionService + endpoints + frontend)
8. CHECKPOINT FASE 1 → avançar
9. FASE 2 (GatekeeperService + endpoints + frontend)
10. CHECKPOINT FASE 2 → avançar
11. FASE 3 (module codegen + test generation)
12. FASE 4 (pode iniciar em paralelo com Fase 3)
13. CHECKPOINT FASES 3 e 4 → avançar
14. FASE 5 (complementar, por prioridade: Roadmap → Admin Params → Legacy → Merge)
15. CRITÉRIOS DE ACEITAÇÃO GLOBAIS
```

---

*FIM DO DOCUMENTO — TASK_GCA_MASTER.md*
*Versão 1.0 | 08/04/2026 | Luiz Carlos Pielak*
*Repositório: https://github.com/Pielak/GCA.git*
