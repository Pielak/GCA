"""Testes basicos para permissions.py — atualizado para spec v2.0."""
import pytest
from app.core.permissions import ROLE_ACTIONS, has_action, get_actions_for_role


class TestRoleActions:
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
            "code:write", "code:review", "pipeline:execute", "pipeline:review",
            "security:review", "compliance:validate", "qa:approve",
            "git:commit", "backlog:manage", "audit:view", "audit:export", "docs:edit",
        }
        actions = get_actions_for_role("gp")
        assert expected == actions

    def test_gp_cannot_manage_gp(self):
        assert has_action("gp", "project:manage_gp") is False

    def test_gp_can_write_code(self):
        assert has_action("gp", "code:write") is True

    def test_tech_lead_has_code_write(self):
        assert has_action("tech_lead", "code:write") is True

    def test_tech_lead_has_pipeline_review(self):
        assert has_action("tech_lead", "pipeline:review") is True

    def test_dev_senior_has_pipeline_execute(self):
        assert has_action("dev_senior", "pipeline:execute") is True

    def test_dev_pleno_has_pipeline_execute(self):
        assert has_action("dev_pleno", "pipeline:execute") is True

    def test_dev_pleno_has_code_write(self):
        assert has_action("dev_pleno", "code:write") is True

    def test_qa_has_pipeline_execute(self):
        assert has_action("qa", "pipeline:execute") is True

    def test_qa_has_qa_approve(self):
        assert has_action("qa", "qa:approve") is True

    def test_qa_cannot_write_code(self):
        assert has_action("qa", "code:write") is False

    def test_compliance_has_extended_permissions(self):
        actions = get_actions_for_role("compliance")
        assert "project:edit" in actions
        assert "security:review" in actions
        assert "compliance:validate" in actions

    def test_stakeholder_only_view(self):
        actions = get_actions_for_role("stakeholder")
        assert actions == {"project:view"}

    def test_unknown_role_returns_empty(self):
        actions = get_actions_for_role("nonexistent")
        assert actions == set()

    def test_has_action_unknown_role(self):
        assert has_action("nonexistent", "project:view") is False
