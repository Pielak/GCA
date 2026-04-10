# Fase 1: Multi-Papeis por Membro — Plano de Implementacao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que um membro de projeto tenha multiplos papeis simultaneos (GP + Dev Senior + QA), com permissoes acumuladas e trilha de auditoria.

**Architecture:** Nova tabela `ProjectMemberRole` (N:N). `permissions.py` atualizado com nova matriz de acoes (Secao 10 do spec). `require_action()` adaptado para resolver lista de papeis. Frontend adaptado para `roles[]`. Auto-atribuicao de papeis pelo GP via Equipe e on-demand no pipeline.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, React 18 + TypeScript + Zustand

**Spec:** `docs/superpowers/specs/2026-04-10-multi-roles-codegen-backlog-design.md` (Secoes 1-3, 10)

---

## File Structure

### Backend — Criar

| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/app/models/project_member_role.py` | Modelo ProjectMemberRole |
| `backend/app/routers/member_roles_router.py` | Endpoints auto-atribuicao + audit |
| `backend/app/services/member_roles_service.py` | Logica de adicao/listagem de papeis |
| `backend/tests/test_multi_roles.py` | Testes unitarios |

### Backend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `backend/app/core/permissions.py` | Nova matriz (Secao 10) + `get_actions_for_roles()` + `has_action_any()` |
| `backend/app/dependencies/require_action.py` | `resolve_user_role_in_project()` retorna `list[str]` |
| `backend/app/dependencies/project_access.py` | `get_user_project_roles()` (plural) consulta ProjectMemberRole |
| `backend/app/routers/projects.py` | Endpoint `/permissions` retorna `roles[]` |
| `backend/app/main.py` | Registrar novo router |

### Frontend — Modificar

| Arquivo | O que muda |
|---------|-----------|
| `frontend/src/hooks/useProjectPermissions.ts` | `role` -> `roles[]` |
| `frontend/src/app/pages/projects/ProjectTeamPage.tsx` | UI de auto-atribuicao de papeis |

---

## Task 1: Modelo ProjectMemberRole + Atualizar permissions.py

**Files:**
- Create: `backend/app/models/project_member_role.py`
- Modify: `backend/app/core/permissions.py`
- Test: `backend/tests/test_multi_roles.py`

- [ ] **Step 1: Escrever testes para nova matriz de permissoes**

```python
# backend/tests/test_multi_roles.py
import pytest
from app.core.permissions import (
    ROLE_ACTIONS, has_action, get_actions_for_role,
    get_actions_for_roles, has_action_any,
)


class TestNewPermissionMatrix:
    """Testa nova matriz de permissoes (Secao 10 do spec)."""

    # GP agora tem code:write, code:review, security:review, git:commit, etc.
    def test_gp_has_code_write(self):
        assert has_action("gp", "code:write") is True

    def test_gp_has_code_review(self):
        assert has_action("gp", "code:review") is True

    def test_gp_has_security_review(self):
        assert has_action("gp", "security:review") is True

    def test_gp_has_qa_approve(self):
        assert has_action("gp", "qa:approve") is True

    def test_gp_has_git_commit(self):
        assert has_action("gp", "git:commit") is True

    def test_gp_has_backlog_manage(self):
        assert has_action("gp", "backlog:manage") is True

    def test_gp_has_audit_view(self):
        assert has_action("gp", "audit:view") is True

    def test_gp_has_audit_export(self):
        assert has_action("gp", "audit:export") is True

    def test_gp_has_compliance_validate(self):
        assert has_action("gp", "compliance:validate") is True

    # Tech Lead
    def test_tech_lead_has_code_review(self):
        assert has_action("tech_lead", "code:review") is True

    def test_tech_lead_has_security_review(self):
        assert has_action("tech_lead", "security:review") is True

    def test_tech_lead_has_git_commit(self):
        assert has_action("tech_lead", "git:commit") is True

    def test_tech_lead_has_backlog_manage(self):
        assert has_action("tech_lead", "backlog:manage") is True

    def test_tech_lead_no_qa_approve(self):
        assert has_action("tech_lead", "qa:approve") is False

    def test_tech_lead_no_compliance_validate(self):
        assert has_action("tech_lead", "compliance:validate") is False

    # Dev Senior
    def test_dev_senior_has_code_review(self):
        assert has_action("dev_senior", "code:review") is True

    def test_dev_senior_has_git_commit(self):
        assert has_action("dev_senior", "git:commit") is True

    def test_dev_senior_has_audit_view(self):
        assert has_action("dev_senior", "audit:view") is True

    def test_dev_senior_no_security_review(self):
        assert has_action("dev_senior", "security:review") is False

    # Dev Pleno
    def test_dev_pleno_no_git_commit(self):
        assert has_action("dev_pleno", "git:commit") is False

    def test_dev_pleno_no_code_review(self):
        assert has_action("dev_pleno", "code:review") is False

    # QA
    def test_qa_has_qa_approve(self):
        assert has_action("qa", "qa:approve") is True

    def test_qa_has_audit_view(self):
        assert has_action("qa", "audit:view") is True

    def test_qa_no_code_write(self):
        assert has_action("qa", "code:write") is False

    # Compliance
    def test_compliance_has_compliance_validate(self):
        assert has_action("compliance", "compliance:validate") is True

    def test_compliance_has_security_review(self):
        assert has_action("compliance", "security:review") is True

    def test_compliance_has_backlog_manage(self):
        assert has_action("compliance", "backlog:manage") is True

    def test_compliance_has_audit_export(self):
        assert has_action("compliance", "audit:export") is True

    def test_compliance_has_project_edit(self):
        assert has_action("compliance", "project:edit") is True

    # Stakeholder
    def test_stakeholder_only_view(self):
        actions = get_actions_for_role("stakeholder")
        assert actions == {"project:view"}


class TestMultiRoleFunctions:
    """Testa funcoes para multiplos papeis."""

    def test_get_actions_for_roles_union(self):
        actions = get_actions_for_roles(["gp", "dev_senior"])
        # Deve ter union de ambos
        assert "project:manage_team" in actions  # GP
        assert "code:write" in actions  # ambos
        assert "pipeline:execute" in actions  # ambos

    def test_get_actions_for_roles_empty(self):
        actions = get_actions_for_roles([])
        assert actions == set()

    def test_has_action_any_true(self):
        assert has_action_any(["qa", "compliance"], "qa:approve") is True

    def test_has_action_any_false(self):
        assert has_action_any(["stakeholder"], "code:write") is False

    def test_has_action_any_empty_roles(self):
        assert has_action_any([], "project:view") is False

    def test_admin_viewer_unchanged(self):
        actions = get_actions_for_role("admin_viewer")
        assert "project:view" in actions
        assert "project:manage_gp" in actions
        assert len(actions) == 2
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
cd /home/luiz/GCA/backend && python3 -m pytest tests/test_multi_roles.py -v
```

Esperado: FAIL (funcoes novas nao existem, acoes novas nao existem)

- [ ] **Step 3: Atualizar permissions.py com nova matriz + funcoes multi-papel**

Substituir conteudo completo de `backend/app/core/permissions.py`:

```python
"""
Mapeamento de papeis para acoes no sistema GCA.

Matriz de permissoes conforme Secao 10 do spec v2.0.
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
        "code:write",
        "code:review",
        "pipeline:execute",
        "pipeline:review",
        "security:review",
        "compliance:validate",
        "qa:approve",
        "git:commit",
        "backlog:manage",
        "audit:view",
        "audit:export",
        "docs:edit",
    },
    "tech_lead": {
        "project:view",
        "project:edit",
        "code:write",
        "code:review",
        "pipeline:execute",
        "pipeline:review",
        "security:review",
        "git:commit",
        "backlog:manage",
        "audit:view",
        "docs:edit",
    },
    "dev_senior": {
        "project:view",
        "code:write",
        "code:review",
        "pipeline:execute",
        "git:commit",
        "audit:view",
    },
    "dev_pleno": {
        "project:view",
        "code:write",
        "pipeline:execute",
    },
    "qa": {
        "project:view",
        "pipeline:execute",
        "qa:approve",
        "audit:view",
    },
    "compliance": {
        "project:view",
        "project:edit",
        "pipeline:execute",
        "security:review",
        "compliance:validate",
        "backlog:manage",
        "audit:view",
        "audit:export",
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


def get_actions_for_roles(roles: list[str]) -> set[str]:
    """Union de acoes de todos os papeis."""
    actions = set()
    for role in roles:
        actions |= get_actions_for_role(role)
    return actions


def has_action_any(roles: list[str], action: str) -> bool:
    """Verifica se qualquer um dos papeis tem a acao."""
    return action in get_actions_for_roles(roles)
```

- [ ] **Step 4: Criar modelo ProjectMemberRole**

```python
# backend/app/models/project_member_role.py
"""Modelo para multiplos papeis por membro de projeto."""
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class ProjectMemberRole(Base):
    __tablename__ = "project_member_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("project_members.id"), nullable=False)
    role = Column(String(30), nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("member_id", "role", name="uq_member_role"),
    )
```

- [ ] **Step 5: Rodar testes**

```bash
cd /home/luiz/GCA/backend && python3 -m pytest tests/test_multi_roles.py -v
```

Esperado: PASS (todos os testes da nova matriz)

- [ ] **Step 6: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/core/permissions.py backend/app/models/project_member_role.py backend/tests/test_multi_roles.py
git commit -m "feat: nova matriz de permissoes (Secao 10) + modelo ProjectMemberRole + get_actions_for_roles()

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Adaptar require_action() e project_access para multiplos papeis

**Files:**
- Modify: `backend/app/dependencies/project_access.py:18-35`
- Modify: `backend/app/dependencies/require_action.py`
- Modify: `backend/app/routers/projects.py` (endpoint /permissions)
- Test: `backend/tests/test_multi_roles.py` (adicionar testes)

- [ ] **Step 1: Adicionar testes para resolucao multi-papel**

Adicionar ao final de `backend/tests/test_multi_roles.py`:

```python
@pytest.mark.asyncio
class TestResolveMultiRoles:

    async def test_member_returns_list_of_roles(self):
        from app.dependencies.require_action import resolve_user_roles_in_project
        from unittest.mock import AsyncMock, patch

        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=["gp", "dev_senior"]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            roles = await resolve_user_roles_in_project(uuid4(), uuid4(), db)
            assert roles == ["gp", "dev_senior"]

    async def test_admin_without_membership_returns_admin_viewer(self):
        from app.dependencies.require_action import resolve_user_roles_in_project
        from unittest.mock import AsyncMock, patch

        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=[]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            roles = await resolve_user_roles_in_project(uuid4(), uuid4(), db)
            assert roles == ["admin_viewer"]

    async def test_admin_with_membership_returns_member_roles(self):
        from app.dependencies.require_action import resolve_user_roles_in_project
        from unittest.mock import AsyncMock, patch

        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=["gp", "qa"]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            roles = await resolve_user_roles_in_project(uuid4(), uuid4(), db)
            assert roles == ["gp", "qa"]

    async def test_non_member_non_admin_raises_403(self):
        from app.dependencies.require_action import resolve_user_roles_in_project
        from unittest.mock import AsyncMock, patch
        from fastapi import HTTPException

        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=[]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_roles_in_project(uuid4(), uuid4(), db)
            assert exc_info.value.status_code == 403
```

Adicionar import no topo do arquivo:
```python
from uuid import uuid4
```

- [ ] **Step 2: Criar get_user_project_roles() em project_access.py**

Adicionar nova funcao em `backend/app/dependencies/project_access.py` (apos `get_user_project_role`):

```python
async def get_user_project_roles(
    user_id: UUID,
    project_id: UUID,
    db: AsyncSession,
) -> list[str]:
    """
    Retorna TODOS os papeis do usuario no projeto.
    Consulta ProjectMemberRole se existir, senao fallback para ProjectMember.role.
    """
    from app.models.project_member_role import ProjectMemberRole

    # Buscar member_id
    member_result = await db.execute(
        select(ProjectMember.id, ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.is_active == True,
        )
    )
    member_row = member_result.first()
    if not member_row:
        return []

    member_id = member_row.id
    base_role = member_row.role

    # Buscar papeis adicionais na tabela ProjectMemberRole
    roles_result = await db.execute(
        select(ProjectMemberRole.role).where(
            ProjectMemberRole.member_id == member_id,
        )
    )
    additional_roles = [r.role for r in roles_result.all()]

    # Combinar: papel base + papeis adicionais (sem duplicatas)
    all_roles = list(set([base_role] + additional_roles))
    return all_roles
```

- [ ] **Step 3: Atualizar require_action.py para multiplos papeis**

Substituir conteudo completo de `backend/app/dependencies/require_action.py`:

```python
"""
Dependency FastAPI para verificar permissoes por acao.

Suporta multiplos papeis por membro. Acoes sao acumuladas de todos os papeis.

Uso:
    @router.post("/projects/{project_id}/settings")
    async def update_settings(
        project_id: UUID,
        permissions: dict = Depends(require_action("project:edit")),
    ):
        user_id = permissions["user_id"]
        roles = permissions["roles"]
"""
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import has_action_any
from app.db.database import get_db
from app.dependencies.project_access import get_user_project_roles
from app.middleware.auth import get_current_user_from_token
from app.models.base import User


async def _get_user_is_admin(user_id: UUID, db: AsyncSession) -> bool:
    result = await db.execute(select(User.is_admin).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row is True


async def resolve_user_roles_in_project(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> list[str]:
    """
    Resolve os papeis efetivos do usuario no projeto.

    - Se e membro -> retorna lista de papeis (base + adicionais)
    - Se NAO e membro mas e Admin -> retorna ['admin_viewer']
    - Se NAO e membro e NAO e Admin -> 403
    """
    roles = await get_user_project_roles(user_id, project_id, db)

    if roles:
        return roles

    is_admin = await _get_user_is_admin(user_id, db)
    if is_admin:
        return ["admin_viewer"]

    raise HTTPException(
        status_code=403,
        detail="Acesso negado: voce nao e membro deste projeto",
    )


# Manter compatibilidade com codigo existente que usa resolve_user_role_in_project
async def resolve_user_role_in_project(
    user_id: UUID, project_id: UUID, db: AsyncSession
) -> str:
    """Compatibilidade: retorna primeiro papel da lista."""
    roles = await resolve_user_roles_in_project(user_id, project_id, db)
    return roles[0] if roles else "admin_viewer"


def require_action(action: str):
    """
    Dependency factory que verifica se o usuario tem a acao no projeto.

    Retorna dict com user_id, roles e project_id.
    """

    async def _dependency(
        project_id: UUID,
        user_id: UUID = Depends(get_current_user_from_token),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        roles = await resolve_user_roles_in_project(user_id, project_id, db)

        if not has_action_any(roles, action):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso negado: seus papeis {roles} nao tem permissao para '{action}'",
            )

        return {"user_id": user_id, "roles": roles, "role": roles[0], "project_id": project_id}

    return _dependency
```

- [ ] **Step 4: Atualizar endpoint /permissions em projects.py**

Em `backend/app/routers/projects.py`, alterar o endpoint `get_user_permissions`:

Substituir:
```python
from app.dependencies.require_action import resolve_user_role_in_project
```
Por:
```python
from app.dependencies.require_action import resolve_user_roles_in_project
```

E alterar o corpo do endpoint:
```python
@router.get("/{project_id}/permissions")
async def get_user_permissions(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna os papeis e acoes do usuario no projeto."""
    roles = await resolve_user_roles_in_project(user_id, project_id, db)
    actions = get_actions_for_roles(roles)
    return {
        "roles": roles,
        "actions": sorted(actions),
        "is_read_only": roles == ["admin_viewer"] or actions <= {"project:view", "project:manage_gp"},
    }
```

Atualizar import:
```python
from app.core.permissions import get_actions_for_roles
```

- [ ] **Step 5: Rodar testes**

```bash
cd /home/luiz/GCA/backend && python3 -m pytest tests/test_multi_roles.py -v
```

Esperado: PASS (todos incluindo os novos testes de resolucao)

- [ ] **Step 6: Rodar testes de regressao**

```bash
cd /home/luiz/GCA/backend && python3 -m pytest tests/ -v
```

Esperado: todos passando. Os testes antigos de `test_permissions.py` e `test_require_action.py` podem precisar de ajustes se importam funcoes renomeadas — corrigir se necessario.

- [ ] **Step 7: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/dependencies/project_access.py backend/app/dependencies/require_action.py backend/app/routers/projects.py backend/tests/test_multi_roles.py
git commit -m "refactor: require_action() suporta multiplos papeis por membro

resolve_user_roles_in_project() retorna list[str].
Endpoint /permissions retorna roles[].
Compatibilidade mantida via resolve_user_role_in_project().

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Servico e Endpoints de auto-atribuicao de papeis

**Files:**
- Create: `backend/app/services/member_roles_service.py`
- Create: `backend/app/routers/member_roles_router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Criar servico**

```python
# backend/app/services/member_roles_service.py
"""Servico para gestao de papeis multiplos por membro."""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectMember
from app.models.project_member_role import ProjectMemberRole

import structlog
logger = structlog.get_logger(__name__)


class MemberRolesService:

    async def get_member_roles(
        self, db: AsyncSession, project_id: UUID, user_id: UUID
    ) -> list[dict]:
        """Retorna todos os papeis de um membro no projeto."""
        member = await self._get_member(db, project_id, user_id)
        if not member:
            return []

        roles_result = await db.execute(
            select(ProjectMemberRole).where(
                ProjectMemberRole.member_id == member.id,
            )
        )
        additional_roles = roles_result.scalars().all()

        result = [{"role": member.role, "is_base": True, "assigned_at": str(member.joined_at or member.invited_at)}]
        for r in additional_roles:
            result.append({"role": r.role, "is_base": False, "assigned_at": str(r.assigned_at)})

        return result

    async def add_roles(
        self, db: AsyncSession, project_id: UUID, user_id: UUID, roles: list[str], assigned_by: UUID
    ) -> dict:
        """Adiciona papeis ao membro logado."""
        member = await self._get_member(db, project_id, user_id)
        if not member:
            return {"success": False, "error": "Voce nao e membro deste projeto"}

        added = []
        skipped = []
        for role in roles:
            if role == member.role:
                skipped.append(role)
                continue

            # Verificar se ja tem
            existing = await db.execute(
                select(ProjectMemberRole).where(
                    ProjectMemberRole.member_id == member.id,
                    ProjectMemberRole.role == role,
                )
            )
            if existing.scalar_one_or_none():
                skipped.append(role)
                continue

            new_role = ProjectMemberRole(
                id=uuid4(),
                member_id=member.id,
                role=role,
                assigned_at=datetime.now(timezone.utc),
                assigned_by=assigned_by,
            )
            db.add(new_role)
            added.append(role)

        await db.commit()
        logger.info("roles_added", project_id=str(project_id), user_id=str(user_id), added=added, skipped=skipped)
        return {"success": True, "added": added, "skipped": skipped}

    async def get_role_audit(
        self, db: AsyncSession, project_id: UUID
    ) -> list[dict]:
        """Historico de atribuicoes de papeis no projeto."""
        from app.models.base import User

        members = await db.execute(
            select(ProjectMember.id, ProjectMember.user_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.is_active == True,
            )
        )
        member_rows = members.all()
        member_ids = [m.id for m in member_rows]
        user_map = {m.id: m.user_id for m in member_rows}

        if not member_ids:
            return []

        roles = await db.execute(
            select(ProjectMemberRole).where(
                ProjectMemberRole.member_id.in_(member_ids),
            ).order_by(ProjectMemberRole.assigned_at.desc())
        )

        result = []
        for r in roles.scalars().all():
            # Buscar email do usuario
            user_id = user_map.get(r.member_id)
            user = await db.get(User, user_id) if user_id else None
            result.append({
                "role": r.role,
                "user_email": user.email if user else "?",
                "assigned_at": str(r.assigned_at),
                "assigned_by": str(r.assigned_by),
            })

        return result

    async def _get_member(
        self, db: AsyncSession, project_id: UUID, user_id: UUID
    ) -> ProjectMember | None:
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True,
            )
        )
        return result.scalar_one_or_none()
```

- [ ] **Step 2: Criar router**

```python
# backend/app/routers/member_roles_router.py
"""Endpoints para gestao de papeis multiplos por membro."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.middleware.auth import get_current_user_from_token
from app.services.member_roles_service import MemberRolesService

router = APIRouter(tags=["Member Roles"])
service = MemberRolesService()


class AddRolesRequest(BaseModel):
    roles: list[str]


@router.get("/projects/{project_id}/members/self/roles")
async def get_my_roles(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna meus papeis no projeto."""
    user_id = permissions["user_id"]
    roles = await service.get_member_roles(db, project_id, user_id)
    return {"roles": roles}


@router.post("/projects/{project_id}/members/self/roles")
async def add_my_roles(
    project_id: UUID,
    request: AddRolesRequest,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona papeis ao meu membro no projeto (auto-atribuicao GP)."""
    user_id = permissions["user_id"]
    valid_roles = {"tech_lead", "dev_senior", "dev_pleno", "qa", "compliance", "stakeholder"}
    invalid = set(request.roles) - valid_roles
    if invalid:
        raise HTTPException(status_code=422, detail=f"Papeis invalidos: {invalid}")

    result = await service.add_roles(db, project_id, user_id, request.roles, user_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/projects/{project_id}/audit/roles")
async def get_role_audit(
    project_id: UUID,
    permissions: dict = Depends(require_action("audit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Historico de atribuicoes de papeis no projeto."""
    audit = await service.get_role_audit(db, project_id)
    return {"audit": audit}
```

- [ ] **Step 3: Registrar router no main.py**

Em `backend/app/main.py`, adicionar:
```python
from app.routers.member_roles_router import router as member_roles_router
```
E:
```python
app.include_router(member_roles_router, prefix=f"{settings.API_PREFIX}")
```

- [ ] **Step 4: Criar migration Alembic**

```bash
cd /home/luiz/GCA/backend && alembic revision --autogenerate -m "add project_member_roles table"
cd /home/luiz/GCA/backend && alembic upgrade head
```

Se alembic nao esta configurado ou falha, criar tabela manualmente:
```bash
cd /home/luiz/GCA/backend && python3 -c "
import asyncio
from app.db.database import engine
from app.models.project_member_role import ProjectMemberRole
from app.models.base import Base

async def create():
    async with engine.begin() as conn:
        await conn.run_sync(ProjectMemberRole.__table__.create, checkfirst=True)
    print('Table created')

asyncio.run(create())
"
```

- [ ] **Step 5: Rodar testes**

```bash
cd /home/luiz/GCA/backend && python3 -m pytest tests/ -v
```

Esperado: todos passando

- [ ] **Step 6: Commit**

```bash
cd /home/luiz/GCA && git add backend/app/services/member_roles_service.py backend/app/routers/member_roles_router.py backend/app/main.py
git commit -m "feat: endpoints auto-atribuicao de papeis + audit de papeis

POST /members/self/roles para GP adicionar papeis.
GET /audit/roles para historico de atribuicoes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Frontend — useProjectPermissions adaptado para roles[]

**Files:**
- Modify: `frontend/src/hooks/useProjectPermissions.ts`
- Modify: `frontend/src/pages/projects/ProjectDetailLayout.tsx` (Outlet context)

- [ ] **Step 1: Atualizar hook**

Substituir conteudo de `frontend/src/hooks/useProjectPermissions.ts`:

```typescript
import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { apiClient } from '@/lib/api'

interface ProjectPermissions {
  roles: string[]
  actions: string[]
  isReadOnly: boolean
}

export function useProjectPermissions() {
  const { id: projectId } = useParams<{ id: string }>()
  const [permissions, setPermissions] = useState<ProjectPermissions>({
    roles: [],
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
          roles: res.data.roles || [],
          actions: res.data.actions || [],
          isReadOnly: res.data.is_read_only ?? true,
        })
      } catch {
        setPermissions({ roles: [], actions: [], isReadOnly: true })
      } finally {
        setLoading(false)
      }
    }

    fetchPermissions()
  }, [projectId])

  const can = (action: string): boolean => {
    return permissions.actions.includes(action)
  }

  const hasRole = (role: string): boolean => {
    return permissions.roles.includes(role)
  }

  return {
    can,
    hasRole,
    roles: permissions.roles,
    role: permissions.roles[0] || '',
    isReadOnly: permissions.isReadOnly,
    loading,
  }
}
```

- [ ] **Step 2: Atualizar Outlet context no ProjectDetailLayout**

Em `ProjectDetailLayout.tsx`, onde passa `role` no Outlet context, alterar para tambem passar `roles`:

```typescript
<Outlet context={{ repoConnected, can, role, roles, isReadOnly, projectStatus: project?.status }} />
```

Onde `roles` vem do hook:
```typescript
const { can, role, roles, isReadOnly } = useProjectPermissions()
```

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/hooks/useProjectPermissions.ts frontend/src/pages/projects/ProjectDetailLayout.tsx
git commit -m "feat: useProjectPermissions adaptado para roles[] multiplos

Hook retorna roles[], hasRole(), role (primeiro), can() inalterado.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Frontend — UI de auto-atribuicao na aba Equipe

**Files:**
- Modify: `frontend/src/app/pages/projects/ProjectTeamPage.tsx`

- [ ] **Step 1: Adicionar secao de papeis do GP na ProjectTeamPage**

Apos os imports existentes, adicionar:
```typescript
import { apiClient } from '@/lib/api'
```

Dentro do componente, adicionar state e logica:
```typescript
const [myRoles, setMyRoles] = useState<{role: string, is_base: boolean}[]>([])
const [addingRole, setAddingRole] = useState(false)
const [selectedNewRole, setSelectedNewRole] = useState('')

const AVAILABLE_ROLES = [
  { value: 'tech_lead', label: 'Tech Lead' },
  { value: 'dev_senior', label: 'Dev Senior' },
  { value: 'dev_pleno', label: 'Dev Pleno' },
  { value: 'qa', label: 'QA' },
  { value: 'compliance', label: 'Compliance' },
  { value: 'stakeholder', label: 'Stakeholder' },
]

useEffect(() => {
  if (!projectId) return
  apiClient.get(`/projects/${projectId}/members/self/roles`)
    .then(res => setMyRoles(res.data.roles || []))
    .catch(() => {})
}, [projectId])

const handleAddRole = async () => {
  if (!selectedNewRole || !projectId) return
  setAddingRole(true)
  try {
    await apiClient.post(`/projects/${projectId}/members/self/roles`, { roles: [selectedNewRole] })
    const res = await apiClient.get(`/projects/${projectId}/members/self/roles`)
    setMyRoles(res.data.roles || [])
    setSelectedNewRole('')
  } catch { /* error handling */ }
  finally { setAddingRole(false) }
}
```

No JSX, antes da secao de membros, adicionar bloco:
```typescript
{canManageTeam && (
  <div className="bg-dark-100 border border-slate-700 rounded-xl p-6">
    <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
      Meus Papeis no Projeto
    </h2>
    <div className="flex flex-wrap gap-2 mb-4">
      {myRoles.map(r => (
        <span key={r.role} className={`px-3 py-1 rounded-full text-xs font-medium ${
          r.is_base ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-violet-500/20 text-violet-300 border border-violet-500/30'
        }`}>
          {ROLE_OPTIONS.find(o => o.value === r.role)?.label || r.role}
          {r.is_base && ' (base)'}
        </span>
      ))}
    </div>
    <div className="flex gap-2">
      <select
        value={selectedNewRole}
        onChange={e => setSelectedNewRole(e.target.value)}
        className="bg-dark-200 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-100"
      >
        <option value="">Adicionar papel...</option>
        {AVAILABLE_ROLES.filter(r => !myRoles.find(mr => mr.role === r.value)).map(r => (
          <option key={r.value} value={r.value}>{r.label}</option>
        ))}
      </select>
      <button
        onClick={handleAddRole}
        disabled={!selectedNewRole || addingRole}
        className="bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg px-4 py-2 text-sm font-medium"
      >
        Adicionar
      </button>
    </div>
  </div>
)}
```

- [ ] **Step 2: Verificar build**

```bash
cd /home/luiz/GCA/frontend && npx tsc --noEmit 2>&1 | tail -10
```

- [ ] **Step 3: Commit**

```bash
cd /home/luiz/GCA && git add frontend/src/app/pages/projects/ProjectTeamPage.tsx
git commit -m "feat: UI de auto-atribuicao de papeis na aba Equipe

GP pode ver seus papeis e adicionar novos (Tech Lead, Dev, QA, etc.).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Rebuild, Testes e Verificacao Manual

- [ ] **Step 1: Rodar todos os testes backend**

```bash
cd /home/luiz/GCA/backend && python3 -m pytest tests/ -v
```

Esperado: todos passando

- [ ] **Step 2: Restart containers**

```bash
cd /home/luiz/GCA && docker compose restart backend frontend
```

- [ ] **Step 3: Testar endpoint de papeis**

```bash
PROJECT_ID="9220601b-e006-4e10-9310-ab8aa0fb9250"
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pielak.ctba@gmail.com","password":"Topazio01#"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Testar permissions (agora retorna roles[])
curl -s "http://localhost:8000/api/v1/projects/$PROJECT_ID/permissions" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Testar meus papeis
curl -s "http://localhost:8000/api/v1/projects/$PROJECT_ID/members/self/roles" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Adicionar papel dev_senior
curl -s -X POST "http://localhost:8000/api/v1/projects/$PROJECT_ID/members/self/roles" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"roles": ["dev_senior", "qa"]}' | python3 -m json.tool

# Verificar permissions atualizadas
curl -s "http://localhost:8000/api/v1/projects/$PROJECT_ID/permissions" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

- [ ] **Step 4: Verificar frontend**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173
curl -s -o /dev/null -w "%{http_code}" https://gca.code-auditor.com.br
```

Esperado: 200

- [ ] **Step 5: Commit final se necessario**

```bash
cd /home/luiz/GCA && git status
# Se houver mudancas:
git add -A && git commit -m "fix: ajustes finais multi-papeis fase 1

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
