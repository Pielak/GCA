"""M01 — orquestrador de questionário iterativo.

Regras canônicas:
- Trigger: overall_score < 90 AND min(pilares) < 75.
- Convergência (D3): |overall_after - overall_before| < convergence_threshold (default 1.0).
- Inviabilidade (D4): ≥50% das respostas da iteração classificadas como 'not_applicable'.
- Score é atualizado APENAS pelo pipeline canônico (Arguidor → OCG Updater).
  Este service NÃO toca em ocg.overall_score — só lê e decide próxima iteração.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    CustomQuestionnaireIteration,
    OCG,
    Project,
    IngestedDocument,
    ArguiderAnalysis,
)
from app.services.iterative_questionnaire_generator import (
    build_iterative_prompt,
    parse_iterative_response,
)

logger = logging.getLogger(__name__)

OVERALL_TARGET = 90.0
PILLAR_DEFICIT_THRESHOLD = 75.0
DEFAULT_CONVERGENCE_THRESHOLD = 1.0
INFEASIBLE_RATIO = 0.5

_PILLAR_KEYS = [
    "P1_business_case", "P2_business_model", "P3_scope", "P4_quality",
    "P5_ux", "P6_legal", "P7_security",
]


async def _load_latest_ocg(db: AsyncSession, project_id: UUID) -> OCG | None:
    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(desc(OCG.version)).limit(1)
    )
    return result.scalar_one_or_none()


def _extract_pillar_scores(ocg_data: dict | None) -> dict[str, float]:
    """Usa a mesma convenção canônica de `ocg_updater_service._extract_pillar_score`."""
    if not isinstance(ocg_data, dict):
        return {}
    pillars_block = ocg_data.get("PILLAR_SCORES") or {}
    if not isinstance(pillars_block, dict):
        return {}
    out: dict[str, float] = {}
    for key in _PILLAR_KEYS:
        val = pillars_block.get(key)
        if isinstance(val, dict) and "score" in val:
            try:
                out[key] = float(val["score"])
            except (TypeError, ValueError):
                continue
    return out


def _extract_overall(ocg_data: dict | None) -> float | None:
    if not isinstance(ocg_data, dict):
        return None
    comp = ocg_data.get("COMPOSITE_SCORE")
    if isinstance(comp, dict) and "value" in comp:
        try:
            return float(comp["value"])
        except (TypeError, ValueError):
            return None
    return None


async def compute_status_snapshot(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """Status público consumido pelo router + frontend."""
    ocg = await _load_latest_ocg(db, project_id)
    overall: float | None = None
    deficit: dict[str, float] = {}
    if ocg:
        ocg_json = json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
        overall = _extract_overall(ocg_json)
        pillars = _extract_pillar_scores(ocg_json)
        deficit = {k: v for k, v in pillars.items() if v < PILLAR_DEFICIT_THRESHOLD}

    latest_result = await db.execute(
        select(CustomQuestionnaireIteration)
        .where(CustomQuestionnaireIteration.project_id == project_id)
        .order_by(desc(CustomQuestionnaireIteration.iteration))
        .limit(1)
    )
    latest: CustomQuestionnaireIteration | None = latest_result.scalar_one_or_none()

    eligible = (
        overall is not None
        and overall < OVERALL_TARGET
        and len(deficit) > 0
        and (latest is None or latest.status in ("converged", "infeasible", "answered", "superseded"))
    )
    has_pending = latest is not None and latest.status == "pending"
    converged = latest is not None and latest.status == "converged"

    return {
        "overall": overall,
        "deficit_pillars": deficit,
        "eligible_for_iteration": eligible,
        "has_pending": has_pending,
        "converged": converged,
        "latest_iteration": (
            {
                "id": str(latest.id),
                "iteration": latest.iteration,
                "status": latest.status,
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
                "target_pillars": latest.target_pillars or [],
                "question_count": len(latest.questions or []),
                "overall_before": float(latest.overall_before) if latest.overall_before is not None else None,
                "overall_after": float(latest.overall_after) if latest.overall_after is not None else None,
            } if latest else None
        ),
    }


async def _collect_arguider_gaps(
    db: AsyncSession, project_id: UUID, target_pillars: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Agrega module_candidates/gatekeeper_items do Arguidor por pilar."""
    result = await db.execute(
        select(ArguiderAnalysis)
        .join(IngestedDocument, IngestedDocument.id == ArguiderAnalysis.document_id)
        .where(IngestedDocument.project_id == project_id)
        .order_by(desc(ArguiderAnalysis.created_at))
        .limit(20)
    )
    analyses = result.scalars().all()
    gaps_by_pillar: dict[str, list[dict[str, Any]]] = {p: [] for p in target_pillars}
    for a in analyses:
        mc = a.module_candidates
        if isinstance(mc, str):
            try:
                mc = json.loads(mc)
            except json.JSONDecodeError:
                continue
        if not isinstance(mc, list):
            continue
        for item in mc:
            if not isinstance(item, dict):
                continue
            pillar = item.get("pillar") or item.get("affected_pillar")
            if pillar in gaps_by_pillar and len(gaps_by_pillar[pillar]) < 8:
                gaps_by_pillar[pillar].append({
                    "name": str(item.get("name") or item.get("title") or "")[:120],
                    "severity": item.get("severity") or "info",
                })
    return gaps_by_pillar


async def generate_iteration(
    db: AsyncSession,
    project_id: UUID,
) -> CustomQuestionnaireIteration:
    """Gera nova iteração. Chama LLM via llm_low_criticality (provider do projeto)."""
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError("Projeto não encontrado")

    snap = await compute_status_snapshot(db, project_id)
    if not snap["eligible_for_iteration"]:
        raise ValueError(
            "Projeto não elegível pra nova iteração (overall >= 90 ou nenhum pilar < 75 "
            "ou última iteração ainda pending)."
        )

    target_pillars_scores: dict[str, float] = snap["deficit_pillars"]
    overall_before: float = snap["overall"] or 0.0

    last_result = await db.execute(
        select(CustomQuestionnaireIteration)
        .where(CustomQuestionnaireIteration.project_id == project_id)
        .order_by(desc(CustomQuestionnaireIteration.iteration))
        .limit(1)
    )
    last = last_result.scalar_one_or_none()
    next_iteration = (last.iteration + 1) if last else 1

    # Agrega TODAS as perguntas de iterações anteriores pra o LLM não repetir.
    # Inclui todas, mesmo superseded, porque semântica idêntica é o que matamos.
    prior_result = await db.execute(
        select(CustomQuestionnaireIteration.iteration, CustomQuestionnaireIteration.questions)
        .where(CustomQuestionnaireIteration.project_id == project_id)
        .order_by(CustomQuestionnaireIteration.iteration.asc())
    )
    previously_asked: list[str] = []
    for iter_num, questions_json in prior_result.all():
        if not questions_json:
            continue
        for q in questions_json:
            if isinstance(q, dict) and q.get("text"):
                previously_asked.append(f"[Iter {iter_num}] {q['text']}")

    gaps = await _collect_arguider_gaps(db, project_id, list(target_pillars_scores.keys()))
    # M02 — remove gaps cuja decision_key já tem default aplicado
    # (defesa em profundidade: o Arguidor já filtra na análise nova, mas
    # iterações antigas podem ter module_candidates stale que referenciam
    # gaps agora resolvidos).
    try:
        from app.services.domain_defaults_resolver import list_applied
        applied = await list_applied(db, project_id, include_contested=False)
        applied_kind_tokens = set()
        for a in applied:
            # Pega o sufixo após o ponto (ex: 'retention.civil_cases' → 'civil_cases')
            # + versão normalizada com espaços
            key = a.decision_key
            tail = key.split(".", 1)[-1] if "." in key else key
            applied_kind_tokens.add(tail.lower())
            applied_kind_tokens.add(tail.replace("_", " ").lower())
        if applied_kind_tokens:
            for pillar, gap_list in list(gaps.items()):
                filtered = []
                for g in (gap_list or []):
                    if not isinstance(g, dict):
                        filtered.append(g)
                        continue
                    gap_text = (
                        str(g.get("name", ""))
                        + " "
                        + str(g.get("description", ""))
                    ).lower()
                    if any(tok in gap_text for tok in applied_kind_tokens if tok):
                        continue
                    filtered.append(g)
                gaps[pillar] = filtered
    except Exception:  # noqa: BLE001
        # Se a filtragem falhar, deixa gaps como está — Task 5 já filtrou na origem.
        pass
    prev_feedback = None
    if last and last.status in ("answered", "infeasible") and last.overall_after is not None:
        prev_feedback = (
            f"Iter {last.iteration}: overall {last.overall_before}→{last.overall_after}; "
            f"razão de 'não se aplica' {float(last.not_applicable_ratio or 0):.0%}."
        )

    prompt = build_iterative_prompt(
        project_name=project.name,
        iteration=next_iteration,
        overall_before=overall_before,
        target_pillars_scores=target_pillars_scores,
        arguider_gaps_by_pillar=gaps,
        previous_iteration_feedback=prev_feedback,
        previously_asked_questions=previously_asked,
    )

    from app.services.llm_low_criticality import resolve_llm_config, call_llm

    llm_cfg = await resolve_llm_config(db, project_id)
    if llm_cfg is None:
        raise ValueError("Nenhum provedor de IA configurado para este projeto.")

    raw_text = await call_llm(
        config=llm_cfg,
        system_prompt="Você é um analista de produto sênior, falante nativo de PT-BR. Responda em JSON estrito quando solicitado.",
        user_prompt=prompt,
        max_tokens=8192,  # perguntas individualizadas podem gerar N itens — cabe mais
        temperature=0.3,
        log_context="m01_iterative_questionnaire",
    )

    try:
        parsed = parse_iterative_response(raw_text)
    except Exception as exc:
        logger.error("m01.parse_failed", extra={"project_id": str(project_id), "error": str(exc)})
        raise ValueError(f"LLM retornou JSON inválido: {exc}")

    ocg = await _load_latest_ocg(db, project_id)
    ocg_version_before = ocg.version if ocg else None

    iteration_row = CustomQuestionnaireIteration(
        project_id=project_id,
        iteration=next_iteration,
        status="pending",
        target_pillars=list(target_pillars_scores.keys()),
        questions=parsed["questions"],
        ocg_version_before=ocg_version_before,
        overall_before=Decimal(str(overall_before)),
        convergence_threshold=Decimal(str(DEFAULT_CONVERGENCE_THRESHOLD)),
    )
    db.add(iteration_row)
    await db.commit()
    await db.refresh(iteration_row)
    return iteration_row


async def evaluate_convergence_after_ocg_update(
    db: AsyncSession,
    project_id: UUID,
    trigger_document_id: UUID,
) -> None:
    """Chamado pelo OCG Updater quando o doc fonte do update é uma resposta de iteração."""
    iter_result = await db.execute(
        select(CustomQuestionnaireIteration)
        .where(CustomQuestionnaireIteration.answer_document_id == trigger_document_id)
        .order_by(desc(CustomQuestionnaireIteration.iteration))
        .limit(1)
    )
    row = iter_result.scalar_one_or_none()
    if row is None or row.status != "pending":
        return

    ocg = await _load_latest_ocg(db, project_id)
    if ocg is None:
        return
    ocg_json = json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
    overall_after = _extract_overall(ocg_json)

    before_val = float(row.overall_before) if row.overall_before is not None else 0.0
    threshold = float(row.convergence_threshold) if row.convergence_threshold is not None else DEFAULT_CONVERGENCE_THRESHOLD
    delta = abs((overall_after or 0.0) - before_val)

    row.ocg_version_after = ocg.version
    row.overall_after = Decimal(str(overall_after)) if overall_after is not None else None

    if row.not_applicable_ratio is not None and float(row.not_applicable_ratio) >= INFEASIBLE_RATIO:
        row.status = "infeasible"
        row.converged = False
    elif overall_after is not None and overall_after >= OVERALL_TARGET:
        row.status = "converged"
        row.converged = True
    elif delta < threshold:
        row.status = "converged"
        row.converged = True
    else:
        row.status = "answered"
        row.converged = False

    await db.commit()
    logger.info(
        "m01.convergence_evaluated",
        extra={
            "project_id": str(project_id),
            "iteration": row.iteration,
            "status": row.status,
            "delta": delta,
        },
    )

    # Pipeline ativo (feedback canônico `feedback_ativo_passivo_pipeline`):
    # se a iteração terminou como `answered` (não convergiu e não é inviável)
    # e o projeto ainda está elegível (overall<90 AND min pilar<75),
    # **gera automaticamente** a próxima iteração com os novos gaps revelados
    # pelo Arguidor. Badge do sidebar volta a alertar e o usuário vê perguntas
    # renovadas sem precisar clicar "Gerar". Falha silenciosa — usuário pode
    # gerar manualmente como fallback se a auto-regeneração quebrar.
    if row.status == "answered":
        try:
            snap = await compute_status_snapshot(db, project_id)
            if snap.get("eligible_for_iteration"):
                new_row = await generate_iteration(db, project_id)
                logger.info(
                    "m01.auto_regenerated_after_answer",
                    extra={
                        "project_id": str(project_id),
                        "previous_iteration": row.iteration,
                        "new_iteration": new_row.iteration,
                        "new_iteration_id": str(new_row.id),
                    },
                )
        except Exception as regen_exc:  # noqa: BLE001
            logger.warning(
                "m01.auto_regeneration_failed",
                extra={
                    "project_id": str(project_id),
                    "previous_iteration": row.iteration,
                    "error": str(regen_exc),
                },
            )


def classify_not_applicable_ratio(canonical_text: str) -> float:
    """Heurística simples: contagem de 'não se aplica' / 'nsa' vs total de perguntas referenciadas."""
    if not canonical_text:
        return 0.0
    lowered = canonical_text.lower()
    import re
    question_markers = re.findall(r"\bq\d+[\.\:]", lowered)
    total = max(1, len(question_markers))
    nsa = lowered.count("não se aplica") + lowered.count("n/a") + lowered.count(" nsa ")
    return min(1.0, nsa / total)
