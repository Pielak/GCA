"""MVP 9 Fase 9.4 — Plano de deploy sugerido.

Determinístico (sem LLM): ordena os `module_candidates` do projeto pra
montar uma sequência de construção/deploy honesta:

  1. Por camada canônica (DEPLOY_ORDER do MVP 9.1):
     infrastructure → observability → middleware → backend_service
     → feature → deploy_pipeline
  2. Dentro da camada, **topological sort** baseado em
     `dependencies_inferred` (Fase 9.3) — itens que dependem de outros
     da MESMA camada vêm depois.
  3. Empate: priority (high → medium → low).
  4. Empate: readiness (ready_for_codegen primeiro, depois partial,
     needs_input, unknown, sem readiness).
  5. Empate: nome alfabético.

Exporta como dict (pra UI) ou Markdown (pra download).

Sem dependência cíclica detectada: items em ciclo entram na ordem
parcial possível e ganham marker `cycle: true` na saída pra UI
sinalizar revisão manual.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.module_categories import (
    CATEGORY_LABELS_PT_BR,
    DEPLOY_ORDER,
    normalize_module_type,
)
from app.models.base import ModuleCandidate

logger = structlog.get_logger(__name__)


READINESS_RANK = {
    "ready_for_codegen": 0,
    "partial": 1,
    "needs_input": 2,
    "unknown": 3,
    None: 4,
}

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


async def build_deploy_plan(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """Monta o plano de deploy. Retorna dict serializável pra UI:

        {
          "project_id": "...",
          "generated_at": "iso-8601",
          "total_modules": int,
          "ready_count": int,
          "blocked_count": int,
          "layers": [
            {
              "layer": "infrastructure",
              "label": "Infraestrutura",
              "items": [
                {"id", "name", "module_type", "priority", "status",
                 "readiness_status", "depends_on": [...], "cycle": bool},
                ...
              ]
            },
            ...
          ]
        }
    """
    rows = await db.execute(
        select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
    )
    modules = rows.scalars().all()

    items_by_layer: dict[str, list[dict[str, Any]]] = {k: [] for k in DEPLOY_ORDER}
    items_by_layer["other"] = []  # bucket pra categorias não-canônicas

    name_to_id: dict[str, str] = {}
    for m in modules:
        nm_lower = (m.name or "").strip().lower()
        if nm_lower:
            name_to_id[nm_lower] = str(m.id)

    for m in modules:
        layer = normalize_module_type(m.module_type)
        bucket = items_by_layer.get(layer, items_by_layer["other"])
        deps = _resolve_deps(m, name_to_id)
        bucket.append({
            "id": str(m.id),
            "name": m.name or "(sem nome)",
            "module_type": layer,
            "priority": m.priority or "medium",
            "status": m.status or "sugerido",
            "readiness_status": m.readiness_status,
            "description": (m.description or "")[:300],
            "depends_on": deps,
            "cycle": False,  # marcado pelo topo_sort se necessário
        })

    layers_payload: list[dict[str, Any]] = []
    ready_count = 0
    blocked_count = 0

    for layer_name in DEPLOY_ORDER:
        bucket = items_by_layer.get(layer_name, [])
        if not bucket:
            continue
        ordered = _topological_sort(bucket)
        for item in ordered:
            if item["readiness_status"] == "ready_for_codegen":
                ready_count += 1
            elif item["readiness_status"] in ("needs_input", "unknown"):
                blocked_count += 1
        layers_payload.append({
            "layer": layer_name,
            "label": CATEGORY_LABELS_PT_BR.get(layer_name, layer_name),
            "items": ordered,
        })

    if items_by_layer["other"]:
        ordered_other = _topological_sort(items_by_layer["other"])
        layers_payload.append({
            "layer": "other",
            "label": "Outros (categoria não-canônica)",
            "items": ordered_other,
        })

    return {
        "project_id": str(project_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_modules": len(modules),
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "layers": layers_payload,
    }


def _resolve_deps(module: ModuleCandidate, name_to_id: dict[str, str]) -> list[dict[str, str]]:
    """Resolve dependencies_inferred (Fase 9.3) pra dicts {id, name}.

    A 9.3 já filtra pra nomes/ids reais do projeto, então aqui é só
    materializar pro frontend consumir.
    """
    if not module.dependencies_inferred:
        return []
    try:
        raw = json.loads(module.dependencies_inferred)
    except (ValueError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen_ids = set()
    for item in raw[:10]:
        if not isinstance(item, str):
            continue
        # Tenta como id direto primeiro, depois como name
        candidate_id = item if item in name_to_id.values() else name_to_id.get(item.strip().lower())
        if candidate_id and candidate_id not in seen_ids:
            # Resolver nome reverso
            name = next(
                (n for n, i in name_to_id.items() if i == candidate_id),
                item,
            )
            out.append({"id": candidate_id, "name": name})
            seen_ids.add(candidate_id)
    return out


def _topological_sort(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort topológico estável dentro de uma camada.

    Itens sem dependências (na mesma camada) vêm primeiro.
    Empate: (priority, readiness, name).
    Ciclo detectado: itens restantes entram na ordem dos critérios de
    empate e ganham `cycle=True`.
    """
    by_id = {it["id"]: it for it in items}
    in_layer_ids = set(by_id.keys())

    # in_degree: quantas deps deste item estão NA MESMA camada (deps fora
    # da camada não bloqueiam — outra camada vem antes ou depois conforme
    # DEPLOY_ORDER)
    in_degree: dict[str, int] = {}
    for it in items:
        ds = [d["id"] for d in it["depends_on"] if d["id"] in in_layer_ids and d["id"] != it["id"]]
        in_degree[it["id"]] = len(ds)

    def _tie_key(it):
        return (
            PRIORITY_RANK.get(it["priority"], 1),
            READINESS_RANK.get(it["readiness_status"], 4),
            it["name"].lower(),
        )

    output: list[dict[str, Any]] = []
    remaining = dict(in_degree)
    while remaining:
        # Escolhe candidatos com in_degree=0
        ready = [iid for iid, deg in remaining.items() if deg == 0]
        if not ready:
            # Ciclo — pega o melhor pelo tie-key e marca
            ordered = sorted(remaining.keys(), key=lambda i: _tie_key(by_id[i]))
            chosen = ordered[0]
            it = by_id[chosen]
            it["cycle"] = True
            output.append(it)
            remaining.pop(chosen)
            for other in remaining:
                deps_other = [d["id"] for d in by_id[other]["depends_on"]]
                if chosen in deps_other:
                    remaining[other] -= 1
            continue
        # Sort estável dos ready
        ready_sorted = sorted(ready, key=lambda i: _tie_key(by_id[i]))
        chosen = ready_sorted[0]
        output.append(by_id[chosen])
        remaining.pop(chosen)
        for other in remaining:
            deps_other = [d["id"] for d in by_id[other]["depends_on"]]
            if chosen in deps_other:
                remaining[other] -= 1
    return output


# ---------------------------------------------------------------------------
# Export Markdown
# ---------------------------------------------------------------------------

_PRIORITY_LABEL_PT = {"high": "Alta", "medium": "Média", "low": "Baixa"}
_READINESS_LABEL_PT = {
    "ready_for_codegen": "✓ Pronto para CodeGen",
    "partial": "◐ Parcial",
    "needs_input": "⚠ Precisa input",
    "unknown": "? Sem avaliação",
}
_STATUS_LABEL_PT = {
    "sugerido": "Sugerido",
    "aguardando_resposta": "Aguardando resposta",
    "adicionado": "Adicionado",
    "concluido": "Concluído",
}


def render_markdown(plan: dict[str, Any], *, project_name: str | None = None) -> str:
    """Converte plan em Markdown legível pro GP imprimir/exportar."""
    lines: list[str] = []
    title = project_name or f"Projeto {plan['project_id']}"
    lines.append(f"# Plano de Deploy — {title}")
    lines.append("")
    lines.append(f"_Gerado em {plan['generated_at']}_")
    lines.append("")
    lines.append(f"**Resumo**: {plan['total_modules']} módulos · "
                 f"{plan['ready_count']} prontos para CodeGen · "
                 f"{plan['blocked_count']} bloqueados (precisam input).")
    lines.append("")
    lines.append("Os módulos abaixo estão ordenados por camada de construção e "
                 "por dependências inferidas. Cada bloco é uma camada — "
                 "complete a anterior antes de iniciar a próxima.")
    lines.append("")

    seq = 1
    for layer in plan["layers"]:
        if not layer["items"]:
            continue
        lines.append(f"## {seq}. {layer['label']}")
        lines.append("")
        for item in layer["items"]:
            seq_inner = item.get("name", "")
            cycle_marker = " ⚠ ciclo de dependência" if item.get("cycle") else ""
            lines.append(f"### {seq_inner}{cycle_marker}")
            lines.append("")
            prio = _PRIORITY_LABEL_PT.get(item["priority"], item["priority"])
            stat = _STATUS_LABEL_PT.get(item["status"], item["status"])
            ready = _READINESS_LABEL_PT.get(item.get("readiness_status") or "unknown", "—")
            lines.append(f"- **Prioridade**: {prio}")
            lines.append(f"- **Status**: {stat}")
            lines.append(f"- **Readiness**: {ready}")
            if item.get("depends_on"):
                deps_label = ", ".join(d["name"] for d in item["depends_on"])
                lines.append(f"- **Depende de**: {deps_label}")
            if item.get("description"):
                lines.append("")
                lines.append(item["description"])
            lines.append("")
        seq += 1

    if seq == 1:
        lines.append("_(Nenhum módulo no Roadmap ainda.)_")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Plano gerado automaticamente pelo GCA. Critério de ordenação: "
                 "camada canônica (infra → observabilidade → middleware → backend → "
                 "funcionalidade → deploy) com sort topológico de dependências dentro "
                 "de cada camada. Itens marcados com ⚠ ciclo precisam revisão manual._")
    return "\n".join(lines)
