"""Filtro de tópicos de governança corporativa pro pipeline GCA.

GCA é gerador de aplicações, não controlador de projeto. Em projetos
solo_owner (default), o pipeline (Arguidor/M01/Backlog) suprime gaps
e module_candidates que sejam puramente de governança corporativa
(cronograma absoluto, EAP, RACI, orçamento, KPIs corporativos, status
report, go/no-go formal, definition of done corporativa).

Itens TÉCNICOS continuam passando — RNFs codáveis (latência, cobertura),
schema, integrações, security funcional, etc. A regra é: se o item não
gera código nem documenta o que está sendo construído, ele é governança.

Referência canônica: `feedback_gca_construtor_nao_governanca.md` (memory).
"""
from __future__ import annotations

import re
from typing import Iterable

# Padrões obviamente de governança corporativa.
# Usamos regex case-insensitive com word boundaries pra evitar falso
# positivo em palavras compostas (ex: "kPi" no meio de identificador).
_GOVERNANCE_PATTERNS = [
    # Estrutura de gestão de projeto
    r"\bEAP\b",
    r"\bRACI\b",
    r"\bestrutura anal[íi]tica\b",
    r"\bmatriz de responsabilidade\b",

    # Cronograma absoluto / sprint corporativo
    r"\bcronograma absoluto\b",
    r"\bdatas absolutas\b",
    r"\bsprint plan(ning)?\b",
    r"\bburn[\-\s]?down\b",
    r"\bmilestone burn\b",

    # Orçamento / custo
    r"\borçamento (formal|do projeto|estimado)\b",
    r"\brubrica orçament[áa]ria\b",
    r"\bbudget (tracking|burn|estimado)\b",
    r"\bROI (do projeto|estimado|formal)\b",
    r"\bcusto[\-\s]benef[íi]cio\b",
    r"\bcusto por hora\b",

    # Gates de stakeholder externo
    r"\bgo[\-/\s]?no[\-\s]?go\b",
    r"\bgate de stakeholder\b",
    r"\baprovação formal de stakeholder\b",

    # Status / report corporativo
    r"\bstatus report\b",
    r"\brelat[óo]rio semanal de status\b",
    r"\bdashboard de gerência\b",

    # KPIs corporativos (KPIs funcionais do app NÃO entram aqui)
    r"\bKPI corporativ[oa]\b",
    r"\bKPIs? de neg[óo]cio formal\b",

    # Definition of Done corporativa (DoD técnica fica fora deste filtro)
    r"\bDefinition of Done corporativa\b",
    r"\bDoD corporativa\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _GOVERNANCE_PATTERNS]


def is_governance_topic(text: str | None) -> bool:
    """Heurística conservadora: True se `text` cita explicitamente um
    padrão de governança corporativa.

    Conservador por design — preferimos deixar passar item ambíguo a
    descartar item técnico legítimo. Falso negativo é tolerável (item
    aparece e owner ignora); falso positivo (item técnico filtrado)
    quebra a confiança do pipeline.
    """
    if not text:
        return False
    return any(rx.search(text) for rx in _COMPILED)


def filter_governance_items(
    items: Iterable[dict] | None,
    text_keys: tuple[str, ...] = ("name", "title", "description", "text"),
) -> tuple[list[dict], list[dict]]:
    """Particiona `items` em (mantidos, descartados) pelo filtro de governança.

    Cada item é examinado nos seus `text_keys`. Se qualquer um deles bate
    num padrão de governança, o item vai pra `descartados`.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        haystack = " ".join(
            str(item.get(k, "")) for k in text_keys if item.get(k)
        )
        if is_governance_topic(haystack):
            dropped.append(item)
        else:
            kept.append(item)
    return kept, dropped


SOLO_OWNER_PROMPT_CLAUSE = """

=== MODO DE GOVERNANÇA: SOLO_OWNER ===
Este projeto está em modo **solo_owner** — o owner decide, executa e financia
sozinho, sem stakeholders externos. NÃO gere `gaps`, `module_candidates` nem
`improvement_suggestions` cujo conteúdo seja:

- Cronograma com datas absolutas, EAP, sprint plan, burn-down.
- RACI, matriz de responsabilidade, organograma de papéis.
- Orçamento formal, rubrica orçamentária, custo, ROI.
- Status report, dashboard de gerência, prestação de contas.
- Go/no-go formal, gate aprovativo de stakeholder externo.
- KPIs corporativos (KPIs funcionais do app SIM, métricas de gerência NÃO).
- Definition of Done corporativa (DoD técnica de teste/cobertura SIM).

Itens TÉCNICOS continuam obrigatórios: stack, schema, segurança funcional,
RNFs codáveis (latência, cobertura, bundle size), integrações, padrões de
arquitetura, compliance via código (LGPD por cifragem, audit log, etc).

Documentação técnica do **que está sendo construído** (escopo, módulos,
decisões de stack, APIs) FICA — é entregável do core do GCA. O que sai
é puramente PM corporativo.
"""
