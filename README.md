# GCA — Gestão de Codificação Assistida

Plataforma **instalável por cliente** para governança de projetos de TI assistida por IA.

> **Status atual:** MVP 1 em saneamento (base operacional).
> Estado canônico em [`GCA_MVP_PROGRESS.md`](GCA_MVP_PROGRESS.md).

---

## Fonte soberana

Em caso de conflito entre documentos, esta é a ordem de precedência (contrato §3):

1. [`GCA_CANONICAL_CONTRACT.md`](GCA_CANONICAL_CONTRACT.md) — contrato canônico do produto
2. [`GCA_MVP_PROGRESS.md`](GCA_MVP_PROGRESS.md) — progresso por MVP e dívidas abertas
3. [`CLAUDE.md`](CLAUDE.md) — diretrizes operacionais para Claude Code
4. [`TASK_GCA_MASTER.md`](TASK_GCA_MASTER.md)
5. Código existente
6. Documentos históricos (manual, tutorial, análises, PDFs)

Documentos históricos explicam contexto mas **não autorizam implementação** — ver [`CLAUDE.md §14`](CLAUDE.md).

---

## Modelo do produto (contrato §2)

- **Instalável por cliente.** Uma instância por cliente.
- Isolamento principal por **projeto** dentro da instância.
- Não é, nesta versão, um SaaS multi-tenant compartilhado entre clientes.
- Cada cliente usa seus próprios provedores de IA e chaves.

---

## RBAC canônico (contrato §4)

5 papéis: **Admin**, **GP**, **Dev**, **Tester**, **QA** (+ `admin_viewer` virtual).
Papéis como Tech Lead, Compliance, Stakeholder etc. são históricos — não implementados como roles do sistema nesta versão.

---

## Política de IA (contrato §6)

- Configurável por cliente (provedor/modelo/chave).
- Roteamento híbrido por criticidade da tarefa:
  - **Baixa** (sumarização, extração, normalização): modelo local/Ollama ou barato.
  - **Média** (pré-análise, propostas iniciais): local ou remoto com validação.
  - **Alta** (consolidação de OCG, decisões arquiteturais, compliance crítica, codegen crítico): modelo premium obrigatório.
- Nenhum provedor é tratado como "melhor universal".
- Sem fallback silencioso entre provedores de camada diferente (GCA/admin vs Projeto/GP).

---

## Rodar local

```bash
cd /home/luiz/GCA
docker compose up -d
```

| Serviço     | URL / Porta              |
|-------------|--------------------------|
| Frontend    | http://localhost:5173    |
| Backend API | http://localhost:8000/docs |
| PostgreSQL  | localhost:5432           |
| Redis       | 6379                     |
| n8n         | http://localhost:5678    |

---

## Desenvolvimento

```bash
# Backend (FastAPI + Python 3.11)
docker compose exec backend python -m pytest /app/tests/
docker compose exec backend python -m pytest /app/app/tests/ -m unit

# Frontend (React 18 + Vite + TS)
cd frontend && npm run type-check
cd frontend && npm run build
```

Convenções completas em [`CLAUDE.md §12`](CLAUDE.md).

---

## Onde está o produto de fato

A verdade operacional — o que funciona, o que está por saneamento, e quais DTs permanecem abertas — está em [`GCA_MVP_PROGRESS.md`](GCA_MVP_PROGRESS.md).
Verificar sempre antes de fazer afirmações sobre maturidade ou completude.
