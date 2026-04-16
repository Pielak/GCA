"""Classifica strings de OCG.DELIVERABLES em (kind, category) conhecidos.

OCG.DELIVERABLES é uma lista de strings em PT-BR (ou EN). Este módulo
mapeia cada string para uma estrutura ``(kind, category)`` rastreável e
verificável. Exemplos:

    "Documento de Caso de Negócio e ROI"           → (business_case, doc)
    "Repositório de Código Fonte com Pipeline CI/CD" → (ci_pipeline, code)
    "SBOM (Software Bill of Materials) inicial"    → (sbom, code)
    "Política de Compliance LGPD"                   → (compliance_doc, process)
    "qualquer coisa não reconhecida"                → (other_manual, other)

Quem não casa nenhum padrão vira ``other_manual`` — só pode ser atestado
manualmente pelo GP. Sem regex match agressivo: padrões são conservadores.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Tuple


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_name(name: str) -> str:
    """Lowercase, sem acentos, espaços colapsados — base para dedup + match."""
    if not name:
        return ""
    s = _strip_accents(name).lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


# Padrões em ORDEM (primeiro match ganha). Cada entrada:
#   (regex, kind, category)
# Regex aplicado sobre nome NORMALIZADO (lowercase, sem acentos).
_PATTERNS: list[Tuple[str, str, str]] = [
    # ── Code / Infra ─────────────────────────────────────────────────
    # Match parcial em "containerizado", "containerização", etc. — sem \b à direita
    (r"\b(dockerfile\b|container|imagem docker\b)", "dockerfile", "code"),
    (r"\b(ci/?cd|pipeline.*(ci|cd|deploy)|github actions|gitlab ci|jenkins)\b", "ci_pipeline", "code"),
    (r"\b(sbom|software bill of materials|bill of material)\b", "sbom", "code"),
    (r"\b(pyproject|package\.json|manifest.*depend|gestao.*depend|dependenc.*manifest)\b", "manifests", "code"),
    (r"\b(repositorio.*codig|source.*code|code.*repository)\b", "code_repository", "code"),
    (r"\b(ddl|migrations|schema.*banco|database design|projeto.*banco.*dados)\b", "database_design", "code"),

    # ── API / Docs técnicos ─────────────────────────────────────────
    (r"\b(openapi|swagger|api.*spec|documenta.*api)\b", "openapi", "doc"),
    (r"\b(adr|architecture decision|decis.*arquitetura)\b", "adr", "doc"),
    (r"\b(diagrama.*arquitet|architecture.*diagram|c4|context map|component diagram)\b", "architecture_diagram", "doc"),
    (r"\b(documento.*arquitetura|architecture.*doc|solution.*design)\b", "architecture_doc", "doc"),

    # ── Negócio / processo ──────────────────────────────────────────
    (r"\b(caso de negocio|business case|roi)\b", "business_case", "doc"),
    (r"\b(justificativa|justification record)\b", "justification_record", "process"),
    (r"\b(politica.*depend|supply chain|cadeia de suprim)\b", "dependency_policy", "process"),

    # ── Compliance ──────────────────────────────────────────────────
    (r"\b(politica.*compliance|lgpd|gdpr|aipd|hipaa|pci.?dss)\b", "compliance_doc", "process"),
    (r"\b(checklist.*compliance|compliance.*checklist)\b", "compliance_checklist", "process"),
    (r"\b(politica.*backup|retencao.*dados|retention policy)\b", "data_retention_policy", "process"),

    # ── Testes ──────────────────────────────────────────────────────
    # Match em "Plano de Testes", "Plano de Teste" — sem \b à direita pra cobrir plural
    (r"\b(plano.*teste|test plan|estrategia.*teste|testing strategy)", "test_plan", "test"),
    (r"\b(teste.*unit|unit test|teste.*integra|integration test|\be2e\b|end.to.end|performance test|load test)", "test_implementation", "test"),

    # ── Backlog / planejamento ──────────────────────────────────────
    (r"\b(backlog priorizado|mvp.*backlog|especifica.*mvp)\b", "backlog", "process"),
    (r"\b(roadmap|cronograma)\b", "roadmap", "process"),

    # ── Observability ────────────────────────────────────────────────
    (r"\b(dashboard.*observ|grafana|prometheus|monitoring dashboard)\b", "observability_dashboard", "code"),
    (r"\b(logs estruturados|log.*aggreg|elk|loki)\b", "logging_setup", "code"),

    # ── Ambiente ────────────────────────────────────────────────────
    (r"\b(ambiente.*desenvolv|dev environment|environment setup)\b", "dev_environment", "code"),

    # ── Manuais ──────────────────────────────────────────────────────
    (r"\b(manual.*usuario|user manual|guia.*operac|runbook|playbook)\b", "user_manual", "doc"),
]


def classify_deliverable(name: str) -> Tuple[str, str]:
    """Retorna ``(kind, category)`` para um item de OCG.DELIVERABLES.

    Sem match → ``("other_manual", "other")`` — entregável só pode ser
    atestado manualmente pelo GP.
    """
    if not name or not isinstance(name, str):
        return "other_manual", "other"

    normalized = normalize_name(name)
    for pattern, kind, category in _PATTERNS:
        if re.search(pattern, normalized):
            return kind, category
    return "other_manual", "other"


def is_auto_verifiable(kind: str) -> bool:
    """True se o kind tem verifier determinístico (não requer atestação manual)."""
    return kind != "other_manual" and kind != "business_case"
