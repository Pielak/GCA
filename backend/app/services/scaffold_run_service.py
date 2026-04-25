"""Serviço de scaffold server-side persistido (2026-04-25).

Antes da camada A da cascata, a orquestração do scaffold MVP 30 vivia no
frontend: o navegador chamava `/scaffold/plan`, recebia a lista de
arquivos, e iterava `/scaffold/item` síncrono pra cada path. Qualquer
network error ou refresh de aba descartava progresso.

Aqui a orquestração roda no backend (Celery task `scaffold_run_executor`)
e persiste em duas tabelas:

  - `scaffold_runs` (status global da run)
  - `scaffold_run_items` (1 row por arquivo do plano + content gerado)

Frontend vira observador via `GET /scaffold/runs/{run_id}`. O `apply` é
manual (usuário aprova) e commita só os items com status='done'.

Topologia de dependências (B) e enlaces de conteúdo entre peers (C) são
camadas seguintes — não estão neste arquivo ainda.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    BacklogItem,
    ModuleCandidate,
    OCG,
    Project,
    ScaffoldRun,
    ScaffoldRunItem,
)
from app.services.scaffold_planner import build_item_prompt, build_plan_prompt

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helpers — replicam o mínimo do que o router /scaffold/plan e
# /scaffold/item fazem hoje, sem import cíclico via Celery → router.
# ──────────────────────────────────────────────────────────────────────


async def _load_latest_ocg_data(db: AsyncSession, project_id: UUID) -> dict:
    """Carrega o JSON da OCG mais recente do projeto. {} se não houver."""
    res = await db.execute(
        select(OCG.ocg_data).where(OCG.project_id == project_id).order_by(OCG.version.desc()).limit(1)
    )
    raw = res.scalar()
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw or {}


async def _load_ready_modules_ordered(db: AsyncSession, project_id: UUID) -> List[Dict[str, Any]]:
    """Lê backlog do projeto filtrado por items prontos pra CodeGen,
    na ordem canônica do roadmap (priority + ready + created_at).

    Espelha a query do `/scaffold/plan` (router) — mantida em sync.
    """
    PHASE_MAP = {"critical": 1, "high": 1, "medium": 2, "low": 3}
    priority_rank = case(
        (BacklogItem.priority == "critical", 0),
        (BacklogItem.priority == "high", 1),
        (BacklogItem.priority == "medium", 2),
        (BacklogItem.priority == "low", 3),
        else_=4,
    )
    ready_rank = case(
        (ModuleCandidate.ready_for_codegen.is_(True), 0),
        (ModuleCandidate.id.is_(None), 0),  # OCG direto = ready
        else_=1,
    )
    rows = (await db.execute(
        select(BacklogItem, ModuleCandidate)
        .outerjoin(ModuleCandidate, ModuleCandidate.id == BacklogItem.module_candidate_id)
        .where(
            BacklogItem.project_id == project_id,
            BacklogItem.parent_item_id.is_(None),
            BacklogItem.category != "governance",
            BacklogItem.status.notin_(("completed", "concluido", "rejected")),
        )
        .order_by(priority_rank, ready_rank, BacklogItem.created_at.asc())
    )).all()

    modules: List[Dict[str, Any]] = []
    for bl, mc in rows:
        if mc is not None and not bool(mc.ready_for_codegen):
            continue
        modules.append({
            "name": bl.title,
            "description": bl.description or "",
            "module_type": bl.module_type or (mc.module_type if mc else "feature"),
            "priority": bl.priority or "medium",
            "phase": PHASE_MAP.get((bl.priority or "medium").lower(), 2),
            "category": bl.category,
            "ready_for_codegen": bool(mc.ready_for_codegen) if mc else True,
        })
    return modules


def _try_parse_json(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _parse_llm_json(raw_text: str) -> Optional[dict]:
    """Parser tolerante: mesmo regime do /scaffold/plan endpoint.

    1) json.loads direto
    2) bloco ```json ... ``` fechado
    3) ```json sem fechamento (truncate)
    4) primeiro `{` até o último `}`
    """
    stripped = raw_text.strip()
    parsed = _try_parse_json(stripped)
    if parsed is not None:
        return parsed
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if m:
        parsed = _try_parse_json(m.group(1).strip())
        if parsed is not None:
            return parsed
    m = re.match(r"^```(?:json)?\s*\n?([\s\S]*)$", stripped)
    if m:
        parsed = _try_parse_json(m.group(1).strip())
        if parsed is not None:
            return parsed
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if 0 <= first_brace < last_brace:
        return _try_parse_json(stripped[first_brace : last_brace + 1])
    return None


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


async def create_run(
    db: AsyncSession, project_id: UUID, triggered_by: Optional[UUID]
) -> ScaffoldRun:
    """Cria uma run pendente. A execução real fica pro Celery task."""
    run = ScaffoldRun(
        project_id=project_id,
        triggered_by=triggered_by,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    logger.info("scaffold_run.created", run_id=str(run.id), project_id=str(project_id))
    return run


async def execute_run(run_id: UUID) -> None:
    """Pipeline completo da run: planning → items → completed.

    Aberto numa session dedicada (worker Celery roda em processo separado).
    Falha de 1 item não invalida os demais — registra `failed` e segue.
    """
    from anthropic import AsyncAnthropic

    from app.core.config import settings as app_settings
    from app.db.database import AsyncSessionLocal

    api_key = app_settings.ANTHROPIC_API_KEY
    if not api_key:
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run:
                run.status = "failed"
                run.error = "ANTHROPIC_API_KEY não configurada."
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
        return

    client = AsyncAnthropic(api_key=api_key)

    # Fase 1 — planning
    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        if run is None:
            logger.warning("scaffold_run.not_found", run_id=str(run_id))
            return
        if run.status != "pending":
            logger.info("scaffold_run.skip_not_pending", run_id=str(run_id), status=run.status)
            return

        run.status = "planning"
        await db.commit()

        project = await db.get(Project, run.project_id)
        if project is None:
            run.status = "failed"
            run.error = "Projeto não encontrado."
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return

        ocg_data = await _load_latest_ocg_data(db, run.project_id)
        modules = await _load_ready_modules_ordered(db, run.project_id)
        if not modules:
            run.status = "failed"
            run.error = (
                "Nenhum item do backlog está pronto pra CodeGen. "
                "Responda Questões em Aberto ou ingira mais documentos."
            )
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return

        prompt = build_plan_prompt(
            project_name=project.name,
            project_slug=project.slug,
            project_description=project.description,
            stack=ocg_data.get("STACK_RECOMMENDATION", {}),
            architecture=ocg_data.get("ARCHITECTURE_OVERVIEW", {}),
            modules=modules,
            arguider_modules=[],
        )

    # LLM call (fora da session pra não segurar conexão)
    try:
        plan_response = await client.messages.create(
            model=app_settings.ANTHROPIC_MODEL,
            max_tokens=16384,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        plan_raw = plan_response.content[0].text
        plan_tokens = plan_response.usage.output_tokens
    except Exception as exc:  # noqa: BLE001
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run:
                run.status = "failed"
                run.error = f"LLM erro na fase plan: {str(exc)[:300]}"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
        return

    plan_data = _parse_llm_json(plan_raw)
    if plan_data is None:
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run:
                run.status = "failed"
                run.error = f"LLM retornou plano inválido (tokens={plan_tokens}). Preview: {plan_raw[:200]}"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
        return

    items_raw = plan_data.get("items") or []
    valid_items = [
        it for it in items_raw if isinstance(it, dict) and it.get("path")
    ]
    summary_text = (plan_data.get("summary") or f"Scaffold de {len(valid_items)} arquivos")[:1000]

    # Persiste plano + items pending
    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        if run is None:
            return
        run.status = "generating"
        run.plan_summary = summary_text
        run.plan_tokens_used = plan_tokens
        run.total_items = len(valid_items)
        for ordinal, it in enumerate(valid_items):
            db.add(ScaffoldRunItem(
                run_id=run_id,
                ordinal=ordinal,
                path=str(it.get("path", ""))[:500],
                file_type=str(it.get("file_type") or "")[:40] or None,
                purpose=(str(it.get("purpose") or "")[:500]) or None,
                est_lines=int(it.get("est_lines") or 0) or None,
                status="pending",
            ))
        await db.commit()

    # Fase 2 — gerar conteúdo item-a-item
    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        project = await db.get(Project, run.project_id)
        ocg_data = await _load_latest_ocg_data(db, run.project_id)
        stack = ocg_data.get("STACK_RECOMMENDATION", {})
        architecture = ocg_data.get("ARCHITECTURE_OVERVIEW", {})
        rnf_contracts = ocg_data.get("RNF_CONTRACTS")
        frontend_obj = stack.get("frontend") if isinstance(stack, dict) else None
        design_tokens = (
            frontend_obj.get("design_tokens") if isinstance(frontend_obj, dict) else None
        )

        items_q = await db.execute(
            select(ScaffoldRunItem)
            .where(ScaffoldRunItem.run_id == run_id)
            .order_by(ScaffoldRunItem.ordinal.asc())
        )
        all_items = items_q.scalars().all()
        all_paths = [it.path for it in all_items]

    completed = 0
    failed = 0
    for it_snapshot in all_items:
        # Marca generating
        async with AsyncSessionLocal() as db:
            it = await db.get(ScaffoldRunItem, it_snapshot.id)
            it.status = "generating"
            it.started_at = datetime.now(timezone.utc)
            await db.commit()

        peer_paths = [p for p in all_paths if p != it_snapshot.path][:30]
        item_prompt = build_item_prompt(
            project_name=project.name,
            project_slug=project.slug,
            stack=stack,
            architecture=architecture,
            item_path=it_snapshot.path,
            item_purpose=it_snapshot.purpose or "(sem propósito declarado)",
            item_file_type=it_snapshot.file_type or "txt",
            peer_paths=peer_paths,
            rnf_contracts=rnf_contracts,
            design_tokens=design_tokens,
        )
        try:
            item_response = await client.messages.create(
                model=app_settings.ANTHROPIC_MODEL,
                max_tokens=8192,
                temperature=0.3,
                messages=[{"role": "user", "content": item_prompt}],
            )
            item_raw = item_response.content[0].text
            item_tokens = item_response.usage.output_tokens
        except Exception as exc:  # noqa: BLE001
            async with AsyncSessionLocal() as db:
                it = await db.get(ScaffoldRunItem, it_snapshot.id)
                it.status = "failed"
                it.error = f"LLM erro: {str(exc)[:300]}"
                it.finished_at = datetime.now(timezone.utc)
                await db.commit()
            failed += 1
            continue

        parsed_item = _parse_llm_json(item_raw)
        async with AsyncSessionLocal() as db:
            it = await db.get(ScaffoldRunItem, it_snapshot.id)
            if parsed_item is None:
                it.status = "failed"
                it.error = f"JSON inválido (tokens={item_tokens})"
                it.tokens_used = item_tokens
                failed += 1
            else:
                content = parsed_item.get("content") or ""
                notes = (parsed_item.get("notes") or "")[:1000] or None
                it.content = content
                it.notes = notes
                it.tokens_used = item_tokens
                it.status = "done" if content.strip() else "failed"
                if it.status == "done":
                    completed += 1
                else:
                    it.error = "LLM devolveu content vazio"
                    failed += 1
            it.finished_at = datetime.now(timezone.utc)
            await db.commit()

    # Encerra run
    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        run.completed_items = completed
        run.failed_items = failed
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(
        "scaffold_run.completed",
        run_id=str(run_id),
        total=len(all_items),
        done=completed,
        failed=failed,
    )


async def snapshot_run(db: AsyncSession, run_id: UUID) -> Optional[dict]:
    """Snapshot serializável da run + items, pra GET endpoint."""
    run = await db.get(ScaffoldRun, run_id)
    if run is None:
        return None
    items_q = await db.execute(
        select(ScaffoldRunItem)
        .where(ScaffoldRunItem.run_id == run_id)
        .order_by(ScaffoldRunItem.ordinal.asc())
    )
    items = items_q.scalars().all()
    return {
        "id": str(run.id),
        "project_id": str(run.project_id),
        "status": run.status,
        "plan_summary": run.plan_summary,
        "plan_tokens_used": run.plan_tokens_used,
        "total_items": run.total_items,
        "completed_items": run.completed_items,
        "failed_items": run.failed_items,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "applied_at": run.applied_at.isoformat() if run.applied_at else None,
        "apply_committed": run.apply_committed,
        "apply_failed": run.apply_failed,
        "items": [
            {
                "id": str(it.id),
                "ordinal": it.ordinal,
                "path": it.path,
                "file_type": it.file_type,
                "purpose": it.purpose,
                "status": it.status,
                "tokens_used": it.tokens_used,
                "error": it.error,
                "notes": it.notes,
                "has_content": bool(it.content),
                "started_at": it.started_at.isoformat() if it.started_at else None,
                "finished_at": it.finished_at.isoformat() if it.finished_at else None,
            }
            for it in items
        ],
    }
