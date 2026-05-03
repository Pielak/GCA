"""MVP 34 — Reversão de propagação ao deletar documento.

Quando GP soft-deleta um `IngestedDocument`, este service reverte os efeitos
cumulativos do doc no OCG, backlog e tabelas auxiliares — sem violar a regra
canônica §2.4 ("OCG não contrai por ingestão"). É operação de gestão, não
de análise: reversão por DELEÇÃO da fonte, não por análise negativa.

Operação atômica:
  1. Marca `ingested_documents.deleted_at` (soft-delete)
  2. Recompute do OCG (ignora doc deletado via JOIN — Fase 34.1)
  3. Cria nova versão OCG com `change_type='REVERT_DOCUMENT_DELETE'`
  4. `ocg_delta_log` row com `trigger_source='document_revert'`
  5. Cleanup tabelas auxiliares: `conflicts_pending_review`,
     `chunk_errors_pending_review`, `persona_follow_up_questions`
  6. Auto-archive `module_candidates` órfãos (parse JSON `source_document_ids`)
  7. Audit event `DOCUMENT_REVERTED` em `audit_log_global` (hash chain)
  8. Salva resultado em `ingested_documents.revert_metadata` (JSONB com schema CHECK)

Idempotência dupla (Arq-S2):
  - Layer 1: `_try_claim_task_lease` Redis bloqueia execução simultânea
  - Layer 2: verifica `deleted_at IS NOT NULL` no início → retorna `already_reverted`

Aviso de regressão de maturidade (M3): quando `score_after < SCORE_MATURIDADE`
(95), payload `revert_metadata.maturity_warning` é populado em PT-BR.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, text as sql_text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IngestedDocument,
    ModuleCandidate,
    OCG,
)
from app.services.audit_service import AuditEvents, AuditService
from app.services.ocg_gate import SCORE_MATURIDADE
from app.services.ocg_updater_service import _compute_status

logger = structlog.get_logger(__name__)


REVERT_TRIGGER_SOURCE = "document_revert"


class AlreadyRevertedError(Exception):
    """Doc já tem `deleted_at` setado — operação é no-op idempotente."""


class DocumentNotFoundError(Exception):
    """Doc não existe no DB."""


async def revert_document_propagation(
    db: AsyncSession,
    document_id: UUID,
    project_id: UUID,
    actor_id: Optional[UUID],
    reason: str,
) -> dict[str, Any]:
    """Operação principal de reversão.

    Args:
        db: AsyncSession ativa (escopo da task Celery — sessão dedicada).
        document_id: doc a soft-deletar.
        project_id: projeto dono (validação canônica).
        actor_id: user que disparou (None = sistema).
        reason: 'manual'|'lgpd'|'smoke_cleanup' (validado por CHECK no DB).

    Returns:
        dict com chaves canônicas:
          - status: 'reverted' | 'already_reverted'
          - score_before, score_after, version_from, version_to
          - modules_archived: list[str] de IDs
          - maturity_warning: str | None
          - delta_fields_reverted: list[str]

    Raises:
        DocumentNotFoundError: doc inexistente.
        AlreadyRevertedError: doc já marcado deleted_at (caller decide UX).
    """
    # ── 1. Carregar doc + validar idempotência (Arq-S2 layer 2) ───────────
    # IMPORTANTE: idempotência via `revert_metadata IS NOT NULL` (job COMPLETO),
    # não via `deleted_at`. O endpoint `delete_document` já marca `deleted_at`
    # sync antes de enfileirar (necessário para LGPD — doc some imediato das
    # queries). Se usássemos `deleted_at` aqui, o job nunca processaria.
    doc = await db.get(IngestedDocument, document_id)
    if doc is None:
        raise DocumentNotFoundError(f"Documento {document_id} não encontrado")
    if doc.project_id != project_id:
        raise DocumentNotFoundError(
            f"Documento {document_id} não pertence ao projeto {project_id}"
        )
    if doc.revert_metadata is not None:
        logger.info(
            "document_revert.already_reverted",
            document_id=str(document_id),
            project_id=str(project_id),
            completed_at=doc.revert_metadata.get("completed_at"),
        )
        raise AlreadyRevertedError(
            f"Documento {document_id} já foi revertido em {doc.revert_metadata.get('completed_at')}"
        )

    # ── 2. Snapshot do OCG atual (score_before, version_from) ─────────────
    ocg_now = await _load_latest_ocg(db, project_id)
    score_before = float(ocg_now.overall_score or 0) if ocg_now else 0.0
    version_from = ocg_now.version if ocg_now else 0
    pillar_before = _snapshot_pillar_scores(ocg_now)

    logger.info(
        "document_revert.start",
        document_id=str(document_id),
        project_id=str(project_id),
        actor_id=str(actor_id) if actor_id else None,
        reason=reason,
        score_before=score_before,
        version_from=version_from,
    )

    # ── 3. SOFT-DELETE do doc (idempotente: se endpoint já marcou via
    #     `IngestionService.delete_document`, mantém os valores existentes.
    #     Se chamado via outro caller, marca aqui). Precisa estar antes do
    #     recompute para que `_load_persona_scores` já exclua via JOIN
    #     deleted_at IS NULL. ──
    if doc.deleted_at is None:
        doc.deleted_at = datetime.now(timezone.utc)
        doc.deleted_by = actor_id
        doc.deleted_reason = reason
        await db.flush()

    # ── 4. Recompute do OCG ignorando o doc soft-deleted ──────────────────
    # `_load_persona_scores` (MVP 34) faz JOIN com IngestedDocument WHERE
    # deleted_at IS NULL — agregado natural sem o doc.
    from app.services.ocg_updater_service import OCGUpdaterService

    updater = OCGUpdaterService(db)
    persona_scores = await updater._load_persona_scores(project_id)

    # Reconstrói `PILLAR_SCORES` no formato canônico
    new_pillar_scores: dict[str, dict[str, float]] = {}
    if persona_scores:
        for key, value in persona_scores.items():
            if key == "overall_score":
                continue
            if isinstance(value, dict) and "score" in value:
                new_pillar_scores[key] = {"score": float(value["score"])}

    # Overall = média dos pillars com score
    if new_pillar_scores:
        scores_list = [v["score"] for v in new_pillar_scores.values()]
        new_overall = round(sum(scores_list) / len(scores_list), 1)
    else:
        new_overall = 0.0

    # ── 5. Diff dos campos revertidos (para audit + payload) ──────────────
    delta_fields_reverted = _diff_pillars(pillar_before, new_pillar_scores)

    # ── 6. Versionamento canônico: OCG é UPDATE in-place (1 row por
    #     projeto, version incrementa). Mesmo padrão de OCGUpdaterService. ──
    if ocg_now is None:
        # Caso degenerado: revert em projeto sem OCG. Não há base para recompute.
        # Marca apenas o doc como deletado e retorna.
        logger.warning(
            "document_revert.no_ocg_to_revert",
            project_id=str(project_id),
            document_id=str(document_id),
        )
        version_to = 0
        score_after = 0.0
    else:
        # Atualiza ocg_data com novo PILLAR_SCORES
        try:
            ocg_data = json.loads(ocg_now.ocg_data) if ocg_now.ocg_data else {}
        except (ValueError, TypeError):
            ocg_data = {}

        # Override do PILLAR_SCORES com o agregado novo
        ocg_data["PILLAR_SCORES"] = new_pillar_scores

        # Status canônico (Active/At-Risk/Blocked)
        pillar_floats = {
            int(k.replace("p", "").split("_")[0]): v["score"]
            for k, v in new_pillar_scores.items()
            if k.startswith("p")
        }
        new_status, new_blocking = _compute_status(pillar_floats, new_overall)

        # UPDATE in-place + incrementa version (mesmo padrão do OCGUpdaterService).
        # Constraint UNIQUE em questionnaire_id impede INSERT de nova row.
        ocg_now.overall_score = new_overall
        ocg_now.p1_business_score = new_pillar_scores.get("p1_business_score", {}).get("score")
        ocg_now.p2_rules_score = new_pillar_scores.get("p2_rules_score", {}).get("score")
        ocg_now.p3_features_score = new_pillar_scores.get("p3_features_score", {}).get("score")
        ocg_now.p4_nfr_score = new_pillar_scores.get("p4_nfr_score", {}).get("score")
        ocg_now.p5_architecture_score = new_pillar_scores.get("p5_architecture_score", {}).get("score")
        ocg_now.p6_data_score = new_pillar_scores.get("p6_data_score", {}).get("score")
        ocg_now.p7_security_score = new_pillar_scores.get("p7_security_score", {}).get("score")
        ocg_now.status = new_status
        ocg_now.is_blocking = new_blocking
        ocg_now.ocg_data = json.dumps(ocg_data, ensure_ascii=False)
        ocg_now.version = ocg_now.version + 1
        ocg_now.change_type = "REVERT_DOCUMENT_DELETE"
        await db.flush()

        version_to = ocg_now.version
        score_after = new_overall

        # ── 7. ocg_delta_log row ──────────────────────────────────────────
        await _insert_delta_log(
            db,
            project_id=project_id,
            document_id=document_id,
            version_from=version_from,
            version_to=version_to,
            actor_id=actor_id,
            delta_fields_reverted=delta_fields_reverted,
            new_ocg_data=ocg_data,
        )

    # ── 8. Cleanup de tabelas auxiliares (DBA-M5) ─────────────────────────
    await _cleanup_aux_tables(db, document_id)

    # ── 9. Auto-archive de module_candidates órfãos (DBA-S3) ──────────────
    modules_archived = await _archive_orphan_modules(db, document_id)

    # ── 10. Aviso de regressão de maturidade (M3) ─────────────────────────
    maturity_warning = None
    if score_after < SCORE_MATURIDADE:
        maturity_warning = (
            f"OCG regrediu de score {score_before} para {score_after} — "
            f"CodeGen volta a ser bloqueado pelo gate de maturidade "
            f"(limiar {SCORE_MATURIDADE}). Continue ingerindo documentos "
            f"para amadurecer o OCG novamente."
        )

    # ── 11. Audit event canônico DOCUMENT_REVERTED (Arq-S5) ───────────────
    await AuditService(db).log_event(
        event_type=AuditEvents.DOCUMENT_REVERTED,
        resource_type="document",
        resource_id=document_id,
        actor_id=actor_id,
        details={
            "project_id": str(project_id),
            "document_id": str(document_id),
            "deleted_reason": reason,
            "score_before": score_before,
            "score_after": score_after,
            "version_from": version_from,
            "version_to": version_to,
            "modules_archived": [str(mid) for mid in modules_archived],
            "delta_fields_reverted": delta_fields_reverted,
            "maturity_warning": maturity_warning,
        },
    )

    # ── 12. Persiste payload em revert_metadata (JSONB com CHECK) ─────────
    revert_payload = {
        "score_before": score_before,
        "score_after": score_after,
        "version_from": version_from,
        "version_to": version_to,
        "delta_fields_reverted": delta_fields_reverted,
        "modules_archived": [str(mid) for mid in modules_archived],
        "maturity_warning": maturity_warning,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.revert_metadata = revert_payload
    await db.flush()
    await db.commit()

    logger.info(
        "document_revert.success",
        document_id=str(document_id),
        project_id=str(project_id),
        score_before=score_before,
        score_after=score_after,
        version_to=version_to,
        modules_archived_count=len(modules_archived),
        maturity_regression=(score_after < SCORE_MATURIDADE),
    )

    return {
        "status": "reverted",
        **revert_payload,
    }


# =============================================================================
# Helpers privados
# =============================================================================


async def _load_latest_ocg(db: AsyncSession, project_id: UUID) -> Optional[OCG]:
    """Carrega versão mais recente do OCG do projeto."""
    stmt = (
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(OCG.version.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _snapshot_pillar_scores(ocg: Optional[OCG]) -> dict[str, dict[str, float]]:
    """Extrai PILLAR_SCORES do `ocg.ocg_data` JSON ou retorna {}."""
    if ocg is None or not ocg.ocg_data:
        return {}
    try:
        data = json.loads(ocg.ocg_data)
        scores = data.get("PILLAR_SCORES", {})
        if isinstance(scores, dict):
            return scores
    except (ValueError, TypeError):
        pass
    return {}


def _diff_pillars(
    before: dict[str, dict[str, float]],
    after: dict[str, dict[str, float]],
) -> list[str]:
    """Lista os pillars que mudaram (incluindo removidos e adicionados)."""
    changed = []
    all_keys = set(before.keys()) | set(after.keys())
    for key in sorted(all_keys):
        b = before.get(key, {}).get("score")
        a = after.get(key, {}).get("score")
        if b != a:
            changed.append(key)
    return changed


async def _insert_delta_log(
    db: AsyncSession,
    *,
    project_id: UUID,
    document_id: UUID,
    version_from: int,
    version_to: int,
    actor_id: Optional[UUID],
    delta_fields_reverted: list[str],
    new_ocg_data: dict[str, Any],
) -> None:
    """Insere row em `ocg_delta_log` com `trigger_source='document_revert'`."""
    fields_changed_payload = {
        "operation": "revert_document_delete",
        "fields_reverted": delta_fields_reverted,
    }
    summary = (
        f"Revert do documento {document_id} — {len(delta_fields_reverted)} pillars recalculados"
    )
    snapshot = json.dumps(new_ocg_data, ensure_ascii=False)
    await db.execute(
        sql_text(
            """
            INSERT INTO ocg_delta_log (
                id, project_id, document_id, ocg_version_from, ocg_version_to,
                fields_changed, change_summary, trigger_source, source,
                ocg_snapshot, changed_by, created_at
            ) VALUES (
                gen_random_uuid(), :pid, :did, :vfrom, :vto,
                :fields, :summary, :trigger, :source,
                :snapshot, :actor, NOW()
            )
            """
        ),
        {
            "pid": str(project_id),
            "did": str(document_id),
            "vfrom": version_from,
            "vto": version_to,
            "fields": json.dumps(fields_changed_payload, ensure_ascii=False),
            "summary": summary,
            "trigger": REVERT_TRIGGER_SOURCE,
            "source": REVERT_TRIGGER_SOURCE,
            "snapshot": snapshot,
            "actor": str(actor_id) if actor_id else None,
        },
    )


async def _cleanup_aux_tables(db: AsyncSession, document_id: UUID) -> None:
    """Marca registros auxiliares do doc como expired/archived (DBA-M5/S2).

    - persona_follow_up_questions: status='expired' (status já no enum)
    - conflicts_pending_review: status='archived_doc_deleted'
    - chunk_errors_pending_review: status='archived_doc_deleted'
    """
    # 1. persona_follow_up_questions
    await db.execute(
        sql_text(
            "UPDATE persona_follow_up_questions "
            "SET status = 'expired', updated_at = NOW() "
            "WHERE document_id = :did AND status = 'pending'"
        ),
        {"did": str(document_id)},
    )

    # 2. conflicts_pending_review (verifica se a tabela existe e tem document_id)
    try:
        await db.execute(
            sql_text(
                "UPDATE conflicts_pending_review "
                "SET status = 'archived_doc_deleted' "
                "WHERE document_id = :did AND status = 'pending'"
            ),
            {"did": str(document_id)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "document_revert.cleanup_conflicts_pending_review_skipped",
            document_id=str(document_id),
            error=str(exc),
        )

    # 3. chunk_errors_pending_review
    try:
        await db.execute(
            sql_text(
                "UPDATE chunk_errors_pending_review "
                "SET status = 'archived_doc_deleted' "
                "WHERE document_id = :did AND status = 'pending'"
            ),
            {"did": str(document_id)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "document_revert.cleanup_chunk_errors_pending_review_skipped",
            document_id=str(document_id),
            error=str(exc),
        )


async def _archive_orphan_modules(
    db: AsyncSession,
    document_id: UUID,
) -> list[UUID]:
    """Auto-archive de `module_candidates` órfãos (Arq-S3 / DBA-S3).

    Estratégia (parse JSON em Python — `source_document_ids` é TEXT JSON):
      - Lista TODOS os module_candidates que mencionam `document_id` na
        coluna TEXT (busca textual ampla com `LIKE`)
      - Para cada um, parseia `source_document_ids` (JSON list)
      - Se for ÚNICA fonte → status='archived'
      - Se for MÚLTIPLAS fontes → remove `document_id` da lista, mantém status

    Retorna lista de IDs dos módulos arquivados (NÃO os modificados).
    """
    doc_id_str = str(document_id)
    candidates_q = await db.execute(
        select(ModuleCandidate)
        .where(ModuleCandidate.source_document_ids.like(f"%{doc_id_str}%"))
    )
    candidates = candidates_q.scalars().all()

    archived: list[UUID] = []
    for mc in candidates:
        try:
            source_ids = json.loads(mc.source_document_ids or "[]")
            if not isinstance(source_ids, list):
                continue
        except (ValueError, TypeError):
            continue

        # Filtra source_ids pra remover o doc_id
        filtered = [sid for sid in source_ids if str(sid) != doc_id_str]

        if len(filtered) == 0 and len(source_ids) > 0:
            # Fonte única → archive
            mc.status = "archived"
            mc.source_document_ids = "[]"
            archived.append(mc.id)
        elif len(filtered) < len(source_ids):
            # Múltiplas fontes — remove só este doc, mantém candidato
            mc.source_document_ids = json.dumps(filtered, ensure_ascii=False)
        # Se filtered == source_ids, é match falso-positivo (LIKE pegou substring)

    if archived:
        await db.flush()

    return archived
