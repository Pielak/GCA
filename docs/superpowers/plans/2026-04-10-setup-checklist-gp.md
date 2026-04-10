# Checklist de Configuracao do GP — Plano de Implementacao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar checklist de configuracao obrigatoria no dashboard do GP quando projeto esta em "initializing", com bloqueio de pipeline ate ativacao.

**Architecture:** Novo endpoint `GET /setup-status` verifica se repo e LLM estao configurados. Novo endpoint `POST /activate-project` muda status para "active". ProjectDashPage mostra painel de checklist quando status = initializing. ProjectDetailLayout bloqueia tabs de pipeline quando initializing.

**Tech Stack:** FastAPI (backend), React 18 + TypeScript (frontend)

**Spec:** `docs/superpowers/specs/2026-04-10-setup-checklist-gp-design.md`

---

## File Structure

### Backend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/app/routers/project_setup_router.py` | Endpoints setup-status e activate-project |
| `backend/tests/test_project_setup.py` | Testes dos endpoints |

### Backend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `backend/app/main.py` | Registrar novo router |

### Frontend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `frontend/src/components/projects/SetupChecklist.tsx` | Componente checklist com items e botao ativar |

### Frontend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `frontend/src/pages/projects/ProjectDashPage.tsx` | Mostrar SetupChecklist quando status=initializing |
| `frontend/src/pages/projects/ProjectDetailLayout.tsx` | Bloquear tabs de pipeline quando initializing |

---

## Task 1: Endpoints setup-status e activate-project (Backend)

**Files:**
- Create: `backend/app/routers/project_setup_router.py`
- Create: `backend/tests/test_project_setup.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Escrever testes**

```python
# backend/tests/test_project_setup.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


@pytest.mark.asyncio
class TestSetupStatus:

    async def test_both_configured_returns_ready(self):
        """Quando repo e LLM configurados, ready_to_activate = True."""
        from app.routers.project_setup_router import _check_setup_status

        db = AsyncMock()
        project_id = uuid4()

        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["repo_configured"] is True
            assert result["llm_configured"] is True
            assert result["ready_to_activate"] is True

    async def test_missing_repo_not_ready(self):
        """Sem repo, ready_to_activate = False."""
        from app.routers.project_setup_router import _check_setup_status

        db = AsyncMock()
        project_id = uuid4()

        with patch("app.routers.project_setup_router._has_repo_configured", return_value=False), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=True):
            result = await _check_setup_status(db, project_id)
            assert result["repo_configured"] is False
            assert result["ready_to_activate"] is False

    async def test_missing_llm_not_ready(self):
        """Sem LLM, ready_to_activate = False."""
        from app.routers.project_setup_router import _check_setup_status

        db = AsyncMock()
        project_id = uuid4()

        with patch("app.routers.project_setup_router._has_repo_configured", return_value=True), \
             patch("app.routers.project_setup_router._has_llm_configured", return_value=False):
            result = await _check_setup_status(db, project_id)
            assert result["llm_configured"] is False
            assert result["ready_to_activate"] is False
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_project_setup.py -v
```

Esperado: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar router**

```python
# backend/app/routers/project_setup_router.py
"""Endpoints para checklist de configuracao obrigatoria do projeto."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import Project, ProjectSettings, ProjectGitConfig

router = APIRouter(tags=["Project Setup"])


async def _has_repo_configured(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem repo git configurado e verificado."""
    result = await db.execute(
        select(
            exists().where(
                ProjectGitConfig.project_id == project_id,
                ProjectGitConfig.connection_verified == True,
            )
        )
    )
    return result.scalar()


async def _has_llm_configured(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem chaves de IA configuradas."""
    result = await db.execute(
        select(
            exists().where(
                ProjectSettings.project_id == project_id,
                ProjectSettings.setting_type == "llm",
            )
        )
    )
    return result.scalar()


async def _check_setup_status(db: AsyncSession, project_id: UUID) -> dict:
    """Retorna status do checklist de configuracao."""
    repo = await _has_repo_configured(db, project_id)
    llm = await _has_llm_configured(db, project_id)
    return {
        "repo_configured": repo,
        "llm_configured": llm,
        "ready_to_activate": repo and llm,
    }


@router.get("/projects/{project_id}/setup-status")
async def get_setup_status(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna status do checklist de configuracao obrigatoria."""
    return await _check_setup_status(db, project_id)


@router.post("/projects/{project_id}/activate-project")
async def activate_project(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Ativa o projeto apos checklist completo."""
    status = await _check_setup_status(db, project_id)
    if not status["ready_to_activate"]:
        missing = []
        if not status["repo_configured"]:
            missing.append("Repositorio Git")
        if not status["llm_configured"]:
            missing.append("Chaves de IA")
        raise HTTPException(
            status_code=400,
            detail=f"Configuracao incompleta. Falta: {', '.join(missing)}",
        )

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado")

    if project.status != "initializing":
        raise HTTPException(status_code=400, detail=f"Projeto ja esta com status '{project.status}'")

    project.status = "active"
    await db.commit()

    return {"success": True, "status": "active"}
```

**IMPORTANTE:** O modelo `ProjectGitConfig` pode nao existir ou ter nome diferente. Ao implementar, verifique o nome real em `backend/app/models/base.py` buscando por `connection_verified` ou `git_config`. Se o modelo se chamar diferente, ajustar. Se nao existir `connection_verified`, usar a presenca do registro como indicador (sem filtro por verified).

- [ ] **Step 4: Registrar router no main.py**

Em `backend/app/main.py`, adicionar:

```python
from app.routers.project_setup_router import router as project_setup_router
```

E na secao de registro:

```python
app.include_router(project_setup_router, prefix=f"{settings.API_PREFIX}")
```

- [ ] **Step 5: Rodar testes**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_project_setup.py -v
```

Esperado: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/routers/project_setup_router.py backend/tests/test_project_setup.py backend/app/main.py
git commit -m "feat: endpoints setup-status e activate-project para checklist GP

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Componente SetupChecklist (Frontend)

**Files:**
- Create: `frontend/src/components/projects/SetupChecklist.tsx`

- [ ] **Step 1: Criar componente**

```typescript
// frontend/src/components/projects/SetupChecklist.tsx
import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Circle, GitBranch, Cpu, Loader2, Rocket } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface SetupStatus {
  repo_configured: boolean
  llm_configured: boolean
  ready_to_activate: boolean
}

export function SetupChecklist() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [status, setStatus] = useState<SetupStatus | null>(null)
  const [activating, setActivating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    apiClient.get(`/projects/${projectId}/setup-status`)
      .then((res) => setStatus(res.data))
      .catch(() => setStatus(null))
  }, [projectId])

  const handleActivate = async () => {
    if (!projectId) return
    setActivating(true)
    setError(null)
    try {
      await apiClient.post(`/projects/${projectId}/activate-project`)
      window.location.reload()
    } catch (err: any) {
      setError(err?.message || 'Erro ao ativar projeto')
    } finally {
      setActivating(false)
    }
  }

  if (!status) return null

  const items = [
    {
      label: 'Conectar Repositorio Git',
      description: 'Configure o provider, URL e token de acesso do repositorio do projeto.',
      done: status.repo_configured,
      icon: GitBranch,
      path: `/projects/${projectId}/repository`,
    },
    {
      label: 'Configurar Chaves de IA',
      description: 'Selecione o provider de IA e insira a API key para geracao de codigo.',
      done: status.llm_configured,
      icon: Cpu,
      path: `/projects/${projectId}/settings`,
    },
  ]

  return (
    <div className="rounded-xl border border-violet-600/30 bg-violet-950/20 p-6">
      <h2 className="text-lg font-semibold text-white mb-2">Configurar Projeto</h2>
      <p className="text-sm text-slate-400 mb-6">
        Bem-vindo ao seu projeto! Para que o pipeline fique funcional, complete as configuracoes obrigatorias abaixo.
      </p>

      <div className="space-y-4">
        {items.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.label}
              className="flex items-center gap-4 rounded-lg border border-slate-700 bg-slate-900/50 p-4"
            >
              {item.done ? (
                <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-400" />
              ) : (
                <Circle className="h-6 w-6 shrink-0 text-slate-500" />
              )}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${item.done ? 'text-emerald-300' : 'text-white'}`}>
                  {item.label}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{item.description}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Icon className="h-4 w-4 text-slate-500" />
                {!item.done && (
                  <button
                    onClick={() => navigate(item.path)}
                    className="rounded-lg bg-violet-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-violet-500 transition-colors"
                  >
                    Configurar
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {error && (
        <div className="mt-4 rounded-lg bg-red-900/40 border border-red-800/50 p-3">
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {status.ready_to_activate && (
        <button
          onClick={handleActivate}
          disabled={activating}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
        >
          {activating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Rocket className="h-4 w-4" />
          )}
          Ativar Projeto
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/components/projects/SetupChecklist.tsx
git commit -m "feat: componente SetupChecklist para configuracao obrigatoria do GP

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Integrar SetupChecklist no ProjectDashPage (Frontend)

**Files:**
- Modify: `frontend/src/pages/projects/ProjectDashPage.tsx`

- [ ] **Step 1: Importar componente e dados do projeto**

No topo de `ProjectDashPage.tsx`, adicionar import:

```typescript
import { SetupChecklist } from '@/components/projects/SetupChecklist'
```

- [ ] **Step 2: Obter status do projeto**

O `ProjectDashPage` precisa saber o status do projeto. O `ProjectDetailLayout` ja carrega `project.status` e passa via Outlet context. Verificar se o context ja inclui `project` ou `status`.

Se o context so tem `repoConnected`, adicionar `projectStatus` ao context no `ProjectDetailLayout.tsx` (linha onde define o Outlet context):

Em `ProjectDetailLayout.tsx`, alterar:

```typescript
<Outlet context={{ repoConnected, can, role, isReadOnly, projectStatus: project?.status }} />
```

No `ProjectDashPage.tsx`, obter:

```typescript
import { useOutletContext } from 'react-router-dom'

interface ProjectContext {
  repoConnected: boolean | null
  can: (action: string) => boolean
  role: string
  isReadOnly: boolean
  projectStatus: string
}

// Dentro do componente:
const { projectStatus } = useOutletContext<ProjectContext>()
```

- [ ] **Step 3: Renderizar checklist condicionalmente**

No inicio do JSX do `ProjectDashPage`, antes dos KPIs existentes, adicionar:

```typescript
{projectStatus === 'initializing' && (
  <div className="mb-6">
    <SetupChecklist />
  </div>
)}
```

- [ ] **Step 4: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npx tsc --noEmit 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/ProjectDashPage.tsx frontend/src/pages/projects/ProjectDetailLayout.tsx
git commit -m "feat: mostrar SetupChecklist no dashboard quando projeto initializing

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Bloquear tabs de pipeline quando initializing (Frontend)

**Files:**
- Modify: `frontend/src/pages/projects/ProjectDetailLayout.tsx`

- [ ] **Step 1: Definir quais tabs sao bloqueadas**

No `ProjectDetailLayout.tsx`, apos a definicao de MODULES (linha 21-36), adicionar conjunto de paths bloqueados:

```typescript
const PIPELINE_PATHS = new Set([
  'ingestion', 'gatekeeper', 'arguider', 'codegen',
  'qa', 'tester-review', 'backlog', 'roadmap', 'docs',
])
```

- [ ] **Step 2: Condicionar renderizacao das tabs**

Na secao de Module Tabs, alterar o mapeamento de MODULES para desabilitar tabs de pipeline quando initializing:

```typescript
{MODULES.map(mod => {
  const Icon = mod.icon
  const to = mod.path ? `/projects/${id}/${mod.path}` : `/projects/${id}`
  const isBlocked = project?.status === 'initializing' && PIPELINE_PATHS.has(mod.path)

  if (isBlocked) {
    return (
      <span
        key={mod.path || 'dashboard'}
        title="Complete a configuracao obrigatoria para acessar"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap text-slate-600 cursor-not-allowed opacity-50"
      >
        <Icon className="w-3.5 h-3.5" />
        {mod.label}
      </span>
    )
  }

  return (
    <NavLink
      key={mod.path || 'dashboard'}
      to={to}
      end={mod.end}
      className={({ isActive }) =>
        `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
          isActive ? 'bg-violet-600/20 text-violet-300 border border-violet-600/30' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
        }`
      }
    >
      <Icon className="w-3.5 h-3.5" />
      {mod.label}
    </NavLink>
  )
})}
```

- [ ] **Step 3: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npx tsc --noEmit 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/ProjectDetailLayout.tsx
git commit -m "feat: bloquear tabs de pipeline quando projeto em initializing

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Rebuild e Teste Manual

- [ ] **Step 1: Restart containers**

```bash
cd /home/luiz/GCA && docker compose restart backend frontend
```

- [ ] **Step 2: Verificar backend**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Testar setup-status
curl -s http://localhost:8000/api/v1/projects/{PROJECT_ID}/setup-status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Esperado: `{"repo_configured": bool, "llm_configured": bool, "ready_to_activate": bool}`

- [ ] **Step 3: Verificar frontend carrega**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173
```

Esperado: 200

- [ ] **Step 4: Rodar todos os testes**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/ -v --timeout=30
```

Esperado: todos passando sem regressao

- [ ] **Step 5: Commit final (se necessario)**

```bash
cd /home/luiz/GCA && git add -A && git status
# Se houver mudancas pendentes:
git commit -m "fix: ajustes finais checklist de configuracao GP

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
