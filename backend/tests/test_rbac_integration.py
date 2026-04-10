"""Testes de integracao para RBAC compartimentalizado."""
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
        with patch("app.dependencies.require_action.get_user_project_role", return_value=None), \
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
        with patch("app.dependencies.require_action.get_user_project_role", return_value="gp"), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert role == "gp"
            assert has_action(role, "project:edit") is True
            assert has_action(role, "project:manage_team") is True
            assert has_action(role, "pipeline:execute") is True

    async def test_gp_cannot_manage_gp(self):
        """GP nao pode designar outros GPs (compartimentalizacao)."""
        assert has_action("gp", "project:manage_gp") is False

    async def test_dev_cannot_manage_team(self):
        """Dev Senior/Pleno nao pode gerenciar equipe."""
        assert has_action("dev_senior", "project:manage_team") is False
        assert has_action("dev_pleno", "project:manage_team") is False

    async def test_qa_cannot_execute_pipeline(self):
        """QA pode revisar mas nao executar pipeline."""
        assert has_action("qa", "pipeline:execute") is False
        assert has_action("qa", "pipeline:review") is True

    async def test_non_member_non_admin_blocked(self):
        """Usuario nao membro e nao admin toma 403."""
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_role", return_value=None), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert exc_info.value.status_code == 403

    async def test_all_roles_have_project_view(self):
        """Todos os papeis tem acesso minimo project:view."""
        for role_name, actions in ROLE_ACTIONS.items():
            assert "project:view" in actions, f"Papel '{role_name}' nao tem project:view"

    async def test_tech_lead_can_write_code_and_review(self):
        """Tech Lead pode escrever codigo e revisar pipeline."""
        assert has_action("tech_lead", "code:write") is True
        assert has_action("tech_lead", "pipeline:review") is True
        assert has_action("tech_lead", "pipeline:execute") is True

    async def test_dev_senior_cannot_review_pipeline(self):
        """Dev Senior pode executar mas nao revisar."""
        assert has_action("dev_senior", "pipeline:execute") is True
        assert has_action("dev_senior", "pipeline:review") is False

    async def test_compliance_stakeholder_have_view_only(self):
        """Compliance e Stakeholder sao view-only."""
        assert get_actions_for_role("compliance") == {"project:view"}
        assert get_actions_for_role("stakeholder") == {"project:view"}

    async def test_admin_viewer_cannot_edit(self):
        """admin_viewer nao pode editar projeto."""
        assert has_action("admin_viewer", "project:edit") is False
        assert has_action("admin_viewer", "code:write") is False
        assert has_action("admin_viewer", "pipeline:execute") is False

    async def test_gp_can_manage_team(self):
        """GP pode gerenciar equipe do projeto."""
        assert has_action("gp", "project:manage_team") is True
        assert has_action("gp", "project:view") is True
        assert has_action("gp", "project:edit") is True

    async def test_docs_edit_restricted_properly(self):
        """Apenas GP e Tech Lead podem editar docs."""
        assert has_action("gp", "docs:edit") is True
        assert has_action("tech_lead", "docs:edit") is True
        assert has_action("dev_senior", "docs:edit") is False
        assert has_action("qa", "docs:edit") is False
        assert has_action("compliance", "docs:edit") is False

    async def test_code_write_restricted_properly(self):
        """Apenas Dev roles e Tech Lead podem escrever codigo."""
        assert has_action("dev_senior", "code:write") is True
        assert has_action("dev_pleno", "code:write") is True
        assert has_action("tech_lead", "code:write") is True
        assert has_action("gp", "code:write") is False
        assert has_action("qa", "code:write") is False
