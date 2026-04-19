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
