"""MVP 29 Fase 1 — Schema canônico de documento.

Dataclass + constantes usadas pelo `document_canonicalizer.py` pra
representar qualquer documento ingerido de forma uniforme antes de
alimentar o Arguidor/LLM.

Design completo em `docs/design/document_canonical_schema.md`.

Versionamento: qualquer mudança em regex, dicionário, lógica de
classificação ou shape deve bumpar `CANONICAL_VERSION` (invalida
cache em Fase 2).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CANONICAL_VERSION = "v1.0.0"

# Tipos canônicos de documento.
DOCUMENT_TYPES = frozenset({"PDF", "DOCX", "MD", "XLSX", "IMAGE", "QUESTIONNAIRE"})

# Tipos canônicos de seção (estrutura física).
SECTION_TYPES = frozenset({
    "heading", "bullet", "paragraph", "table", "list", "code_block",
})

# Tipos canônicos de semântica (o que a seção representa no projeto).
SEMANTIC_TYPES = frozenset({
    "functional_requirement",
    "non_functional_requirement",
    "business_rule",
    "actor",
    "interface",
    "glossary",
    "risk",
    "assumption",
    "unknown",
})

# Tipos canônicos de entidade extraída.
ENTITY_TYPES = frozenset({
    "actor", "system", "requirement", "date", "integration",
    "rule", "version", "reference",
})


# ------------------------------------------------------------------ #
# Dicionário do projeto — valores conhecidos que viram entidades 1.0 #
# ------------------------------------------------------------------ #

_PROJECT_DICTIONARY: dict[str, list[str]] = {
    "actors": [
        "Administrador", "Admin", "GP", "Gerente de Projeto", "Tech Lead",
        "Dev", "Desenvolvedor", "Dev Sr", "Dev Pl", "Tester", "QA",
        "Compliance", "Auditor", "Stakeholder", "Usuário Final", "Usuário",
    ],
    "systems": [
        "DataJud", "PostgreSQL", "Redis", "Celery", "FastAPI", "React",
        "Tauri", "SQLCipher", "Ollama", "Anthropic", "OpenAI", "DeepSeek",
        "Grok", "Docker", "n8n", "Prometheus", "Flower", "Cloudflare",
        "Nginx", "Kubernetes", "Traefik", "Vault", "S3",
    ],
    "integrations": [
        "OAuth", "OIDC", "SAML", "LGPD", "GDPR", "SLA", "API REST",
        "Webhook", "SSO", "MFA", "JWT", "HTTPS", "TLS",
    ],
}


def get_project_dictionary() -> dict[str, list[str]]:
    """Cópia imutável do dicionário (pra teste/inspeção)."""
    return {k: list(v) for k, v in _PROJECT_DICTIONARY.items()}


# ------------------------------------------------------------------ #
# Keyword maps pra classificação semântica                           #
# ------------------------------------------------------------------ #

# Mapa canônico (semantic_type → lista de keywords/frases que sinalizam).
# Primeiro match vence, ordem importa: mais específicos antes.
SEMANTIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("non_functional_requirement", [
        "latência", "tempo de resposta", "performance", "sla",
        "disponibilidade", "uptime", "escalabilidade", "carga",
        "throughput", "criptografia", "segurança de transporte",
        "observabilidade", "monitoramento", "alta disponibilidade",
    ]),
    ("business_rule", [
        "regra:", "condição:", "quando ", " então ", "se ",
        "validação", "precondição", "pós-condição",
    ]),
    ("risk", [
        "risco:", "ameaça:", "vulnerabilidade", "mitigação",
    ]),
    ("assumption", [
        "assume-se que", "premissa:", "hipótese:",
    ]),
    ("glossary", [
        "glossário", "definições", "siglas", "acrônimos",
    ]),
    ("interface", [
        "api", "endpoint", "tela de", "componente", "módulo ",
        "expõe", "contrato de", "interface",
    ]),
    ("functional_requirement", [
        "o sistema deve", "a aplicação deve", "o módulo deve",
        "o usuário pode", "permitir que", "funcionalidade",
        "listar", "cadastrar", "consultar", "criar", "atualizar",
        "excluir",
    ]),
    ("actor", [
        "administrador", "gerente de projeto", "tech lead",
        "desenvolvedor", "tester", "qa", "compliance", "auditor",
        "stakeholder", "usuário final",
    ]),
]


# ------------------------------------------------------------------ #
# Dataclasses                                                         #
# ------------------------------------------------------------------ #

@dataclass
class CanonicalEntity:
    entity_type: str
    value: str
    confidence: float = 1.0
    source_section_id: str | None = None

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(
                f"entity_type inválido: {self.entity_type!r}. "
                f"Aceitos: {sorted(ENTITY_TYPES)}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence deve estar em [0,1], recebido {self.confidence}")


@dataclass
class CanonicalSection:
    id: str
    section_type: str
    semantic_type: str
    content: str
    depth: int = 1
    title: str | None = None

    def __post_init__(self) -> None:
        if self.section_type not in SECTION_TYPES:
            raise ValueError(
                f"section_type inválido: {self.section_type!r}. "
                f"Aceitos: {sorted(SECTION_TYPES)}"
            )
        if self.semantic_type not in SEMANTIC_TYPES:
            raise ValueError(
                f"semantic_type inválido: {self.semantic_type!r}. "
                f"Aceitos: {sorted(SEMANTIC_TYPES)}"
            )
        if self.depth < 0:
            raise ValueError(f"depth deve ser >= 0, recebido {self.depth}")


@dataclass
class DocumentCanonical:
    """Representação canônica de um documento ingerido.

    Input principal do Arguidor/LLM após MVP 29. Substitui texto bruto.
    Gerado determinísticamente (zero LLM) por `document_canonicalizer`.
    """
    id: str
    title: str
    document_type: str
    original_filename: str
    sections: list[CanonicalSection] = field(default_factory=list)
    entities: list[CanonicalEntity] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    affected_pillars: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    extractor_version: str = CANONICAL_VERSION
    raw_text_fallback: str | None = None

    def __post_init__(self) -> None:
        if self.document_type not in DOCUMENT_TYPES:
            raise ValueError(
                f"document_type inválido: {self.document_type!r}. "
                f"Aceitos: {sorted(DOCUMENT_TYPES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialização JSON-friendly (pra persistir em coluna text/jsonb)."""
        return asdict(self)

    def stats_summary(self) -> dict[str, int]:
        """Contagens calculadas on-demand pra logs e relatório."""
        return {
            "sections_count": len(self.sections),
            "entities_count": len(self.entities),
            "requirements_count": len(self.requirements),
            "actors_count": len(self.actors),
            "rules_count": len(self.rules),
            "refs_count": len(self.refs),
            "char_count": sum(len(s.content) for s in self.sections),
        }
