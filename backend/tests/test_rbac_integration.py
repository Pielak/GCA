"""Testes de integracao para RBAC compartimentalizado — atualizado para spec v2.0."""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import HTTPException

from app.core.permissions import has_action, get_actions_for_role, ROLE_ACTIONS
from app.dependencies.require_action import resolve_user_role_in_project


@pytest.mark.asyncio
class TestRBACIntegration:

    async def test_admin_sees_project_as_viewer(self):
        """Admin nao membro se torna admin_viewer com acesso restrito."""
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=[]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert role == "admin_viewer"
            assert has_action(role, "project:view") is True
            assert has_action(role, "project:manage_gp") is True
            assert has_action(role, "project:edit") is False
            assert has_action(role, "pipeline:execute") is False

    async def test_admin_as_gp_has_full_access(self):
        """Admin como GP no projeto tem acesso completo como GP."""
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=["gp"]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert role == "gp"
            assert has_action(role, "project:edit") is True
            assert has_action(role, "project:manage_team") is True
            assert has_action(role, "pipeline:execute") is True

    async def test_gp_cannot_manage_gp(self):
        assert has_action("gp", "project:manage_gp") is False

    async def test_dev_cannot_manage_team(self):
        assert has_action("dev_senior", "project:manage_team") is False
        assert has_action("dev_pleno", "project:manage_team") is False

    async def test_qa_has_pipeline_execute(self):
        """QA pode executar pipeline (spec v2.0) e aprovar."""
        assert has_action("qa", "pipeline:execute") is True
        assert has_action("qa", "qa:approve") is True

    async def test_non_member_non_admin_blocked(self):
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=[]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert exc_info.value.status_code == 403

    async def test_all_roles_have_project_view(self):
        for role_name, actions in ROLE_ACTIONS.items():
            assert "project:view" in actions, f"Papel '{role_name}' nao tem project:view"

    async def test_tech_lead_can_write_code_and_review(self):
        assert has_action("tech_lead", "code:write") is True
        assert has_action("tech_lead", "code:review") is True
        assert has_action("tech_lead", "pipeline:review") is True
        assert has_action("tech_lead", "pipeline:execute") is True

    async def test_dev_senior_has_code_review(self):
        """Dev Senior pode executar, escrever e revisar codigo."""
        assert has_action("dev_senior", "pipeline:execute") is True
        assert has_action("dev_senior", "code:write") is True
        assert has_action("dev_senior", "code:review") is True

    async def test_compliance_has_extended_permissions(self):
        """Compliance tem permissoes estendidas (spec v2.0)."""
        assert has_action("compliance", "project:edit") is True
        assert has_action("compliance", "security:review") is True
        assert has_action("compliance", "compliance:validate") is True
        assert has_action("compliance", "audit:export") is True

    async def test_stakeholder_view_only(self):
        assert get_actions_for_role("stakeholder") == {"project:view"}

    async def test_admin_viewer_cannot_edit(self):
        assert has_action("admin_viewer", "project:edit") is False
        assert has_action("admin_viewer", "code:write") is False
        assert has_action("admin_viewer", "pipeline:execute") is False

    async def test_gp_can_manage_team(self):
        assert has_action("gp", "project:manage_team") is True
        assert has_action("gp", "project:view") is True
        assert has_action("gp", "project:edit") is True

    async def test_gp_has_full_pipeline_access(self):
        """GP tem acesso completo ao pipeline (spec v2.0)."""
        assert has_action("gp", "code:write") is True
        assert has_action("gp", "code:review") is True
        assert has_action("gp", "git:commit") is True
        assert has_action("gp", "security:review") is True
        assert has_action("gp", "compliance:validate") is True
        assert has_action("gp", "qa:approve") is True
        assert has_action("gp", "backlog:manage") is True
        assert has_action("gp", "audit:view") is True
        assert has_action("gp", "audit:export") is True
