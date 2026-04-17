"""Testes para multi-papéis e matriz de permissões canônica.

Fonte: GCA_CANONICAL_CONTRACT.md §4. Papéis canônicos: admin (via admin_viewer
virtual), gp, dev, tester, qa. Papéis históricos (tech_lead, dev_senior,
dev_pleno, compliance, stakeholder) foram removidos do RBAC.
"""
import pytest
from uuid import uuid4
from app.core.permissions import (
    ROLE_ACTIONS, has_action, get_actions_for_role,
    get_actions_for_roles, has_action_any,
)


class TestCanonicalPermissionMatrix:
    """Matriz de permissões dos 5 papéis canônicos + admin_viewer."""

    # ── GP: conduz projeto, aprova, NÃO escreve código ──

    def test_gp_cannot_write_code(self):
        assert has_action("gp", "code:write") is False
        assert has_action("gp", "code:review") is False
        assert has_action("gp", "git:commit") is False
        assert has_action("gp", "pipeline:execute") is False

    def test_gp_has_qa_approve(self):
        assert has_action("gp", "qa:approve") is True

    def test_gp_has_backlog_manage(self):
        assert has_action("gp", "backlog:manage") is True

    def test_gp_has_audit_view_and_export(self):
        assert has_action("gp", "audit:view") is True
        assert has_action("gp", "audit:export") is True

    def test_gp_has_project_edit_and_manage_team(self):
        assert has_action("gp", "project:edit") is True
        assert has_action("gp", "project:manage_team") is True

    def test_gp_has_pipeline_review(self):
        assert has_action("gp", "pipeline:review") is True

    def test_gp_has_docs_edit(self):
        assert has_action("gp", "docs:edit") is True

    # ── Dev: implementa código, NÃO aprova módulo ──

    def test_dev_writes_and_reviews_code(self):
        assert has_action("dev", "code:write") is True
        assert has_action("dev", "code:review") is True

    def test_dev_can_commit_and_execute(self):
        assert has_action("dev", "git:commit") is True
        assert has_action("dev", "pipeline:execute") is True

    def test_dev_no_qa_approve(self):
        assert has_action("dev", "qa:approve") is False

    def test_dev_no_manage_team(self):
        assert has_action("dev", "project:manage_team") is False

    # ── Tester: cria/edita/executa testes, exporta evidências ──

    def test_tester_has_pipeline_execute(self):
        assert has_action("tester", "pipeline:execute") is True

    def test_tester_has_audit_export(self):
        assert has_action("tester", "audit:export") is True

    def test_tester_no_code_write(self):
        assert has_action("tester", "code:write") is False

    def test_tester_no_qa_approve(self):
        assert has_action("tester", "qa:approve") is False

    # ── QA: revisa/aprova, NÃO edita teste ──

    def test_qa_has_approve(self):
        assert has_action("qa", "qa:approve") is True

    def test_qa_has_security_and_compliance(self):
        assert has_action("qa", "security:review") is True
        assert has_action("qa", "compliance:validate") is True

    def test_qa_no_code_write(self):
        assert has_action("qa", "code:write") is False

    def test_qa_no_pipeline_execute(self):
        # QA revisa, não executa.
        assert has_action("qa", "pipeline:execute") is False

    # ── Papéis históricos foram removidos ──

    def test_historical_roles_removed(self):
        for legacy in ("tech_lead", "dev_senior", "dev_pleno", "compliance", "stakeholder", "viewer"):
            assert legacy not in ROLE_ACTIONS


class TestMultiRoleFunctions:
    """Funções para múltiplos papéis (um usuário pode ter 1+ roles no projeto)."""

    def test_get_actions_for_roles_union(self):
        # Usuário com gp+dev: aprovação de GP + escrita de código de Dev.
        actions = get_actions_for_roles(["gp", "dev"])
        assert "project:manage_team" in actions  # vem do GP
        assert "code:write" in actions           # vem do Dev
        assert "qa:approve" in actions           # vem do GP

    def test_get_actions_for_roles_empty(self):
        assert get_actions_for_roles([]) == set()

    def test_has_action_any_true(self):
        assert has_action_any(["qa", "tester"], "qa:approve") is True

    def test_has_action_any_false(self):
        assert has_action_any(["tester"], "code:write") is False

    def test_has_action_any_empty_roles(self):
        assert has_action_any([], "project:view") is False

    def test_admin_viewer_unchanged(self):
        actions = get_actions_for_role("admin_viewer")
        assert actions == {"project:view", "project:manage_gp"}


@pytest.mark.asyncio
class TestResolveMultiRoles:

    async def test_member_returns_list_of_roles(self):
        from app.dependencies.require_action import resolve_user_roles_in_project
        from unittest.mock import AsyncMock, patch

        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=["gp", "dev"]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            roles = await resolve_user_roles_in_project(uuid4(), uuid4(), db)
            assert roles == ["gp", "dev"]

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
