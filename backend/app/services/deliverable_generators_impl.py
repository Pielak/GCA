"""Implementações concretas dos auto-generators (C.2 + C.3 + C.4).

Cada generator é decorado com @register_generator e produz um artefato
markdown/mermaid/etc. a partir de campos do OCG. Determinístico (sem LLM)
para começar — mantém o pipeline rápido e auditável.

Convenção de paths gerados:
    docs/compliance.md           (compliance_doc)
    docs/architecture.mmd        (architecture_diagram)
    docs/adr/000N-<slug>.md      (adr — 1 por CRITICAL_FINDING)

Idempotência: cada generator inclui um header gerado com ``<!-- gca:auto -->``.
Caller pode escolher sobrescrever ou pular se header não bate (TODO Fase D).
Por enquanto sobrescreve — consciente trade-off para iteração rápida no
dogfood.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deliverable_generators import (
    GeneratorResult,
    _commit_via_git,
    register_generator,
)


def _slugify(text: str, max_len: int = 60) -> str:
    """Slug ASCII para nomes de arquivo (ADR)."""
    s = unicodedata.normalize("NFD", text or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).lower().strip()
    s = re.sub(r"\s+", "-", s)
    return (s or "sem-titulo")[:max_len].rstrip("-")


# ────────────────────── compliance_doc ────────────────────────────────

@register_generator("compliance_doc")
@register_generator("compliance_checklist")
async def _gen_compliance_doc(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/compliance.md`` com tabela de items do OCG.COMPLIANCE_CHECKLIST."""
    items = ocg_data.get("COMPLIANCE_CHECKLIST", []) or []
    if not isinstance(items, list) or not items:
        return GeneratorResult(
            kind="compliance_doc",
            committed=False,
            skipped_reason="OCG.COMPLIANCE_CHECKLIST vazio",
        )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")

    lines: List[str] = [
        "<!-- gca:auto generator=compliance_doc -->",
        f"# Checklist de Compliance — {project_name}",
        "",
        f"_Gerado automaticamente em {now_iso} a partir de OCG.COMPLIANCE_CHECKLIST._",
        "",
        f"**Total**: {len(items)} item(s) — "
        f"**resolvidos**: {sum(1 for i in items if str(i.get('status', '')).upper() != 'PENDENTE')} | "
        f"**pendentes**: {sum(1 for i in items if str(i.get('status', '')).upper() == 'PENDENTE')}",
        "",
        "| # | Item | Status | Responsável |",
        "|---|------|--------|-------------|",
    ]
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        text = (item.get("item") or "").replace("|", "\\|")
        status = (item.get("status") or "PENDENTE").upper()
        owner = (item.get("owner") or "—").replace("|", "\\|")
        status_badge = "✅" if status != "PENDENTE" else "⏳"
        lines.append(f"| {idx} | {text} | {status_badge} {status} | {owner} |")

    content = "\n".join(lines) + "\n"
    path = "docs/compliance.md"

    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"docs(compliance): regenerar checklist ({len(items)} items) [gca:auto]",
    )
    if not ok:
        return GeneratorResult(
            kind="compliance_doc",
            committed=False,
            skipped_reason="commit Git falhou (ver logs)",
        )
    return GeneratorResult(
        kind="compliance_doc",
        committed=True,
        path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"{len(items)} items processados",
    )


# ────────────────────── adr ────────────────────────────────────────────

@register_generator("adr")
async def _gen_adr(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/adr/0001-*.md`` para cada CRITICAL_FINDING + 1 ADR de stack.

    Formato MADR (Markdown Architecture Decision Records) simplificado.
    Cada finding crítico vira um ADR — facilita rastreabilidade decisão→risco.
    """
    findings_raw = ocg_data.get("CRITICAL_FINDINGS")
    # CRITICAL_FINDINGS pode ser dict ou list (varia entre versões do OCG)
    findings: List[Dict[str, Any]] = []
    if isinstance(findings_raw, list):
        findings = [f for f in findings_raw if isinstance(f, dict)]
    elif isinstance(findings_raw, dict):
        findings = [findings_raw]

    stack = ocg_data.get("STACK_RECOMMENDATION", {}) or {}
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not findings and not stack:
        return GeneratorResult(
            kind="adr",
            committed=False,
            skipped_reason="OCG sem CRITICAL_FINDINGS nem STACK_RECOMMENDATION",
        )

    written = 0
    total_bytes = 0

    # ADR 0001: Stack Decision (se há stack)
    if stack:
        slug = "stack-recommendation"
        path = f"docs/adr/0001-{slug}.md"
        backend = stack.get("backend", {})
        frontend = stack.get("frontend", {})
        database = stack.get("database", {})
        content = (
            f"<!-- gca:auto generator=adr -->\n"
            f"# 0001. Stack tecnológica recomendada\n\n"
            f"- **Status:** Aceito\n"
            f"- **Data:** {now_iso}\n"
            f"- **Projeto:** {project_name}\n\n"
            f"## Contexto\n\n"
            f"O OCG do projeto definiu a stack inicial baseada em pilares "
            f"avaliados via Arguidor. Esta decisão consolida as escolhas para "
            f"frontend, backend e persistência.\n\n"
            f"## Decisão\n\n"
            f"- **Backend**: {backend.get('framework', '?')} "
            f"({backend.get('language', '?')})\n"
            f"- **Frontend**: {frontend.get('framework', '?')} "
            f"({frontend.get('language', '?')})\n"
            f"- **Database**: {database.get('primary', '?')}\n\n"
            f"## Justificativas (do OCG.STACK_RECOMMENDATION)\n\n"
            f"- Backend: {backend.get('rationale', 'N/A')}\n"
            f"- Frontend: {frontend.get('rationale', 'N/A')}\n"
            f"- Database: {database.get('rationale', 'N/A')}\n\n"
            f"## Consequências\n\n"
            f"Mudanças nesta stack devem ser registradas como novos ADRs "
            f"superseding este, com trigger no OCG.\n"
        )
        if await _commit_via_git(
            project_id, db, path, content,
            commit_message="docs(adr): 0001 stack recommendation [gca:auto]",
        ):
            written += 1
            total_bytes += len(content.encode("utf-8"))

    # ADRs 0002+: 1 por CRITICAL_FINDING
    for idx, finding in enumerate(findings, start=2):
        title = finding.get("finding", "")[:80] or f"Finding crítico {idx}"
        slug = _slugify(title, max_len=50)
        path = f"docs/adr/{idx:04d}-{slug}.md"
        severity = (finding.get("severity") or "?").upper()
        pillar = finding.get("pillar") or "?"
        recommendation = finding.get("recommendation") or "(sem recomendação)"

        content = (
            f"<!-- gca:auto generator=adr -->\n"
            f"# {idx:04d}. {title}\n\n"
            f"- **Status:** Proposto\n"
            f"- **Data:** {now_iso}\n"
            f"- **Pilar afetado:** {pillar}\n"
            f"- **Severidade:** {severity}\n\n"
            f"## Contexto\n\n"
            f"Finding crítico identificado pelo Arguidor durante análise do projeto:\n\n"
            f"> {finding.get('finding', 'N/A')}\n\n"
            f"## Decisão\n\n"
            f"{recommendation}\n\n"
            f"## Consequências\n\n"
            f"O Gatekeeper bloqueará progressão para CodeGen enquanto este "
            f"finding estiver `PENDENTE`. Marcar como resolvido apenas após "
            f"implementação verificável (e atualizar este ADR para `Aceito`).\n"
        )
        if await _commit_via_git(
            project_id, db, path, content,
            commit_message=f"docs(adr): {idx:04d} {slug} [gca:auto]",
        ):
            written += 1
            total_bytes += len(content.encode("utf-8"))

    if written == 0:
        return GeneratorResult(
            kind="adr",
            committed=False,
            skipped_reason="todos commits Git falharam",
        )
    return GeneratorResult(
        kind="adr",
        committed=True,
        path=f"docs/adr/ ({written} arquivos)",
        bytes_written=total_bytes,
        notes=f"{written} ADRs gerados (1 stack + {written-1 if stack else written} findings)",
    )


# ────────────────────── architecture_diagram (mermaid C4) ──────────────

@register_generator("architecture_diagram")
async def _gen_architecture_diagram(
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Gera ``docs/architecture.mmd`` (mermaid) representando key_components do OCG."""
    arch = ocg_data.get("ARCHITECTURE_OVERVIEW", {}) or {}
    components: List[Any] = arch.get("key_components", []) or []
    style = arch.get("style", "(estilo não definido)")
    project_name = ocg_data.get("PROJECT_PROFILE", {}).get("project_name", "(projeto)")

    if not components:
        return GeneratorResult(
            kind="architecture_diagram",
            committed=False,
            skipped_reason="OCG.ARCHITECTURE_OVERVIEW.key_components vazio",
        )

    # Cada componente vira um node mermaid; conexões deduzidas via heurística
    # simples (frontend → backend → database). É melhor que nada — Fase C+
    # pode evoluir para LLM-augmented.
    nodes: List[str] = []
    edges: List[str] = []
    for idx, comp in enumerate(components, start=1):
        if not isinstance(comp, str):
            continue
        comp_clean = comp.replace('"', "'")[:80]
        node_id = f"C{idx}"
        # Heurística de classificação simples
        c_lower = comp.lower()
        if any(k in c_lower for k in ("frontend", "react", "vue", "spa", "ui")):
            shape = f'{node_id}["🖥️ {comp_clean}"]'
        elif any(k in c_lower for k in ("backend", "api", "fastapi", "service")):
            shape = f'{node_id}["⚙️ {comp_clean}"]'
        elif any(k in c_lower for k in ("postgres", "mysql", "database", "db", "redis")):
            shape = f'{node_id}[("🗄️ {comp_clean}")]'
        elif any(k in c_lower for k in ("kafka", "rabbitmq", "broker", "queue")):
            shape = f'{node_id}{{"📨 {comp_clean}"}}'
        else:
            shape = f'{node_id}["{comp_clean}"]'
        nodes.append(f"    {shape}")

    # Edges heurísticos: conecta nodes em sequência
    for i in range(1, len(nodes)):
        edges.append(f"    C{i} --> C{i+1}")

    diagram = (
        "%%{ init: { 'theme': 'dark' } }%%\n"
        "graph LR\n"
        f"    %% Auto-gerado pelo GCA — não editar manualmente.\n"
        f"    %% Style: {style}\n"
        + "\n".join(nodes)
        + "\n"
        + "\n".join(edges)
        + "\n"
    )
    header = f"<!-- gca:auto generator=architecture_diagram project={project_name} -->\n"
    content = header + diagram
    path = "docs/architecture.mmd"

    ok = await _commit_via_git(
        project_id, db, path, content,
        commit_message=f"docs(architecture): mermaid C4 ({len(nodes)} components) [gca:auto]",
    )
    if not ok:
        return GeneratorResult(
            kind="architecture_diagram",
            committed=False,
            skipped_reason="commit Git falhou",
        )
    return GeneratorResult(
        kind="architecture_diagram",
        committed=True,
        path=path,
        bytes_written=len(content.encode("utf-8")),
        notes=f"{len(nodes)} components no diagrama",
    )
