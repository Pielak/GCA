# Engine de Análise de Repositórios Externos

**Data:** 2026-04-15
**Status:** Aprovado
**Objetivo:** Construir engine Python para análise de repositórios externos, extraindo conhecimento técnico, negocial e regras de negócio que alimentam a ingestão do projeto.

---

## Arquitetura

```
ExternalReposPage (frontend)
    ↓ POST /external-repos/{repo_id}/read
Backend (external_repos_router)
    ↓ POST n8n webhook (trigger)
n8n Workflow (orquestrador)
    ↓ POST /external-repos/{repo_id}/analyze (callback para o backend)
Backend — RepoAnalysisService (engine Python)
    ├── 1. Listar árvore de arquivos via API do provider (GitHub/GitLab/Bitbucket)
    ├── 2. Categorizar arquivos em 6 categorias de conhecimento
    ├── 3. Baixar conteúdo dos arquivos relevantes (limite 30/categoria, max 50KB/arquivo)
    ├── 4. Enviar para IA (provider escolhido pelo GP do projeto)
    ├── 5. Extrair métricas estruturadas do resultado
    ├── 6. Salvar resultados no banco (tabela repo_analysis_results)
    └── 7. Injetar documentos .md na Ingestão com source_type="external_repo"
ExternalReposPage (frontend)
    └── Painel de resultados ao clicar no repo com status "completed"
```

### Decisões de design

- **Híbrido Python + n8n**: Engine de análise no backend Python (robusto, testável). n8n apenas como orquestrador de trigger.
- **Provider de IA configurável pelo GP**: Cada projeto define qual provider usar. Neste caso de teste: DeepSeek.
- **Foco em extração de conhecimento**: Não é scanner técnico genérico — extrai documentação, regras de negócio e processos úteis para o projeto principal.
- **Documentos de ingestão com rastreabilidade**: Todo documento gerado é marcado como externo, com URL de origem e repo_id.

---

## Backend — Componentes

### 1. `RepoAnalysisService` (`services/repo_analysis_service.py`)

Métodos:
- `analyze_repository(project_id, repo_id)` — orquestra o fluxo completo
- `_list_files(provider, repo_url, branch, token)` — lista árvore via API do provider
- `_categorize_files(tree)` — categoriza em 13 categorias de conhecimento
- `_fetch_file_contents(provider, repo_path, files, branch, token)` — baixa conteúdo via API
- `_analyze_category(category, files_content, ai_provider)` — envia para IA e recebe análise
- `_extract_metrics(analysis_results)` — extrai métricas estruturadas
- `_inject_into_ingestion(project_id, repo_id, repo_url, documents)` — cria documentos na ingestão
- `_update_status(repo_id, status, files_total, files_processed, error)` — atualiza status do repo

### 2. Categorias de extração (13)

#### Grupo A — Conhecimento de Negócio
| Categoria | O que busca | Arquivos-alvo |
|-----------|-------------|---------------|
| `business_rules` | Validações, constantes, enums, lógica de domínio | *.py, *.ts, *.java, *.go (excluindo testes) |
| `domain_glossary` | Termos de domínio, entidades de negócio, vocabulário ubíquo | models/, entities/, domain/, *.py, *.ts (classes/interfaces) |
| `workflows` | Fluxos de usuário, máquinas de estado, processos step-by-step | *workflow*, *flow*, *state*, *machine*, *saga*, *pipeline* |

#### Grupo B — Conhecimento Técnico
| Categoria | O que busca | Arquivos-alvo |
|-----------|-------------|---------------|
| `technical_docs` | Arquitetura, setup, APIs, decisões técnicas | README*, docs/*, CONTRIBUTING*, ARCHITECTURE*, ADR* |
| `architecture_patterns` | Design patterns, organização de módulos, camadas, separação de responsabilidades | src/, lib/, app/, core/, services/, controllers/, routes/ |
| `data_models` | Schemas de banco, entidades, relacionamentos, migrations | models/, schemas/, migrations/, alembic/, prisma/, *.sql |
| `api_contracts` | Endpoints, schemas, interfaces, tipos | openapi.*, *.proto, schemas/, types/, interfaces/, routes/ |

#### Grupo C — Infraestrutura e Processos
| Categoria | O que busca | Arquivos-alvo |
|-----------|-------------|---------------|
| `processes` | CI/CD, deploy, migrations, infra | .github/, Dockerfile, docker-compose*, alembic/, Makefile |
| `dependencies` | Stack, versões, compatibilidade | package.json, requirements.txt, pyproject.toml, go.mod, Cargo.toml |
| `integration_points` | Serviços externos, webhooks, filas, APIs de terceiros, SDKs | *client*, *sdk*, *webhook*, *queue*, *broker*, *integration* |

#### Grupo D — Qualidade e Segurança
| Categoria | O que busca | Arquivos-alvo |
|-----------|-------------|---------------|
| `security_patterns` | Auth, RBAC, criptografia, sessões, tokens, middleware de segurança | auth/, security/, middleware/, *guard*, *policy*, *permission* |
| `error_handling` | Códigos de erro, fallbacks, retry, circuit breakers, logging | *error*, *exception*, *handler*, *fallback*, *retry*, logger* |
| `test_patterns` | Estratégia de testes, cobertura, fixtures, padrões de mock | tests/, *test*, *spec*, conftest*, jest.config*, *.test.* |

### 3. Tabela `repo_analysis_results`

```sql
CREATE TABLE repo_analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES project_external_repos(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,  -- business_rules, technical_docs, etc.
    summary TEXT NOT NULL,          -- resumo gerado pela IA
    metrics JSONB DEFAULT '{}',     -- linguagens, frameworks, contagens, etc.
    files_analyzed INTEGER DEFAULT 0,
    ai_provider VARCHAR(50),        -- deepseek, anthropic, openai, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. Campos novos em `IngestedDocument`

- `source_type VARCHAR(20) DEFAULT 'upload'` — `'upload'` ou `'external_repo'`
- `source_url TEXT` — URL do repositório de origem
- `source_repo_id UUID` — FK para `project_external_repos(id)`, nullable

### 5. Novos endpoints

- `POST /projects/{project_id}/external-repos/{repo_id}/analyze` — chamado pelo n8n, executa o engine
- `GET /projects/{project_id}/external-repos/{repo_id}/analysis` — retorna resultados para o frontend

### 6. Config de IA por projeto

Novo campo em `ProjectExternalRepo` ou em settings do projeto:
- `ai_provider VARCHAR(50) DEFAULT 'deepseek'` — provider escolhido pelo GP

---

## n8n — Workflow corrigido

### Problemas atuais
1. Webhook path não funciona no n8n 2.x (path prefixado com workflow ID)
2. Nodes `n8n-nodes-base.function` deprecated (v1) — usar `n8n-nodes-base.code` (v2)
3. Lógica de negócio no n8n (análise, categorização) — mover para Python

### Novo workflow simplificado
- **Nó 1 — Webhook**: Recebe trigger do backend
- **Nó 2 — HTTP Request**: Chama `POST /external-repos/{repo_id}/analyze` no backend
- **Nó 3 — Respond**: Retorna status

O n8n vira apenas um "dispatcher" — toda lógica fica no Python.

### Correção da URL no backend
O `external_repos_router.py` deve usar o path completo do webhook:
```python
n8n_url = "http://n8n:5678/webhook/{workflow_id}/webhook/{path}"
```

---

## Frontend — ExternalReposPage expandido

### Painel de resultados
Ao clicar em repo com status `completed`, abre painel/modal com:

1. **Header**: Nome do repo, URL, branch, data da análise, provider IA
2. **Métricas gerais**: Linguagens detectadas, frameworks, total de arquivos analisados
3. **Resumo por categoria**: Tabs ou accordion com as 6 categorias
4. **Documentos injetados**: Lista com links para os docs na Ingestão, marcados como `[EXTERNO]`

### Formato dos documentos injetados

```markdown
# [EXTERNO] {repo-name} — {Categoria}
**Origem:** {repo_url} (branch: {branch})
**Analisado em:** {timestamp}
**Provider IA:** {ai_provider}

## Conteúdo
{análise gerada pela IA}
```

Filename pattern: `external_{repo_name}_{category}.md`

---

## Providers suportados

| Provider | Listar arquivos | Baixar conteúdo | Auth |
|----------|----------------|-----------------|------|
| GitHub | `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` | `GET /repos/{owner}/{repo}/contents/{path}?ref={branch}` | Bearer token |
| GitLab | `GET /projects/{id}/repository/tree?recursive=true&ref={branch}` | `GET /projects/{id}/repository/files/{path}/raw?ref={branch}` | Private-Token |
| Bitbucket | `GET /repositories/{workspace}/{repo}/src/{branch}/?pagelen=100` | `GET /repositories/{workspace}/{repo}/src/{branch}/{path}` | Bearer token |

---

## Filtros de arquivos

### Diretórios ignorados
`node_modules`, `.git`, `dist`, `build`, `__pycache__`, `.next`, `vendor`, `.venv`, `venv`, `.idea`, `.vscode`

### Extensões ignoradas
`png`, `jpg`, `jpeg`, `gif`, `svg`, `ico`, `woff`, `woff2`, `ttf`, `eot`, `map`, `lock`, `min.js`, `min.css`

### Limites
- Max 30 arquivos por categoria
- Max 50KB por arquivo
- Max 500KB total por análise de categoria (para não estourar contexto da IA)

---

## Fluxo E2E — Teste com samplemod

1. GP adiciona `https://github.com/navdeep-G/samplemod` (✅ já feito)
2. GP clica "Ler Dados" → backend envia trigger ao n8n
3. n8n chama `POST /external-repos/{repo_id}/analyze`
4. Engine lista 21 arquivos via GitHub API
5. Categoriza em até 13 categorias de conhecimento
6. Baixa conteúdo dos arquivos relevantes por categoria
7. Envia cada categoria para DeepSeek com prompt específico de extração de conhecimento
8. Gera até 13 documentos `.md`, injeta na Ingestão como `source_type="external_repo"`
9. Salva métricas estruturadas em `repo_analysis_results`
10. Status → `completed`, GP vê análise no painel

---

## Prompts de IA por categoria

Cada categoria recebe um prompt específico que orienta a IA a extrair o tipo certo de conhecimento. Todos os prompts incluem o contexto: "Você está analisando um repositório externo para extrair conhecimento que será reutilizado em outro projeto. Documente de forma clara e completa em Português-BR."

### Grupo A — Conhecimento de Negócio
- **business_rules**: "Identifique validações, constantes de domínio, enums, regras de negócio implícitas no código. Documente cada regra com contexto, condições e impacto. Separe regras explícitas (validações escritas) de regras implícitas (assumidas no fluxo)."
- **domain_glossary**: "Extraia todos os termos de domínio: nomes de entidades, conceitos de negócio, estados, tipos enumerados. Monte um glossário com definição, sinônimos e relacionamentos entre termos. Isso será a linguagem ubíqua do novo projeto."
- **workflows**: "Mapeie fluxos de usuário, processos de negócio, máquinas de estado e pipelines. Para cada fluxo, documente: trigger, passos, condições de decisão, resultado esperado, tratamento de erro."

### Grupo B — Conhecimento Técnico
- **technical_docs**: "Extraia decisões de arquitetura, padrões utilizados, setup necessário, requisitos de ambiente. Organize como documentação técnica de referência."
- **architecture_patterns**: "Identifique padrões de design (MVC, CQRS, Event Sourcing, etc.), organização de camadas, separação de responsabilidades, injeção de dependências. Documente como cada módulo se conecta."
- **data_models**: "Mapeie todas as entidades, seus campos, tipos, relacionamentos (1:1, 1:N, N:N), índices, constraints. Documente o modelo de dados como referência para o novo projeto."
- **api_contracts**: "Mapeie todos os endpoints, schemas, tipos, interfaces. Documente contratos de entrada/saída, códigos de status, paginação, filtros."

### Grupo C — Infraestrutura e Processos
- **processes**: "Descreva o pipeline de CI/CD, processo de deploy, migrations, scripts de automação. Identifique dependências de infra e requisitos de ambiente."
- **dependencies**: "Liste todas as dependências com versões, identifique potenciais conflitos, vulnerabilidades conhecidas, compatibilidade. Classifique em: core, dev, optional."
- **integration_points**: "Identifique todas as integrações externas: APIs de terceiros, SDKs, webhooks, filas de mensagens, bancos externos. Para cada um, documente: URL/endpoint, autenticação, formato de dados, frequência de uso."

### Grupo D — Qualidade e Segurança
- **security_patterns**: "Analise padrões de segurança: autenticação, autorização/RBAC, criptografia, gestão de sessões/tokens, sanitização de input, CORS, rate limiting. Documente como referência de segurança."
- **error_handling**: "Mapeie a estratégia de tratamento de erros: códigos de erro customizados, fallbacks, retry patterns, circuit breakers, logging estruturado. Documente padrões para reuso."
- **test_patterns**: "Analise a estratégia de testes: unitários, integração, E2E. Documente fixtures, factories, padrões de mock, cobertura estimada. Identifique gaps e boas práticas."
