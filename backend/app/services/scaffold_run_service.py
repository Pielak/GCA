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

from app.db.database import AsyncSessionLocal
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

    MVP-B (2026-04-25): provider+modelo agora são DINÂMICOS por projeto via
    `resolve_llm_config(prefer_ollama=False)`. Antes, scaffold ignorava
    `ProjectSettings.llm_provider/llm_model` e sempre usava
    `app_settings.ANTHROPIC_MODEL` global. Agora respeita escolha do owner
    (Anthropic/OpenAI/DeepSeek/Grok/Gemini) e clampa max_tokens ao cap
    conhecido do modelo (Opus 4.6 = 32k, DeepSeek = 8k, etc.).
    """
    from app.db.database import AsyncSessionLocal
    from app.services.llm_low_criticality import (
        resolve_llm_config,
        call_llm,
        clamp_max_tokens,
        get_provider_max_concurrency,
    )
    from app.services.ocg_gate import evaluate_ocg_maturity

    # Carrega project_id pra resolver config — buscamos a run primeiro.
    async with AsyncSessionLocal() as db:
        run_for_pid = await db.get(ScaffoldRun, run_id)
        if run_for_pid is None:
            return
        project_id_for_llm = run_for_pid.project_id

    # DT-082: gate de maturidade do OCG na entrada do worker (defesa em
    # profundidade). Se algum caller futuro enfileirar a run sem passar pelo
    # endpoint HTTP que já chama check_ocg_maturity_gate, o worker recusa
    # sem levantar exceção (não tem caller HTTP).
    #
    # DT-083 (2026-05-03): originalmente DT-082 marcava `run.status='blocked'`,
    # mas a CHECK constraint `scaffold_runs_status_check` só aceita
    # {pending,planning,generating,completed,failed,applied,applying}. Para
    # evitar migration de schema, usamos `status='failed'` + prefixo canônico
    # `[ocg_gate:<level>]` no `error` — a métrica Prometheus
    # `gca_codegen_blocked_total{block_level}` em metrics_service parseia o
    # prefixo. Bloqueio do gate ainda é sinalizado por log canônico.
    async with AsyncSessionLocal() as db:
        gate_result = await evaluate_ocg_maturity(project_id_for_llm, db)
    if gate_result["blocked"]:
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run:
                run.status = "failed"
                run.error = (
                    f"[ocg_gate:{gate_result['block_level']}] "
                    f"{gate_result['blocking_reason']}"
                )
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
        logger.warning(
            "scaffold_run.blocked_by_ocg_gate",
            run_id=str(run_id),
            project_id=str(project_id_for_llm),
            block_level=gate_result["block_level"],
            overall_score=gate_result["overall_score"],
        )
        return

    async with AsyncSessionLocal() as db:
        llm_cfg = await resolve_llm_config(db, project_id_for_llm, prefer_ollama=False)
    if llm_cfg is None:
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run:
                run.status = "failed"
                run.error = "Nenhum provedor de IA configurado para este projeto. Configure em /admin ou /settings."
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
        return

    # Fase 1 — planning. Aceita 'pending' (start) OU 'generating' (resume após
    # restart do worker). Em resume, pula direto pra Fase 2 com items pending.
    resume_mode = False
    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        if run is None:
            logger.warning("scaffold_run.not_found", run_id=str(run_id))
            return
        if run.status == "generating":
            # Resume: plan já existe, items já estão no DB. Pula planning.
            resume_mode = True
            logger.info("scaffold_run.resume", run_id=str(run_id))
        elif run.status != "pending":
            logger.info("scaffold_run.skip_not_pending", run_id=str(run_id), status=run.status)
            return
        else:
            run.status = "planning"
            run.last_progress_at = datetime.now(timezone.utc)
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
            design_md=design_md_content,  # MVP-N
        )

    # Em resume mode, pula toda a fase planning — items + plan_summary
    # já estão persistidos no DB. Vai direto pra Fase 2 (loop topológico).
    if not resume_mode:
        try:
            plan_max_tokens = clamp_max_tokens(llm_cfg["model"], 32000)
            plan_raw = await call_llm(
                config=llm_cfg,
                system_prompt="Você é um analista sênior de arquitetura de software, falante nativo de PT-BR.",
                user_prompt=prompt,
                max_tokens=plan_max_tokens,
                temperature=0.2,
                log_context="scaffold.plan",
                auto_continue=True,   # MVP-J fase 2 — continuation se truncado
                expect_json=True,     # MVP-J fase 3 — reprompt se JSON ruim
            )
            plan_tokens = 0  # call_llm não devolve usage; será logado pelo provider
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

        # Camada B — sanitiza depends_on de cada item antes de persistir.
        valid_paths = {str(it.get("path", "")).strip() for it in valid_items}
        valid_paths.discard("")

        def _clean_deps(raw_deps: Any) -> List[str]:
            if not isinstance(raw_deps, list):
                return []
            out = []
            for d in raw_deps:
                if not isinstance(d, str):
                    continue
                d = d.strip()
                if d and d in valid_paths:
                    out.append(d)
            return out

        # Persiste plano + items pending
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run is None:
                return
            run.status = "generating"
            run.plan_summary = summary_text
            run.plan_tokens_used = plan_tokens
            run.total_items = len(valid_items)
            run.last_progress_at = datetime.now(timezone.utc)
            for ordinal, it in enumerate(valid_items):
                cleaned = _clean_deps(it.get("depends_on"))
                db.add(ScaffoldRunItem(
                    run_id=run_id,
                    ordinal=ordinal,
                    path=str(it.get("path", ""))[:500],
                    file_type=str(it.get("file_type") or "")[:40] or None,
                    purpose=(str(it.get("purpose") or "")[:500]) or None,
                    est_lines=int(it.get("est_lines") or 0) or None,
                    status="pending",
                    depends_on=json.dumps(cleaned, ensure_ascii=False),
                ))
            await db.commit()

    # Fase 2 — gerar conteúdo item-a-item NA ORDEM TOPOLÓGICA (camada B).
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

    # MVP-N (2026-04-26): tenta carregar docs/DESIGN.md do repo Git do
    # projeto. Best-effort — se Git config faltando, file não existe ou
    # leitura falha, segue sem (comportamento idêntico ao pré-MVP-N).
    design_md_content: str | None = None
    try:
        from app.services.git_service import GitService
        async with AsyncSessionLocal() as db_md:
            git_svc = GitService(db_md)
            for candidate_path in ("docs/DESIGN.md", "DESIGN.md"):
                content = await git_svc.get_file_content(run_for_pid.project_id, candidate_path)
                if content and content.strip():
                    design_md_content = content
                    logger.info(
                        "scaffold_run.design_md_loaded",
                        run_id=str(run_id),
                        path=candidate_path,
                        chars=len(content),
                    )
                    break
    except Exception as exc:  # noqa: BLE001
        logger.info("scaffold_run.design_md_unavailable", run_id=str(run_id), reason=str(exc)[:100])

        items_q = await db.execute(
            select(ScaffoldRunItem)
            .where(ScaffoldRunItem.run_id == run_id)
            .order_by(ScaffoldRunItem.ordinal.asc())
        )
        all_items = items_q.scalars().all()
        all_paths = [it.path for it in all_items]

    # Toposort de Kahn. Ordem resultante: items sem dep primeiro, depois
    # quem depende deles, propagando. Empate desempata por ordinal (estável).
    deps_by_path: Dict[str, List[str]] = {}
    item_by_path: Dict[str, ScaffoldRunItem] = {}
    for it in all_items:
        try:
            deps_by_path[it.path] = json.loads(it.depends_on or "[]") or []
        except json.JSONDecodeError:
            deps_by_path[it.path] = []
        item_by_path[it.path] = it

    in_degree: Dict[str, int] = {p: 0 for p in deps_by_path}
    rdeps: Dict[str, List[str]] = {p: [] for p in deps_by_path}
    for path, deps in deps_by_path.items():
        for d in deps:
            if d in in_degree:
                in_degree[path] += 1
                rdeps[d].append(path)

    # ordinal map pra desempate estável
    ordinal_by_path = {it.path: it.ordinal for it in all_items}
    ready = sorted(
        (p for p, deg in in_degree.items() if deg == 0),
        key=lambda p: ordinal_by_path[p],
    )
    topo_order: List[str] = []
    while ready:
        current = ready.pop(0)
        topo_order.append(current)
        for nxt in rdeps[current]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                # insert mantendo ordem por ordinal
                inserted = False
                for i, p in enumerate(ready):
                    if ordinal_by_path[p] > ordinal_by_path[nxt]:
                        ready.insert(i, nxt)
                        inserted = True
                        break
                if not inserted:
                    ready.append(nxt)

    if len(topo_order) != len(all_items):
        # ciclo detectado — Kahn não consome todos os nós
        cyclic = [p for p, deg in in_degree.items() if deg > 0]
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            run.status = "failed"
            run.error = (
                f"Ciclo de dependências entre arquivos do plano: "
                f"{', '.join(cyclic[:5])}{'...' if len(cyclic) > 5 else ''}. "
                "Reexecute pra um novo plano sem ciclos."
            )
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
        logger.error("scaffold_run.cycle_detected", run_id=str(run_id), cyclic=cyclic[:10])
        return

    # Reordena all_items na ordem topológica calculada
    all_items_topo = [item_by_path[p] for p in topo_order if p in item_by_path]
    logger.info(
        "scaffold_run.toposort_ok",
        run_id=str(run_id),
        items=len(all_items_topo),
        first_5=topo_order[:5],
    )

    # Em resume, parte de onde estava: já conta done/failed pré-existentes,
    # pula items já feitos. Em start novo, começa do zero.
    completed = sum(1 for it in all_items_topo if it.status == "done")
    failed = sum(1 for it in all_items_topo if it.status == "failed")

    # Escreve contador imediatamente pra UI ver status real (resume mostra
    # progresso prévio sem precisar esperar o próximo item completar).
    if resume_mode and (completed + failed) > 0:
        async with AsyncSessionLocal() as db:
            run = await db.get(ScaffoldRun, run_id)
            if run is not None:
                run.completed_items = completed
                run.failed_items = failed
                run.last_progress_at = datetime.now(timezone.utc)
                await db.commit()

    # Camada C — buffer de content já gerado, indexado por path. Em resume
    # mode, popula com content de items already done pra peers funcionarem.
    generated_content_by_path: Dict[str, str] = {}
    if resume_mode:
        async with AsyncSessionLocal() as db:
            done_items = (await db.execute(
                select(ScaffoldRunItem).where(
                    ScaffoldRunItem.run_id == run_id,
                    ScaffoldRunItem.status == "done",
                )
            )).scalars().all()
            for d in done_items:
                if d.content:
                    generated_content_by_path[d.path] = d.content

    # MVP-C (2026-04-25): paralelismo respeitando depends_on.
    # Antes loop processava 1 item por vez (10h+ no AJA com 164 arquivos).
    # Agora cálculo de "waves" topológicas: items sem dep entre si rodam
    # em paralelo até SCAFFOLD_PARALLELISM. Wave N+1 só começa quando wave
    # N termina (peer_contents fica completo).
    import asyncio as _asyncio
    from app.core.config import settings as _app_settings

    # MVP-J fase 4 (2026-04-25): clamp ao RPM do provider em uso.
    # SCAFFOLD_PARALLELISM=5 é teto do operador, mas se provider tem rate
    # limit menor (ex: Grok 30 RPM = ~2 paralelas seguras), get_provider_max_concurrency
    # reduz pra não estourar 429 e disparar retry recorrente.
    requested_parallelism = max(1, getattr(_app_settings, "SCAFFOLD_PARALLELISM", 5))
    parallelism = get_provider_max_concurrency(llm_cfg["provider"], requested_parallelism)
    if parallelism != requested_parallelism:
        logger.info(
            "scaffold_run.parallelism_adjusted",
            run_id=str(run_id),
            provider=llm_cfg["provider"],
            requested=requested_parallelism,
            applied=parallelism,
            reason="rate_limit_safety",
        )

    # Calcula em qual wave cada path pertence: max(wave dos deps) + 1.
    # Items sem dep ficam na wave 0. Toposort já garante que deps vêm antes.
    wave_by_path: Dict[str, int] = {}
    for path in topo_order:
        deps = [d for d in deps_by_path.get(path, []) if d in wave_by_path]
        wave_by_path[path] = (max((wave_by_path[d] for d in deps), default=-1) + 1)

    # Agrupa items por wave preservando ordinal pra desempate previsível.
    max_wave = max(wave_by_path.values(), default=-1)
    waves: List[List[ScaffoldRunItem]] = [[] for _ in range(max_wave + 1)]
    for it in all_items_topo:
        waves[wave_by_path[it.path]].append(it)

    logger.info(
        "scaffold_run.waves_computed",
        run_id=str(run_id),
        total_items=len(all_items_topo),
        waves=len(waves),
        wave_sizes=[len(w) for w in waves],
        parallelism=parallelism,
    )

    async def _process_one_item(it_snapshot: ScaffoldRunItem) -> tuple[str, Optional[str], str]:
        """Processa 1 item end-to-end: marca generating → LLM → parseia → salva.

        Retorna `(path, content_or_None, status_final)`. status_final ∈
        {'done', 'failed'}. Cada chamada usa session DB própria pra não
        compartilhar entre coroutines paralelas.
        """
        # Pula se já terminado (resume)
        if it_snapshot.status in ("done", "failed", "skipped"):
            return (it_snapshot.path, None, it_snapshot.status)

        # Marca generating + started_at
        async with AsyncSessionLocal() as db_g:
            it = await db_g.get(ScaffoldRunItem, it_snapshot.id)
            it.status = "generating"
            it.started_at = datetime.now(timezone.utc)
            await db_g.commit()

        deps_for_item = deps_by_path.get(it_snapshot.path, [])
        peer_contents: Dict[str, str] = {
            d: generated_content_by_path[d]
            for d in deps_for_item
            if d in generated_content_by_path
        }
        item_prompt = build_item_prompt(
            project_name=project.name,
            project_slug=project.slug,
            stack=stack,
            architecture=architecture,
            item_path=it_snapshot.path,
            item_purpose=it_snapshot.purpose or "(sem propósito declarado)",
            item_file_type=it_snapshot.file_type or "txt",
            peer_contents=peer_contents,
            rnf_contracts=rnf_contracts,
            design_tokens=design_tokens,
            build_errors=getattr(it_snapshot, "build_errors", None),  # MVP-K
            design_md=design_md_content,  # MVP-N
        )

        item_max_tokens = clamp_max_tokens(llm_cfg["model"], 32000)
        try:
            item_raw = await call_llm(
                config=llm_cfg,
                system_prompt="Você é um engenheiro de software sênior, falante nativo de PT-BR. Responda em JSON estrito.",
                user_prompt=item_prompt,
                max_tokens=item_max_tokens,
                temperature=0.3,
                log_context="scaffold.item",
                auto_continue=True,   # MVP-J fase 2 — continuation se truncado
                expect_json=True,     # MVP-J fase 3 — reprompt se JSON ruim
            )
        except Exception as exc:  # noqa: BLE001
            async with AsyncSessionLocal() as db_e:
                it = await db_e.get(ScaffoldRunItem, it_snapshot.id)
                it.status = "failed"
                it.error = f"LLM erro: {str(exc)[:300]}"
                it.finished_at = datetime.now(timezone.utc)
                await db_e.commit()
            return (it_snapshot.path, None, "failed")

        parsed_item = _parse_llm_json(item_raw)
        async with AsyncSessionLocal() as db_s:
            it = await db_s.get(ScaffoldRunItem, it_snapshot.id)
            if parsed_item is None:
                it.status = "failed"
                it.error = "JSON inválido"
                it.tokens_used = 0
                it.finished_at = datetime.now(timezone.utc)
                await db_s.commit()
                return (it_snapshot.path, None, "failed")
            content = parsed_item.get("content") or ""
            notes = (parsed_item.get("notes") or "")[:1000] or None
            it.content = content
            it.notes = notes
            it.tokens_used = 0
            if content.strip():
                it.status = "done"
                final_status = "done"
            else:
                it.status = "failed"
                it.error = "LLM devolveu content vazio"
                final_status = "failed"
            it.finished_at = datetime.now(timezone.utc)
            await db_s.commit()
            return (it_snapshot.path, content if final_status == "done" else None, final_status)

    # Semaphore limita concorrência mesmo dentro de wave grande
    sem = _asyncio.Semaphore(parallelism)

    async def _bounded_process(it: ScaffoldRunItem) -> tuple[str, Optional[str], str]:
        async with sem:
            return await _process_one_item(it)

    # Itera waves; dentro de cada, gather paralelo. Heartbeat ao fim de cada
    # wave (em vez de por item) — reduz pressão no DB e ainda mantém watchdog
    # informado (worst case = duração da wave maior).
    for wave_idx, wave in enumerate(waves):
        pending = [it for it in wave if it.status not in ("done", "failed", "skipped")]
        if not pending:
            continue
        results = await _asyncio.gather(
            *[_bounded_process(it) for it in pending],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                failed += 1
                continue
            path, content, st = r
            if st == "done" and content is not None:
                completed += 1
                generated_content_by_path[path] = content
            elif st == "failed":
                failed += 1

        # Heartbeat por wave: contadores na run + last_progress_at.
        async with AsyncSessionLocal() as db_hb:
            run_hb = await db_hb.get(ScaffoldRun, run_id)
            if run_hb is not None:
                run_hb.completed_items = completed
                run_hb.failed_items = failed
                run_hb.last_progress_at = datetime.now(timezone.utc)
                await db_hb.commit()
        logger.info(
            "scaffold_run.wave_done",
            run_id=str(run_id),
            wave_idx=wave_idx,
            wave_size=len(pending),
            completed_so_far=completed,
            failed_so_far=failed,
        )

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


async def execute_apply(run_id: UUID, user_id: UUID) -> dict:
    """Executor canônico do apply assíncrono (MVP-E, 2026-04-25).

    Espelha o que o handler HTTP `apply_scaffold_run` fazia inline antes
    da migração pra Celery. Disparado via `scaffold_apply_executor.delay`.
    Pré-requisitos (perms, git_config, status check) já foram validados
    pelo handler antes de enfileirar — esta função assume que está
    autorizada a rodar.

    Heartbeat: atualiza `apply_committed/apply_failed/last_progress_at`
    a cada arquivo commitado, pra watchdog enxergar progresso e UI
    mostrar contadores incrementais via polling existente.

    Retorna o mesmo shape do antigo `ScaffoldApplyResponse` mais o
    qa_artifacts_created. Em caso de erro fatal (sem ser falha de commit
    de arquivo), marca a run como `failed` e levanta a exception pro
    Celery registrar.
    """
    from app.models.base import (
        Project,
        ScaffoldRun,
        ScaffoldRunItem,
        TestArtifact,
    )
    from app.routers.code_generation import (
        _missing_required_docstring,
        _notify_scaffold_completion,
    )
    from app.services.audit_service import AuditEvents, AuditService
    from app.services.git_service import GitService
    import re as _re

    TEST_FILE_RE = _re.compile(
        r"(^|/)(tests?/|test_[^/]+\.py$|[^/]+_test\.[a-z]+$|[^/]+\.test\.[a-z]+$|[^/]+\.spec\.[a-z]+$)",
        _re.IGNORECASE,
    )

    # Carrega contexto base + items done numa transação curta.
    async with AsyncSessionLocal() as db:
        run = await db.get(ScaffoldRun, run_id)
        if run is None:
            return {"committed": 0, "failed": 0, "results": [], "qa_artifacts_created": 0}
        project = await db.get(Project, run.project_id)
        items_q = await db.execute(
            select(ScaffoldRunItem)
            .where(ScaffoldRunItem.run_id == run_id, ScaffoldRunItem.status == "done")
            .order_by(ScaffoldRunItem.ordinal.asc())
        )
        done_items_snap = [
            {"id": it.id, "path": it.path, "content": it.content or ""}
            for it in items_q.scalars().all()
        ]
        project_id = run.project_id
        project_name = project.name

    # Loop de commit com heartbeat. Cada arquivo: 1 commit + 1 update no
    # DB. GitService.commit_file faz a chamada HTTP no GitHub/GitLab.
    committed = 0
    failed = 0
    results: list[dict] = []
    qa_files: list[dict] = []  # path + content pra criar TestArtifact depois

    async with AsyncSessionLocal() as db:
        git_service = GitService(db)
        for snap_item in done_items_snap:
            path = snap_item["path"]
            content = snap_item["content"]
            if not path or not content:
                continue
            if _missing_required_docstring(path, content):
                failed += 1
                results.append({
                    "path": path,
                    "status": "error",
                    "error": "Docstring obrigatória ausente (re-validação no apply).",
                })
            else:
                git_result = await git_service.commit_file(
                    project_id=project_id,
                    file_path=path,
                    content=content,
                    commit_message=f"feat(codegen): {path}",
                )
                if git_result.get("success"):
                    committed += 1
                    results.append({"path": path, "status": "ok"})
                    if TEST_FILE_RE.search(path):
                        qa_files.append({"path": path, "content": content})
                else:
                    failed += 1
                    results.append({
                        "path": path,
                        "status": "error",
                        "error": git_result.get("message"),
                    })

            # Heartbeat por arquivo: nova session, update curtinho, commit.
            # Mantém apply_committed/failed/last_progress_at sempre frescos
            # pro watchdog não considerar zombie e pra UI mostrar progresso.
            async with AsyncSessionLocal() as db_hb:
                run_hb = await db_hb.get(ScaffoldRun, run_id)
                if run_hb is not None:
                    run_hb.apply_committed = committed
                    run_hb.apply_failed = failed
                    run_hb.last_progress_at = datetime.now(timezone.utc)
                    await db_hb.commit()

    logger.info(
        "scaffold.apply_commits_finished",
        project_id=str(project_id),
        run_id=str(run_id),
        committed=committed,
        failed=failed,
    )

    # Notificação + TestArtifacts + audit + transição de status.
    async with AsyncSessionLocal() as db:
        await _notify_scaffold_completion(db, project_id, project_name, committed, failed)

        qa_artifacts_created = 0
        try:
            for qa in qa_files:
                db.add(TestArtifact(
                    project_id=project_id,
                    module_id=None,
                    test_type="unit",
                    title=qa["path"].rsplit("/", 1)[-1][:255],
                    description=f"Teste gerado pelo scaffold run {run_id} em {qa['path']}",
                    file_path=qa["path"],
                    content=str(qa["content"]),
                    status="pending_review",
                    created_by=user_id,
                ))
                qa_artifacts_created += 1
        except Exception as qa_err:  # noqa: BLE001
            logger.warning(
                "scaffold_run.apply_qa_failed",
                run_id=str(run_id),
                error=str(qa_err),
            )

        run = await db.get(ScaffoldRun, run_id)
        if run is not None:
            run.status = "applied"
            run.applied_at = datetime.now(timezone.utc)
            run.apply_committed = committed
            run.apply_failed = failed
            run.last_progress_at = datetime.now(timezone.utc)

            await AuditService(db).log_codegen_event(
                event_type=AuditEvents.CODEGEN_SCAFFOLD_APPLIED,
                actor_id=user_id,
                project_id=project_id,
                action="apply_scaffold_run",
                files_count=committed,
                extra={
                    "run_id": str(run_id),
                    "failed": failed,
                    "qa_artifacts_created": qa_artifacts_created,
                },
            )
        await db.commit()

    # Arguidor #2 — best-effort, falha não invalida o apply.
    if committed > 0:
        try:
            from app.tasks.scaffold import code_audit_executor
            code_audit_executor.send(str(run_id))
            logger.info(
                "scaffold_run.audit_triggered",
                run_id=str(run_id),
                project_id=str(project_id),
            )
        except Exception as audit_err:  # noqa: BLE001
            logger.warning(
                "scaffold_run.audit_trigger_failed",
                run_id=str(run_id),
                error=str(audit_err),
            )

    return {
        "committed": committed,
        "failed": failed,
        "results": results,
        "qa_artifacts_created": qa_artifacts_created,
    }


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
