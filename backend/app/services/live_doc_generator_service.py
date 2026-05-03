"""MVP 10 Fase 10.7 — Documentação Viva real (LiveDoc) gerada por LLM.

Substitui o LiveDocsPage placeholder (comentário "será gerado via LLM em
produção") por geração real:
  - **module_doc** → Ollama (§6.2 baixa criticidade; repetitivo por módulo)
  - **index** e **architecture** → Premium (§6.3 alta criticidade; consolida
    OCG inteiro e descreve direção arquitetural do projeto)

Preserva `livedocs_service.py` existente (que lê seções Git) — este
service ADICIONA a camada `LiveDoc` da tabela `live_docs` do MVP 10.

Mesmo padrão de provenance e idempotência das Fases 10.2 (unit/integration
Ollama) e 10.3 (security/compliance Premium). Stale detection na Fase 10.4
já funciona out-of-the-box.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IngestedDocument, LiveDoc, ModuleCandidate, OCG,
)

logger = structlog.get_logger(__name__)


# --- Constantes compartilhadas ---

LOCAL_DOC_TYPES = ("module_doc",)
PREMIUM_DOC_TYPES = ("index", "architecture")
ALL_DOC_TYPES = LOCAL_DOC_TYPES + PREMIUM_DOC_TYPES

PREMIUM_PROVIDERS = ("anthropic", "openai")
DEFAULT_PREMIUM_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}

# DT-086 consolidada: helpers de baixa criticidade centralizados
from app.services.llm_low_criticality import (
    resolve_llm_config as _resolve_llm_config_low_crit,
    call_llm as _call_llm_low_crit,
)


# --- Prompts ---

SYSTEM_PROMPT = """Você é um technical writer sênior. Sempre responde em
português-BR e em markdown puro (sem code fences envolvendo a resposta
toda, sem preâmbulo, sem "Claro, aqui está...").

Foque em **utilidade operacional**: o leitor é um Dev/Tester/GP que
precisa decidir algo hoje. Evite marketing, evite discurso genérico
sobre boas práticas — descreva o sistema que ESTÁ sendo construído,
conforme o contexto fornecido.

Seja honesto: prefere dizer "não consta no OCG" ou "a definir pelo GP"
quando o detalhe está fora do contexto fornecido. Não invente APIs,
contratos ou decisões."""


MODULE_DOC_TEMPLATE = """Gere a DOCUMENTAÇÃO TÉCNICA do módulo abaixo
para alimentar o livro vivo do projeto. Público-alvo: Dev/Tester que
vai implementar/testar.

Módulo: **{name}** (categoria: {module_type})
Descrição do Roadmap: {description}

Detalhamento técnico (Fase 9.2):
{details_block}

Stack do projeto:
- Backend: {backend_stack}
- Frontend: {frontend_stack}
- Banco: {database}
- Modelo de execução: {execution_model}

Estrutura obrigatória (markdown):

## Visão geral
2-3 frases: o que esse módulo faz, qual problema resolve, quem consome.

## Responsabilidades
Lista bullet do que o módulo DEVE fazer (e o que NÃO é escopo dele).

## Interfaces
Contratos do módulo — endpoints (se backend_service), telas (se
feature), comandos (se deploy_pipeline), eventos (se middleware).
Use nome e propósito de cada interface; especifique apenas o que
está no contexto acima.

## Pré-requisitos operacionais
O que precisa estar de pé pra esse módulo funcionar (envs,
serviços externos, schema de DB, secrets).

## Notas de manutenção
Onde typically falha, como investigar. Somente o que pode ser
inferido do contexto — evite suposições.

## Referências
Módulos vizinhos relacionados (pelo Roadmap): {neighbors_list}."""


INDEX_DOC_TEMPLATE = """Gere o ÍNDICE EXECUTIVO deste projeto de software
para servir como capa da documentação viva. Público-alvo: stakeholder
+ líder técnico.

## Contexto consolidado (OCG v{ocg_version})

### Perfil
{project_profile_block}

### Stack
{stack_block}

### Arquitetura
{architecture_block}

### Roadmap (resumo dos módulos)
{modules_block}

### Entregáveis declarados
{deliverables_block}

---

Estrutura obrigatória (markdown):

## Visão executiva
2-3 frases: o que o projeto entrega, para quem, qual é o diferencial.

## Status do Roadmap
Resumo por fase (Fundação/Funcionalidades Principais/Complementos)
com N módulos em cada + destaques.

## Stack decidida
Lista das tecnologias confirmadas no OCG, agrupadas por camada.

## Planos de teste ativos
Menciona que o projeto tem specs de unit/integration (por módulo),
security e compliance (globais); não lista os specs individuais.

## Como navegar a documentação
- Documentação por módulo: aba Documentação Viva.
- Plano de testes: aba Testes.
- Arquitetura detalhada: doc `architecture` (mesma aba)."""


ARCHITECTURE_DOC_TEMPLATE = """Gere o DOCUMENTO DE ARQUITETURA do
projeto para registrar as decisões estruturais. Público-alvo: líder
técnico, arquiteto, auditoria.

## Contexto consolidado (OCG v{ocg_version})

### Stack
{stack_block}

### Arquitetura declarada no OCG
{architecture_block}

### Pilares de governança (scores)
{pillars_block}

### Módulos por camada
{modules_by_layer_block}

### Modelo de dados (DATA_MODEL)
{data_model_block}

---

Estrutura obrigatória (markdown):

## Visão de alto nível
Diagrama textual em ASCII/markdown das camadas e seu relacionamento
(sem imagem).

## Camadas
Para cada camada presente no Roadmap (infrastructure, observability,
middleware, backend_service, feature, deploy_pipeline):
- Propósito.
- Módulos que a compõem (só nomes, lista curta).
- Responsabilidade no pipeline de deploy.

## Fluxo de execução principal
Sequência dos passos que um request/comando percorre desde a entrada
até a persistência/resposta. 4-8 passos, numerados.

## Modelo de dados
Com base no DATA_MODEL acima:
- Engine e dialeto.
- Tabelas principais agrupadas por propósito (identidade, auditoria,
  domínio do projeto, operacional).
- Relações importantes (FKs críticas).
- Convenções adotadas (UUID, timestamps, soft delete, audit_log
  append-only, etc).
Se o DATA_MODEL reportou warnings, liste-os como pendências.

## Decisões arquiteturais
Lista numerada de decisões explícitas (ex: "Banco PostgreSQL
monolítico em vez de NoSQL distribuído", "Execução em containers
Docker Compose em vez de Kubernetes nesta fase"). Para cada:
- Decisão.
- Motivo (do OCG).
- Trade-off aceito.

## Padrões obrigatórios
Convenções que o projeto DEVE seguir (log estruturado, timezone UTC,
naming de endpoints, tratamento de erros, etc).

## Áreas a decidir
O que ainda não está definido no OCG e precisa de decisão do GP/
arquiteto antes da próxima fase. Honestidade sobre gaps."""


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def generate_module_live_doc(
    db: AsyncSession, project_id: UUID, module_id: UUID,
) -> LiveDoc:
    """Gera LiveDoc de tipo 'module_doc' via Ollama (baixa criticidade)."""
    module = await db.get(ModuleCandidate, module_id)
    if not module or module.project_id != project_id:
        raise ValueError(f"Módulo {module_id} não encontrado no projeto {project_id}")

    config = await _resolve_llm_config_low_crit(db, project_id)
    if not config:
        raise RuntimeError(
            "Nenhum provider de IA configurado no projeto. LiveDoc por "
            "módulo aceita qualquer provider (§6.2 — baixa criticidade). "
            "Configure Anthropic, Ollama, DeepSeek, OpenAI, Grok ou Gemini "
            "em Settings → IA."
        )

    ocg_ctx = await _load_ocg_context(db, project_id)
    neighbors = await _load_neighbors(db, project_id, exclude_id=module_id)
    details = _safe_load_details(module)
    prompt = _build_module_doc_prompt(
        module=module, details=details, ocg_ctx=ocg_ctx, neighbors=neighbors,
    )

    content = await _call_llm_low_crit(
        config=config, system_prompt=SYSTEM_PROMPT, user_prompt=prompt,
        max_tokens=3000, log_context="live_doc",
    )
    content = _strip_outer_fence(content.strip())

    return await _upsert_live_doc(
        db=db, project_id=project_id, module_id=module_id,
        doc_type="module_doc", content=content, ocg_ctx=ocg_ctx,
        provider="ollama", model=config["model"],
        prompt=prompt, neighbors_ids=[n["id"] for n in neighbors],
    )


async def generate_consolidated_live_doc(
    db: AsyncSession, project_id: UUID, doc_type: str,
) -> LiveDoc:
    """Gera LiveDoc consolidada (index | architecture) via Premium."""
    if doc_type not in PREMIUM_DOC_TYPES:
        raise ValueError(
            f"doc_type '{doc_type}' não suportado pelo consolidado. "
            f"Aceitos: {PREMIUM_DOC_TYPES}. 'module_doc' é por módulo (Ollama)."
        )

    config = await _resolve_premium_config(db, project_id)
    if not config:
        raise RuntimeError(
            "Nenhum provider Premium configurado. LiveDoc consolidada "
            "(index/architecture) é alta criticidade (§6.3) e não cai "
            "para LLM local. Configure Anthropic ou OpenAI."
        )

    ocg_ctx = await _load_ocg_context(db, project_id)
    if ocg_ctx["version"] is None:
        raise ValueError(
            f"Projeto {project_id} não tem OCG — gere via questionário antes."
        )

    modules = await _load_modules_summary(db, project_id)

    if doc_type == "index":
        prompt = _build_index_prompt(ocg_ctx=ocg_ctx, modules=modules)
    else:  # architecture
        prompt = _build_architecture_prompt(ocg_ctx=ocg_ctx, modules=modules)

    content = await _call_premium(
        provider=config["provider"], model=config["model"], api_key=config["api_key"],
        system_prompt=SYSTEM_PROMPT, user_prompt=prompt,
    )
    content = _strip_outer_fence(content.strip())

    return await _upsert_live_doc(
        db=db, project_id=project_id, module_id=None,
        doc_type=doc_type, content=content, ocg_ctx=ocg_ctx,
        provider=config["provider"], model=config["model"],
        prompt=prompt, modules_ids=[m["id"] for m in modules],
    )


async def regenerate_all_module_docs(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any]:
    """Bulk: gera module_doc pra todos os módulos do projeto."""
    rows = await db.execute(
        select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
    )
    modules = rows.scalars().all()
    report = {"total": len(modules), "generated": 0, "failed": 0, "errors": []}
    for mc in modules:
        try:
            await generate_module_live_doc(db, project_id, mc.id)
            report["generated"] += 1
        except Exception as exc:
            report["failed"] += 1
            report["errors"].append({
                "module_id": str(mc.id), "module_name": mc.name,
                "error": str(exc)[:300],
            })
            logger.warning(
                "live_doc.generation_failed",
                module_id=str(mc.id), project_id=str(project_id),
                error=str(exc),
            )
    return report


async def regenerate_all_consolidated_docs(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any]:
    """Bulk: gera index + architecture via Premium."""
    report = {"generated": 0, "failed": 0, "errors": []}
    for dt in PREMIUM_DOC_TYPES:
        try:
            await generate_consolidated_live_doc(db, project_id, dt)
            report["generated"] += 1
        except Exception as exc:
            report["failed"] += 1
            report["errors"].append({"doc_type": dt, "error": str(exc)[:300]})
            logger.warning(
                "live_doc.consolidated_failed",
                doc_type=dt, project_id=str(project_id), error=str(exc),
            )
    return report


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

# _resolve_ollama_config removida — DT-086 consolidada. Use
# `_resolve_llm_config_low_crit` importado de `llm_low_criticality`.


async def _resolve_premium_config(
    db: AsyncSession, project_id: UUID,
) -> Optional[dict[str, Any]]:
    from app.services.ai_key_resolver import AIKeyResolver
    chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
    for entry in chain:
        provider = (entry.get("provider") or "").lower()
        if provider not in PREMIUM_PROVIDERS:
            continue
        api_key = await AIKeyResolver.get_project_key(db, project_id, provider)
        if not api_key:
            continue
        model = entry.get("model") or DEFAULT_PREMIUM_MODEL[provider]
        return {"provider": provider, "model": model, "api_key": api_key}
    return None


async def _load_ocg_context(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any]:
    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.version.desc()).limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg:
        return {"version": None, "data": {}, "questionnaire_id": None, "ingested_doc_ids": []}
    try:
        data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (ValueError, TypeError):
        data = {}
    # MVP 34: ignora docs soft-deleted — livedocs não devem citar docs deletados.
    docs_rows = await db.execute(
        select(IngestedDocument.id).where(
            IngestedDocument.project_id == project_id,
            IngestedDocument.arguider_status == "completed",
            IngestedDocument.deleted_at.is_(None),
        )
    )
    doc_ids = [str(r[0]) for r in docs_rows.all()]
    return {
        "version": ocg.version,
        "data": data,
        "questionnaire_id": str(ocg.questionnaire_id) if ocg.questionnaire_id else None,
        "ingested_doc_ids": doc_ids,
    }


async def _load_neighbors(
    db: AsyncSession, project_id: UUID, exclude_id: UUID,
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(ModuleCandidate).where(
            ModuleCandidate.project_id == project_id,
            ModuleCandidate.id != exclude_id,
        )
    )
    items = rows.scalars().all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items_sorted = sorted(
        items,
        key=lambda m: (priority_rank.get(m.priority or "medium", 1), m.name or ""),
    )[:20]
    return [
        {"id": str(m.id), "name": m.name or "(sem nome)", "module_type": m.module_type or "feature"}
        for m in items_sorted
    ]


async def _load_modules_summary(
    db: AsyncSession, project_id: UUID,
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(ModuleCandidate).where(ModuleCandidate.project_id == project_id)
    )
    items = rows.scalars().all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items_sorted = sorted(
        items,
        key=lambda m: (priority_rank.get(m.priority or "medium", 1), m.name or ""),
    )
    return [
        {
            "id": str(m.id),
            "name": m.name or "(sem nome)",
            "module_type": m.module_type or "feature",
            "priority": m.priority or "medium",
            "readiness_status": m.readiness_status,
        }
        for m in items_sorted
    ]


def _safe_load_details(module: ModuleCandidate) -> dict[str, Any]:
    if not module.details_json:
        return {}
    try:
        return json.loads(module.details_json)
    except (ValueError, TypeError):
        return {}


# --- Prompt builders ---

def _build_module_doc_prompt(
    *, module: ModuleCandidate, details: dict[str, Any],
    ocg_ctx: dict[str, Any], neighbors: list[dict[str, Any]],
) -> str:
    stack = ocg_ctx["data"].get("STACK_RECOMMENDATION") or {}
    arch = ocg_ctx["data"].get("ARCHITECTURE_OVERVIEW") or {}
    backend = stack.get("backend") or {}
    frontend = stack.get("frontend") or {}
    database = stack.get("database") or {}

    def _ls(v):
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v)
        return str(v) if v else "—"

    backend_stack = _ls(backend.get("framework")) if backend.get("enabled") else "não habilitado"
    frontend_stack = _ls(frontend.get("stack")) if frontend.get("enabled") else "não habilitado"
    db_engine = database.get("engine") or "—"
    exec_model = _ls(arch.get("execution_model"))

    if details:
        details_block = (
            f"- O que é: {details.get('what_it_is', '—')}\n"
            f"- Pré-requisitos: {', '.join(details.get('prerequisites', [])) or '—'}"
        )
    else:
        details_block = "(detalhamento não gerado — infira da categoria do módulo)"

    neighbors_list = ", ".join(n["name"] for n in neighbors[:8]) or "—"

    return MODULE_DOC_TEMPLATE.format(
        name=module.name or "(sem nome)",
        module_type=module.module_type or "feature",
        description=module.description or "(sem descrição)",
        details_block=details_block,
        backend_stack=backend_stack,
        frontend_stack=frontend_stack,
        database=db_engine,
        execution_model=exec_model,
        neighbors_list=neighbors_list,
    )


def _build_index_prompt(
    *, ocg_ctx: dict[str, Any], modules: list[dict[str, Any]],
) -> str:
    data = ocg_ctx.get("data", {})
    return INDEX_DOC_TEMPLATE.format(
        ocg_version=ocg_ctx.get("version") or "?",
        project_profile_block=_render_project_profile(data.get("PROJECT_PROFILE") or {}),
        stack_block=_render_stack(data.get("STACK_RECOMMENDATION") or {}),
        architecture_block=_render_architecture(data.get("ARCHITECTURE_OVERVIEW") or {}),
        modules_block=_render_modules(modules),
        deliverables_block=_render_deliverables(data.get("DELIVERABLES") or {}),
    )


def _build_architecture_prompt(
    *, ocg_ctx: dict[str, Any], modules: list[dict[str, Any]],
) -> str:
    data = ocg_ctx.get("data", {})
    return ARCHITECTURE_DOC_TEMPLATE.format(
        ocg_version=ocg_ctx.get("version") or "?",
        stack_block=_render_stack(data.get("STACK_RECOMMENDATION") or {}),
        architecture_block=_render_architecture(data.get("ARCHITECTURE_OVERVIEW") or {}),
        pillars_block=_render_pillars(data.get("PILLAR_SCORES") or {}),
        modules_by_layer_block=_render_modules_by_layer(modules),
        data_model_block=_render_data_model(data.get("DATA_MODEL") or {}),
    )


# --- Renderers ---

def _render_project_profile(p: dict[str, Any]) -> str:
    if not p:
        return "(não declarado)"
    lines = []
    for k in ("initiative_type", "criticality_level", "handles_pii", "output_formats", "deliverables"):
        if k not in p:
            continue
        v = p[k]
        if isinstance(v, list):
            lines.append(f"- {k}: {', '.join(str(x) for x in v) or '—'}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) if lines else "(campos relevantes vazios)"


def _render_stack(s: dict[str, Any]) -> str:
    if not s:
        return "(stack não declarado)"
    lines = []
    for layer in ("backend", "frontend", "database", "cache", "messaging", "ai"):
        sub = s.get(layer)
        if not isinstance(sub, dict):
            continue
        if sub.get("enabled") is False:
            lines.append(f"- {layer}: não habilitado")
            continue
        bits = []
        for k in ("framework", "stack", "language", "engine", "provider"):
            v = sub.get(k)
            if isinstance(v, list) and v:
                bits.append(f"{k}={', '.join(str(x) for x in v)}")
            elif isinstance(v, str) and v:
                bits.append(f"{k}={v}")
        if bits:
            lines.append(f"- {layer}: " + "; ".join(bits))
    return "\n".join(lines) if lines else "(chaves vazias)"


def _render_architecture(a: dict[str, Any]) -> str:
    if not a:
        return "(não declarado)"
    lines = []
    for k in ("architectural_profile", "execution_model", "multi_tenant", "high_availability", "async_processing"):
        if k not in a:
            continue
        v = a[k]
        if isinstance(v, list):
            lines.append(f"- {k}: {', '.join(str(x) for x in v) or '—'}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) if lines else "(campos relevantes vazios)"


def _render_pillars(p: Any) -> str:
    if not isinstance(p, dict) or not p:
        return "(pilares não avaliados)"
    lines = []
    for pk in sorted(p.keys()):
        pv = p[pk]
        if isinstance(pv, dict):
            lines.append(f"- {pk}: score={pv.get('score')} status={pv.get('status')}")
        else:
            lines.append(f"- {pk}: {pv}")
    return "\n".join(lines)


def _render_deliverables(d: Any) -> str:
    if not d:
        return "(não declarados)"
    if isinstance(d, dict):
        parts = []
        for k, v in d.items():
            if isinstance(v, list):
                parts.append(f"- {k}: {', '.join(str(x) for x in v)}")
            else:
                parts.append(f"- {k}: {v}")
        return "\n".join(parts)
    if isinstance(d, list):
        return "\n".join(f"- {x}" for x in d)
    return str(d)


def _render_modules(modules: list[dict[str, Any]]) -> str:
    if not modules:
        return "(nenhum módulo)"
    return "\n".join(
        f"- {m['name']} ({m['module_type']}, {m['priority']}, readiness={m.get('readiness_status') or 'n/a'})"
        for m in modules
    )


def _render_data_model(dm: Any) -> str:
    """DT-076 Fase 5 — Renderiza DATA_MODEL como texto pro prompt Premium.

    Mostra engine, contagem, tabelas com colunas principais e FKs.
    Warnings também aparecem pra LLM mencionar como pendências.
    """
    if not isinstance(dm, dict) or not dm:
        return "(sem DATA_MODEL — dialecto do banco não foi inferido)"
    engine = dm.get("engine_raw") or dm.get("engine") or "(não declarado)"
    supported = dm.get("dialect_supported", False)
    warnings = dm.get("warnings") or []
    tables = dm.get("tables") or []
    fks = dm.get("foreign_keys") or []

    lines = [f"- Engine: {engine} (suporte automático: {'sim' if supported else 'não'})"]
    lines.append(f"- Tabelas: {len(tables)}")
    if warnings:
        lines.append("- Warnings:")
        for w in warnings[:5]:
            lines.append(f"  - {w}")
    if not tables:
        return "\n".join(lines)

    lines.append("- Principais tabelas:")
    for t in tables[:12]:
        name = t.get("name", "?")
        n_cols = len(t.get("columns") or [])
        comment = (t.get("comment") or "").strip()
        if comment:
            lines.append(f"  - `{name}` ({n_cols} colunas): {comment}")
        else:
            lines.append(f"  - `{name}` ({n_cols} colunas)")
    if len(tables) > 12:
        lines.append(f"  - (… e mais {len(tables) - 12} tabela(s))")

    if fks:
        lines.append(f"- Relações (FKs): {len(fks)} restrições configuradas")

    return "\n".join(lines)


def _render_modules_by_layer(modules: list[dict[str, Any]]) -> str:
    if not modules:
        return "(nenhum módulo)"
    LAYER_ORDER = ("infrastructure", "observability", "middleware", "backend_service", "feature", "deploy_pipeline")
    by_layer: dict[str, list[str]] = {l: [] for l in LAYER_ORDER}
    by_layer["other"] = []
    for m in modules:
        layer = m["module_type"] if m["module_type"] in by_layer else "other"
        by_layer[layer].append(m["name"])
    out = []
    for layer in list(LAYER_ORDER) + ["other"]:
        names = by_layer[layer]
        if not names:
            continue
        out.append(f"- **{layer}** ({len(names)}): {', '.join(names)}")
    return "\n".join(out) or "(nenhum módulo)"


# --- Upsert + LLM calls ---

async def _upsert_live_doc(
    *, db: AsyncSession, project_id: UUID, module_id: Optional[UUID],
    doc_type: str, content: str, ocg_ctx: dict[str, Any],
    provider: str, model: str, prompt: str,
    neighbors_ids: Optional[list[str]] = None,
    modules_ids: Optional[list[str]] = None,
) -> LiveDoc:
    """Upsert via lookup manual (lida com NULL no UniqueConstraint)."""
    query = select(LiveDoc).where(
        LiveDoc.project_id == project_id,
        LiveDoc.doc_type == doc_type,
    )
    if module_id is None:
        query = query.where(LiveDoc.module_id.is_(None))
    else:
        query = query.where(LiveDoc.module_id == module_id)

    row = await db.execute(query)
    existing = row.scalar_one_or_none()
    is_new = existing is None

    provenance = {
        "ocg_version": ocg_ctx.get("version"),
        "questionnaire_id": ocg_ctx.get("questionnaire_id"),
        "ingested_doc_ids": ocg_ctx.get("ingested_doc_ids", []),
        "neighbors_considered": neighbors_ids or [],
        "modules_considered": modules_ids or [],
        "llm": {"provider": provider, "model": model},
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing is None:
        doc = LiveDoc(
            project_id=project_id, module_id=module_id, doc_type=doc_type,
            content=content,
            provenance_json=json.dumps(provenance, ensure_ascii=False),
            ocg_version_at_generation=ocg_ctx.get("version"),
            generated_at=datetime.now(timezone.utc),
            generator_provider=provider, generator_model=model,
        )
        db.add(doc)
    else:
        doc = existing
        doc.content = content
        doc.provenance_json = json.dumps(provenance, ensure_ascii=False)
        doc.ocg_version_at_generation = ocg_ctx.get("version")
        doc.generated_at = datetime.now(timezone.utc)
        doc.generator_provider = provider
        doc.generator_model = model

    await db.commit()
    logger.info(
        "live_doc.generated",
        doc_id=str(doc.id), project_id=str(project_id),
        doc_type=doc_type, new=is_new, provider=provider, model=model,
        content_chars=len(content),
    )
    return doc


# _call_ollama removida — DT-086 consolidada. Use `_call_llm_low_crit`
# importado de `llm_low_criticality` (aceita qualquer provider).


async def _call_premium(
    *, provider: str, model: str, api_key: str,
    system_prompt: str, user_prompt: str,
) -> str:
    if provider == "anthropic":
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model, max_tokens=4096, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        blocks = getattr(resp, "content", []) or []
        return "\n".join(getattr(b, "text", "") or "" for b in blocks).strip()
    if provider == "openai":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model, max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choices = getattr(resp, "choices", []) or []
        if not choices:
            return ""
        msg = getattr(choices[0], "message", None)
        return (getattr(msg, "content", "") or "").strip() if msg else ""
    raise ValueError(f"Provider sem handler na 10.7: {provider}")


def _strip_outer_fence(text: str) -> str:
    m = re.match(
        r"^\s*```(?:markdown|md)?\s*\n?(?P<body>.*?)\n?```\s*$",
        text, re.DOTALL,
    )
    return m.group("body").strip() if m else text
