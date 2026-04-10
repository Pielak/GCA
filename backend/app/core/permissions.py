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
