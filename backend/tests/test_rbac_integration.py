"""Testes de integração do RBAC canônico — 5 papéis + admin_viewer virtual.

Alinhado a GCA_CANONICAL_CONTRACT.md §4.
"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import HTTPException

from app.core.permissions import has_action, get_actions_for_role, ROLE_ACTIONS
from app.dependencies.require_action import resolve_user_role_in_project


@pytest.mark.asyncio
class TestRBACIntegration:

    # ── admin_viewer (virtual, admin não membro) ─────────────────────

    async def test_admin_sees_project_as_viewer(self):
        """Admin não membro se torna admin_viewer com acesso restrito."""
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=[]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert role == "admin_viewer"
            assert has_action(role, "project:view") is True
            assert has_action(role, "project:manage_gp") is True
            assert has_action(role, "project:edit") is False
            assert has_action(role, "pipeline:execute") is False

    async def test_admin_viewer_cannot_edit_or_execute(self):
        assert has_action("admin_viewer", "project:edit") is False
        assert has_action("admin_viewer", "code:write") is False
        assert has_action("admin_viewer", "pipeline:execute") is False

    async def test_non_member_non_admin_blocked(self):
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=[]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert exc_info.value.status_code == 403

    # ── GP ───────────────────────────────────────────────────────────

    async def test_admin_as_gp_has_gp_access(self):
        """Admin com membership como GP no projeto atua como GP."""
        db = AsyncMock()
        with patch("app.dependencies.require_action.get_user_project_roles", return_value=["gp"]), \
             patch("app.dependencies.require_action._get_user_is_admin", return_value=True):
            role = await resolve_user_role_in_project(uuid4(), uuid4(), db)
            assert role == "gp"
            assert has_action(role, "project:edit") is True
            assert has_action(role, "project:manage_team") is True

    async def test_gp_cannot_manage_gp(self):
        assert has_action("gp", "project:manage_gp") is False

    async def test_gp_does_not_write_code(self):
        """Contrato §4.1: GP conduz projeto, NÃO escreve código."""
        assert has_action("gp", "code:write") is False
        assert has_action("gp", "code:review") is False
        assert has_action("gp", "pipeline:execute") is False
        assert has_action("gp", "git:commit") is False

    async def test_gp_can_approve_and_manage(self):
        assert has_action("gp", "qa:approve") is True
        assert has_action("gp", "backlog:manage") is True
        assert has_action("gp", "pipeline:review") is True
        assert has_action("gp", "audit:export") is True

    # ── Dev ──────────────────────────────────────────────────────────

    async def test_dev_writes_and_commits(self):
        assert has_action("dev", "code:write") is True
        assert has_action("dev", "code:review") is True
        assert has_action("dev", "pipeline:execute") is True
        assert has_action("dev", "git:commit") is True

    async def test_dev_does_not_approve_or_manage_team(self):
        assert has_action("dev", "qa:approve") is False
        assert has_action("dev", "project:manage_team") is False

    # ── Tester ───────────────────────────────────────────────────────

    async def test_tester_executes_and_exports(self):
        assert has_action("tester", "pipeline:execute") is True
        assert has_action("tester", "audit:export") is True

    async def test_tester_does_not_write_code_or_approve(self):
        assert has_action("tester", "code:write") is False
        assert has_action("tester", "qa:approve") is False

    # ── QA ───────────────────────────────────────────────────────────

    async def test_qa_approves_and_validates(self):
        assert has_action("qa", "qa:approve") is True
        assert has_action("qa", "security:review") is True
        assert has_action("qa", "compliance:validate") is True

    async def test_qa_does_not_write_or_execute(self):
        """Contrato §4.1: QA revisa/aprova. NÃO edita teste nem executa pipeline."""
        assert has_action("qa", "code:write") is False
        assert has_action("qa", "pipeline:execute") is False

    # ── Invariantes canônicos ────────────────────────────────────────

    async def test_all_canonical_roles_have_project_view(self):
        for role_name, actions in ROLE_ACTIONS.items():
            assert "project:view" in actions, f"Papel '{role_name}' não tem project:view"

    async def test_historical_roles_removed(self):
        """Papéis não-canônicos foram removidos (contrato §4.2)."""
        for legacy in ("tech_lead", "dev_senior", "dev_pleno", "compliance", "stakeholder", "viewer"):
            assert legacy not in ROLE_ACTIONS, f"papel histórico {legacy} ainda presente"
