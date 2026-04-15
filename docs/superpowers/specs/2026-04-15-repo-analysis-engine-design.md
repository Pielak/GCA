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
n8n Workflow (orquestrador — apenas dispatcher)
    ↓ POST /external-repos/{repo_id}/analyze (callback para o backend)
Backend — RepoAnalysisService (engine Python)
    ├── Fase 1: Stack Detection (determinístico) → stack.json
    ├── Fase 2: Security & Deprecation (ferramentas nativas) → vulnerabilities.json
    ├── Fase 3: GCA Compatibility Assessment (IA) → compatibility_matrix.json
    ├── Fase 4: Análise 13 categorias (IA) → 13 docs .md
    ├── Fase 5: Decisão de integração (automática + aprovação GP)
    └── Fase 6: Injeção na Ingestão (se aprovado)
ExternalReposPage (frontend)
    └── Painel 5 abas ao clicar no repo com status "completed"
```

### Decisões de design

- **Híbrido Python + n8n**: Engine de análise no backend Python (robusto, testável). n8n apenas como orquestrador de trigger.
- **Provider de IA configurável pelo GP**: Cada projeto define qual provider usar. Neste caso de teste: DeepSeek.
- **Foco em extração de conhecimento**: Não é scanner técnico genérico — extrai documentação, regras de negócio e processos úteis para o projeto principal.
- **Documentos de ingestão com rastreabilidade**: Todo documento gerado é marcado como externo, com URL de origem e repo_id.
- **Fases determinísticas antes de IA**: Stack detection e security check são determinísticos (parsing, ferramentas nativas) — mais rápido e confiável.
- **Matriz de compatibilidade GCA**: Avalia automaticamente se o repo externo é compatível com o stack GCA antes de ingerir.

---

## Backend — Componentes

### 1. `RepoAnalysisService` (`services/repo_analysis_service.py`)

Métodos principais:
- `analyze_repository(project_id, repo_id)` — orquestra o fluxo completo (6 fases)
- `_list_files(provider, repo_url, branch, token)` — lista árvore via API do provider
- `_categorize_files(tree)` — categoriza em 13 categorias de conhecimento
- `_fetch_file_contents(provider, repo_path, files, branch, token)` — baixa conteúdo via API
- `_analyze_category(category, files_content, ai_provider)` — envia para IA e recebe análise
- `_extract_metrics(analysis_results)` — extrai métricas estruturadas
- `_inject_into_ingestion(project_id, repo_id, repo_url, documents)` — cria documentos na ingestão
- `_update_status(repo_id, status, files_total, files_processed, error)` — atualiza status do repo

### 2. Stack Detection Engine (Fase 1 — determinístico)

**Executado como primeira etapa**, antes de categorizar arquivos. Detecta linguagem, versão, frameworks e dependências exatas — **entrada obrigatória para avaliar viabilidade de integração com GCA**.

#### Métodos
- `_detect_primary_language(tree)` — identifica linguagem principal via extensões e estrutura
- `_parse_manifest_files(provider, repo_path, files, token)` — parseia requirements.txt, package.json, pyproject.toml, go.mod, etc.
- `_extract_dependencies(manifest_content)` — extrai lista estruturada (name, version, pinned, type: runtime/dev)
- `_detect_frameworks(tree, manifest)` — identifica frameworks (FastAPI, Django, Flask, Express, React, etc.)
- `_extract_runtime_version(files)` — detecta Python 3.x, Node.js LTS, etc.
- `_detect_database_support(manifest, tree)` — identifica adapters (PostgreSQL, MySQL, SQLite, etc.)

#### Output: stack.json

```json
{
  "repository": {
    "name": "samplemod",
    "url": "https://github.com/navdeep-G/samplemod",
    "branch": "main",
    "files_total": 21
  },
  "language": {
    "primary": "python",
    "distribution": {
      "python": 85,
      "javascript": 10,
      "json": 5
    }
  },
  "runtime": {
    "type": "python",
    "required_version": "3.9+",
    "eol_status": "active | deprecated | eol",
    "detected_in": ["setup.py", "pyproject.toml", ".python-version"]
  },
  "frameworks": [
    {
      "name": "django",
      "version": "3.2.0",
      "category": "web_framework",
      "eol_date": "2024-04-01",
      "eol_status": "eol"
    }
  ],
  "database": {
    "primary": "postgresql",
    "supported": ["postgresql", "mysql", "sqlite3"],
    "orm": "django_orm"
  },
  "api_style": "rest",
  "detected_patterns": ["models-views-templates (MVT)", "ORM usage", "middleware pattern"],
  "has_dockerfile": true,
  "has_cicd": true,
  "has_tests": true,
  "test_framework": "pytest"
}
```

#### Tabela de referência: suporte por linguagem

| Linguagem | Manifest | Framework Detection | Runtime Version |
|-----------|----------|---------------------|-----------------|
| Python | requirements.txt, pyproject.toml, setup.py, Pipfile | Django, Flask, FastAPI, Celery | .python-version, runtime.txt |
| Node.js | package.json, yarn.lock | React, Express, Next.js, Nest | .nvmrc, .node-version, engines |
| Go | go.mod, go.sum | Gin, Echo, Fiber | go.mod (go directive) |
| Java | pom.xml, build.gradle | Spring Boot, Quarkus | pom.xml (java.version) |
| Rust | Cargo.toml | Actix, Rocket, Axum | rust-toolchain.toml |

### 3. Security & Deprecation Analysis (Fase 2 — determinístico)

**Após stack detection**, executar verificações de segurança e deprecação.

#### Métodos
- `_check_vulnerabilities(dependencies, language)` — executa `safety` (Python), `npm audit` (Node), etc.
- `_check_runtime_eol(runtime_type, version)` — valida se versão está em suporte
- `_check_framework_eol(frameworks)` — valida EOL de frameworks
- `_classify_risk(vulnerabilities, eol_items)` — calcula risk score (baixo/médio/alto)

#### Output: vulnerabilities.json

```json
{
  "security_summary": {
    "total_vulnerabilities": 3,
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 0,
    "risk_level": "médio"
  },
  "vulnerabilities": [
    {
      "package": "django",
      "version": "3.2.0",
      "type": "eol",
      "severity": "high",
      "issue": "Suporte terminado em Abril 2024",
      "recommended_version": "4.2 LTS ou 5.0+",
      "impact_on_integration": "Requer atualização obrigatória antes de integração"
    }
  ],
  "runtime_eol": {
    "python": {
      "current": "3.9",
      "eol_date": "2025-10-05",
      "status": "em_suporte"
    }
  },
  "breaking_changes": [
    "Django 3.2 → 4.0: urls.path() replaces url()",
    "Python 3.9 EOL em Outubro 2025: planejar migração"
  ]
}
```

### 4. Categorias de extração (13)

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

### 5. Tabelas do banco

#### Tabela `repo_analysis_results` (nova)

```sql
CREATE TABLE repo_analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES project_external_repos(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Stack detection
    stack_json JSONB DEFAULT '{}',
    primary_language VARCHAR(50),
    framework_name VARCHAR(100),
    framework_version VARCHAR(20),
    has_docker BOOLEAN DEFAULT false,
    has_cicd BOOLEAN DEFAULT false,
    has_tests BOOLEAN DEFAULT false,

    -- Security & Deprecation
    vulnerabilities_json JSONB DEFAULT '{}',
    risk_level VARCHAR(20),
    vulnerabilities_count INTEGER DEFAULT 0,
    critical_vulnerabilities INTEGER DEFAULT 0,

    -- GCA Compatibility
    compatibility_matrix JSONB DEFAULT '{}',
    gca_overall_status VARCHAR(50),
    gca_integration_effort_days INTEGER,
    gca_backend_compatible BOOLEAN,
    gca_frontend_compatible BOOLEAN,
    gca_database_compatible BOOLEAN,

    -- Análise por categoria
    category VARCHAR(50) NOT NULL,
    summary TEXT NOT NULL,
    metrics JSONB DEFAULT '{}',
    files_analyzed INTEGER DEFAULT 0,
    ai_provider VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_repo_analysis_repo_id ON repo_analysis_results(repo_id);
CREATE INDEX idx_repo_analysis_gca_status ON repo_analysis_results(gca_overall_status);
CREATE INDEX idx_repo_analysis_risk ON repo_analysis_results(risk_level);
```

#### Tabela `repo_integration_roadmap` (nova)

```sql
CREATE TABLE repo_integration_roadmap (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES project_external_repos(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    step_number INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    effort_hours INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    dependencies TEXT[],
    breaking_changes TEXT[],

    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
```

#### Campos novos em `project_external_repos`

```sql
ALTER TABLE project_external_repos ADD COLUMN stack_json JSONB DEFAULT '{}';
ALTER TABLE project_external_repos ADD COLUMN compatibility_status VARCHAR(50);
ALTER TABLE project_external_repos ADD COLUMN last_compatibility_check TIMESTAMPTZ;
ALTER TABLE project_external_repos ADD COLUMN ai_provider VARCHAR(50) DEFAULT 'deepseek';
ALTER TABLE project_external_repos ADD COLUMN is_approved_for_integration BOOLEAN DEFAULT false;
ALTER TABLE project_external_repos ADD COLUMN approved_by_gp UUID REFERENCES users(id);
```

#### Campos novos em `IngestedDocument`

- `source_type VARCHAR(20) DEFAULT 'upload'` — `'upload'` ou `'external_repo'`
- `source_url TEXT` — URL do repositório de origem
- `source_repo_id UUID` — FK para `project_external_repos(id)`, nullable

### 6. Novos endpoints

- `POST /projects/{project_id}/external-repos/{repo_id}/analyze` — chamado pelo n8n, executa o engine completo (6 fases)
- `GET /projects/{project_id}/external-repos/{repo_id}/analysis` — retorna resultados para o frontend
- `POST /projects/{project_id}/external-repos/{repo_id}/approve-integration` — GP aprova ingestão de repo que "requer adaptação"

### 7. Config de IA por projeto

Campo `ai_provider` em `ProjectExternalRepo` — GP escolhe qual provider usar na análise.

---

## GCA Compatibility Matrix (Fase 3)

Após análise de stack e vulnerabilidades, o engine produz matriz estruturada via IA.

### Output: compatibility_matrix.json

```json
{
  "repo_id": "uuid",
  "repo_name": "samplemod",
  "compatibility_assessment": {
    "overall_status": "compatível | requer_adaptação | incompatível",
    "risk_level": "baixo | médio | alto",
    "effort_estimate_days": 5,
    "can_proceed_with_integration": true
  },
  "gca_backend_compatibility": {
    "status": "compatível",
    "reason": "Python backend, REST API",
    "details": {
      "language_match": "python_to_fastapi: compatível",
      "api_style": "rest_to_rest: direto",
      "patterns_alignable": ["orm_usage", "middleware", "error_handling"]
    },
    "effort": "baixo",
    "blockers": []
  },
  "gca_frontend_compatibility": {
    "status": "requer_adaptação",
    "reason": "Backend Django templates, GCA usa React + Vite",
    "details": {
      "language_mismatch": "django_templates_to_react: requer refactor",
      "ui_patterns": "não_reutilizáveis"
    },
    "effort": "alto",
    "blockers": ["Frontend completamente em Django, sem separação clara"]
  },
  "gca_database_compatibility": {
    "status": "compatível",
    "reason": "Suporta PostgreSQL como GCA",
    "details": {
      "orm": "django_orm_to_sqlalchemy: mapeável",
      "migrations": "alembic_compatible"
    },
    "effort": "médio",
    "notes": ["Schemas Django não são 1:1 com SQLAlchemy, requer mapeamento"]
  },
  "gca_integration_pattern": {
    "recommended": "n8n_webhook_to_fastapi_bridge",
    "description": "Expor endpoints via proxy FastAPI, ingerir documentação gerada",
    "steps": [
      "1. Containerizar aplicação",
      "2. Criar FastAPI proxy",
      "3. Mapear outputs para schema GCA",
      "4. Testar com Gatekeeper (7 pilares)"
    ]
  },
  "breaking_changes_for_integration": [
    {
      "issue": "Framework EOL",
      "impact": "Não roda em ambiente GCA moderno",
      "resolution": "Atualizar para versão LTS antes de integração"
    }
  ],
  "security_impact_on_integration": {
    "vulnerabilities_must_fix": [],
    "vulnerabilities_recommended": [],
    "compliance_gaps": []
  },
  "technical_debt_detected": [],
  "reuse_potential": {
    "high_value_components": [
      {
        "component": "business_rules_layer",
        "reuse_effort": "baixo",
        "reason": "Lógica de domínio isolada"
      }
    ],
    "low_value_components": []
  }
}
```

### Métodos para gerar matriz
- `_assess_language_compatibility(stack_json)` — Python, Node, Go, etc.
- `_assess_api_style_compatibility(stack_json)` — REST, GraphQL, etc.
- `_assess_database_compatibility(stack_json)` — PostgreSQL, MySQL, etc.
- `_assess_integration_pattern(stack_json, gca_config)` — recomenda padrão de integração
- `_calculate_effort_estimate(compatibility_matrix)` — estimativa em dias
- `_identify_breaking_changes(stack_json, vulnerabilities_json)` — lista bloqueadores
- `_score_reuse_potential(repo_analysis, gca_patterns)` — componentes reutilizáveis

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
O `external_repos_router.py` deve usar o path completo do webhook conforme registrado no n8n 2.x.

---

## Frontend — ExternalReposPage expandido

### Painel de resultados (5 abas)

Ao clicar em repo com status `completed`, abre painel/modal com abas:

#### Aba 1: Stack Detectado
- Linguagem primária, distribuição
- Runtime (Python 3.9+, Node 18+, etc.)
- Frameworks principais com versão
- Dependências principais
- Database support
- API style (REST, GraphQL, etc.)
- Indicadores: `Has Docker?`, `Has Tests?`, `Has CI/CD?`

#### Aba 2: Segurança & Deprecação
- **Risk Level badge**: `Baixo | Médio | Alto`
- **Vulnerabilidades**: tabela com package, version, severity, recommended version
- **EOL Status**: Runtime EOL date, Framework EOL
- **Breaking Changes**: lista para migração
- **Ação sugerida**: "Requer atualização antes de integração" ou "Compatível para integração"

#### Aba 3: Compatibilidade GCA
- **Overall Status**: `Compatível | Requer Adaptação | Incompatível` (badge colorido)
- **Risk Level**: `Baixo | Médio | Alto`
- **Esforço estimado**: "X dias para integração completa"
- **Sub-seções colapsáveis**:
  - Backend Compatibility: status + reason
  - Frontend Compatibility: status + reason
  - Database Compatibility: status + reason
  - Integration Pattern: recomendação
  - Breaking Changes: blockers e resoluções
  - Security Impact: vulnerabilidades que bloqueiam, compliance gaps
  - Technical Debt: issues detectadas
  - Reuse Potential: componentes com alto valor
- **Call-to-action**:
  - Se "Compatível": botão `[Proceder com Ingestão]` habilitado
  - Se "Requer Adaptação": botão `[Ver Roadmap de Integração]`
  - Se "Incompatível": aviso `[Não recomendado para integração no momento]`

#### Aba 4: Análise por Categoria
- Tabs ou accordion com as 13 categorias
- Cada aba mostra summary gerado pela IA + métricas
- Link para documento .md na ingestão

#### Aba 5: Documentos Injetados
- Lista com links para os docs na Ingestão, marcados como `[EXTERNO]`
- Filtrar por categoria
- Download em massa (ZIP)

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

## Fluxo E2E — Teste com samplemod (6 fases)

### Fase 1: Stack Detection (determinístico, Python)

1. GP adiciona `https://github.com/navdeep-G/samplemod` (✅ já feito)
2. GP clica "Ler Dados" → backend envia trigger ao n8n
3. n8n chama `POST /external-repos/{repo_id}/analyze`
4. Engine lista 21 arquivos via GitHub API
5. Parseia `requirements.txt`, `setup.py`, `pyproject.toml` (se existirem)
6. Detecta linguagem, runtime, frameworks, database, patterns
7. Gera `stack.json` → salva em `repo_analysis_results.stack_json`

### Fase 2: Security & Deprecation (determinístico, ferramentas nativas)

8. Executa `safety check` para Python
9. Executa `npm audit` para Node.js (se existir package.json)
10. Detecta EOL de runtime e frameworks
11. Classifica vulnerabilidades por severity
12. Gera `vulnerabilities.json` → salva em `repo_analysis_results.vulnerabilities_json`
13. Define `risk_level` (baixo/médio/alto)

### Fase 3: GCA Compatibility Assessment (IA)

14. Envia ao DeepSeek: `stack.json` + `vulnerabilities.json` + árvore do repo
15. DeepSeek retorna `compatibility_matrix.json` estruturado
16. Define `gca_overall_status`: compatível / requer_adaptação / incompatível
17. Salva em `repo_analysis_results.compatibility_matrix`

### Fase 4: Análise por Categoria (IA, paralelo)

18. Categoriza arquivos em até 13 categorias
19. Baixa conteúdo dos arquivos relevantes (max 50KB/arquivo)
20. Para cada categoria, envia ao DeepSeek um prompt específico
21. Gera até 13 documentos `.md`
22. Extrai métricas estruturadas de cada categoria
23. Salva cada categoria como registro em `repo_analysis_results`

### Fase 5: Decisão de Integração

24. **Se `gca_overall_status` = "compatível"**:
    - Badge verde ✅ "Pronto para Integração"
    - Botão `[Proceder com Ingestão]` habilitado
    - Injeta documentos na Ingestão automaticamente

25. **Se `gca_overall_status` = "requer_adaptação"**:
    - Badge amarela ⚠️ "Requer Adaptação"
    - Mostra breaking_changes e integration_pattern
    - Botão `[Proceder com Ingestão]` desabilitado até GP aprovar
    - Salva roadmap em `repo_integration_roadmap`

26. **Se `gca_overall_status` = "incompatível"**:
    - Badge vermelha ❌ "Não Recomendado"
    - Botão desabilitado
    - Recomenda volta para pesquisa

### Fase 6: Ingestão (se aprovado)

27. Injeta até 13 documentos `.md` na Ingestão com `source_type="external_repo"`
28. Marca cada documento com URL de origem e `repo_id`
29. Gera `RELATORIO_EXECUTIVO.md` — summary visual para GP
30. Status → `completed`, GP vê análise no painel

### Saída final esperada

```
/analysis/{repo-name}/
├── stack.json
├── vulnerabilities.json
├── compatibility_matrix.json
├── integration_roadmap.json
├── external_{repo}_business_rules.md
├── external_{repo}_domain_glossary.md
├── external_{repo}_workflows.md
├── external_{repo}_technical_docs.md
├── external_{repo}_architecture_patterns.md
├── external_{repo}_data_models.md
├── external_{repo}_api_contracts.md
├── external_{repo}_processes.md
├── external_{repo}_dependencies.md
├── external_{repo}_integration_points.md
├── external_{repo}_security_patterns.md
├── external_{repo}_error_handling.md
├── external_{repo}_test_patterns.md
└── RELATORIO_EXECUTIVO.md
```

---

## Prompts de IA por categoria

Cada categoria recebe um prompt específico que orienta a IA a extrair o tipo certo de conhecimento. Todos os prompts incluem o contexto: "Você está analisando um repositório externo para extrair conhecimento que será reutilizado em outro projeto. Documente de forma clara e completa em Português-BR."

Cada prompt também inclui **como o conhecimento será usado no GCA** para direcionar a extração.

### GCA Compatibility Assessment (Fase 3 — IA)

```
Você é um especialista em arquitetura de software e integração de sistemas.

Analise este repositório externo para determinar sua compatibilidade com integração em GCA (Gerenciador Central de Arquiteturas).

## Stack detectado
{stack_json}

## Vulnerabilidades/Deprecações
{vulnerabilities_json}

## Arquitetura GCA (para referência)
- Backend: FastAPI + Python 3.11+
- Frontend: React 18 + Vite + TypeScript + Tailwind CSS
- Database: PostgreSQL 16+
- Integração: n8n, Cloudflare Tunnel
- LLMs: Multi-provider (Anthropic, OpenAI, Gemini, DeepSeek)

## Estrutura do repositório
{repo_tree_summary}

## Seu objetivo
Retorne APENAS um JSON estruturado (sem preamble, sem markdown) com a compatibility_matrix completa.
```

### Grupo A — Conhecimento de Negócio
- **business_rules**: "Identifique validações, constantes de domínio, enums, regras de negócio implícitas no código. Documente cada regra com contexto, condições e impacto. Separe regras explícitas (validações escritas) de regras implícitas (assumidas no fluxo). **Como será usado em GCA:** Estas regras serão mapeadas para o CodeGenerator e Gatekeeper para validação automática de projeto."
- **domain_glossary**: "Extraia todos os termos de domínio: nomes de entidades, conceitos de negócio, estados, tipos enumerados. Monte um glossário com definição, sinônimos e relacionamentos entre termos. Isso será a linguagem ubíqua do novo projeto. **Como será usado em GCA:** Vocabulário para o OCG (Objeto de Contexto Global) e para treinamento de LLMs."
- **workflows**: "Mapeie fluxos de usuário, processos de negócio, máquinas de estado e pipelines. Para cada fluxo, documente: trigger, passos, condições de decisão, resultado esperado, tratamento de erro. **Como será usado em GCA:** Referência para o Arguidor Técnico validar fluxos do novo projeto."

### Grupo B — Conhecimento Técnico
- **technical_docs**: "Extraia decisões de arquitetura, padrões utilizados, setup necessário, requisitos de ambiente. Organize como documentação técnica de referência. **Como será usado em GCA:** LiveDocs para referência durante desenvolvimento."
- **architecture_patterns**: "Identifique padrões de design (MVC, CQRS, Event Sourcing, etc.), organização de camadas, separação de responsabilidades, injeção de dependências. Documente como cada módulo se conecta. **Como será usado em GCA:** Patterns para o CodeGenerator e Gatekeeper (7 pilares)."
- **data_models**: "Mapeie todas as entidades, seus campos, tipos, relacionamentos (1:1, 1:N, N:N), índices, constraints. Documente o modelo de dados como referência para o novo projeto. **Como será usado em GCA:** Mapeamento para schema GCA, validação no Gatekeeper."
- **api_contracts**: "Mapeie todos os endpoints, schemas, tipos, interfaces. Documente contratos de entrada/saída, códigos de status, paginação, filtros. **Como será usado em GCA:** Referência para integração com sistemas externos via n8n."

### Grupo C — Infraestrutura e Processos
- **processes**: "Descreva o pipeline de CI/CD, processo de deploy, migrations, scripts de automação. Identifique dependências de infra e requisitos de ambiente. **Como será usado em GCA:** Modelo para CI/CD do novo projeto (n8n + Cloudflare Tunnel)."
- **dependencies**: "Liste todas as dependências com versões, identifique potenciais conflitos, vulnerabilidades conhecidas, compatibilidade. Classifique em: core, dev, optional. **Como será usado em GCA:** Auditoria de stack no Gatekeeper, atualizar documentação de dependências."
- **integration_points**: "Identifique todas as integrações externas: APIs de terceiros, SDKs, webhooks, filas de mensagens, bancos externos. Para cada um, documente: URL/endpoint, autenticação, formato de dados, frequência de uso. **Como será usado em GCA:** Mapa de integrações para o Gatekeeper e CodeGenerator."

### Grupo D — Qualidade e Segurança
- **security_patterns**: "Analise padrões de segurança: autenticação, autorização/RBAC, criptografia, gestão de sessões/tokens, sanitização de input, CORS, rate limiting. Documente como referência de segurança. **Como será usado em GCA:** Validação de segurança no Gatekeeper (pilares de segurança)."
- **error_handling**: "Mapeie a estratégia de tratamento de erros: códigos de erro customizados, fallbacks, retry patterns, circuit breakers, logging estruturado. Documente padrões para reuso. **Como será usado em GCA:** Padrões para o CodeGenerator, validação no Gatekeeper."
- **test_patterns**: "Analise a estratégia de testes: unitários, integração, E2E. Documente fixtures, factories, padrões de mock, cobertura estimada. Identifique gaps e boas práticas. **Como será usado em GCA:** Modelo para testes automáticos do novo projeto."
