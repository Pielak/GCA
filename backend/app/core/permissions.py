"""
Mapeamento de papéis canônicos para ações no sistema GCA.

Fonte soberana: GCA_CANONICAL_CONTRACT.md §4.
Papéis canônicos nesta versão: Admin, GP, Dev, Tester, QA.
`admin_viewer` é papel virtual atribuído a Admin sem membership no projeto
(Admin não atua operacionalmente em projetos — §4.1).

Papéis históricos (Tech Lead, Compliance, Stakeholder, Viewer, Dev Sênior/Pleno
como roles distintas) foram removidos do RBAC conforme contrato §4.2 — podem
continuar existindo como atores narrativos em docs ou responsabilidades de
negócio não modeladas no RBAC.
"""

ROLE_ACTIONS: dict[str, set[str]] = {
    "admin_viewer": {
        # Admin sem membership: só vê projeto e gerencia GP. Não atua dentro.
        "project:view",
        "project:manage_gp",
    },
    "gp": {
        # GP conduz projeto, aprova módulos/OCG, convida time. NÃO escreve código.
        "project:view",
        "project:edit",
        "project:manage_team",
        "pipeline:review",
        "qa:approve",
        "backlog:manage",
        "audit:view",
        "audit:export",
        "docs:edit",
    },
    "dev": {
        # Dev implementa código, opera ingestão/Arguidor/CodeGen e commits.
        # NÃO aprova módulo no Gatekeeper.
        "project:view",
        "code:write",
        "code:review",
        "pipeline:execute",
        "git:commit",
        "audit:view",
        "docs:edit",
    },
    "tester": {
        # Tester cria/edita/executa testes. Registra e exporta evidências.
        "project:view",
        "pipeline:execute",
        "audit:view",
        "audit:export",
    },
    "qa": {
        # QA revisa/aprova resultados e execuções. Valida qualidade final,
        # segurança e compliance. NÃO edita conteúdo de teste.
        "project:view",
        "qa:approve",
        "security:review",
        "compliance:validate",
        "audit:view",
    },
}


def get_actions_for_role(role: str) -> set[str]:
    """Retorna o conjunto de ações permitidas para um papel."""
    return ROLE_ACTIONS.get(role, set())


def has_action(role: str, action: str) -> bool:
    """Verifica se um papel tem uma ação específica."""
    return action in get_actions_for_role(role)


def get_actions_for_roles(roles: list[str]) -> set[str]:
    """União de ações de todos os papéis."""
    actions = set()
    for role in roles:
        actions |= get_actions_for_role(role)
    return actions


def has_action_any(roles: list[str], action: str) -> bool:
    """Verifica se qualquer um dos papéis tem a ação."""
    return action in get_actions_for_roles(roles)
