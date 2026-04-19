"""Emenda RBAC 2026-04-19: GP é soberano do projeto.

Garante que GP tem UNION das actions de Dev + Tester + QA + suas próprias.
Se alguma action de outro papel do projeto NÃO estiver no set do GP, o
teste quebra — força consistência com o contrato §4.1 emendado.
"""
from app.core.permissions import ROLE_ACTIONS, get_actions_for_role, has_action


def test_gp_has_all_dev_actions():
    dev_actions = ROLE_ACTIONS["dev"]
    gp_actions = ROLE_ACTIONS["gp"]
    missing = dev_actions - gp_actions
    assert not missing, f"GP não cobre actions de Dev: {missing}"


def test_gp_has_all_tester_actions():
    tester_actions = ROLE_ACTIONS["tester"]
    gp_actions = ROLE_ACTIONS["gp"]
    missing = tester_actions - gp_actions
    assert not missing, f"GP não cobre actions de Tester: {missing}"


def test_gp_has_all_qa_actions():
    qa_actions = ROLE_ACTIONS["qa"]
    gp_actions = ROLE_ACTIONS["gp"]
    missing = qa_actions - gp_actions
    assert not missing, f"GP não cobre actions de QA: {missing}"


def test_gp_has_code_write_after_emenda():
    """Restrição 'GP não escreve código' revogada pela emenda 2026-04-19."""
    assert has_action("gp", "code:write")
    assert has_action("gp", "code:review")
    assert has_action("gp", "git:commit")


def test_gp_has_pipeline_execute_after_emenda():
    assert has_action("gp", "pipeline:execute")


def test_gp_has_security_and_compliance_after_emenda():
    assert has_action("gp", "security:review")
    assert has_action("gp", "compliance:validate")


def test_dev_still_limited():
    """Dev continua com escopo restrito — não ganha powers de GP."""
    dev = ROLE_ACTIONS["dev"]
    assert "backlog:manage" not in dev
    assert "project:manage_team" not in dev
    assert "project:edit" not in dev


def test_tester_still_limited():
    tester = ROLE_ACTIONS["tester"]
    assert "code:write" not in tester
    assert "backlog:manage" not in tester


def test_qa_still_limited():
    qa = ROLE_ACTIONS["qa"]
    assert "code:write" not in qa
    assert "pipeline:execute" not in qa  # QA revisa, não executa pipeline


def test_admin_viewer_stays_minimal():
    """Admin continua não atuando operacionalmente em projetos."""
    av = ROLE_ACTIONS["admin_viewer"]
    assert av == {"project:view", "project:manage_gp"}


def test_get_actions_for_role_returns_gp_union():
    gp = get_actions_for_role("gp")
    # Sanidade — 9 originais + 5 herdadas = 14+ (não conto exato pra não
    # travar em adições futuras)
    assert len(gp) >= 14
    # Spot checks das críticas
    assert "code:write" in gp
    assert "pipeline:execute" in gp
    assert "security:review" in gp
    assert "project:manage_team" in gp
