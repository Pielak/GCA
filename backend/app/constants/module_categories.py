"""MVP 9 Fase 9.1 — Categorias canônicas de módulos do Roadmap.

Fonte soberana: `GCA_CANONICAL_CONTRACT.md §7 MVP 9`.

Antes do MVP 9 o Arguidor só gerava `module_type='feature'` — o Roadmap
virava um catálogo de funcionalidades de negócio, sem backend,
middleware, infra ou deploy. Não servia como plano de construção.

As 6 categorias abaixo cobrem todas as camadas que alimentam o CodeGen
(MVP 3). Nomes em inglês pra match direto com convenções técnicas e
com o que o LLM costuma gerar em prompts técnicos; labels pt-BR
ficam na UI.

Mudar esta lista requer emenda no contrato — é contrato público entre
Arguidor, Roadmap, CodeGen e UI.
"""
from __future__ import annotations


#: Categorias canônicas. Ordem define ordem padrão de construção
#: (infra primeiro, feature por último, deploy fechando).
CANONICAL_MODULE_TYPES: tuple[str, ...] = (
    "infrastructure",
    "observability",
    "middleware",
    "backend_service",
    "feature",
    "deploy_pipeline",
)

#: Valor default quando o LLM não classifica. Mantido por retrocompat —
#: docs pré-MVP9 tinham só `feature`/`component`.
DEFAULT_MODULE_TYPE = "feature"

#: Valores aceitos como sinônimos durante a migração. O Arguidor antigo
#: emitia `component`; o validador redireciona pra `feature`.
LEGACY_MODULE_TYPE_ALIASES = {
    "component": "feature",
}

#: Ordem de deploy/construção sugerida. Usada pela Fase 9.4.
DEPLOY_ORDER: dict[str, int] = {
    "infrastructure": 0,
    "observability": 1,
    "middleware": 2,
    "backend_service": 3,
    "feature": 4,
    "deploy_pipeline": 5,
}

#: Labels humanos por categoria (pt-BR). Frontend consome do próprio
#: arquivo pra manter backend+frontend sincronizados sem duplicar.
CATEGORY_LABELS_PT_BR: dict[str, str] = {
    "infrastructure": "Infraestrutura",
    "observability": "Observabilidade",
    "middleware": "Middleware",
    "backend_service": "Serviço de Backend",
    "feature": "Funcionalidade",
    "deploy_pipeline": "Pipeline de Deploy",
}


def normalize_module_type(value: str | None) -> str:
    """Normaliza qualquer valor recebido do LLM/usuário pra uma
    categoria canônica. Valores desconhecidos caem em `DEFAULT_MODULE_TYPE`
    (com log no caller, se precisar)."""
    if not value:
        return DEFAULT_MODULE_TYPE
    v = value.strip().lower()
    if v in CANONICAL_MODULE_TYPES:
        return v
    if v in LEGACY_MODULE_TYPE_ALIASES:
        return LEGACY_MODULE_TYPE_ALIASES[v]
    return DEFAULT_MODULE_TYPE


def is_canonical(value: str) -> bool:
    """True se o valor já é uma categoria canônica."""
    return value in CANONICAL_MODULE_TYPES


# ============================================================================
# MVP 9 Fase 9.1.2 — Status canônicos em pt-BR
# ============================================================================

#: Status canônicos do ciclo de vida de um módulo no Roadmap.
#: Transições permitidas (regra dura do contrato §7 MVP 9):
#:   sugerido → aguardando_resposta → adicionado → concluido
#:   adicionado → sugerido  (somente se GP reabrir explicitamente)
#:   concluido não regride.
CANONICAL_MODULE_STATUSES: tuple[str, ...] = (
    "sugerido",
    "aguardando_resposta",
    "adicionado",
    "concluido",
)

DEFAULT_MODULE_STATUS = "sugerido"

#: Aliases legados (schema livre pré-MVP9 tinha valores em inglês).
#: Normalização sem migration destrutiva — docs antigas continuam legíveis.
LEGACY_MODULE_STATUS_ALIASES: dict[str, str] = {
    "suggested": "sugerido",
    "candidate": "sugerido",
    "pending": "sugerido",
    "approved": "adicionado",
    "ready": "adicionado",
    "added": "adicionado",
    "completed": "concluido",
    "done": "concluido",
    # Legacy ingles da Fase 9.3 planejada — mantidos como aliases pra
    # quando o contrato avançar (needs_input mapeia a aguardando_resposta).
    "needs_input": "aguardando_resposta",
    "partial": "aguardando_resposta",
    "ready_for_codegen": "adicionado",
    # Status obsoletos (generating/in_progress/failed) não têm canônico
    # direto — preservam o valor original pra UI tratar caso-a-caso.
}

#: Labels pt-BR por status canônico. Frontend consome daqui.
STATUS_LABELS_PT_BR: dict[str, str] = {
    "sugerido": "Sugerido",
    "aguardando_resposta": "Aguardando resposta",
    "adicionado": "Adicionado",
    "concluido": "Concluído",
}


def normalize_module_status(value: str | None) -> str:
    """Normaliza qualquer valor de status pra forma canônica pt-BR.

    Valores já canônicos passam direto. Aliases legados (en-US) são
    traduzidos. Valores desconhecidos mantém-se como vieram (ex:
    `generating`/`in_progress`/`failed` do CodeGen pipeline) — o caller
    decide se trata ou normaliza pra `sugerido`.
    """
    if not value:
        return DEFAULT_MODULE_STATUS
    v = value.strip().lower()
    if not v:  # string só com espaços
        return DEFAULT_MODULE_STATUS
    if v in CANONICAL_MODULE_STATUSES:
        return v
    if v in LEGACY_MODULE_STATUS_ALIASES:
        return LEGACY_MODULE_STATUS_ALIASES[v]
    return v  # preserva valor não-canônico pra UI tratar (ex: 'failed')


def is_canonical_status(value: str) -> bool:
    """True se o valor é status canônico do ciclo de vida (pt-BR)."""
    return value in CANONICAL_MODULE_STATUSES


#: Transições permitidas — regra dura no contrato.
#: Falso não-transições: `sugerido` → `adicionado` direto (tem que passar
#: por `aguardando_resposta`), `concluido` → qualquer coisa.
ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "sugerido": frozenset({"aguardando_resposta", "adicionado"}),
    "aguardando_resposta": frozenset({"sugerido", "adicionado"}),
    "adicionado": frozenset({"sugerido", "concluido"}),  # sugerido só se GP reabrir
    "concluido": frozenset(),  # terminal
}


def is_allowed_transition(current: str, target: str) -> bool:
    """Valida transição de status conforme regra dura do contrato §7 MVP 9.

    Retorna True pra no-op (mesmo status) e quando a transição é permitida.
    False bloqueia: service levanta erro no caller.
    """
    if current == target:
        return True
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())
    return target in allowed
