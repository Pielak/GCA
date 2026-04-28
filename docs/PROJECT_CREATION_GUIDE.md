# Project Creation Guide — GCA v1.0

## Overview

A partir de agora, cada novo projeto criado no GCA deve seguir um padrão claro de organização:

- **GCA Codebase** → `/home/luiz/GCA` (unchanged)
- **Project Data** → `/home/luiz/nome-do-projeto`

Esta separação garante:
1. ✅ Isolamento entre GCA e dados de projeto
2. ✅ Limpeza de documentação (GCA docs não contaminadas)
3. ✅ Facilidade de organizar/arquivar múltiplos projetos
4. ✅ Backup independente de projeto e codebase

---

## Step-by-Step: Criar Novo Projeto

### 1. Definir Nome do Projeto

Escolha um nome descritivo e crie o diretório:

```bash
# Exemplo: novo projeto chamado "projeto-xyz"
mkdir -p /home/luiz/projeto-xyz
cd /home/luiz/projeto-xyz
```

**Convenção:** use slug em minúsculo com hífens (ex: `meu-projeto-juridico`, `automacao-vendas`)

### 2. Criar Estrutura Básica

```bash
/home/luiz/projeto-xyz/
├── README.md           # Documentação do projeto
├── .env               # Variáveis de ambiente (gitignore)
├── project.yml        # Config metadata (opcional)
├── scaffold/          # Será preenchido pelo GCA
│   ├── run-<uuid>/
│   └── artifacts/
├── previews/          # Será preenchido pelo GCA
├── backups/           # Backups locais
└── docs/              # Documentação específica do projeto (opcional)
```

### 3. Inicializar Projeto no GCA

Na UI do GCA (http://localhost:5173):

1. **Login** → Select or create project
2. **New Project** → Enter name (ex: "Projeto XYZ")
3. **Project ID** será salvo no banco de dados (`projects.id`)
4. **Setup Wizard** → Configure IA provider, questionnaire, etc.

### 4. Vincular com Diretório Local

No arquivo `/home/luiz/projeto-xyz/project.yml`:

```yaml
# project.yml
name: "Projeto XYZ"
project_id: "<uuid-from-gca>"  # Copiar do GCA backend
gca_url: "http://localhost:5173"
created_at: "2026-04-28"
```

### 5. Configurar Scaffolding

Quando o GCA gera scaffold outputs:

```bash
# GCA salva automaticamente em:
/home/luiz/projeto-xyz/scaffold/run-<uuid>/
├── modules/
├── code/
├── artifacts.json
└── log.txt
```

**Nota:** Não editar manualmente. GCA gerencia este diretório.

### 6. Backups Locais (Opcional)

Se quiser backups locais do projeto:

```bash
# Criar estrutura de backup
mkdir -p /home/luiz/projeto-xyz/backups

# Backup manual (ex: pre-release)
psql gca -c "COPY (SELECT * FROM projects WHERE id='<uuid>') TO '/home/luiz/projeto-xyz/backups/backup_20260428.sql';"
```

---

## File Organization per Project Type

### Projeto Jurídico (com Arguidor + OCG)

```
/home/luiz/projeto-juridico/
├── README.md
├── project.yml
├── inputs/              # Documentos ingeridos (opcional mirror)
├── scaffold/           # Saídas do scaffold (GCA-managed)
│   └── run-<uuid>/
│       └── ocg/       # OCG consolidado
├── previews/          # Previews gerados (GCA-managed)
└── docs/              # Análises, notas, specs (opcional)
```

### Projeto com CodeGen

```
/home/luiz/projeto-codegen/
├── README.md
├── project.yml
├── scaffold/          # Saídas do scaffold
│   └── run-<uuid>/
│       ├── modules/   # Generated modules
│       └── src/       # Generated code
└── previews/
```

---

## Project Directory @ Database Level

**Isolamento de dados** é garantido via `project_id` em **todas** as tabelas project-scoped:

```sql
-- Exemplo: user A nunca vê dados de project B
SELECT * FROM ocg WHERE project_id = '<project-a-uuid>';
SELECT * FROM arguider_analyses WHERE project_id = '<project-a-uuid>';
SELECT * FROM module_candidates WHERE project_id = '<project-a-uuid>';
```

→ Compartimentalização garantida em 3 níveis:
1. **Filesystem** — projetos em `/home/luiz/nome-projeto` isolado
2. **Database** — `WHERE project_id = X` em todas as queries
3. **Middleware** (future RLS) — PostgreSQL Row-Level Security

---

## Troubleshooting

### "Novo projeto vê dados de outro projeto"

1. **Verify compartimentalização fixes:**
   ```bash
   grep -r "project_id" /home/luiz/GCA/backend/app/services/ | wc -l
   ```
   Deve retornar ✓ 7+ queries com project_id

2. **Clear localStorage:** Abrir DevTools → Application → LocalStorage → Clear
3. **Restart GCA:** `docker compose down && docker compose up -d`

### "Não consigo encontrar meu projeto em `/home/luiz/`"

Verificar se está em `/home/luiz/projetos/` (diretório de arquivos órfãos):

```bash
ls /home/luiz/projetos/
```

---

## Migration from Old Projects

Projetos anteriores foram migrados:
- `aja-scaffold/` → `/home/luiz/projetos/aja-scaffold`
- `automacao-juridica-assistida/` → `/home/luiz/projetos/automacao-juridica-assistida`
- `gca-backups/` → `/home/luiz/projetos/gca-backups`

Não são mais misturados com o GCA codebase.

---

**Versão:** 1.0  
**Data:** 2026-04-28  
**Autor:** Claude  
**Status:** Active — padrão para novos projetos
