# Repositórios Externos — Especificação Técnica

**Data**: 2026-04-09
**Sessão**: 17
**Status**: Aprovado pelo usuário

---

## Objetivo

Permitir que o GP cadastre repositórios externos (read-only) no projeto. O GCA lê o repositório via pipeline n8n, analisa o conteúdo com DeepSeek, e injeta documentação item a item no pipeline de Ingestão. O OCG engorda progressivamente com o conhecimento externo.

---

## Princípios

1. **Read-only** — GCA nunca escreve no repositório externo
2. **Progressivo** — documentos entram um a um, não como avalanche
3. **A qualquer momento** — repositórios podem ser adicionados e relidos durante todo o ciclo do projeto
4. **Independente** — cada repositório tem status próprio
5. **Categorizado** — arquivos são classificados antes da análise (código, docs, config, CI/CD, testes, schemas)

---

## Posição no Pipeline

```
Dashboard → Equipe → OCG → Questionário
    → Repositórios Externos → Ingestão → Gatekeeper → Arguidor
    → Geração de Código → Testes → Revisão de Testes
    → Roadmap → Documentação Viva
```

Repositórios Externos ficam antes da Ingestão porque alimentam a Ingestão com documentação derivada.

---

## Modelo de Dados

### Nova Tabela: `project_external_repos`

```sql
CREATE TABLE project_external_repos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    repo_url VARCHAR(500) NOT NULL,
    provider VARCHAR(20) NOT NULL,  -- github, gitlab, bitbucket
    branch VARCHAR(100) NOT NULL DEFAULT 'main',
    access_token_encrypted TEXT,    -- vault (pgp_sym_encrypt)
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, reading, completed, error, partial
    last_read_at TIMESTAMP WITH TIME ZONE,
    files_total INTEGER DEFAULT 0,
    files_processed INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    error_message TEXT,
    added_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ext_repos_project ON project_external_repos(project_id);
CREATE INDEX idx_ext_repos_status ON project_external_repos(status);
```

---

## Pipeline n8n

### Trigger
Webhook disparado pelo botão "Ler Dados" no frontend:
```
POST https://n8n:5678/webhook/read-external-repo
Body: { project_id, repo_id, repo_url, branch, access_token, callback_url }
```

### Nós do Workflow

**Nó 1 — Clonar/Listar**: Clona repo shallow (depth=1) ou usa API do provider para listar tree completa.

**Nó 2 — Categorizar**: Classifica cada arquivo por tipo:

| Categoria | Extensões/Padrões |
|-----------|-------------------|
| `code` | `.py`, `.ts`, `.js`, `.java`, `.go`, `.rs`, `.cs`, `.kt`, `.rb`, `.php`, `.swift` |
| `docs` | `.md`, `.txt`, `.docx`, `README*`, `CHANGELOG*`, `CONTRIBUTING*`, `LICENSE` |
| `config` | `.yml`, `.yaml`, `.json`, `.toml`, `.ini`, `.env.example`, `Dockerfile`, `docker-compose*` |
| `ci_cd` | `.github/workflows/*`, `.gitlab-ci*`, `Jenkinsfile`, `.circleci/*` |
| `tests` | `test_*`, `*_test.*`, `*_spec.*`, `tests/`, `__tests__/`, `spec/` |
| `schema` | `migrations/`, `.sql`, `prisma/`, `alembic/`, `*.prisma` |
| `skip` | `node_modules/`, `.git/`, `dist/`, `build/`, `*.png`, `*.jpg`, `*.exe`, `*.woff`, `package-lock.json`, `yarn.lock` |

**Nó 3 — Análise por Grupo**: Para cada categoria (não para cada arquivo individual):
- Agrupa arquivos da mesma categoria
- Envia ao DeepSeek com prompt:
  ```
  Analise estes arquivos de um repositório externo e gere um documento
  resumo em Português-BR que descreva:
  - Estrutura e organização
  - Tecnologias e dependências identificadas
  - Padrões de código/arquitetura
  - Pontos de atenção para integração
  
  Categoria: {categoria}
  Arquivos: {lista com conteúdo truncado}
  ```
- Resultado: 1 documento de ingestão por categoria (máximo 6-7 documentos por repo)

**Nó 4 — Injetar no GCA**: Para cada documento gerado:
```
POST /api/v1/projects/{project_id}/ingestion
Content-Type: multipart/form-data
file: {documento_gerado.md}
description: "Repositório externo: {repo_url} — {categoria}"
```

**Nó 5 — Callback**: Atualiza status do repo:
```
POST /api/v1/projects/{project_id}/external-repos/{repo_id}/callback
Body: { status: "completed", files_total: N, files_processed: M, files_skipped: S }
```

---

## Endpoints

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| `GET` | `/projects/{id}/external-repos` | Listar repositórios cadastrados | Membro |
| `POST` | `/projects/{id}/external-repos` | Cadastrar novo repositório (URL, provider, branch, token) | GP |
| `DELETE` | `/projects/{id}/external-repos/{repo_id}` | Remover repositório | GP |
| `POST` | `/projects/{id}/external-repos/{repo_id}/read` | Disparar leitura via n8n webhook | GP |
| `GET` | `/projects/{id}/external-repos/{repo_id}/status` | Progresso da leitura (files_total/processed) | Membro |
| `POST` | `/projects/{id}/external-repos/{repo_id}/callback` | Callback do n8n para atualizar status | Interno (n8n) |

---

## Frontend — Seção "Repositórios Externos"

### Tela Principal
- Tabela de repositórios cadastrados:
  - URL (link), Provider (ícone), Branch, Status (badge colorido), Última Leitura, Progresso
  - Botão "Ler Dados" (individual por repo) — desabilitado se já em leitura
  - Botão "Remover" — com confirmação
- Formulário de cadastro:
  - URL do repositório
  - Provider (GitHub / GitLab / Bitbucket)
  - Branch (default: main)
  - Token de acesso (read-only) — campo password
- Barra de progresso durante leitura (files_processed / files_total)

### Status por Repositório

| Status | Badge | Descrição |
|--------|-------|-----------|
| `pending` | Cinza | Cadastrado, nunca lido |
| `reading` | Azul pulsante | Leitura em andamento |
| `completed` | Verde | Leitura concluída, documentos injetados |
| `partial` | Amarelo | Leitura parcial (alguns arquivos falharam) |
| `error` | Vermelho | Erro na leitura (token inválido, repo não encontrado) |

---

## Integração com Pipeline Existente

1. Documentos gerados pelo n8n entram via `POST /ingestion` (pipeline normal)
2. Ingestão marca `origin = 'external_repo'` e `external_repo_id` no documento
3. Gatekeeper avalia qualidade normalmente
4. Arguidor identifica lacunas normalmente
5. OCG engorda com cada documento ingerido (via OCG Updater Service quando implementado)

---

## Segurança

- Token de acesso armazenado no vault (pgp_sym_encrypt) — nunca em texto claro
- Token é read-only — GCA nunca faz push/write no repositório
- Token não é exposto na API de listagem (apenas masked)
- n8n recebe token via payload do webhook (HTTPS) — não persiste

---

## Critérios de Aceite

1. GP cadastra repositório com URL, provider, branch e token
2. Botão "Ler Dados" dispara pipeline n8n
3. n8n categoriza arquivos e gera documentos por categoria via DeepSeek
4. Documentos entram um a um na Ingestão (não avalanche)
5. Status atualizado em tempo real (pending → reading → completed)
6. Progresso visível (X de Y arquivos processados)
7. Releitura possível a qualquer momento
8. Múltiplos repositórios por projeto, cada um independente
9. Token armazenado criptografado, nunca exposto

---

## Fora de Escopo (futuro)

- Webhook automático (repo atualiza → GCA relê automaticamente)
- Diff entre leituras (o que mudou desde a última leitura)
- Leitura seletiva (escolher quais pastas/arquivos ler)
- Suporte a repositórios privados sem token (deploy keys)
