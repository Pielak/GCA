# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GCA (Gerenciador Central de Arquiteturas) is an architectural governance and AI-assisted code generation platform. It manages the full lifecycle: project intake via questionnaires, technology verification (Gatekeeper), AI-powered architecture generation (OCG), code generation, QA readiness, and live documentation.

## Language

All communication, commit messages, comments, and documentation must be in **Portuguese-BR**.

## OCG (Obrigatório)

Sempre usar a skill `gca-ocg-engine` para decisões de contexto.

Regras:
- O OCG começa no questionário externo
- O OCG é um objeto de estado evolutivo
- O OCG expande com boa ingestão
- O OCG contrai com ingestão ruim ou conflitante
- Nenhuma decisão deve ignorar o OCG

## Development Commands

### Backend (FastAPI + Python 3.11)

```bash
# Start all services (Postgres, Redis, backend, frontend, n8n)
cd /home/luiz/GCA && docker compose up -d

# Run backend locally (outside Docker)
cd /home/luiz/GCA/backend && uvicorn app.main:app --reload --port 8000

# Run tests
cd /home/luiz/GCA/backend && python -m pytest app/tests/ -v
cd /home/luiz/GCA/backend && python -m pytest app/tests/test_specific.py -v  # single file
cd /home/luiz/GCA/backend && python -m pytest app/tests/ -m unit            # only unit tests
cd /home/luiz/GCA/backend && python -m pytest app/tests/ -m integration      # only integration

# Linting/formatting
cd /home/luiz/GCA/backend && black app/ --line-length 120
cd /home/luiz/GCA/backend && isort app/ --profile black --line-length 120

# Database migrations (Alembic)
cd /home/luiz/GCA/backend && alembic upgrade head
cd /home/luiz/GCA/backend && alembic revision --autogenerate -m "description"
```

### Frontend (React 18 + Vite + TypeScript)

```bash
cd /home/luiz/GCA/frontend && npm run dev        # dev server on :5173
cd /home/luiz/GCA/frontend && npm run build       # production build
cd /home/luiz/GCA/frontend && npm run lint        # ESLint
cd /home/luiz/GCA/frontend && npm run type-check  # TypeScript check
```

## Architecture

### Backend (`/backend/app/`)

- **Entry point**: `main.py` — FastAPI app with lifespan, CORS, 26 routers
- **API prefix**: `/api/v1/` (configured in `core/config.py`)
- **Auth**: JWT RS256 tokens with role-based access control (RBAC)
- **Database**: PostgreSQL 16 via SQLAlchemy 2.0 async (asyncpg), models in `models/`
- **Services layer**: Business logic in `services/` — routers delegate to services
- **AI orchestration**: `services/ai_service.py` supports Anthropic, OpenAI, Gemini, Deepseek, Grok
- **Agent system**: 8-agent architecture (Analyzer + 7 Pillar Specialists + Consolidator) for OCG generation, defined in `services/agent_service.py` and `services/agent_prompts.py`

### Frontend (`/frontend/src/`)

- **Routing**: `routes.tsx` — React Router with `AppLayout` wrapper, `RequireAdmin` guard
- **State**: Zustand stores in `stores/` + React Query for server state via `hooks/`
- **UI**: Tailwind CSS + shadcn/ui components in `components/ui/`
- **Path alias**: `@/*` maps to `src/*`
- **Pages structure**: Admin pages under `pages/admin/`, project pipeline pages under `pages/projects/`

### Key Pipeline Flow (Project Pages)

Questionnaire → Ingestion → Gatekeeper → OCG → ArguiderPage → CodeGenerator → QAReadiness → TesterReview → Legacy → MergeEngine → Roadmap → LiveDocs

### Infrastructure

- **Docker**: `docker-compose.yml` with postgres, redis, backend, frontend, n8n
- **Production**: Cloudflare tunnel reverse proxy to local machine (`gca.code-auditor.com.br`)
- **n8n**: Workflow automation on port 5678

## RBAC Roles

5 roles with strict separation: **Admin** (system config, never acts on projects), **GP** (project manager, never writes code), **Dev** (develops, never approves), **Tester** (edits test plans), **QA** (reviews only, never edits). All actions are logged.

## Coding Conventions

- Backend: Black formatter, 120 char line length, isort with black profile
- Frontend: Never use inline `style={{ color: '#hex' }}` — always use Tailwind classes from `tailwind.config.ts`
- Work in small sequential phases with regression tests between each. Commit at the end of each phase.
- All 4 auth components (LoginPage, FirstAccessModal, ResetPasswordPage, ProjectTeamPage) must be updated in parallel when changing auth logic.

## Services & Ports

| Service    | Port  |
|------------|-------|
| Backend    | 8000  |
| Frontend   | 5173  |
| PostgreSQL | 5432  |
| Redis      | 6379  |
| n8n        | 5678  |
