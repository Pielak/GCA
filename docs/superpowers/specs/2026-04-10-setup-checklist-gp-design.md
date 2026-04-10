# Design: Checklist de Configuracao Obrigatoria do GP

**Data:** 2026-04-10
**Status:** Aprovado

---

## Contexto

Quando um projeto e aprovado pelo Admin, o GP recebe acesso ao workspace com status "initializing". O pipeline fica bloqueado ate que o GP complete a configuracao obrigatoria. Nao existe wizard sequencial — e um checklist que o GP completa na ordem que preferir.

## Itens Obrigatorios

Apenas 2 itens sao obrigatorios para ativar o projeto:

1. **Repositorio Git** — Conectar repo (provider + URL + token), validado em tempo real
2. **Chaves de IA** — Configurar provider + API key, validado contra a API do provider

Equipe e opcional — o GP pode fazer tudo sozinho.

---

## 1. Checklist no ProjectDashPage

Quando `project.status = "initializing"`, o dashboard mostra painel de configuracao:

**Mensagem:**
> "Bem-vindo ao seu projeto! Para que o pipeline fique funcional, complete as configuracoes obrigatorias abaixo."

**Checklist visual:**

| Item | Status | Acao |
|------|--------|------|
| Conectar Repositorio Git | Pendente / Completo | Botao "Configurar" -> `/projects/{id}/repository` |
| Configurar Chaves de IA | Pendente / Completo | Botao "Configurar" -> `/projects/{id}/settings` |

**Regras:**
- Itens completos mostram check verde
- Apos ambos completos, aparece botao "Ativar Projeto"
- GP clica "Ativar Projeto" -> `POST /projects/{id}/activate-project` -> status muda para `active`
- Resumo do questionario aprovado visivel abaixo do checklist
- Link para convidar equipe (opcional, sempre acessivel)

---

## 2. Validacao de Repositorio em Tempo Real

**Campos na RepositoryPage:**
- Provider (select: GitHub / GitLab / Bitbucket)
- URL do repositorio
- Token de acesso (PAT)

**Fluxo:**
1. GP preenche e clica "Validar e Conectar"
2. Backend testa conexao com a API do provider:
   - GitHub: `GET https://api.github.com/repos/{owner}/{repo}`
   - GitLab: `GET https://gitlab.com/api/v4/projects/{encoded_path}`
   - Bitbucket: `GET https://api.bitbucket.org/2.0/repositories/{owner}/{repo}`
3. Se OK -> salva em `ProjectExternalRepo` + retorna sucesso
4. Se falha -> erro especifico ("Token invalido", "Repo nao encontrado", "Sem permissao")

**Endpoint:**
```
POST /projects/{project_id}/repository/validate
Body: { provider: str, repo_url: str, access_token: str }
Response: { valid: bool, error?: str, repo_name?: str, default_branch?: str }
```

Validar = salvar em uma operacao (se valido, ja persiste).

---

## 3. Validacao de Chaves de IA

Reutiliza endpoints existentes:
- `POST /projects/{id}/settings/llm/validate` — testa chave contra API do provider
- `POST /projects/{id}/settings/llm` — salva provider + key + modelo

Frontend chama validate antes de save. Endpoints ja existem, sem alteracao.

---

## 4. Endpoints de Status e Ativacao

**Status do checklist:**
```
GET /projects/{project_id}/setup-status
Response: {
  repo_configured: bool,
  llm_configured: bool,
  ready_to_activate: bool
}
```

Verifica:
- `repo_configured`: existe `ProjectExternalRepo` ativo para o projeto
- `llm_configured`: existe `ProjectSettings` com `setting_type = "llm"` para o projeto
- `ready_to_activate`: ambos true

**Ativar projeto:**
```
POST /projects/{project_id}/activate-project
```
- Requer `require_action("project:edit")`
- Verifica que ambos itens estao completos
- Muda `project.status` de `initializing` para `active`
- Retorna 400 se faltar configuracao

---

## 5. Bloqueio do Pipeline

Quando `project.status = "initializing"`:

**Abas bloqueadas** (opacity-50, clique desabilitado, tooltip "Complete a configuracao obrigatoria"):
- Ingestion, Gatekeeper, Arguider, CodeGen, QA, Tester Review, Backlog, Roadmap, LiveDocs

**Abas sempre acessiveis:**
- Dashboard, Equipe, OCG, Questionario, Repositorio, Settings, Repos Externos

O `RequireRepository` guard existente ja bloqueia parte disso. Adicionar verificacao de `project.status !== "initializing"` ao guard.
