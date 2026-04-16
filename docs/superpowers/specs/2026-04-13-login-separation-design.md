# Separação de Login Admin / GP+Equipe — Design Spec

## Objetivo

Separar completamente a área do Admin da área do GP e equipe, com URLs distintas, fluxos de onboarding diferentes, e compartimentalização total entre projetos.

## URLs

| Quem | URL | Descrição |
|------|-----|-----------|
| Admin | `gca.code-auditor.com.br/login` | Login do sistema administrativo |
| GP + Equipe | `gca.code-auditor.com.br/p/{slug}` | Login por projeto (ex: `/p/financehub-pro`) |

- `slug`: nome curto, max 15 chars, lowercase alfanumérico + hífens
- Gerado automaticamente na criação do projeto
- Único globalmente (inclui projetos arquivados)
- Armazenado em campo `short_slug` na tabela `projects`

## Fluxo Admin (sem mudanças)

1. Admin acessa `/login`
2. Login com email/senha
3. Redireciona para `/admin` (dashboard global)
4. Admin pode criar projetos, aprovar GPs, configurar sistema
5. Admin NÃO acessa dados internos dos tenants

## Fluxo GP (novo)

1. GP solicita uso do GCA (formulário público ou contato direto)
2. Admin aprova → sistema gera:
   - Projeto com `short_slug` único
   - Convite para GP com senha provisória via email
   - Email contém URL do projeto: `gca.code-auditor.com.br/p/{slug}`
3. GP acessa URL do projeto → tela de login do projeto
4. Login com email + senha provisória
5. Troca de senha obrigatória (first access)
6. **Primeira tela: Ingestão** (upload de documentos, opcional mas recomendado)
7. **Segunda tela: Questionário Inteligente**
   - Perguntas adaptam-se com base nos docs ingeridos
   - Perguntas já respondidas por documentação são puladas
   - Barra de progresso: docs + questionário = X% de 95%
   - Para avançar: >= 95% de completude
8. Após 95%: GP pode convidar equipe
   - Mesmo processo: email + senha provisória + URL do projeto
9. Pipeline normal continua (Gatekeeper → OCG → etc.)

## Fluxo Equipe do Projeto

1. GP convida membro → sistema envia email com:
   - Senha provisória
   - URL do projeto: `gca.code-auditor.com.br/p/{slug}`
   - Papel atribuído (Dev, QA, Tech Lead, etc.)
2. Membro acessa URL → login do projeto
3. Troca senha obrigatória
4. Vê apenas o que seu papel permite (RBAC)
5. Se participa de múltiplos projetos → tem múltiplas URLs, cada uma é um login separado

## Compartimentalização

- Cada projeto é 100% isolado (tenant)
- Mesmo GP em 2 projetos = 2 contextos separados
- Dados de um projeto NUNCA vazam para outro
- Admin vê métricas agregadas, NÃO dados internos
- Repos contextuais visíveis para toda equipe do tenant, NÃO para Admin

## Mudanças Técnicas

### Backend

#### 1. Campo `short_slug` na tabela `projects`
- Tipo: `String(15)`, unique, indexed
- Gerado automaticamente: pega nome do projeto, sanitiza, trunca em 15 chars
- Se conflitar, adiciona sufixo numérico (ex: `financehub-2`)
- Validação: `^[a-z0-9][a-z0-9-]{1,13}[a-z0-9]$`

#### 2. Endpoint de resolução de slug
- `GET /api/v1/projects/by-slug/{slug}` → retorna project_id, name, status
- Público (sem auth) — apenas retorna se projeto existe e está ativo
- NÃO retorna dados sensíveis

#### 3. Login com contexto de projeto
- `POST /api/v1/auth/project-login` → email, senha, project_slug
- Valida: usuário existe, senha correta, é membro do projeto
- Retorna: JWT com `project_id` no payload + dados do projeto
- Se não for membro: 403 "Você não tem acesso a este projeto"

#### 4. Geração automática de slug
- Na criação do projeto (router `projects.py`)
- Função `generate_short_slug(name: str)` → sanitiza, verifica unicidade

#### 5. Convite com URL do projeto
- `InvitationToken` já tem `project_id` → adicionar `project_slug` ao email
- Template de email inclui link: `{FRONTEND_URL}/p/{slug}`

### Frontend

#### 1. Nova rota `/p/:slug`
- Rota pública (sem auth)
- Resolve slug → mostra tela de login do projeto
- Branding: nome do projeto no header
- Após login: redireciona para dashboard do projeto

#### 2. Nova rota `/p/:slug/login`
- LoginPage com contexto de projeto
- Campos: email, senha
- Chama `POST /api/v1/auth/project-login`
- Após first access: redireciona para `/p/:slug/ingestion`

#### 3. Rotas do projeto sob `/p/:slug/...`
- `/p/:slug/ingestion` → IngestãoPage
- `/p/:slug/questionnaire` → QuestionárioPage
- `/p/:slug/dashboard` → ProjectDashPage
- `/p/:slug/team` → ProjectTeamPage (GP only, após 95%)
- `/p/:slug/...` → demais páginas do pipeline

#### 4. Login admin fica em `/login` (sem mudança)
- Redireciona para `/admin` após login
- Não mostra projetos na URL

### Migração

1. Alembic migration: adicionar `short_slug` em `projects`
2. Script de backfill: gerar slugs para projetos existentes
3. Projeto FinanceHub Pro: gerar slug `financehub-pro`

## Testes

- Gerar slug sem conflito
- Login via slug com membro válido → 200
- Login via slug com não-membro → 403
- Login via slug com projeto inexistente → 404
- Login via slug com projeto arquivado → 410
- First access + troca de senha via URL de projeto
- Convite com URL de projeto no email
- Admin NÃO consegue logar via `/p/{slug}`
- Múltiplos projetos = múltiplas URLs funcionam independentemente
