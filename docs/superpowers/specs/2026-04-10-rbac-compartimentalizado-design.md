# Design: RBAC Compartimentalizado — Workspace do GP

**Data:** 2026-04-10
**Status:** Aprovado
**Abordagem:** Permissões por Ação (Abordagem 1)

---

## 1. Sistema de Permissoes por Acao

### Acoes Definidas

| Acao | Descricao |
|------|-----------|
| `project:view` | Visualizar dados do projeto (abas, pipeline, membros) |
| `project:edit` | Editar configuracoes do projeto (repo, AI keys, settings) |
| `project:manage_team` | Convidar/remover membros, atribuir papeis |
| `project:manage_gp` | Substituir/adicionar GP (exclusivo Admin) |
| `pipeline:execute` | Executar etapas do pipeline (ingestion, gatekeeper, codegen, etc.) |
| `pipeline:review` | Aprovar/rejeitar resultados de etapas (QA, Tester Review) |
| `code:write` | Gerar/editar codigo, merge, commits |
| `docs:edit` | Editar documentacao, roadmap, backlog |

### Mapeamento Papel -> Acoes

| Papel | Acoes |
|-------|-------|
| **Admin** (sem membership) | `project:view`, `project:manage_gp` |
| **GP** | `project:view`, `project:edit`, `project:manage_team`, `pipeline:execute`, `pipeline:review`, `docs:edit` |
| **Tech Lead** | `project:view`, `pipeline:execute`, `pipeline:review`, `code:write`, `docs:edit` |
| **Dev Senior** | `project:view`, `pipeline:execute`, `code:write` |
| **Dev Pleno** | `project:view`, `code:write` |
| **QA** | `project:view`, `pipeline:review` |
| **Compliance** | `project:view` |
| **Stakeholder** | `project:view` |

### Dependency: require_action()

```python
@router.post("/projects/{project_id}/settings/llm")
async def update_llm_settings(
    project_id: UUID,
    user=Depends(require_action("project:edit"))
):
    ...
```

O `require_action()` resolve o papel do usuario no projeto, verifica se tem a acao, retorna 403 se nao.

---

## 2. Dashboard do GP

### Fluxo de Login

1. GP faz login -> backend retorna `user.is_admin = false` + lista de `project_memberships`
2. Frontend detecta que nao e Admin -> redireciona para `/projects`
3. `/projects` renderiza cards dos projetos

### Layout dos Cards

Cada card mostra:
- **Nome do projeto** (titulo principal)
- **Status** (badge: `Em configuracao`, `Ativo`, `Arquivado`)
- **Papel do usuario** naquele projeto (ex: "Gerente de Projeto", "Dev Senior")
- **Ultimo acesso** (data relativa: "ha 2 horas")
- **Score Gatekeeper** (barra de progresso, se existir)
- **Membros ativos** (avatares pequenos, max 5 + "+N")

### Regras de Filtragem

- GP ve apenas projetos onde e `ProjectMember` ativo (`accepted_at IS NOT NULL`, `is_active = true`)
- Admin ve todos os projetos com badge "Somente Leitura" nos que nao e membro
- Dev/QA/etc ve apenas projetos onde participa
- Zero dados cruzados entre projetos

### Ao Clicar no Card

- Ativa projeto via `POST /projects/{id}/activate`
- Redireciona para `/projects/{id}` (workspace compartimentalizado)
- Header mostra nome do projeto ativo, sem referencia a outros

### Contexto Duplo: Admin + GP

Um usuario pode ser Admin (`is_admin = true`) e GP de projetos simultaneamente.

**Logica de Resolucao:**
```
Se usuario e membro do projeto:
    -> usa o papel do ProjectMember (gp, dev, qa, etc.)
    -> permissoes daquele papel, independente de is_admin
Se usuario NAO e membro mas is_admin = true:
    -> project:view + project:manage_gp (read-only + substituir GP)
Se NAO e membro e NAO e admin:
    -> 403 sem acesso
```

**No Dashboard:**
- Se `is_admin = true` -> mostra link "Painel Admin" no header
- Secao "Meus Projetos" (onde e membro, com papel real)
- Secao "Todos os Projetos" (read-only, para Admin)

---

## 3. Workspace Compartimentalizado do Projeto

### Setup Wizard (GP Configura)

Quando projeto recem-aprovado (`status = "initializing"`), GP e direcionado ao Setup Wizard:

| Etapa | O que configura | Quem faz |
|-------|----------------|----------|
| 1. Repositorio | URL do repo, provider (GitHub/GitLab/BB), token de acesso | GP |
| 2. Chaves de IA | Provider (Anthropic/OpenAI/etc), API key, modelo preferido | GP |
| 3. Equipe | Convida membros por e-mail com papel definido | GP |
| 4. Confirmacao | Revisa tudo, ativa o projeto | GP |

**Mudancas vs atual:**
- Remover etapa SMTP do wizard (agora e global)
- Remover etapa de arquitetura/stack (vem do OCG pos-Gatekeeper)
- GP so avanca quando cada etapa esta completa

### Chaves de IA por Projeto

- Armazenadas no Vault (criptografadas), vinculadas ao `project_id`
- GP configura via `/projects/{id}/settings`
- Cada projeto usa suas proprias chaves — sem fallback para chaves globais
- Se nao configurou -> pipeline bloqueia com mensagem clara

### Convites de Equipe (dentro do workspace)

- GP acessa aba "Equipe" (`/projects/{id}/team`)
- Convida por e-mail + papel (Tech Lead, Dev Senior, Dev Pleno, QA, Compliance, Stakeholder)
- **Nao pode convidar outro GP** — isso e acao de Admin (`project:manage_gp`)
- Membro convidado recebe e-mail com nome do projeto no subject
- Reply-to configurado para e-mail do GP

### Isolamento de Dados

- Cada projeto usa schema isolado no banco (`proj_{slug}_*`)
- Queries sempre filtram por `project_id`
- Frontend carrega dados apenas do projeto ativo via `UserProjectContext`
- Nenhum endpoint retorna dados de multiplos projetos misturados

---

## 4. Admin Read-Only + Gestao de GP

### Visao Read-Only do Admin

Quando Admin navega para projeto onde nao e membro:

**Backend:**
- `require_action("project:view")` -> permite
- `require_action("project:edit")` -> 403
- `require_action("pipeline:execute")` -> 403
- Endpoints GET funcionam normalmente
- Endpoints POST/PUT/PATCH/DELETE rejeitam com 403

**Frontend:**
- Banner fixo no topo: "Modo somente leitura — voce nao e membro deste projeto"
- Botoes de acao `disabled` com tooltip "Somente leitura"
- Formularios com campos desabilitados
- Abas de navegacao funcionam normalmente

### Gestao de GP pelo Admin

Acessivel via painel Admin (`/admin/projects`) ou dentro do projeto em read-only.

**Acoes disponiveis (`project:manage_gp`):**

| Acao | Descricao |
|------|-----------|
| **Adicionar GP** | Convida novo GP por e-mail -> recebe papel "gp" no projeto |
| **Remover GP** | Remove GP atual -> perde acesso de gestao |
| **Substituir GP** | Atalho: remove atual + convida novo em uma operacao |

**Endpoint novo:**
```
POST /admin/projects/{project_id}/manage-gp

# Adicionar novo GP (pode ter multiplos GPs)
Body: { action: "add", email: str }

# Remover GP (proibido se for o ultimo)
Body: { action: "remove", remove_user_id: UUID }

# Substituir GP (remove + adiciona em uma operacao atomica)
Body: { action: "replace", email: str, remove_user_id: UUID }
```

**Regras:**
- Projeto deve ter pelo menos 1 GP ativo — nao pode remover o ultimo sem adicionar outro
- Novo GP recebe e-mail de notificacao com contexto do projeto
- GP removido recebe e-mail informando a remocao
- Log de auditoria registra toda operacao

### AdminProjectsPage (ajustes)

- Coluna "GP Responsavel" (nome + e-mail)
- Botao "Gerenciar GP" em cada projeto
- Filtro por status: Aguardando Configuracao / Ativo / Arquivado

---

## 5. SMTP Global com Contexto de Projeto

### Configuracao

- SMTP configurado uma vez pelo Admin em `/admin/settings`
- Credenciais armazenadas no Vault como configuracao global (sem `project_id`)
- Nao aparece mais no Setup Wizard do GP

### Contextualizacao dos E-mails

**Subject:**
```
[GCA - {nome_do_projeto}] {assunto especifico}
```

Exemplos:
- `[GCA - E-Commerce Platform] Convite para equipe de desenvolvimento`
- `[GCA - App Financeiro] Resultado da analise Gatekeeper`

**Reply-To:**
- Convites de equipe -> e-mail do GP que convidou
- Notificacoes de pipeline -> e-mail do membro responsavel pela etapa
- Notificacoes administrativas -> e-mail do Admin que executou

**From:**
```
GCA - {nome_do_projeto} <noreply@code-auditor.com.br>
Reply-To: {email_do_responsavel}
```

### E-mails Fora de Contexto de Projeto

- Reset de senha, primeiro acesso: `[GCA] Redefinicao de senha`
- Aprovacao de projeto: `[GCA] Seu projeto "{nome}" foi aprovado`

### Implementacao no EmailService

```python
async def send_project_email(
    to: str,
    subject: str,
    body: str,
    project_name: str,
    reply_to: str | None,
):
    full_subject = f"[GCA - {project_name}] {subject}"
    headers = {"Reply-To": reply_to} if reply_to else {}
    # usa credenciais SMTP globais do Vault
```

---

## 6. Frontend — Componentes e Fluxo

### Hook de Permissoes

```typescript
const { can, role, isReadOnly } = useProjectPermissions()

can("project:edit")       // true/false
can("pipeline:execute")   // true/false
isReadOnly                // true se so tem project:view
role                      // "gp", "dev_senior", "admin_viewer", etc.
```

### Componentes Afetados

**ProjectDetailLayout:**
- Carrega permissoes do usuario no projeto ao montar
- Injeta `permissions` no contexto do Outlet
- Se `isReadOnly` -> mostra banner "Somente leitura"

**ProjectListPage:**
- Nao-Admin: lista so projetos onde e membro
- Admin: secao "Meus Projetos" + secao "Todos os Projetos" (read-only)
- Card mostra papel do usuario e badge quando read-only

**Paginas de Pipeline (Ingestion, Gatekeeper, CodeGen, etc.):**
- Botoes de acao: `disabled={!can("pipeline:execute")}`
- Formularios: `readOnly={!can("project:edit")}`
- Mesma interface, so desabilita interacao

**ProjectTeamPage:**
- Formulario de convite visivel so se `can("project:manage_team")`
- Lista de membros visivel para todos com `project:view`

**ProjectSettingsPage:**
- Campos editaveis so se `can("project:edit")`
- Admin ve configuracoes mas nao altera

### Redirecionamento Pos-Login

```
Se is_admin e NAO tem projetos como membro -> /admin
Se is_admin e TEM projetos como membro -> /projects (com link ao painel Admin no header)
Se NAO e admin -> /projects
```

### Header

- Dentro de projeto: nome do projeto, papel do usuario, botao "Voltar aos Projetos"
- Se Admin: icone/link "Painel Admin" sempre visivel no header
- Sem selector de projeto no header — troca via `/projects` (cards)
