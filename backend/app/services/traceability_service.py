"""MVP 19 Fase 19.4 — Matriz de rastreabilidade IEEE 830 §4.

Correlaciona **requisitos** (ModuleCandidate) × **casos de teste** (TestSpec)
× **código gerado** (GeneratedModule + paths no Git) via `module_candidate_id`.

Decisão binária #4 do MVP 19: query sob demanda, sem view materializada.

Zero LLM no caminho crítico — consolidação determinística sobre dados
já persistidos. Read-only.
"""
from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import GeneratedModule, ModuleCandidate, TestSpec


_CATEGORY_PREFIX: dict[str | None, str] = {
    "functional": "RF",
    "non_functional": "RNF",
    "business_rule": "BR",
    None: "REQ",
}


def _requirement_id(category: str | None, index: int) -> str:
    """Gera ID canônico do requisito pela categoria IEEE 830 + índice 1-based."""
    return f"{_CATEGORY_PREFIX.get(category, 'REQ')}-{index:03d}"


async def build_traceability_matrix(db: AsyncSession, project_id: UUID) -> dict:
    """Consolida matriz requisito × test_spec × código gerado.

    Retorna:
        {
            "rows": [
                {
                    "requirement_id": "RF-001",
                    "module_candidate_id": "<uuid>",
                    "name": str,
                    "category": "functional" | "non_functional" | "business_rule" | None,
                    "priority": str,
                    "status": str,
                    "test_specs": [
                        {"id": "<uuid>", "spec_type": str, "status": str}
                    ],
                    "generated_modules": [
                        {
                            "id": "<uuid>",
                            "name": str,
                            "status": str,
                            "git_source_path": str | None,
                            "git_unit_test_path": str | None,
                            "git_integration_test_path": str | None,
                            "git_uat_test_path": str | None,
                            "git_docs_path": str | None,
                            "generated_at": str | None,
                        }
                    ],
                }
            ],
            "summary": {
                "total_requirements": int,
                "by_category": {"functional": int, "non_functional": int,
                                "business_rule": int, "uncategorized": int},
                "with_test_spec": int,
                "with_generated_code": int,
                "fully_traced": int,   # tem spec E código
            },
        }

    Ordem das linhas: categoria (RF → RNF → BR → uncategorized), depois
    `created_at ASC` dentro da categoria. Dentro de cada requisito os arrays
    saem ordenados: test_specs por `spec_type`+`created_at`, generated_modules
    por `generated_at` DESC.
    """
    # 1. Requisitos (todos os ModuleCandidate do projeto).
    mods_result = await db.execute(
        select(ModuleCandidate)
        .where(ModuleCandidate.project_id == project_id)
        .order_by(asc(ModuleCandidate.created_at))
    )
    modules = list(mods_result.scalars().all())

    # 2. Test specs (todos do projeto), agrupados por module_id.
    specs_result = await db.execute(
        select(TestSpec)
        .where(TestSpec.project_id == project_id)
        .order_by(asc(TestSpec.spec_type), asc(TestSpec.created_at))
    )
    specs_by_module: dict[UUID | None, list[TestSpec]] = defaultdict(list)
    for s in specs_result.scalars().all():
        specs_by_module[s.module_id].append(s)

    # 3. Generated modules (todos do projeto), agrupados por module_candidate_id.
    gen_result = await db.execute(
        select(GeneratedModule)
        .where(GeneratedModule.project_id == project_id)
        .order_by(GeneratedModule.generated_at.desc().nulls_last())
    )
    gens_by_candidate: dict[UUID | None, list[GeneratedModule]] = defaultdict(list)
    for g in gen_result.scalars().all():
        gens_by_candidate[g.module_candidate_id].append(g)

    # 4. Particiona módulos por categoria pra respeitar a ordem IEEE 830.
    order_keys = ["functional", "non_functional", "business_rule", None]
    buckets: dict[str | None, list[ModuleCandidate]] = {k: [] for k in order_keys}
    for m in modules:
        key = m.requirement_category if m.requirement_category in buckets else None
        buckets[key].append(m)

    rows: list[dict] = []
    for category in order_keys:
        for idx, mod in enumerate(buckets[category], start=1):
            specs = specs_by_module.get(mod.id, [])
            gens = gens_by_candidate.get(mod.id, [])
            rows.append({
                "requirement_id": _requirement_id(category, idx),
                "module_candidate_id": str(mod.id),
                "name": mod.name,
                "category": category,
                "priority": mod.priority,
                "status": mod.status,
                "test_specs": [
                    {
                        "id": str(s.id),
                        "spec_type": s.spec_type,
                        "status": s.status,
                    }
                    for s in specs
                ],
                "generated_modules": [
                    {
                        "id": str(g.id),
                        "name": g.name,
                        "status": g.status,
                        "git_source_path": g.git_source_path,
                        "git_unit_test_path": g.git_unit_test_path,
                        "git_integration_test_path": g.git_integration_test_path,
                        "git_uat_test_path": g.git_uat_test_path,
                        "git_docs_path": g.git_docs_path,
                        "generated_at": g.generated_at.isoformat() if g.generated_at else None,
                    }
                    for g in gens
                ],
            })

    # 5. Sumário agregado.
    total = len(rows)
    with_spec = sum(1 for r in rows if r["test_specs"])
    with_code = sum(1 for r in rows if r["generated_modules"])
    fully_traced = sum(1 for r in rows if r["test_specs"] and r["generated_modules"])

    by_category = {
        "functional": sum(1 for r in rows if r["category"] == "functional"),
        "non_functional": sum(1 for r in rows if r["category"] == "non_functional"),
        "business_rule": sum(1 for r in rows if r["category"] == "business_rule"),
        "uncategorized": sum(1 for r in rows if r["category"] is None),
    }

    return {
        "rows": rows,
        "summary": {
            "total_requirements": total,
            "by_category": by_category,
            "with_test_spec": with_spec,
            "with_generated_code": with_code,
            "fully_traced": fully_traced,
        },
    }


def render_traceability_markdown(matrix: dict) -> list[str]:
    """Renderiza a matriz em markdown para inclusão na Seção 4 do ERS.

    Retorna lista de linhas (sem \\n) para concatenar no builder do ERS.
    """
    lines: list[str] = []
    rows = matrix.get("rows", [])
    summary = matrix.get("summary", {}) or {}

    if not rows:
        lines.append(
            "_Nenhum requisito registrado ainda. Aprove candidatos do Arguidor ou "
            "popule módulos no backlog para a matriz aparecer aqui._"
        )
        lines.append("")
        return lines

    total = summary.get("total_requirements", 0)
    by_cat = summary.get("by_category", {}) or {}
    fully = summary.get("fully_traced", 0)
    with_spec = summary.get("with_test_spec", 0)
    with_code = summary.get("with_generated_code", 0)

    lines.append(
        f"Cobertura agregada: **{total}** requisitos "
        f"(RF `{by_cat.get('functional', 0)}` · "
        f"RNF `{by_cat.get('non_functional', 0)}` · "
        f"BR `{by_cat.get('business_rule', 0)}` · "
        f"pendentes `{by_cat.get('uncategorized', 0)}`). "
        f"Com spec: **{with_spec}**. Com código gerado: **{with_code}**. "
        f"Rastreamento completo (spec + código): **{fully}**."
    )
    lines.append("")

    lines.append("| ID | Requisito | Categoria | Test Specs | Código gerado |")
    lines.append("|---|---|---|---|---|")

    for r in rows:
        name = (r["name"] or "").replace("|", "\\|")
        if len(name) > 80:
            name = name[:79].rstrip() + "…"
        cat = r["category"] or "—"
        specs = r["test_specs"]
        gens = r["generated_modules"]

        spec_cell = (
            ", ".join(f"`{s['spec_type']}` ({s['status']})" for s in specs)
            if specs else "_(sem spec)_"
        )
        # Pra cada GeneratedModule mostra o source path (mais relevante);
        # paths de teste aparecem na UI expandida, não na tabela resumo.
        code_cell_parts: list[str] = []
        for g in gens:
            label = g["git_source_path"] or g["name"]
            label_clean = str(label).replace("|", "\\|")
            code_cell_parts.append(f"`{label_clean}` ({g['status']})")
        code_cell = ", ".join(code_cell_parts) if code_cell_parts else "_(sem código)_"

        lines.append(
            f"| **{r['requirement_id']}** | {name} | `{cat}` | {spec_cell} | {code_cell} |"
        )

    lines.append("")
    lines.append(
        "> A matriz é gerada sob demanda no momento da regeneração do ERS. "
        "Atualize via `POST /projects/:id/docs/ers/regenerate` ou veja o estado "
        "atual em `/projects/:id/docs` → aba **Rastreabilidade**."
    )
    lines.append("")
    return lines
