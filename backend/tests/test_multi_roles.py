"""Testes para multi-papeis e nova matriz de permissoes (Secao 10 spec v2.0)."""
import pytest
from uuid import uuid4
from app.core.permissions import (
    ROLE_ACTIONS, has_action, get_actions_for_role,
    get_actions_for_roles, has_action_any,
)


class TestNewPermissionMatrix:
    """Testa nova matriz de permissoes (Secao 10 do spec)."""

    # GP — agora tem code:write, code:review, security:review, etc.
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
        assert "project:manage_team" in actions
        assert "code:write" in actions
        assert "pipeline:execute" in actions

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
