"""
Mapeamento de papeis para acoes no sistema GCA.

Cada papel tem um conjunto de acoes permitidas.
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
        "pipeline:execute",
        "pipeline:review",
        "docs:edit",
    },
    "tech_lead": {
        "project:view",
        "pipeline:execute",
        "pipeline:review",
        "code:write",
        "docs:edit",
    },
    "dev_senior": {
        "project:view",
        "pipeline:execute",
        "code:write",
    },
    "dev_pleno": {
        "project:view",
        "code:write",
    },
    "qa": {
        "project:view",
        "pipeline:review",
    },
    "compliance": {
        "project:view",
    },
    "stakeholder": {
        "project:view",
    },
}


def get_actions_for_role(role: str) -> set[str]:
    return ROLE_ACTIONS.get(role, set())


def has_action(role: str, action: str) -> bool:
    return action in get_actions_for_role(role)
