# Design: Multi-Papeis + Backlog Inteligente + CodeGen Real

**Data:** 2026-04-10
**Status:** Aprovado

---

## Contexto

O GP pode acumular multiplos papeis no projeto (GP + Dev Senior + QA, etc.) para executar atividades que exigem papeis especificos. Cada acao registra quem fez e com qual papel (trilha de auditoria). O CodeGen busca escopo do Backlog Inteligente, que e gerado por IA a partir dos documentos ingeridos, stack e OCG. O backlog verifica completude de artefatos e compliance ISO 27001 antes de liberar itens para geracao.

---

## 1. Modelo de Dados — Multiplos Papeis

**Nova tabela: `ProjectMemberRole`**

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | UUID PK | |
| member_id | FK -> ProjectMember | Membro do projeto |
| role | String | "gp", "tech_lead", "dev_senior", "dev_pleno", "qa", "compliance", "stakeholder" |
| assigned_at | DateTime | Quando o papel foi atribuido |
| assigned_by | FK -> User | Quem atribuiu (o proprio GP ou Admin) |

**Regras:**
- Um membro pode ter multiplos papeis simultaneos
- GP e o papel base — nao pode ser removido pelo proprio GP
- Cada acao no pipeline registra `user_id + role_used` no audit log
- `permissions.py` acumula acoes de todos os papeis do membro

---

## 2. Auto-atribuicao de Papeis pelo GP

### Na aba Equipe (`/projects/{id}/team`)

O GP ve seus proprios papeis com botao "Adicionar Papel":
- Lista papeis disponiveis (Tech Lead, Dev Senior, Dev Pleno, QA, Compliance, Stakeholder)
- Seleciona um ou mais, salva
- Audit log: "GP pielak@... assumiu papel Dev Senior em 2026-04-10"

### No pipeline (on-demand)

Quando acao exige papel que o GP nao tem:
- Mensagem: "Esta acao requer papel de Dev Senior"
- Botao: "Assumir este papel e continuar"
- Papel adicionado + acao executada + audit log registra ambos

### Endpoints

```
POST /projects/{project_id}/members/self/roles
Body: { roles: ["dev_senior", "qa"] }
```
- Requer `project:manage_team`
- Adiciona papeis ao membro logado
- Nao pode remover "gp" de si mesmo

```
GET /projects/{project_id}/audit/roles
```
- Historico de atribuicoes de papeis

---

## 3. Sistema de Permissoes — Multiplos Papeis

### permissions.py

Nova funcao:
```python
def get_actions_for_roles(roles: list[str]) -> set[str]:
    """Union de acoes de todos os papeis."""
    actions = set()
    for role in roles:
        actions |= get_actions_for_role(role)
    return actions
```

### require_action()

`resolve_user_role_in_project()` retorna lista de papeis em vez de string unica.
`require_action()` verifica se qualquer papel tem a acao.

### Retorno do /permissions

```json
{
  "roles": ["gp", "dev_senior"],
  "actions": ["project:view", "project:edit", "project:manage_team", "pipeline:execute", "code:write"],
  "is_read_only": false
}
```

### Frontend useProjectPermissions

- `role` passa a ser `roles` (array)
- `can()` continua igual (verifica na lista de acoes acumuladas)

### Audit log

Cada acao protegida registra:
```json
{
  "user_id": "...",
  "action": "code:write",
  "role_used": "dev_senior",
  "project_id": "...",
  "timestamp": "..."
}
```

---

## 4. CodeGen Real com IA

### Fluxo

1. GP (com papel Dev) seleciona item do backlog com status "Pronto"
2. Clica "Gerar Codigo"
3. Backend chama LLM com contexto: OCG + stack + requisitos do item + artefatos vinculados + compliance ISO 27001
4. Codigo retorna no editor para revisao
5. GP revisa, edita se necessario
6. Clica "Commit ao Repositorio" -> commitado via GitHub API
7. Audit log: user, role_used=dev_senior, action=code:write, module, commit_sha

### Backend

```
POST /projects/{id}/backlog/{item_id}/generate-code
  -> require_action("code:write")
  -> Carrega item do backlog com requisitos e artefatos
  -> Carrega OCG context (stack, architecture, testing, compliance)
  -> Carrega chaves IA do Vault (per-project)
  -> Chama LLM com prompt enriquecido
  -> Retorna codigo gerado
  -> Registra billing
```

```
POST /projects/{project_id}/git/commit
Body: { file_path: str, content: str, message: str }
  -> require_action("code:write")
  -> GitService.commit_file() via GitHub API
  -> Audit log com role_used
```

### Endpoints reutilizados

- `POST /code-generation/module` — ajustar auth para require_action
- `POST /code-generation/review-code` — revisao por IA antes de commit
- `GitService.commit_file()` — ja implementado

---

## 5. Backlog Inteligente com Verificacao de Artefatos

### Geracao

Apos Ingestao + Gatekeeper + Arguidor, o sistema gera backlog de modulos/tarefas baseado em:
- Documentos de requisitos ingeridos (negociais, tecnicos)
- Stack definida no OCG
- Arquitetura recomendada pelo Arguidor
- Compliance ISO 27001

### Estrutura de cada item

| Campo | Descricao |
|-------|-----------|
| modulo | Nome do modulo/componente |
| tipo | service, controller, model, middleware, test, migration, ui_screen, ui_flow |
| prioridade | Critico / Alto / Medio / Baixo (baseado em dependencias) |
| requisitos_vinculados | Quais documentos fundamentam este item |
| artefatos_necessarios | O que precisa existir (spec de tela, ERD, regras de negocio) |
| artefatos_presentes | O que ja foi ingerido/aprovado |
| status | Bloqueado / Pronto / Em Geracao / Gerado / Commitado |
| compliance_iso27001 | Checklist ISO 27001 aplicavel ao modulo |
| avisos | Informacoes sobre artefatos faltantes ou ferramentas nao configuradas |

### Verificacao de artefatos (IA)

Antes de marcar item como "Pronto", verifica:
- Documentos de requisito vinculados ingeridos?
- Definicao de telas existe (se modulo frontend)?
- Regras de negocio documentadas?
- Regulamentacoes aplicaveis mapeadas?
- Criterios ISO 27001 relevantes identificados?

Se falta artefato critico -> item "Bloqueado" com mensagem especifica.

### Endpoints

```
POST /projects/{project_id}/backlog/generate
-> IA analisa documentos + stack + OCG -> gera backlog
-> Verifica artefatos de cada item
-> Retorna backlog com status por item

GET /projects/{project_id}/backlog
-> Lista itens com status e artefatos faltantes

PATCH /projects/{project_id}/backlog/{item_id}
-> Atualizar prioridade, vincular artefatos manualmente
```

---

## 6. Integracao com Ferramentas de Design

### Chaves de ferramentas externas

Na aba Settings, alem de LLM, o GP pode configurar:

| Ferramenta | Chave | Uso |
|-----------|-------|-----|
| Figma | API token | Gerar telas a partir de specs de UI |
| Outras futuras | Token | Extensivel por config |

Armazenadas no Vault por projeto, mesmo padrao das chaves LLM.

### Itens de backlog tipo "design"

| Tipo | Exemplo | Ferramenta | Artefato necessario |
|------|---------|-----------|-------------------|
| ui_screen | Tela de Login | Figma (se disponivel) | Spec de tela |
| ui_flow | Fluxo de Onboarding | Figma (se disponivel) | Fluxo de dados |

### Sem ferramenta de design configurada

- Item NAO fica bloqueado
- Aviso: "Sem ferramenta de design configurada. Documentacao detalhada de telas (wireframes, layout, componentes) sera necessaria para geracao de codigo frontend."
- OCG verifica se documentacao ingerida tem especificacao suficiente
- Se documentacao insuficiente -> OCG contrai (confidence cai) e aponta gaps

### Com ferramenta de design configurada

- OCG reconhece ferramenta disponivel -> exige menos documentacao de layout
- Geracao automatica complementa artefatos faltantes

### OCG como verificador central

- Apos cada ingestao, OCG reavalia completude do backlog
- Aponta gaps: "Modulo UserDashboard tem requisitos de negocio mas falta definicao visual"
- Score de confidence reflete completude dos artefatos
