# Gate de Pré-Requisitos do Projeto (Setup) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bloquear o pipeline de projeto até o GP completar 3 pré-requisitos obrigatórios (repositório + PAT, chave IA própria, questionário submetido). Gate enforçado no backend (412) e no frontend (guard + checklist visível).

**Architecture:** Estende `project_setup_router.py` existente para incluir o 3º pré-requisito (questionário). Cria dependency FastAPI reutilizável (`require_project_setup_complete`) aplicada nos endpoints de pipeline (ingestion upload, arguider, codegen, qa). No frontend, substitui o `RequireRepository` por `RequireProjectSetup` que checa todos os 3; Dashboard exibe checklist numerado na ordem de execução (repo → IA → questionário). Backend é a autoridade: frontend é UX, não gate de segurança.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), React 18 + TypeScript + React Query (frontend)

**Pré-requisito:** Backend já tem `project_setup_router.py` (repo + llm checks + endpoint `/setup-status`). Falta adicionar questionário e o gate real.

**Decisão de design:** "Questionário submetido" = existe linha em `questionnaires` para o `project_id` com `responses` não-vazio. Não exige aprovação do admin nem score ≥ 80% — basta ter sido submetido. Critérios mais estritos podem vir depois.

---

## File Structure

### Backend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/app/dependencies/require_project_setup.py` | Dependency FastAPI que retorna 412 se setup incompleto |
| `backend/app/tests/test_project_setup_gate.py` | Testes unit + integration do gate (setup-status + dependency) |

### Backend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `backend/app/routers/project_setup_router.py` | Adicionar `_has_questionnaire_submitted()`; incluir `questionnaire_submitted` em `_check_setup_status`; `ready_to_activate` exige os 3 |
| `backend/app/routers/ingestion_router.py:18` | Aplicar `Depends(require_project_setup_complete)` no `POST /ingestion` |
| `backend/app/routers/code_generation.py` | Aplicar dep em endpoints de scaffold/regenerate |
| `backend/app/routers/pipeline_quality_router.py` | Aplicar dep em endpoints de QA |
| `backend/app/services/arguider_service.py` (router que expõe) | Aplicar dep em endpoint manual do Arguidor |

### Frontend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `frontend/src/hooks/useSetupStatus.ts` | React Query hook que consulta `/setup-status` |
| `frontend/src/components/project/SetupChecklist.tsx` | Painel com 3 steps numerados (repo → IA → questionário) |
| `frontend/src/components/guards/RequireProjectSetup.tsx` | Guard que exibe checklist se setup incompleto |

### Frontend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `frontend/src/routes.tsx:110-120` | Trocar `RequireRepository` por `RequireProjectSetup` em ingestion/arguider/codegen/qa/tester-review/backlog/roadmap/docs/readiness. Repos Externos continua sem guard (decisão anterior). |
| `frontend/src/pages/projects/ProjectDashPage.tsx` | Renderizar `<SetupChecklist>` quando `!setup.ready` |
| `frontend/src/components/guards/RequireRepository.tsx` | Marcar deprecated (manter por enquanto, remover em fase futura) |

---

## Task 1: Backend — adicionar check de questionário submetido

**Files:**
- Modify: `backend/app/routers/project_setup_router.py`
- Test: `backend/app/tests/test_project_setup_gate.py` (criar)

- [ ] **Step 1.1: Criar o teste primeiro (falha esperada)**

Criar `backend/app/tests/test_project_setup_gate.py`:

```python
"""Testes do gate de setup do projeto (3 pré-requisitos obrigatórios)."""
import uuid
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    Organization, Project, ProjectGitConfig, ProjectSettings, Questionnaire,
)
from app.routers.project_setup_router import _check_setup_status

pytestmark = pytest.mark.asyncio


async def _seed_project(db: AsyncSession, name: str) -> uuid.UUID:
    """Cria Organization + Project mínimos e devolve project_id."""
    org = Organization(id=uuid.uuid4(), name=f"Org {name}", slug=f"org-{name}")
    db.add(org)
    await db.flush()
    proj = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Proj {name}",
        slug=f"proj-{name}",
        short_slug=f"p-{name}"[:16],
        status="active",
    )
    db.add(proj)
    await db.commit()
    return proj.id


async def test_setup_status_fresh_project_has_nothing_configured(async_db: AsyncSession):
    pid = await _seed_project(async_db, "fresh")
    status = await _check_setup_status(async_db, pid)
    assert status == {
        "repo_configured": False,
        "llm_configured": False,
        "questionnaire_submitted": False,
        "ready_to_activate": False,
    }


async def test_setup_status_counts_questionnaire_with_responses(async_db: AsyncSession):
    pid = await _seed_project(async_db, "withq")
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=pid,
        gp_email="gp@test.local",
        responses=json.dumps({"1": "nome", "5": "Alta"}),
        status="pending",
        submitted_at=datetime.now(timezone.utc),
    )
    async_db.add(q)
    await async_db.commit()

    status = await _check_setup_status(async_db, pid)
    assert status["questionnaire_submitted"] is True


async def test_setup_status_ignores_empty_questionnaire(async_db: AsyncSession):
    """Questionário registro vazio (responses=null ou '{}') NÃO conta como submetido."""
    pid = await _seed_project(async_db, "emptyq")
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=pid,
        gp_email="gp@test.local",
        responses=None,
        status="pending",
    )
    async_db.add(q)
    await async_db.commit()

    status = await _check_setup_status(async_db, pid)
    assert status["questionnaire_submitted"] is False


async def test_ready_to_activate_requires_all_three(async_db: AsyncSession):
    pid = await _seed_project(async_db, "all3")

    # Adicionar os 3 itens
    async_db.add(ProjectGitConfig(
        id=uuid.uuid4(), project_id=pid,
        provider="github", repository_url="https://github.com/test/repo",
        pat_encrypted="fake-pat", connection_verified=True, default_branch="main",
    ))
    async_db.add(ProjectSettings(
        id=uuid.uuid4(), project_id=pid, setting_type="llm",
        settings_json=json.dumps({"provider": "anthropic", "model": "claude-opus-4-6"}),
    ))
    async_db.add(Questionnaire(
        id=uuid.uuid4(), project_id=pid, gp_email="gp@test.local",
        responses=json.dumps({"1": "x"}), status="pending",
        submitted_at=datetime.now(timezone.utc),
    ))
    await async_db.commit()

    status = await _check_setup_status(async_db, pid)
    assert status["ready_to_activate"] is True
    assert status["repo_configured"] is True
    assert status["llm_configured"] is True
    assert status["questionnaire_submitted"] is True
```

- [ ] **Step 1.2: Rodar o teste e verificar que falha**

```bash
cd /home/luiz/GCA/backend && docker exec gca-backend python3 -m pytest app/tests/test_project_setup_gate.py -v
```

Expected: 3 dos 4 testes falham (o primeiro passa porque a função atual retorna 2 campos; os outros falham porque `questionnaire_submitted` não existe e `ready_to_activate` ignora o questionário).

- [ ] **Step 1.3: Implementar `_has_questionnaire_submitted` e estender `_check_setup_status`**

Modificar `backend/app/routers/project_setup_router.py`:

```python
"""Endpoints para checklist de configuracao obrigatoria do projeto."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, exists, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import Project, ProjectSettings, ProjectGitConfig, Questionnaire

router = APIRouter(tags=["Project Setup"])


async def _has_repo_configured(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem repositorio git configurado."""
    result = await db.execute(
        select(exists().where(ProjectGitConfig.project_id == project_id))
    )
    return result.scalar()


async def _has_llm_configured(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem LLM configurado via ProjectSettings."""
    result = await db.execute(
        select(exists().where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "llm",
        ))
    )
    return result.scalar()


async def _has_questionnaire_submitted(db: AsyncSession, project_id: UUID) -> bool:
    """Questionário conta como submetido se há linha com responses não-vazio."""
    result = await db.execute(
        select(exists().where(
            Questionnaire.project_id == project_id,
            Questionnaire.responses.isnot(None),
            Questionnaire.responses != "",
            Questionnaire.responses != "{}",
        ))
    )
    return result.scalar()


async def _check_setup_status(db: AsyncSession, project_id: UUID) -> dict:
    """Retorna status completo de configuracao do projeto."""
    repo_configured = await _has_repo_configured(db, project_id)
    llm_configured = await _has_llm_configured(db, project_id)
    questionnaire_submitted = await _has_questionnaire_submitted(db, project_id)
    ready_to_activate = repo_configured and llm_configured and questionnaire_submitted
    return {
        "repo_configured": repo_configured,
        "llm_configured": llm_configured,
        "questionnaire_submitted": questionnaire_submitted,
        "ready_to_activate": ready_to_activate,
    }


@router.get("/projects/{project_id}/setup-status")
async def get_setup_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Retorna o status de configuracao obrigatoria do projeto."""
    return await _check_setup_status(db, project_id)


@router.post("/projects/{project_id}/activate-project")
async def activate_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:edit")),
):
    """Ativa o projeto apos verificar que todas as configuracoes obrigatorias estao presentes."""
    status = await _check_setup_status(db, project_id)
    if not status["ready_to_activate"]:
        missing = []
        if not status["repo_configured"]:
            missing.append("repositorio_git")
        if not status["llm_configured"]:
            missing.append("configuracao_llm")
        if not status["questionnaire_submitted"]:
            missing.append("questionario_submetido")
        raise HTTPException(
            status_code=400,
            detail={"message": "Configuracao incompleta", "missing": missing},
        )

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado")

    if project.status != "initializing":
        raise HTTPException(
            status_code=400,
            detail=f"Projeto nao pode ser ativado no status atual: {project.status}",
        )

    project.status = "active"
    await db.commit()
    return {"success": True, "status": "active"}
```

- [ ] **Step 1.4: Rodar os testes e confirmar passagem**

```bash
docker exec gca-backend python3 -m pytest app/tests/test_project_setup_gate.py -v
```

Expected: todos os 4 testes passam.

- [ ] **Step 1.5: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/routers/project_setup_router.py backend/app/tests/test_project_setup_gate.py && git commit -m "feat(setup): setup-status agora inclui questionnaire_submitted"
```

---

## Task 2: Backend — criar dependency `require_project_setup_complete`

**Files:**
- Create: `backend/app/dependencies/require_project_setup.py`
- Test: `backend/app/tests/test_project_setup_gate.py` (adicionar)

- [ ] **Step 2.1: Adicionar teste da dependency (deve falhar)**

Anexar ao fim de `backend/app/tests/test_project_setup_gate.py`:

```python
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.dependencies.require_project_setup import require_project_setup_complete
from app.db.database import get_db


def _make_test_app(db: AsyncSession):
    app = FastAPI()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db

    @app.post("/projects/{project_id}/test-endpoint")
    async def _ep(project_id: uuid.UUID, _setup=Depends(require_project_setup_complete)):
        return {"ok": True}

    return app


async def test_dependency_blocks_when_setup_incomplete(async_db: AsyncSession):
    pid = await _seed_project(async_db, "blocked")
    app = _make_test_app(async_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.post(f"/projects/{pid}/test-endpoint")
    assert res.status_code == 412
    body = res.json()
    assert body["detail"]["code"] == "project_setup_incomplete"
    assert set(body["detail"]["missing"]) == {
        "repositorio_git", "configuracao_llm", "questionario_submetido",
    }


async def test_dependency_allows_when_setup_complete(async_db: AsyncSession):
    pid = await _seed_project(async_db, "ready")
    async_db.add(ProjectGitConfig(
        id=uuid.uuid4(), project_id=pid, provider="github",
        repository_url="https://g/r", pat_encrypted="pat",
        connection_verified=True, default_branch="main",
    ))
    async_db.add(ProjectSettings(
        id=uuid.uuid4(), project_id=pid, setting_type="llm",
        settings_json=json.dumps({"provider": "anthropic"}),
    ))
    async_db.add(Questionnaire(
        id=uuid.uuid4(), project_id=pid, gp_email="gp@t.local",
        responses=json.dumps({"1": "x"}), status="pending",
    ))
    await async_db.commit()

    app = _make_test_app(async_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.post(f"/projects/{pid}/test-endpoint")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
```

- [ ] **Step 2.2: Rodar para ver falha de import**

```bash
docker exec gca-backend python3 -m pytest app/tests/test_project_setup_gate.py::test_dependency_blocks_when_setup_incomplete -v
```

Expected: `ModuleNotFoundError: No module named 'app.dependencies.require_project_setup'`.

- [ ] **Step 2.3: Implementar a dependency**

Criar `backend/app/dependencies/require_project_setup.py`:

```python
"""FastAPI dependency — exige que o projeto tenha setup completo antes de
executar endpoints do pipeline (ingestion, arguider, codegen, qa, etc.).

Returns 412 Precondition Failed com detalhe estruturado indicando exatamente
quais dos 3 pré-requisitos estão pendentes.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.routers.project_setup_router import _check_setup_status


async def require_project_setup_complete(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bloqueia execução se o projeto não completou os 3 pré-requisitos.

    Extrai project_id dos path params — endpoint que usa essa dep DEVE ter
    `project_id: UUID` no path (`/projects/{project_id}/...`).
    """
    project_id_raw = request.path_params.get("project_id")
    if not project_id_raw:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="require_project_setup_complete usada em endpoint sem {project_id} no path",
        )
    try:
        project_id = UUID(str(project_id_raw))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id inválido no path",
        )

    setup = await _check_setup_status(db, project_id)
    if setup["ready_to_activate"]:
        return setup

    missing = []
    if not setup["repo_configured"]:
        missing.append("repositorio_git")
    if not setup["llm_configured"]:
        missing.append("configuracao_llm")
    if not setup["questionnaire_submitted"]:
        missing.append("questionario_submetido")

    raise HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail={
            "code": "project_setup_incomplete",
            "message": (
                "Este projeto ainda não completou os pré-requisitos obrigatórios. "
                "Configure repositório com PAT, provedor IA com API key, e submeta o questionário técnico."
            ),
            "missing": missing,
        },
    )
```

- [ ] **Step 2.4: Criar diretório `dependencies/` com `__init__.py` se não existe**

```bash
docker exec gca-backend ls /app/app/dependencies/ 2>&1 | head
```

Se diretório não existe ou falta `__init__.py`:

```bash
docker exec gca-backend bash -c "mkdir -p /app/app/dependencies && touch /app/app/dependencies/__init__.py"
```

No host, garantir o mesmo (via Write tool ou editor):
- Criar `backend/app/dependencies/__init__.py` (arquivo vazio) se não existir.

- [ ] **Step 2.5: Rodar testes da dependency**

```bash
docker exec gca-backend python3 -m pytest app/tests/test_project_setup_gate.py::test_dependency_blocks_when_setup_incomplete app/tests/test_project_setup_gate.py::test_dependency_allows_when_setup_complete -v
```

Expected: ambos passam.

- [ ] **Step 2.6: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/dependencies/ backend/app/tests/test_project_setup_gate.py && git commit -m "feat(setup): dependency require_project_setup_complete retorna 412 se pré-reqs pendentes"
```

---

## Task 3: Backend — aplicar o gate nos endpoints do pipeline

**Files:**
- Modify: `backend/app/routers/ingestion_router.py`
- Modify: `backend/app/routers/code_generation.py` (endpoints de scaffold/regenerate)
- Modify: `backend/app/routers/pipeline_quality_router.py` (endpoints de QA execute)

- [ ] **Step 3.1: Aplicar na Ingestão (POST upload)**

Em `backend/app/routers/ingestion_router.py:18`:

```python
# antes da linha @router.post("/projects/{project_id}/ingestion")
from app.dependencies.require_project_setup import require_project_setup_complete

@router.post("/projects/{project_id}/ingestion")
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
    _setup: dict = Depends(require_project_setup_complete),
):
    ...
```

**Importante:** `POST /questionnaire/upload-pdf` NÃO recebe o gate — é um dos 3 pré-requisitos. Nem `POST /git/*` (configuração de repo) nem `POST /settings/llm` (configuração de IA).

- [ ] **Step 3.2: Aplicar em CodeGen scaffold/regenerate**

Em `backend/app/routers/code_generation.py`, localizar cada `@router.post` do tipo scaffold/regenerate-file:

```python
from app.dependencies.require_project_setup import require_project_setup_complete

# adicionar em cada endpoint de geração:
_setup: dict = Depends(require_project_setup_complete),
```

- [ ] **Step 3.3: Aplicar no QA executor**

Em `backend/app/routers/pipeline_quality_router.py`, localizar endpoint de `/qa/execute` e adicionar a dependência.

- [ ] **Step 3.4: Aplicar em Arguidor manual**

Localizar endpoint `POST` em `arguider_service` ou equivalente router que dispara análise manual. Aplicar a dependência.

Busca rápida para localizar:

```bash
docker exec gca-backend grep -rn "router.post.*arguider\|arguider.*router.post" /app/app/routers/ 2>&1 | head
```

- [ ] **Step 3.5: Validar via curl que endpoints com gate retornam 412 em projeto incompleto**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Projeto atual (Automação Jurídica Assistida) — tem questionário mas NÃO tem repo nem LLM
curl -s -X POST "http://localhost:8000/api/v1/projects/65cab180-e00d-4eec-aaf2-fb4b5d0f4057/ingestion" -H "Authorization: Bearer $TOKEN" -F "file=@/tmp/test.txt" | python3 -m json.tool
```

Expected: 412 com `detail.missing = ["repositorio_git", "configuracao_llm"]`.

- [ ] **Step 3.6: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/routers/ingestion_router.py backend/app/routers/code_generation.py backend/app/routers/pipeline_quality_router.py && git commit -m "feat(setup): aplicar gate require_project_setup_complete em endpoints de pipeline"
```

---

## Task 4: Frontend — hook `useSetupStatus`

**Files:**
- Create: `frontend/src/hooks/useSetupStatus.ts`

- [ ] **Step 4.1: Criar o hook**

```typescript
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

export interface SetupStatus {
  repo_configured: boolean
  llm_configured: boolean
  questionnaire_submitted: boolean
  ready_to_activate: boolean
}

export const useSetupStatus = (projectId: string | undefined) => {
  return useQuery<SetupStatus>({
    queryKey: ['project-setup-status', projectId],
    queryFn: async () => {
      const res = await apiClient.get<SetupStatus>(`/projects/${projectId}/setup-status`)
      return res.data
    },
    enabled: !!projectId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
}
```

- [ ] **Step 4.2: Commit (só o hook, sem uso ainda)**

```bash
cd /home/luiz/GCA && git add frontend/src/hooks/useSetupStatus.ts && git commit -m "feat(frontend): hook useSetupStatus consulta /projects/{id}/setup-status"
```

---

## Task 5: Frontend — componente `SetupChecklist`

**Files:**
- Create: `frontend/src/components/project/SetupChecklist.tsx`

- [ ] **Step 5.1: Criar componente**

```typescript
import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, GitBranch, Zap, ClipboardList, ArrowRight } from 'lucide-react'
import type { SetupStatus } from '@/hooks/useSetupStatus'

interface Props {
  projectId: string
  status: SetupStatus
}

interface Step {
  n: number
  key: keyof Pick<SetupStatus, 'repo_configured' | 'llm_configured' | 'questionnaire_submitted'>
  label: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  to: (id: string) => string
}

const STEPS: Step[] = [
  {
    n: 1,
    key: 'repo_configured',
    label: 'Repositório com PAT',
    description: 'Conecte o repositório Git do projeto (GitHub/GitLab/Bitbucket) com Personal Access Token.',
    icon: GitBranch,
    to: (id) => `/projects/${id}/repository`,
  },
  {
    n: 2,
    key: 'llm_configured',
    label: 'Provedor IA + API Key',
    description: 'Escolha o provedor (Anthropic/OpenAI/Gemini/DeepSeek/Grok) e forneça sua chave.',
    icon: Zap,
    to: (id) => `/projects/${id}/settings`,
  },
  {
    n: 3,
    key: 'questionnaire_submitted',
    label: 'Questionário Técnico',
    description: 'Baixe o PDF editável, preencha offline e faça upload para gerar o contexto OCG.',
    icon: ClipboardList,
    to: (id) => `/projects/${id}/questionnaire`,
  },
]

export function SetupChecklist({ projectId, status }: Props) {
  const doneCount = STEPS.filter(s => status[s.key]).length
  const allDone = doneCount === STEPS.length

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-slate-100 text-base font-semibold">Setup do Projeto</h3>
        <span className={`text-xs ${allDone ? 'text-emerald-400' : 'text-amber-400'}`}>
          {doneCount}/{STEPS.length} concluídos
        </span>
      </div>
      <p className="text-slate-400 text-xs mb-5">
        {allDone
          ? 'Pré-requisitos completos. Pipeline habilitado.'
          : 'Complete os 3 passos na ordem para habilitar Ingestão, Arguidor, CodeGen e demais etapas.'}
      </p>

      <ol className="space-y-2.5">
        {STEPS.map((s) => {
          const done = status[s.key]
          const Icon = s.icon
          return (
            <li key={s.key}>
              <Link
                to={s.to(projectId)}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                  done
                    ? 'border-emerald-800/40 bg-emerald-950/10 hover:bg-emerald-950/20'
                    : 'border-slate-700 hover:border-violet-600/50 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex-shrink-0">
                  {done
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    : <Circle className="w-5 h-5 text-slate-500" />}
                </div>
                <Icon className={`w-4 h-4 flex-shrink-0 ${done ? 'text-emerald-400' : 'text-violet-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${done ? 'text-emerald-200' : 'text-slate-200'}`}>
                    {s.n}. {s.label}
                  </p>
                  <p className="text-xs text-slate-500 truncate">{s.description}</p>
                </div>
                {!done && <ArrowRight className="w-4 h-4 text-slate-500 flex-shrink-0" />}
              </Link>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
```

- [ ] **Step 5.2: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/components/project/SetupChecklist.tsx && git commit -m "feat(frontend): componente SetupChecklist com 3 passos numerados"
```

---

## Task 6: Frontend — guard `RequireProjectSetup`

**Files:**
- Create: `frontend/src/components/guards/RequireProjectSetup.tsx`

- [ ] **Step 6.1: Criar o guard**

```typescript
import { useParams } from 'react-router-dom'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useSetupStatus } from '@/hooks/useSetupStatus'
import { SetupChecklist } from '@/components/project/SetupChecklist'

/**
 * Guard bloqueante — exibe checklist de setup se algum dos 3 pré-requisitos
 * (repo, IA, questionário) não estiver completo. Substitui RequireRepository
 * nos routes do pipeline.
 */
export function RequireProjectSetup({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>()
  const { data: status, isLoading, error } = useSetupStatus(id)

  if (!id) return null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800/40 rounded-xl p-4 text-center max-w-md mx-auto">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-red-300 text-sm">Falha ao verificar o setup do projeto. Recarregue a página.</p>
        </div>
      </div>
    )
  }

  if (!status?.ready_to_activate) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="mb-5 bg-amber-950/20 border border-amber-800/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-amber-300 text-sm font-semibold mb-1">Seção bloqueada</h3>
              <p className="text-amber-200/80 text-xs">
                Esta aba faz parte do pipeline e só pode ser usada após o setup básico do projeto
                estar completo. Finalize os passos abaixo.
              </p>
            </div>
          </div>
        </div>
        <SetupChecklist projectId={id} status={status!} />
      </div>
    )
  }

  return <>{children}</>
}
```

- [ ] **Step 6.2: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/components/guards/RequireProjectSetup.tsx && git commit -m "feat(frontend): guard RequireProjectSetup exibe checklist se pipeline bloqueado"
```

---

## Task 7: Frontend — aplicar guard nos routes

**Files:**
- Modify: `frontend/src/routes.tsx`

- [ ] **Step 7.1: Substituir `RequireRepository` por `RequireProjectSetup` nos routes do pipeline**

Em `frontend/src/routes.tsx`:

```typescript
// trocar import
import { RequireProjectSetup } from './components/guards/RequireProjectSetup';
// manter import antigo durante migração — RequireRepository não é mais usado

// trocar cada uso:
{ path: 'ingestion',      element: <RequireProjectSetup><IngestionPage /></RequireProjectSetup> },
{ path: 'gatekeeper',     element: <RequireProjectSetup><GatekeeperPage /></RequireProjectSetup> },
{ path: 'arguider',       element: <RequireProjectSetup><ArguiderPage /></RequireProjectSetup> },
{ path: 'codegen',        element: <RequireProjectSetup><CodeGeneratorPage /></RequireProjectSetup> },
{ path: 'qa',             element: <RequireProjectSetup><QAReadinessPage /></RequireProjectSetup> },
{ path: 'tester-review',  element: <RequireProjectSetup><TesterReviewPage /></RequireProjectSetup> },
{ path: 'backlog',        element: <RequireProjectSetup><BacklogPage /></RequireProjectSetup> },
{ path: 'roadmap',        element: <RequireProjectSetup><RoadmapPage /></RequireProjectSetup> },
{ path: 'docs',           element: <RequireProjectSetup><LiveDocsPage /></RequireProjectSetup> },
{ path: 'readiness',      element: <RequireProjectSetup><ReadinessPage /></RequireProjectSetup> },
```

**Não alterar** os routes: `repository`, `settings`, `questionnaire`, `external-repos`, `team`, `ocg`, index (Dashboard). Esses são as TELAS onde o GP completa o setup — não podem ser bloqueados pelo próprio gate.

- [ ] **Step 7.2: Verificar que TypeScript compila**

```bash
cd /home/luiz/GCA/frontend && docker exec gca-frontend npm run type-check 2>&1 | tail -20
```

Expected: sem erros.

- [ ] **Step 7.3: Rebuild e commit**

```bash
docker compose -f /home/luiz/GCA/docker-compose.yml restart frontend
cd /home/luiz/GCA && git add frontend/src/routes.tsx && git commit -m "feat(frontend): routes do pipeline usam RequireProjectSetup em vez de RequireRepository"
```

---

## Task 8: Frontend — Dashboard mostra checklist quando incompleto

**Files:**
- Modify: `frontend/src/pages/projects/ProjectDashPage.tsx`

- [ ] **Step 8.1: Ler o ProjectDashPage para localizar onde inserir**

```bash
head -100 /home/luiz/GCA/frontend/src/pages/projects/ProjectDashPage.tsx
```

- [ ] **Step 8.2: Importar e renderizar SetupChecklist antes do conteúdo normal**

No topo do arquivo:

```typescript
import { useSetupStatus } from '@/hooks/useSetupStatus'
import { SetupChecklist } from '@/components/project/SetupChecklist'
```

Dentro do componente, logo antes do JSX principal do dashboard:

```typescript
const { data: setupStatus } = useSetupStatus(id)

// no JSX, antes do conteúdo normal:
{setupStatus && !setupStatus.ready_to_activate && (
  <div className="mb-6">
    <SetupChecklist projectId={id!} status={setupStatus} />
  </div>
)}
```

- [ ] **Step 8.3: Rebuild e commit**

```bash
docker compose -f /home/luiz/GCA/docker-compose.yml restart frontend
cd /home/luiz/GCA && git add frontend/src/pages/projects/ProjectDashPage.tsx && git commit -m "feat(frontend): Dashboard exibe SetupChecklist quando setup incompleto"
```

---

## Task 9: Integration test — projeto atual exibe o gate corretamente

**Não-automatizado**, smoke manual guiado.

- [ ] **Step 9.1: Aguardar frontend pronto**

```bash
docker compose -f /home/luiz/GCA/docker-compose.yml logs frontend --tail 5 | grep "Local.*5173"
```

- [ ] **Step 9.2: Validar via API**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# projeto atual: tem questionário (Fernando submeteu) e tem... ?
curl -s "http://localhost:8000/api/v1/projects/65cab180-e00d-4eec-aaf2-fb4b5d0f4057/setup-status" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: `{"repo_configured": false, "llm_configured": false, "questionnaire_submitted": true, "ready_to_activate": false}`.

- [ ] **Step 9.3: Validar no browser**

1. Abrir projeto "Automação Jurídica Assistida"
2. Dashboard deve mostrar SetupChecklist no topo com:
   - ✅ passo 3 (Questionário)
   - ⚪ passo 1 (Repositório) — destacado
   - ⚪ passo 2 (IA)
3. Clicar em "Ingestão" na sidebar → tela bloqueada com checklist renderizado (não com documentos)
4. Clicar em "Repositório" → tela normal do setup, sem bloqueio
5. Clicar em "Configurações" (Settings) → tela normal, sem bloqueio
6. Clicar em "Questionário" → tela normal com 39 respostas, sem bloqueio

- [ ] **Step 9.4: Commit final**

Sem código novo, apenas documentar no CHANGELOG se houver:

```bash
cd /home/luiz/GCA && git log --oneline origin/master..HEAD 2>&1 | head
```

---

## Critério de conclusão

- [ ] Todos os 4 testes de `test_project_setup_gate.py` passam
- [ ] Curl em `POST /ingestion` retorna 412 com `missing` preenchido em projeto incompleto
- [ ] Curl em `POST /questionnaire/upload-pdf` ainda funciona em projeto incompleto (é um dos 3 pré-reqs)
- [ ] Dashboard do "Automação Jurídica Assistida" exibe checklist mostrando 1/3
- [ ] Aba Ingestão exibe checklist em vez do conteúdo
- [ ] Aba Repositório/Settings/Questionário NÃO são bloqueadas

## Fora do escopo (deferido para outros planos)

- Wizard passo-a-passo forçando ordem 1→2→3 (hoje apenas sugerida visualmente)
- `project.status = 'initializing' | 'active'` machine (os 2 projetos atuais já estão `active` — não tocar agora)
- Email quando setup completa (futuro)
- Badge "🔒" na sidebar nos items bloqueados (futuro — sidebar já mostra seções, visual pode vir depois)
- Watchdog do `_analyze_async` (DT-003, próximo plano separado)
- Contração de OCG no delete (DT-002, próximo plano separado)
