"""Registro canônico de system prompts das 12 personas LLM (Conjunto B).

Fonte única consultada por:
- IngestionService._dispatch_to_n8n: injeta `persona_prompts` no payload inicial
  do pipeline n8n para que o Conferente despache cada especialista com o prompt
  específico da sua tag (não fallback genérico "Você é um especialista.").
- Demais consumidores que precisem do prompt canônico de uma persona por tag.

Tags canônicas (CLAUDE.md §0.5 — Conjunto B): AUD, GP, ARQ, DBA, DEV, QA, UX,
UI, SEG, CONF, LGPD, NEG.

Não confundir com Conjunto A (5 papéis humanos do RBAC: Admin, GP, Dev, Tester,
QA). Aqui só Conjunto B.
"""
from app.services.personas.auditor import AUDITOR_SYSTEM_PROMPT
from app.services.personas.gp import GP_SYSTEM_PROMPT
from app.services.personas.arq import ARQ_SYSTEM_PROMPT
from app.services.personas.dba import DBA_SYSTEM_PROMPT
from app.services.personas.dev import DEV_SYSTEM_PROMPT
from app.services.personas.qa import QA_SYSTEM_PROMPT
from app.services.personas.ux import UX_SYSTEM_PROMPT
from app.services.personas.ui import UI_SYSTEM_PROMPT
from app.services.personas.seg import SEG_SYSTEM_PROMPT
from app.services.personas.conf import CONF_SYSTEM_PROMPT
from app.services.personas.lgpd import LGPD_SYSTEM_PROMPT
from app.services.personas.negocios import NEG_SYSTEM_PROMPT


PERSONA_PROMPTS: dict[str, str] = {
    "AUD": AUDITOR_SYSTEM_PROMPT,
    "GP": GP_SYSTEM_PROMPT,
    "ARQ": ARQ_SYSTEM_PROMPT,
    "DBA": DBA_SYSTEM_PROMPT,
    "DEV": DEV_SYSTEM_PROMPT,
    "QA": QA_SYSTEM_PROMPT,
    "UX": UX_SYSTEM_PROMPT,
    "UI": UI_SYSTEM_PROMPT,
    "SEG": SEG_SYSTEM_PROMPT,
    "CONF": CONF_SYSTEM_PROMPT,
    "LGPD": LGPD_SYSTEM_PROMPT,
    "NEG": NEG_SYSTEM_PROMPT,
}


CANONICAL_TAGS: frozenset[str] = frozenset(PERSONA_PROMPTS.keys())


def get_persona_prompt(tag: str) -> str:
    """Retorna o system prompt canônico para a tag informada.

    Levanta KeyError se a tag não pertencer ao Conjunto B canônico — é proibido
    fallback genérico silencioso (CLAUDE.md §0). O caller deve tratar a tag
    desconhecida explicitamente (rejeitar, logar erro, etc).
    """
    if tag not in PERSONA_PROMPTS:
        raise KeyError(
            f"Tag '{tag}' não pertence ao Conjunto B canônico. "
            f"Tags válidas: {sorted(CANONICAL_TAGS)}"
        )
    return PERSONA_PROMPTS[tag]
