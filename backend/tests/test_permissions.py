"""Testes de RBAC canônico — 5 papéis (Admin, GP, Dev, Tester, QA) + admin_viewer virtual.

Alinhado a GCA_CANONICAL_CONTRACT.md §4. Papéis históricos (tech_lead,
dev_senior, dev_pleno, compliance, stakeholder) foram removidos do RBAC.
"""
import pytest
from app.core.permissions import ROLE_ACTIONS, has_action, get_actions_for_role


class TestRoleActions:
    # ── admin_viewer (virtual) ────────────────────────────────────────

    def test_admin_viewer_has_project_view(self):
        assert has_action("admin_viewer", "project:view") is True

    def test_admin_viewer_has_manage_gp(self):
        assert has_action("admin_viewer", "project:manage_gp") is True

    def test_admin_viewer_cannot_edit(self):
        assert has_action("admin_viewer", "project:edit") is False

    def test_admin_viewer_cannot_execute_pipeline(self):
        assert has_action("admin_viewer", "pipeline:execute") is False

    # ── GP — conduz projeto, aprova, NÃO escreve código ──────────────

    def test_gp_has_expected_actions(self):
        expected = {
            "project:view", "project:edit", "project:manage_team",
            "pipeline:review", "qa:approve", "backlog:manage",
            "audit:view", "audit:export", "docs:edit",
        }
        actions = get_actions_for_role("gp")
        assert actions == expected

    def test_gp_cannot_manage_gp(self):
        assert has_action("gp", "project:manage_gp") is False

    def test_gp_cannot_write_code(self):
        # Contrato §4.1: GP não escreve código.
        assert has_action("gp", "code:write") is False
        assert has_action("gp", "code:review") is False
        assert has_action("gp", "pipeline:execute") is False
        assert has_action("gp", "git:commit") is False

    # ── Dev — implementa código, NÃO aprova módulo ───────────────────

    def test_dev_can_write_code(self):
        assert has_action("dev", "code:write") is True
        assert has_action("dev", "code:review") is True

    def test_dev_can_commit(self):
        assert has_action("dev", "git:commit") is True

    def test_dev_can_execute_pipeline(self):
        assert has_action("dev", "pipeline:execute") is True

    def test_dev_cannot_approve_module(self):
        # Contrato §4.1: Dev não aprova módulo no Gatekeeper.
        assert has_action("dev", "qa:approve") is False

    def test_dev_cannot_manage_team(self):
        assert has_action("dev", "project:manage_team") is False

    # ── Tester — cria/edita/executa testes, registra evidências ──────

    def test_tester_has_view_and_pipeline(self):
        assert has_action("tester", "project:view") is True
        assert has_action("tester", "pipeline:execute") is True

    def test_tester_can_export_audit(self):
        assert has_action("tester", "audit:export") is True

    def test_tester_cannot_approve(self):
        assert has_action("tester", "qa:approve") is False

    def test_tester_cannot_write_code(self):
        assert has_action("tester", "code:write") is False

    # ── QA — revisa/aprova, NÃO edita teste ──────────────────────────

    def test_qa_has_approve(self):
        assert has_action("qa", "qa:approve") is True

    def test_qa_has_security_and_compliance(self):
        assert has_action("qa", "security:review") is True
        assert has_action("qa", "compliance:validate") is True

    def test_qa_cannot_write_code(self):
        assert has_action("qa", "code:write") is False

    def test_qa_cannot_execute_pipeline(self):
        # Contrato §4.1: QA revisa, não executa.
        assert has_action("qa", "pipeline:execute") is False

    # ── Papéis históricos NÃO existem mais ───────────────────────────

    def test_historical_roles_removed(self):
        for legacy in ("tech_lead", "dev_senior", "dev_pleno", "compliance", "stakeholder", "viewer"):
            assert legacy not in ROLE_ACTIONS, f"papel histórico {legacy} ainda presente"

    # ── Fallbacks ────────────────────────────────────────────────────

    def test_unknown_role_returns_empty(self):
        assert get_actions_for_role("nonexistent") == set()

    def test_has_action_unknown_role(self):
        assert has_action("nonexistent", "project:view") is False

    # ── Apenas 5 canônicos + admin_viewer ────────────────────────────

    def test_exactly_five_canonical_roles_plus_admin_viewer(self):
        expected_keys = {"admin_viewer", "gp", "dev", "tester", "qa"}
        assert set(ROLE_ACTIONS.keys()) == expected_keys
