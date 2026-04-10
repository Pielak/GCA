# RBAC Compartimentalizado — Plano de Implementacao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar sistema de permissoes por acao que compartimentaliza projetos por GP, com Admin read-only e gestao de GP.

**Architecture:** Novo modulo `permissions.py` define mapeamento papel->acoes. Dependency `require_action()` substitui checks ad-hoc nos endpoints. Frontend usa hook `useProjectPermissions()` para controlar UI. SMTP migra para config global com contexto de projeto nos e-mails.

**Tech Stack:** FastAPI (backend), React 18 + TypeScript + Zustand (frontend), PostgreSQL, Vault (secrets)

**Spec:** `docs/superpowers/specs/2026-04-10-rbac-compartimentalizado-design.md`

---

## File Structure

### Backend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/app/core/permissions.py` | Mapeamento papel->acoes, funcao `has_action()` |
| `backend/app/dependencies/require_action.py` | Dependency FastAPI `require_action("action")` |
| `backend/app/routers/admin_gp_router.py` | Endpoint `POST /admin/projects/{id}/manage-gp` |
| `backend/app/services/gp_management_service.py` | Logica de adicionar/remover/substituir GP |
| `backend/tests/test_permissions.py` | Testes unitarios do modulo de permissoes |
| `backend/tests/test_require_action.py` | Testes da dependency require_action |
| `backend/tests/test_gp_management.py` | Testes do servico de gestao de GP |

### Backend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `backend/app/dependencies/project_access.py` | Admin sem membership ganha `project:view` + `project:manage_gp` (em vez de 403) |
| `backend/app/routers/projects.py` | Endpoints de escrita usam `require_action()` |
| `backend/app/routers/settings_router.py` | Endpoints usam `require_action("project:edit")` |
| `backend/app/routers/admin.py` | Registrar novo router `admin_gp_router` |
| `backend/app/services/email_service.py` | Novo metodo `send_project_email()` com subject contextualizado e reply-to |
| `backend/app/main.py` | Registrar novo router |

### Frontend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `frontend/src/hooks/useProjectPermissions.ts` | Hook que expoe `can()`, `role`, `isReadOnly` |
| `frontend/src/components/ui/ReadOnlyBanner.tsx` | Banner "Modo somente leitura" |

### Frontend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `frontend/src/stores/authStore.ts` | Adicionar `activeProjectRole` ao state |
| `frontend/src/routes.tsx` | Redirecionamento pos-login baseado em is_admin + memberships |
| `frontend/src/pages/projects/ProjectListPage.tsx` | Cards com papel, badge read-only, secoes "Meus Projetos"/"Todos" para Admin |
| `frontend/src/pages/projects/ProjectDetailLayout.tsx` | Carregar permissoes, injetar no Outlet, mostrar banner read-only |
| `frontend/src/app/pages/projects/ProjectTeamPage.tsx` | Condicionar formulario de convite a `can("project:manage_team")` |
| `frontend/src/pages/projects/ProjectSettingsPage.tsx` | Campos disabled se `!can("project:edit")` |

---

## Task 1: Modulo de Permissoes (Backend)

**Files:**
- Create: `backend/app/core/permissions.py`
- Test: `backend/tests/test_permissions.py`

- [ ] **Step 1: Escrever teste unitario para mapeamento papel->acoes**

```python
# backend/tests/test_permissions.py
import pytest
from app.core.permissions import ROLE_ACTIONS, has_action, get_actions_for_role


class TestRoleActions:
    """Testa mapeamento de papeis para acoes."""

    def test_admin_viewer_has_project_view(self):
        assert has_action("admin_viewer", "project:view") is True

    def test_admin_viewer_has_manage_gp(self):
        assert has_action("admin_viewer", "project:manage_gp") is True

    def test_admin_viewer_cannot_edit(self):
        assert has_action("admin_viewer", "project:edit") is False

    def test_admin_viewer_cannot_execute_pipeline(self):
        assert has_action("admin_viewer", "pipeline:execute") is False

    def test_gp_has_all_gp_actions(self):
        expected = {
            "project:view", "project:edit", "project:manage_team",
            "pipeline:execute", "pipeline:review", "docs:edit",
        }
        actions = get_actions_for_role("gp")
        assert expected == actions

    def test_gp_cannot_manage_gp(self):
        assert has_action("gp", "project:manage_gp") is False

    def test_gp_cannot_write_code(self):
        assert has_action("gp", "code:write") is False

    def test_tech_lead_has_code_write(self):
        assert has_action("tech_lead", "code:write") is True

    def test_tech_lead_has_pipeline_review(self):
        assert has_action("tech_lead", "pipeline:review") is True

    def test_dev_senior_has_pipeline_execute(self):
        assert has_action("dev_senior", "pipeline:execute") is True

    def test_dev_pleno_no_pipeline_execute(self):
        assert has_action("dev_pleno", "pipeline:execute") is False

    def test_dev_pleno_has_code_write(self):
        assert has_action("dev_pleno", "code:write") is True

    def test_qa_has_pipeline_review(self):
        assert has_action("qa", "pipeline:review") is True

    def test_qa_cannot_write_code(self):
        assert has_action("qa", "code:write") is False

    def test_compliance_only_view(self):
        actions = get_actions_for_role("compliance")
        assert actions == {"project:view"}

    def test_stakeholder_only_view(self):
        actions = get_actions_for_role("stakeholder")
        assert actions == {"project:view"}

    def test_unknown_role_returns_empty(self):
        actions = get_actions_for_role("nonexistent")
        assert actions == set()

    def test_has_action_unknown_role(self):
        assert has_action("nonexistent", "project:view") is False
```

- [ ] **Step 2: Rodar teste para confirmar que falha**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_permissions.py -v
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'app.core.permissions'`

- [ ] **Step 3: Implementar modulo de permissoes**

```python
# backend/app/core/permissions.py
"""
Mapeamento de papeis para acoes no sistema GCA.

Cada papel tem um conjunto de acoes permitidas.
'admin_viewer' e o papel virtual para Admin sem membership no projeto.
"""

ROLE_ACTIONS: dict[str, set[str]] = {
    "admin_viewer": {
        "project:view",
        "project:manage_gp",
    },
    "gp": {
        "project:view",
        "project:edit",
        "project:manage_team",
        "pipeline:execute",
        "pipeline:review",
        "docs:edit",
    },
    "tech_lead": {
        "project:view",
        "pipeline:execute",
        "pipeline:review",
        "code:write",
        "docs:edit",
    },
    "dev_senior": {
        "project:view",
        "pipeline:execute",
        "code:write",
    },
    "dev_pleno": {
        "project:view",
        "code:write",
    },
    "qa": {
        "project:view",
        "pipeline:review",
    },
    "compliance": {
        "project:view",
    },
    "stakeholder": {
        "project:view",
    },
}


def get_actions_for_role(role: str) -> set[str]:
    """Retorna o conjunto de acoes permitidas para um papel."""
    return ROLE_ACTIONS.get(role, set())


def has_action(role: str, action: str) -> bool:
    """Verifica se um papel tem uma acao especifica."""
    return action in get_actions_for_role(role)
```

- [ ] **Step 4: Rodar teste para confirmar que passa**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_permissions.py -v
```

Esperado: PASS (todos os 18 testes)

- [ ] **Step 5: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/core/permissions.py backend/tests/test_permissions.py
git commit -m "feat: modulo de permissoes papel->acoes para RBAC compartimentalizado"
```

---

## Task 2: Dependency require_action() (Backend)

**Files:**
- Create: `backend/app/dependencies/require_action.py`
- Modify: `backend/app/dependencies/project_access.py:38-89`
- Test: `backend/tests/test_require_action.py`

- [ ] **Step 1: Escrever teste para require_action**

```python
# backend/tests/test_require_action.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from fastapi import HTTPException

from app.dependencies.require_action import resolve_user_role_in_project


@pytest.mark.asyncio
class TestResolveUserRole:
    """Testa resolucao do papel do usuario no projeto."""

    async def test_member_with_role_returns_role(self):
        """Membro com papel retorna o papel do ProjectMember."""
        user_id = uuid4()
        project_id = uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.dependencies.require_action.get_user_project_role",
            return_value="gp",
        ), patch(
            "app.dependencies.require_action._get_user_is_admin",
            return_value=False,
        ):
            role = await resolve_user_role_in_project(user_id, project_id, mock_db)
            assert role == "gp"

    async def test_admin_without_membership_returns_admin_viewer(self):
        """Admin sem membership retorna 'admin_viewer'."""
        user_id = uuid4()
        project_id = uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.dependencies.require_action.get_user_project_role",
            return_value=None,
        ), patch(
            "app.dependencies.require_action._get_user_is_admin",
            return_value=True,
        ):
            role = await resolve_user_role_in_project(user_id, project_id, mock_db)
            assert role == "admin_viewer"

    async def test_admin_with_membership_returns_member_role(self):
        """Admin que e membro usa o papel do ProjectMember, nao admin_viewer."""
        user_id = uuid4()
        project_id = uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.dependencies.require_action.get_user_project_role",
            return_value="gp",
        ), patch(
            "app.dependencies.require_action._get_user_is_admin",
            return_value=True,
        ):
            role = await resolve_user_role_in_project(user_id, project_id, mock_db)
            assert role == "gp"

    async def test_non_member_non_admin_raises_403(self):
        """Usuario sem membership e sem admin recebe 403."""
        user_id = uuid4()
        project_id = uuid4()
        mock_db = AsyncMock()

        with patch(
            "app.dependencies.require_action.get_user_project_role",
            return_value=None,
        ), patch(
            "app.dependencies.require_action._get_user_is_admin",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_role_in_project(user_id, project_id, mock_db)
            assert exc_info.value.status_code == 403
```

- [ ] **Step 2: Rodar teste para confirmar que falha**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_require_action.py -v
```

Esperado: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar require_action**

```python
# backend/app/dependencies/require_action.py
"""
Dependency FastAPI para verificar permissoes por acao.

Uso:
    @router.post("/projects/{project_id}/settings")
    async def update_settings(
        project_id: UUID,
        user_id: UUID = Depends(get_current_user_from_token),
        permissions: dict = Depends(require_action("project:edit")),
    ):
        # permissions = {"user_id": UUID, "role": str, "project_id": UUID}
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import has_action
from app.database import get_db
from app.dependencies.project_access import get_user_project_role
from app.middleware.auth import get_current_user_from_token
from app.models.base import User


async def _get_user_is_admin(user_id: UUID, db: AsyncSession) -> bool:
    """Verifica se usuario e admin global."""
    result = await db.execute(select(User.is_admin).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row is True


async def resolve_user_role_in_project(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> str:
    """
    Resolve o papel efetivo do usuario no projeto.

    Logica:
    - Se e membro do projeto -> retorna papel do ProjectMember
    - Se NAO e membro mas e Admin -> retorna 'admin_viewer'
    - Se NAO e membro e NAO e Admin -> 403
    """
    role = await get_user_project_role(user_id, project_id, db)

    if role is not None:
        return role

    is_admin = await _get_user_is_admin(user_id, db)
    if is_admin:
        return "admin_viewer"

    raise HTTPException(
        status_code=403,
        detail="Acesso negado: voce nao e membro deste projeto",
    )


def require_action(action: str):
    """
    Dependency factory que verifica se o usuario tem a acao no projeto.

    Retorna dict com user_id, role e project_id para uso no endpoint.
    """

    async def _dependency(
        project_id: UUID,
        user_id: UUID = Depends(get_current_user_from_token),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        role = await resolve_user_role_in_project(user_id, project_id, db)

        if not has_action(role, action):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso negado: seu papel '{role}' nao tem permissao para '{action}'",
            )

        return {"user_id": user_id, "role": role, "project_id": project_id}

    return _dependency
```

- [ ] **Step 4: Rodar testes para confirmar que passam**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_require_action.py -v
```

Esperado: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/dependencies/require_action.py backend/tests/test_require_action.py
git commit -m "feat: dependency require_action() para RBAC por acao"
```

---

## Task 3: Migrar Endpoints de Projeto para require_action (Backend)

**Files:**
- Modify: `backend/app/routers/projects.py` (endpoints de escrita)
- Modify: `backend/app/routers/settings_router.py` (todos os endpoints POST)

- [ ] **Step 1: Adicionar endpoint GET /projects/{project_id}/permissions para frontend**

Adicionar ao final de `backend/app/routers/projects.py`:

```python
from app.dependencies.require_action import resolve_user_role_in_project
from app.core.permissions import get_actions_for_role

@router.get("/projects/{project_id}/permissions")
async def get_user_permissions(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o papel e acoes do usuario no projeto."""
    role = await resolve_user_role_in_project(user_id, project_id, db)
    actions = get_actions_for_role(role)
    return {
        "role": role,
        "actions": sorted(actions),
        "is_read_only": actions == {"project:view"} or role == "admin_viewer",
    }
```

- [ ] **Step 2: Migrar invite_team_member para require_action**

Em `backend/app/routers/projects.py`, alterar o endpoint `invite_team_member` (linhas 218-252).

Antes:
```python
@router.post("/projects/{project_id}/invite")
async def invite_team_member(
    project_id: UUID,
    request: InviteTeamMemberRequest,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
```

Depois:
```python
from app.dependencies.require_action import require_action

@router.post("/projects/{project_id}/invite")
async def invite_team_member(
    project_id: UUID,
    request: InviteTeamMemberRequest,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    user_id = permissions["user_id"]
```

- [ ] **Step 3: Migrar revoke_invite para require_action**

Em `backend/app/routers/projects.py`, alterar `revoke_invite` (linhas 297-321).

Antes:
```python
@router.post("/projects/{project_id}/invites/{invite_id}/revoke")
async def revoke_invite(
    project_id: UUID,
    invite_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
```

Depois:
```python
@router.post("/projects/{project_id}/invites/{invite_id}/revoke")
async def revoke_invite(
    project_id: UUID,
    invite_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    user_id = permissions["user_id"]
```

- [ ] **Step 4: Migrar list_pending_invites para require_action**

Em `backend/app/routers/projects.py`, alterar `list_pending_invites` (linhas 255-269) e o alias (linhas 207-215).

Substituir auth por `permissions: dict = Depends(require_action("project:manage_team"))`.

- [ ] **Step 5: Migrar force_propagation para require_action**

Em `backend/app/routers/projects.py`, alterar `force_propagation` (linhas 546-556):

```python
@router.post("/projects/{project_id}/ocg/propagate")
async def force_propagation(
    project_id: UUID,
    permissions: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    user_id = permissions["user_id"]
```

- [ ] **Step 6: Migrar settings_router.py — endpoints POST usam require_action("project:edit")**

Em `backend/app/routers/settings_router.py`, alterar todos os endpoints POST:

`save_smtp_settings` (linha 125), `test_smtp_settings` (linha 151), `save_llm_settings` (linha 200), `validate_llm_settings` (linha 226), `save_n8n_settings` (linha 283):

```python
from app.dependencies.require_action import require_action

# Exemplo para save_llm_settings:
@router.post("/projects/{project_id}/settings/llm")
async def save_llm_settings(
    project_id: UUID,
    request: LlmSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    user_id = permissions["user_id"]
```

O endpoint GET `get_project_settings` (linha 80) usa `require_action("project:view")`:

```python
@router.get("/projects/{project_id}/settings")
async def get_project_settings(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
```

- [ ] **Step 7: Testar endpoints migrados**

```bash
cd /home/luiz/GCA/backend && python -m pytest app/tests/ -v -k "project" --timeout=30
```

Esperado: testes existentes continuam passando (a interface dos endpoints nao mudou para o frontend)

- [ ] **Step 8: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/routers/projects.py backend/app/routers/settings_router.py
git commit -m "refactor: migrar endpoints de projeto para require_action()"
```

---

## Task 4: Servico de Gestao de GP (Backend)

**Files:**
- Create: `backend/app/services/gp_management_service.py`
- Create: `backend/app/routers/admin_gp_router.py`
- Modify: `backend/app/main.py` (registrar router)
- Test: `backend/tests/test_gp_management.py`

- [ ] **Step 1: Escrever testes para o servico**

```python
# backend/tests/test_gp_management.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.gp_management_service import GPManagementService


@pytest.mark.asyncio
class TestGPManagement:

    async def test_add_gp_creates_member_with_gp_role(self):
        """Adicionar GP cria ProjectMember com role='gp'."""
        db = AsyncMock()
        service = GPManagementService()
        project_id = uuid4()

        # Mock: usuario existe, nao e membro do projeto
        with patch.object(service, "_get_or_create_user", return_value=(uuid4(), False)), \
             patch.object(service, "_check_existing_membership", return_value=None), \
             patch.object(service, "_create_gp_member", return_value=MagicMock()) as mock_create, \
             patch.object(service, "_send_gp_notification", return_value=None):
            result = await service.add_gp(db, project_id, "novo@gp.com", uuid4())
            assert result["success"] is True
            mock_create.assert_called_once()

    async def test_remove_last_gp_raises_error(self):
        """Nao pode remover o ultimo GP do projeto."""
        db = AsyncMock()
        service = GPManagementService()
        project_id = uuid4()
        gp_user_id = uuid4()

        with patch.object(service, "_count_active_gps", return_value=1):
            result = await service.remove_gp(db, project_id, gp_user_id, uuid4())
            assert result["success"] is False
            assert "ultimo" in result["error"].lower()

    async def test_remove_gp_with_multiple_gps_succeeds(self):
        """Remove GP quando ha mais de 1 GP ativo."""
        db = AsyncMock()
        service = GPManagementService()
        project_id = uuid4()
        gp_user_id = uuid4()

        with patch.object(service, "_count_active_gps", return_value=2), \
             patch.object(service, "_deactivate_member", return_value=None), \
             patch.object(service, "_send_removal_notification", return_value=None):
            result = await service.remove_gp(db, project_id, gp_user_id, uuid4())
            assert result["success"] is True

    async def test_replace_gp_atomic(self):
        """Substituir GP remove antigo e adiciona novo em uma operacao."""
        db = AsyncMock()
        service = GPManagementService()
        project_id = uuid4()
        old_gp_id = uuid4()

        with patch.object(service, "_count_active_gps", return_value=1), \
             patch.object(service, "_get_or_create_user", return_value=(uuid4(), False)), \
             patch.object(service, "_check_existing_membership", return_value=None), \
             patch.object(service, "_deactivate_member", return_value=None), \
             patch.object(service, "_create_gp_member", return_value=MagicMock()), \
             patch.object(service, "_send_gp_notification", return_value=None), \
             patch.object(service, "_send_removal_notification", return_value=None):
            result = await service.replace_gp(db, project_id, old_gp_id, "novo@gp.com", uuid4())
            assert result["success"] is True
```

- [ ] **Step 2: Rodar teste para confirmar que falha**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_gp_management.py -v
```

Esperado: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar GPManagementService**

```python
# backend/app/services/gp_management_service.py
"""Servico para gestao de GPs em projetos (adicionar, remover, substituir)."""
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import User, Project, ProjectMember
from app.services.email_service import EmailService


class GPManagementService:

    async def add_gp(
        self, db: AsyncSession, project_id: UUID, email: str, admin_id: UUID
    ) -> dict:
        """Adiciona um novo GP ao projeto."""
        user_id, is_new = await self._get_or_create_user(db, email)

        existing = await self._check_existing_membership(db, project_id, user_id)
        if existing:
            return {"success": False, "error": f"Usuario {email} ja e membro deste projeto"}

        member = await self._create_gp_member(db, project_id, user_id, admin_id)
        project = await db.get(Project, project_id)
        await self._send_gp_notification(db, email, project.name, is_new)
        await self._log_audit(db, project_id, admin_id, "add_gp", email)
        await db.commit()

        return {"success": True, "user_id": str(user_id), "email": email}

    async def remove_gp(
        self, db: AsyncSession, project_id: UUID, gp_user_id: UUID, admin_id: UUID
    ) -> dict:
        """Remove um GP do projeto. Proibido se for o ultimo."""
        active_gps = await self._count_active_gps(db, project_id)
        if active_gps <= 1:
            return {
                "success": False,
                "error": "Nao e possivel remover o ultimo GP do projeto. Adicione outro GP primeiro ou use substituir.",
            }

        await self._deactivate_member(db, project_id, gp_user_id)
        user = await db.get(User, gp_user_id)
        project = await db.get(Project, project_id)
        await self._send_removal_notification(db, user.email, project.name)
        await self._log_audit(db, project_id, admin_id, "remove_gp", user.email)
        await db.commit()

        return {"success": True}

    async def replace_gp(
        self,
        db: AsyncSession,
        project_id: UUID,
        old_gp_id: UUID,
        new_email: str,
        admin_id: UUID,
    ) -> dict:
        """Substitui GP: remove antigo + adiciona novo atomicamente."""
        new_user_id, is_new = await self._get_or_create_user(db, new_email)

        existing = await self._check_existing_membership(db, project_id, new_user_id)
        if existing:
            return {"success": False, "error": f"Usuario {new_email} ja e membro deste projeto"}

        # Desativa antigo
        await self._deactivate_member(db, project_id, old_gp_id)
        old_user = await db.get(User, old_gp_id)
        project = await db.get(Project, project_id)

        # Adiciona novo
        await self._create_gp_member(db, project_id, new_user_id, admin_id)

        # Notificacoes
        await self._send_removal_notification(db, old_user.email, project.name)
        await self._send_gp_notification(db, new_email, project.name, is_new)
        await self._log_audit(db, project_id, admin_id, "replace_gp", f"{old_user.email} -> {new_email}")
        await db.commit()

        return {"success": True, "new_user_id": str(new_user_id), "email": new_email}

    # --- Metodos internos ---

    async def _get_or_create_user(self, db: AsyncSession, email: str) -> tuple[UUID, bool]:
        """Busca usuario por email ou cria com senha temporaria."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            return user.id, False

        from app.core.security import get_password_hash

        temp_password = secrets.token_urlsafe(12)
        new_user = User(
            id=uuid4(),
            email=email,
            password_hash=get_password_hash(temp_password),
            full_name="",
            is_active=True,
            is_admin=False,
            first_access_completed=False,
        )
        db.add(new_user)
        await db.flush()
        return new_user.id, True

    async def _check_existing_membership(
        self, db: AsyncSession, project_id: UUID, user_id: UUID
    ):
        """Verifica se usuario ja e membro ativo do projeto."""
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def _create_gp_member(
        self, db: AsyncSession, project_id: UUID, user_id: UUID, invited_by: UUID
    ) -> ProjectMember:
        """Cria ProjectMember com role='gp', ja aceito."""
        now = datetime.now(timezone.utc)
        member = ProjectMember(
            id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            role="gp",
            invited_by=invited_by,
            invited_at=now,
            accepted_at=now,
            joined_at=now,
            is_active=True,
        )
        db.add(member)
        await db.flush()
        return member

    async def _count_active_gps(self, db: AsyncSession, project_id: UUID) -> int:
        """Conta GPs ativos no projeto."""
        result = await db.execute(
            select(func.count()).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "gp",
                ProjectMember.is_active == True,
            )
        )
        return result.scalar()

    async def _deactivate_member(
        self, db: AsyncSession, project_id: UUID, user_id: UUID
    ):
        """Desativa membro do projeto."""
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True,
            )
        )
        member = result.scalar_one_or_none()
        if member:
            member.is_active = False
            member.revoked_at = datetime.now(timezone.utc)

    async def _send_gp_notification(
        self, db: AsyncSession, email: str, project_name: str, is_new_user: bool
    ):
        """Envia e-mail de notificacao para novo GP."""
        email_service = EmailService()
        await email_service.send_project_email(
            to=email,
            subject="Voce foi designado como Gerente de Projeto",
            body=f"Voce foi designado como GP do projeto '{project_name}'. Acesse o GCA para gerenciar o projeto.",
            project_name=project_name,
            reply_to=None,
        )

    async def _send_removal_notification(
        self, db: AsyncSession, email: str, project_name: str
    ):
        """Envia e-mail informando remocao de GP."""
        email_service = EmailService()
        await email_service.send_project_email(
            to=email,
            subject="Remocao de papel de Gerente de Projeto",
            body=f"Voce foi removido do papel de GP do projeto '{project_name}'.",
            project_name=project_name,
            reply_to=None,
        )

    async def _log_audit(
        self, db: AsyncSession, project_id: UUID, admin_id: UUID, action: str, detail: str
    ):
        """Registra acao no log de auditoria."""
        # Usa AuditLog se existir no modelo, senao logging basico
        import logging
        logger = logging.getLogger("gca.audit")
        logger.info(f"GP_MANAGEMENT project={project_id} admin={admin_id} action={action} detail={detail}")
```

- [ ] **Step 4: Implementar router admin_gp_router**

```python
# backend/app/routers/admin_gp_router.py
"""Router para gestao de GPs pelo Admin."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_admin
from app.services.gp_management_service import GPManagementService

router = APIRouter(prefix="/admin/projects", tags=["Admin GP Management"])


class ManageGPRequest(BaseModel):
    action: str  # "add", "remove", "replace"
    email: str | None = None
    remove_user_id: UUID | None = None


@router.post("/{project_id}/manage-gp")
async def manage_gp(
    project_id: UUID,
    request: ManageGPRequest,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Gerenciar GPs de um projeto (adicionar, remover, substituir)."""
    service = GPManagementService()

    if request.action == "add":
        if not request.email:
            raise HTTPException(status_code=422, detail="Email e obrigatorio para adicionar GP")
        result = await service.add_gp(db, project_id, request.email, admin_id)

    elif request.action == "remove":
        if not request.remove_user_id:
            raise HTTPException(status_code=422, detail="remove_user_id e obrigatorio para remover GP")
        result = await service.remove_gp(db, project_id, request.remove_user_id, admin_id)

    elif request.action == "replace":
        if not request.email or not request.remove_user_id:
            raise HTTPException(
                status_code=422,
                detail="email e remove_user_id sao obrigatorios para substituir GP",
            )
        result = await service.replace_gp(
            db, project_id, request.remove_user_id, request.email, admin_id
        )

    else:
        raise HTTPException(status_code=422, detail=f"Acao invalida: {request.action}")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
```

- [ ] **Step 5: Registrar router no main.py**

Em `backend/app/main.py`, adicionar:

```python
from app.routers.admin_gp_router import router as admin_gp_router

# Junto dos outros includes de router:
app.include_router(admin_gp_router, prefix="/api/v1")
```

- [ ] **Step 6: Rodar testes**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_gp_management.py -v
```

Esperado: PASS (4 testes)

- [ ] **Step 7: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/services/gp_management_service.py backend/app/routers/admin_gp_router.py backend/tests/test_gp_management.py backend/app/main.py
git commit -m "feat: servico e endpoint de gestao de GP (adicionar/remover/substituir)"
```

---

## Task 5: SMTP Global com Contexto de Projeto (Backend)

**Files:**
- Modify: `backend/app/services/email_service.py:16-101`

- [ ] **Step 1: Adicionar metodo send_project_email ao EmailService**

No final de `backend/app/services/email_service.py`, adicionar:

```python
    async def send_project_email(
        self,
        to: str,
        subject: str,
        body: str,
        project_name: str,
        reply_to: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Envia e-mail contextualizado com nome do projeto no subject.

        Subject format: [GCA - {project_name}] {subject}
        Reply-To: e-mail do GP ou membro responsavel.
        From: GCA - {project_name} <noreply@code-auditor.com.br>
        """
        full_subject = f"[GCA - {project_name}] {subject}"
        from_name = f"GCA - {project_name}"

        extra_headers = {}
        if reply_to:
            extra_headers["Reply-To"] = reply_to

        return await self.send_email(
            to_email=to,
            subject=full_subject,
            html_body=body,
            from_name_override=from_name,
            extra_headers=extra_headers,
        )
```

- [ ] **Step 2: Atualizar metodo send_email para aceitar from_name_override e extra_headers**

Em `backend/app/services/email_service.py`, alterar a assinatura de `send_email` (linha ~16) para aceitar parametros opcionais:

```python
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        from_name_override: str | None = None,
        extra_headers: dict | None = None,
    ) -> tuple[bool, str | None]:
```

Na construcao do MIMEMultipart (por volta da linha 45-50), adicionar:

```python
        from_name = from_name_override or settings.SMTP_FROM_NAME or "GCA"
        msg["From"] = f"{from_name} <{settings.SMTP_FROM_EMAIL}>"

        if extra_headers:
            for key, value in extra_headers.items():
                msg[key] = value
```

- [ ] **Step 3: Testar envio de email contextualizado**

```bash
cd /home/luiz/GCA/backend && python -m pytest app/tests/ -v -k "email" --timeout=30
```

Esperado: testes existentes de email continuam passando

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/services/email_service.py
git commit -m "feat: SMTP global com contexto de projeto (subject, reply-to, from)"
```

---

## Task 6: Hook useProjectPermissions (Frontend)

**Files:**
- Create: `frontend/src/hooks/useProjectPermissions.ts`
- Create: `frontend/src/components/ui/ReadOnlyBanner.tsx`

- [ ] **Step 1: Criar hook useProjectPermissions**

```typescript
// frontend/src/hooks/useProjectPermissions.ts
import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { apiClient } from '@/lib/api'

interface ProjectPermissions {
  role: string
  actions: string[]
  isReadOnly: boolean
}

export function useProjectPermissions() {
  const { id: projectId } = useParams<{ id: string }>()
  const [permissions, setPermissions] = useState<ProjectPermissions>({
    role: '',
    actions: [],
    isReadOnly: true,
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return

    const fetchPermissions = async () => {
      try {
        const res = await apiClient.get(`/projects/${projectId}/permissions`)
        setPermissions({
          role: res.data.role,
          actions: res.data.actions,
          isReadOnly: res.data.is_read_only,
        })
      } catch {
        setPermissions({ role: '', actions: [], isReadOnly: true })
      } finally {
        setLoading(false)
      }
    }

    fetchPermissions()
  }, [projectId])

  const can = (action: string): boolean => {
    return permissions.actions.includes(action)
  }

  return {
    can,
    role: permissions.role,
    isReadOnly: permissions.isReadOnly,
    loading,
  }
}
```

- [ ] **Step 2: Criar componente ReadOnlyBanner**

```typescript
// frontend/src/components/ui/ReadOnlyBanner.tsx
import { ShieldAlert } from 'lucide-react'

export function ReadOnlyBanner() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-300">
      <ShieldAlert className="h-4 w-4 shrink-0" />
      <span>Modo somente leitura — voce nao e membro deste projeto</span>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/hooks/useProjectPermissions.ts frontend/src/components/ui/ReadOnlyBanner.tsx
git commit -m "feat: hook useProjectPermissions + componente ReadOnlyBanner"
```

---

## Task 7: ProjectDetailLayout — Injetar Permissoes e Banner (Frontend)

**Files:**
- Modify: `frontend/src/pages/projects/ProjectDetailLayout.tsx:45-146`

- [ ] **Step 1: Importar hook e banner no layout**

No topo de `ProjectDetailLayout.tsx`, adicionar imports:

```typescript
import { useProjectPermissions } from '@/hooks/useProjectPermissions'
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner'
```

- [ ] **Step 2: Usar hook dentro do componente**

Dentro da funcao do componente, apos os states existentes (por volta da linha 42), adicionar:

```typescript
const { can, role, isReadOnly, loading: permissionsLoading } = useProjectPermissions()
```

- [ ] **Step 3: Adicionar banner read-only antes das abas**

Antes da secao de abas de modulos (por volta da linha 119), adicionar:

```typescript
{isReadOnly && <div className="px-6 pt-2"><ReadOnlyBanner /></div>}
```

- [ ] **Step 4: Passar permissoes no contexto do Outlet**

Alterar o Outlet (linha 143-144) de:

```typescript
<Outlet context={{ repoConnected }} />
```

Para:

```typescript
<Outlet context={{ repoConnected, can, role, isReadOnly }} />
```

- [ ] **Step 5: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npm run type-check && npm run build
```

Esperado: build sem erros

- [ ] **Step 6: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/ProjectDetailLayout.tsx
git commit -m "feat: ProjectDetailLayout injeta permissoes e mostra banner read-only"
```

---

## Task 8: ProjectListPage — Cards com Papel e Secoes Admin (Frontend)

**Files:**
- Modify: `frontend/src/pages/projects/ProjectListPage.tsx:7-148`

- [ ] **Step 1: Atualizar interface Project para incluir papel do usuario**

Em `ProjectListPage.tsx`, alterar a interface (linhas 7-21) para incluir:

```typescript
interface Project {
  id: string
  name: string
  slug: string
  description: string
  status: string
  outputProfile?: string
  phase?: string
  stack?: string[]
  gatekeeperScore?: number
  codeGenCount?: number
  testsPassed?: number
  testsTotal?: number
  pendingIssues?: number
  userRole?: string        // papel do usuario neste projeto
  memberCount?: number     // total de membros ativos
  lastAccessedAt?: string  // ultimo acesso
}
```

- [ ] **Step 2: Importar authStore e separar projetos**

Adicionar ao topo:

```typescript
import { useAuthStore } from '@/stores/authStore'
```

Dentro do componente, apos o useEffect de carregamento:

```typescript
const user = useAuthStore((s) => s.user)
const isAdmin = user?.is_admin ?? false

// Separar projetos onde sou membro vs todos (para admin)
const myProjects = projects.filter((p) => p.userRole && p.userRole !== 'admin_viewer')
const otherProjects = isAdmin ? projects.filter((p) => !p.userRole || p.userRole === 'admin_viewer') : []
```

- [ ] **Step 3: Atualizar renderizacao com secoes e badges**

Substituir o grid de cards por duas secoes:

```typescript
{/* Meus Projetos */}
{myProjects.length > 0 && (
  <div className="mb-8">
    <h2 className="mb-4 text-lg font-semibold text-white">Meus Projetos</h2>
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {myProjects.map((proj) => (
        <ProjectCard key={proj.id} project={proj} onClick={() => navigate(`/projects/${proj.id}`)} />
      ))}
    </div>
  </div>
)}

{/* Todos os Projetos (Admin read-only) */}
{otherProjects.length > 0 && (
  <div>
    <h2 className="mb-4 text-lg font-semibold text-white/60">Todos os Projetos (somente leitura)</h2>
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {otherProjects.map((proj) => (
        <ProjectCard key={proj.id} project={proj} readOnly onClick={() => navigate(`/projects/${proj.id}`)} />
      ))}
    </div>
  </div>
)}
```

- [ ] **Step 4: Extrair componente ProjectCard com badge de papel**

No mesmo arquivo, criar componente interno:

```typescript
function ProjectCard({
  project,
  readOnly = false,
  onClick,
}: {
  project: Project
  readOnly?: boolean
  onClick: () => void
}) {
  const roleLabels: Record<string, string> = {
    gp: 'Gerente de Projeto',
    tech_lead: 'Tech Lead',
    dev_senior: 'Dev Senior',
    dev_pleno: 'Dev Pleno',
    qa: 'QA',
    compliance: 'Compliance',
    stakeholder: 'Stakeholder',
  }

  return (
    <div
      onClick={onClick}
      className={`cursor-pointer rounded-xl border border-dark-100 bg-dark-200 p-5 transition-colors hover:border-violet-600/50 ${readOnly ? 'opacity-75' : ''}`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">{project.name}</h3>
        {readOnly && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-300">
            Somente Leitura
          </span>
        )}
      </div>

      {project.userRole && !readOnly && (
        <span className="mb-2 inline-block rounded-full bg-violet-600/20 px-2 py-0.5 text-xs text-violet-300">
          {roleLabels[project.userRole] || project.userRole}
        </span>
      )}

      <p className="mb-3 line-clamp-2 text-sm text-white/60">{project.description || 'Sem descricao'}</p>

      <div className="flex items-center justify-between text-xs text-white/40">
        <span className={`rounded-full px-2 py-0.5 ${
          project.status === 'active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-blue-500/20 text-blue-400'
        }`}>
          {project.status === 'active' ? 'Ativo' : 'Em configuracao'}
        </span>
        {project.lastAccessedAt && (
          <span>Ultimo acesso: {new Date(project.lastAccessedAt).toLocaleDateString('pt-BR')}</span>
        )}
      </div>

      {project.gatekeeperScore != null && project.gatekeeperScore > 0 && (
        <div className="mt-3">
          <div className="flex justify-between text-xs text-white/40">
            <span>Gatekeeper</span>
            <span>{project.gatekeeperScore}%</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-dark-100">
            <div
              className="h-full rounded-full bg-violet-600"
              style={{ width: `${project.gatekeeperScore}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Atualizar backend GET /projects para retornar userRole**

Em `backend/app/routers/projects.py`, no endpoint `list_projects` (linhas 63-121), adicionar `userRole` ao response.

Onde monta a lista de projetos, adicionar para cada projeto:

```python
# Buscar papel do usuario no projeto
member_result = await db.execute(
    select(ProjectMember.role).where(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == user_id,
        ProjectMember.is_active == True,
    )
)
user_role = member_result.scalar_one_or_none()

# No dict do projeto, adicionar:
"userRole": user_role if user_role else ("admin_viewer" if user.is_admin else None),
```

- [ ] **Step 6: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npm run type-check && npm run build
```

Esperado: build sem erros

- [ ] **Step 7: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/pages/projects/ProjectListPage.tsx backend/app/routers/projects.py
git commit -m "feat: ProjectListPage com cards por papel, secoes Meus Projetos/Todos"
```

---

## Task 9: Redirecionamento Pos-Login e Header Admin (Frontend)

**Files:**
- Modify: `frontend/src/routes.tsx:110-117`
- Modify: `frontend/src/pages/projects/ProjectDetailLayout.tsx` (header)

- [ ] **Step 1: Atualizar redirecionamento pos-login**

Em `frontend/src/routes.tsx`, alterar o index redirect (linhas 110-117):

Antes:
```typescript
// Redireciona admin para /admin, outros para /projects
```

Depois:
```typescript
element: <IndexRedirect />
```

Criar componente no mesmo arquivo:

```typescript
function IndexRedirect() {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()

  useEffect(() => {
    if (!user) {
      navigate('/login')
      return
    }

    // Admin sem projetos como membro -> admin
    // Admin com projetos como membro -> projects (com link admin no header)
    // Nao-admin -> projects
    const hasMemberships = user.project_roles && user.project_roles.length > 0

    if (user.is_admin && !hasMemberships) {
      navigate('/admin')
    } else {
      navigate('/projects')
    }
  }, [user, navigate])

  return null
}
```

- [ ] **Step 2: Adicionar link Admin no header do ProjectDetailLayout**

Em `ProjectDetailLayout.tsx`, na secao do header (por volta da linha 81), adicionar link para admin:

```typescript
import { useAuthStore } from '@/stores/authStore'
import { Shield } from 'lucide-react'

// Dentro do componente:
const user = useAuthStore((s) => s.user)

// No JSX do header, ao lado do botao "Voltar":
{user?.is_admin && (
  <Link to="/admin" className="flex items-center gap-1 rounded-lg bg-violet-600/20 px-3 py-1.5 text-xs text-violet-300 hover:bg-violet-600/30">
    <Shield className="h-3.5 w-3.5" />
    Painel Admin
  </Link>
)}
```

- [ ] **Step 3: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npm run type-check && npm run build
```

Esperado: build sem erros

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/routes.tsx frontend/src/pages/projects/ProjectDetailLayout.tsx
git commit -m "feat: redirecionamento pos-login e link Painel Admin no header"
```

---

## Task 10: Condicionar UI a Permissoes (Frontend)

**Files:**
- Modify: `frontend/src/app/pages/projects/ProjectTeamPage.tsx`
- Modify: `frontend/src/pages/projects/ProjectSettingsPage.tsx`

- [ ] **Step 1: ProjectTeamPage — condicionar convites a permissao**

Em `ProjectTeamPage.tsx`, importar hook e condicionar formulario:

```typescript
import { useProjectPermissions } from '@/hooks/useProjectPermissions'

// Dentro do componente:
const { can } = useProjectPermissions()
```

Envolver o formulario de convite com:

```typescript
{can('project:manage_team') && (
  <div className="...">
    {/* formulario de convite existente */}
  </div>
)}
```

A lista de membros permanece visivel para todos.

- [ ] **Step 2: ProjectSettingsPage — campos disabled para read-only**

Em `ProjectSettingsPage.tsx` (verificar caminho exato), importar hook:

```typescript
import { useProjectPermissions } from '@/hooks/useProjectPermissions'

// Dentro do componente:
const { can, isReadOnly } = useProjectPermissions()
```

Em todos os `<input>`, `<select>`, `<button type="submit">`:

```typescript
<input ... disabled={!can('project:edit')} className={`... ${!can('project:edit') ? 'opacity-50 cursor-not-allowed' : ''}`} />

<button ... disabled={!can('project:edit')}>Salvar</button>
```

- [ ] **Step 3: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npm run type-check && npm run build
```

Esperado: build sem erros

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/app/pages/projects/ProjectTeamPage.tsx frontend/src/pages/projects/ProjectSettingsPage.tsx
git commit -m "feat: condicionar UI de team e settings a permissoes do usuario"
```

---

## Task 11: Teste de Integracao E2E

**Files:**
- Create: `backend/tests/test_rbac_integration.py`

- [ ] **Step 1: Escrever teste de integracao para fluxo completo**

```python
# backend/tests/test_rbac_integration.py
"""Testes de integracao para RBAC compartimentalizado."""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.permissions import has_action, get_actions_for_role
from app.dependencies.require_action import resolve_user_role_in_project


@pytest.mark.asyncio
class TestRBACIntegration:
    """Testa fluxo completo de RBAC."""

    async def test_admin_sees_project_as_viewer(self):
        """Admin sem membership ve projeto como admin_viewer."""
        db = AsyncMock()
        admin_id = uuid4()
        project_id = uuid4()

        with patch("app.dependencies.require_action.get_user_project_role", return_value=None), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(admin_id, project_id, db)
            assert role == "admin_viewer"
            assert has_action(role, "project:view") is True
            assert has_action(role, "project:manage_gp") is True
            assert has_action(role, "project:edit") is False
            assert has_action(role, "pipeline:execute") is False

    async def test_admin_as_gp_has_full_access(self):
        """Admin que tambem e GP do projeto tem poderes de GP."""
        db = AsyncMock()
        admin_gp_id = uuid4()
        project_id = uuid4()

        with patch("app.dependencies.require_action.get_user_project_role", return_value="gp"), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(admin_gp_id, project_id, db)
            assert role == "gp"
            assert has_action(role, "project:edit") is True
            assert has_action(role, "project:manage_team") is True
            assert has_action(role, "pipeline:execute") is True

    async def test_gp_cannot_manage_gp(self):
        """GP nao pode adicionar/remover outros GPs."""
        assert has_action("gp", "project:manage_gp") is False

    async def test_dev_cannot_manage_team(self):
        """Dev nao pode convidar membros."""
        assert has_action("dev_senior", "project:manage_team") is False
        assert has_action("dev_pleno", "project:manage_team") is False

    async def test_qa_cannot_execute_pipeline(self):
        """QA nao pode executar pipeline, so revisar."""
        assert has_action("qa", "pipeline:execute") is False
        assert has_action("qa", "pipeline:review") is True

    async def test_non_member_non_admin_blocked(self):
        """Usuario sem membership e sem admin recebe 403."""
        from fastapi import HTTPException
        db = AsyncMock()

        with patch("app.dependencies.require_action.get_user_project_role", return_value=None), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert exc_info.value.status_code == 403

    async def test_all_roles_have_project_view(self):
        """Todos os papeis tem project:view."""
        from app.core.permissions import ROLE_ACTIONS
        for role_name, actions in ROLE_ACTIONS.items():
            assert "project:view" in actions, f"Papel '{role_name}' nao tem project:view"
```

- [ ] **Step 2: Rodar testes de integracao**

```bash
cd /home/luiz/GCA/backend && python -m pytest tests/test_rbac_integration.py -v
```

Esperado: PASS (7 testes)

- [ ] **Step 3: Rodar todos os testes para regressao**

```bash
cd /home/luiz/GCA/backend && python -m pytest app/tests/ tests/ -v --timeout=30
```

Esperado: todos os testes passando, sem regressao

- [ ] **Step 4: Commit**

```bash
cd /home/luiz/GCA && git add backend/tests/test_rbac_integration.py
git commit -m "test: testes de integracao RBAC compartimentalizado"
```

---

## Task 12: Rebuild e Teste Manual

- [ ] **Step 1: Restart dos containers**

```bash
cd /home/luiz/GCA && docker compose restart backend frontend
```

- [ ] **Step 2: Aguardar build do frontend**

```bash
docker compose logs frontend --tail 5 -f 2>&1 | head -20
```

Esperado: `Local: http://localhost:5173/`

- [ ] **Step 3: Verificar endpoint de permissoes**

```bash
# Gerar token JWT para teste
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Testar endpoint de permissoes
curl -s http://localhost:8000/api/v1/projects/{PROJECT_ID}/permissions \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Esperado: retorna `{"role": "...", "actions": [...], "is_read_only": ...}`

- [ ] **Step 4: Verificar acesso externo**

```bash
curl -s -o /dev/null -w "%{http_code}" https://gca.code-auditor.com.br
curl -s -o /dev/null -w "%{http_code}" https://api.code-auditor.com.br/docs
```

Esperado: ambos 200

- [ ] **Step 5: Commit final**

```bash
cd /home/luiz/GCA && git add -A
git commit -m "RBAC Compartimentalizado: workspace GP, Admin read-only, gestao de GP, permissoes por acao"
```
