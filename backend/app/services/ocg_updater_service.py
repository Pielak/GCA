"""
OCGUpdaterService — Atualiza o OCG de forma reativa após análise do Arguidor.

Fluxo:
  1. Carrega OCG atual do projeto
  2. Chama LLM (DeepSeek/Anthropic) com OCG atual + análise do Arguidor
  3. Faz parse da resposta: updated_ocg, changes[], change_type, context_health
  4. Atualiza o registro OCG (incrementa versão, salva novos dados)
  5. Registra delta no ocg_delta_log
  6. Registra billing
  7. Emite evento de auditoria OCG_UPDATED
  8. Em caso de falha do LLM: marca status como ocg_pending (nunca corrompe o OCG)
"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.base import OCG, OCGDeltaLog, Project
from app.services.ai_billing_service import AIBillingService
from app.services.ai_key_resolver import AIKeyResolver
from app.services.audit_service import AuditService
from app.services.iterative_questionnaire_service import (
    evaluate_convergence_after_ocg_update,
)
from app.services.ocg_compactor import compact_ocg_for_prompt
from app.services.ocg_delta_applier import apply_deltas

logger = structlog.get_logger(__name__)

# Evento de auditoria dedicado ao updater
OCG_UPDATED = "OCG_UPDATED"

# Trigger sources canônicos (constantes — não usar literais em chamadas)
TRIGGER_N8N = "document_ingestion_n8n"
TRIGGER_CELERY = "document_ingestion"  # mantém backward compat com o caminho Celery existente
TRIGGER_HITL_FOLLOWUP = "hitl_followup"  # respostas a perguntas em aberto via upload .md offline

# Pesos canônicos dos 7 pilares (skill gca-ocg-engine; soma = 1.00).
_PILLAR_WEIGHTS: Dict[int, float] = {
    1: 0.10, 2: 0.15, 3: 0.20, 4: 0.20, 5: 0.15, 6: 0.10, 7: 0.10,
}

# Mapa pilar → coluna do model OCG.
_PILLAR_COLUMNS: Dict[int, str] = {
    1: "p1_business_score",
    2: "p2_rules_score",
    3: "p3_features_score",
    4: "p4_nfr_score",
    5: "p5_architecture_score",
    6: "p6_data_score",
    7: "p7_security_score",
}


# Pydantic schemas para validação da resposta do LLM (DT-002: schema validation)
class OCGDeltaSchema(BaseModel):
    """Schema de um delta individual."""
    op: str = Field(..., description="Operação: 'replace' ou 'append'")
    path: str = Field(..., description="Path em dot-notation (ex: PILLAR_SCORES.P1.score)")
    old_value: Optional[Any] = Field(None, description="Valor anterior (replace)")
    new_value: Optional[Any] = Field(None, description="Novo valor (replace)")
    value: Optional[Any] = Field(None, description="Valor (append)")
    reasoning: Optional[str] = Field(None, description="Justificativa da mudança")

    class Config:
        extra = "allow"  # Permite campos adicionais


class ContextHealthSchema(BaseModel):
    """Schema de context_health."""
    depth: float = Field(0.5, ge=0.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    quality: float = Field(0.5, ge=0.0, le=1.0)

    class Config:
        extra = "allow"


class OCGLLMResponseSchema(BaseModel):
    """Schema da resposta esperada do LLM para consolidação OCG."""
    deltas: List[OCGDeltaSchema] = Field(default_factory=list, description="Lista de operações")
    change_type: str = Field("UPDATE", description="Tipo de mudança: EXPAND, CONTRACT, UPDATE")
    context_health: Optional[ContextHealthSchema] = Field(None, description="Saúde do contexto")

    class Config:
        extra = "allow"  # Permite campos adicionais não especificados


def _filter_negative_score_deltas(
    deltas: List[Dict[str, Any]],
    current_ocg: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Bloqueia deltas que tentem BAIXAR score de pilar.

    Reforma 2026-04-25: GCA é construtor; OCG só cresce. Score só sobe via
    Arguidor. Pra baixar é necessário owner explicitamente revogar (não
    via pipeline automático).

    Retorna (mantidos, bloqueados). Bloqueados ganham `_reason='negative_score_blocked'`.
    """
    kept: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for d in deltas or []:
        if not isinstance(d, dict):
            kept.append(d)
            continue
        path = d.get("path") or ""
        op = d.get("op") or "replace"
        # Só nos importamos com replace em PILLAR_SCORES.*.score
        if op != "replace" or not path.startswith("PILLAR_SCORES.") or not path.endswith(".score"):
            kept.append(d)
            continue
        # Lê valor atual no OCG
        try:
            cursor = current_ocg
            for seg in path.split("."):
                if isinstance(cursor, dict):
                    cursor = cursor.get(seg)
                else:
                    cursor = None
                    break
            old_val = float(cursor) if cursor is not None else None
            new_val = float(d.get("value")) if d.get("value") is not None else None
        except (TypeError, ValueError):
            kept.append(d)
            continue
        if old_val is not None and new_val is not None and new_val < old_val:
            entry = dict(d)
            entry["_reason"] = "negative_score_blocked"
            blocked.append(entry)
        else:
            kept.append(d)
    return kept, blocked


def _extract_pillar_score(pillars: Dict[str, Any], pillar_num: int) -> Optional[float]:
    """Lookup tolerante na estrutura canônica PILLAR_SCORES.

    O JSON real do OCG usa chaves descritivas: ``P1_business_case``,
    ``P2_compliance``, ``P3_scope``, ``P4_performance``, ``P5_architecture``,
    ``P6_data``, ``P7_security``. O system prompt do updater também aceita
    forma curta ``P1``, ``P2``, etc. Esta função aceita ambas (case-insensitive)
    e retorna o ``score`` numérico do pilar, ou None se não localizar.
    """
    if not isinstance(pillars, dict):
        return None
    prefix = f"P{pillar_num}_".upper()
    short = f"P{pillar_num}".upper()
    for key, val in pillars.items():
        if not isinstance(val, dict) or not isinstance(key, str):
            continue
        ku = key.upper()
        if ku == short or ku.startswith(prefix):
            score = val.get("score")
            if score is None:
                continue
            try:
                return float(score)
            except (TypeError, ValueError):
                return None
    return None


def _compute_status(pillar_scores: Dict[int, float], overall: Optional[float]) -> Tuple[str, bool]:
    """Status canônico do OCG (skill gca-ocg-engine, contrato §6 / §10):

      - P2 < 70 OR P7 < 70 → BLOCKED (is_blocking=True)
      - overall >= 90       → READY
      - overall >= 75       → NEEDS_REVIEW
      - overall  < 75       → AT_RISK
    """
    p2 = pillar_scores.get(2)
    p7 = pillar_scores.get(7)
    if (p2 is not None and p2 < 70) or (p7 is not None and p7 < 70):
        return "BLOCKED", True
    if overall is None:
        return "AT_RISK", False
    if overall >= 90:
        return "READY", False
    if overall >= 75:
        return "NEEDS_REVIEW", False
    return "AT_RISK", False


async def _auto_generate_in_background(project_id: UUID, ocg_data: Dict[str, Any]) -> None:
    """Roda DeliverableRegistry.auto_generate_pending em sessão própria,
    fire-and-forget. Falha não derruba o flow do OCG."""
    try:
        from app.db.database import AsyncSessionLocal
        from app.services.deliverable_registry import DeliverableRegistry

        async with AsyncSessionLocal() as db:
            registry = DeliverableRegistry(db)
            result = await registry.auto_generate_pending(project_id, ocg_data, re_verify=True)
            await db.commit()
            logger.info(
                "ocg_updater.auto_generate_done",
                project_id=str(project_id),
                generated=len(result.get("generated", [])),
                skipped=len(result.get("skipped", [])),
                errors=len(result.get("errors", [])),
            )
    except Exception as exc:  # noqa: BLE001
        import traceback
        logger.warning(
            "ocg_updater.auto_generate_background_failed",
            project_id=str(project_id),
            error=str(exc) or repr(exc),
            error_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )

# Lock por project_id para serializar updates concorrentes do OCG.
# Sem isto, N tasks paralelas leem version=V, todas escrevem version=V+1,
# causando lost updates (a última commit vence). Com lock asyncio, cada
# task aguarda a anterior antes de ler o OCG, então cada uma vê a versão
# mais recente e incrementa corretamente (V → V+1 → V+2 → ...).
# Limitação: lock é per-process. Em deployment multi-worker (gunicorn N
# workers), conflitos entre workers ainda são possíveis — para isso
# precisaria de lock distribuído (Redis SETNX) ou version_id_col do SA.
_PROJECT_LOCKS: Dict[UUID, asyncio.Lock] = {}


def _get_project_lock(project_id: UUID) -> asyncio.Lock:
    """Lock dedicado por project_id, criado on-demand."""
    lock = _PROJECT_LOCKS.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_LOCKS[project_id] = lock
    return lock


class OCGUpdaterService:
    """
    Serviço reativo que atualiza o OCG após análise do Arguidor.
    Nunca corrompe o OCG existente — em caso de falha do LLM apenas sinaliza.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.billing_service = AIBillingService(db)
        self.audit_service = AuditService(db)

    # ------------------------------------------------------------------ #
    #  Ponto de entrada principal                                          #
    # ------------------------------------------------------------------ #

    async def update_ocg_from_arguider(
        self,
        project_id: UUID,
        arguider_analysis: Dict[str, Any],
        document_id: Optional[UUID] = None,
        actor_id: Optional[UUID] = None,
        trigger_source: str = "document_ingestion",
    ) -> Optional[Dict[str, Any]]:
        """
        Atualiza o OCG do projeto com base na análise do Arguidor.

        Serializado por project_id via asyncio.Lock para evitar lost updates
        quando múltiplos documentos do mesmo projeto disparam updates em paralelo
        (cenário típico: ingestão de N markdowns de um repo externo).

        Args:
            project_id: UUID do projeto
            arguider_analysis: Dict com a análise completa do Arguidor
            actor_id: UUID do usuário que disparou a ação (opcional)
            document_id: UUID do documento ingerido que originou o update (opcional)

        Returns:
            Dict com: ocg_id, version_from, version_to, change_type, context_health, changes
        """
        # Métricas de contenção asyncio.Lock (DBA F1 R3): warn quando
        # aquisição > 100ms — sinal de concorrência alta entre corrotinas
        # do mesmo worker para o mesmo project_id.
        import time as _time
        _t0 = _time.monotonic()
        async with _get_project_lock(project_id):
            _wait_ms = (_time.monotonic() - _t0) * 1000
            if _wait_ms > 100:
                logger.warning(
                    "ocg_updater.asyncio_lock_contention",
                    wait_ms=round(_wait_ms, 1),
                    project_id=str(project_id),
                    trigger_source=trigger_source,
                )
            return await self._update_ocg_from_arguider_locked(
                project_id=project_id,
                arguider_analysis=arguider_analysis,
                document_id=document_id,
                actor_id=actor_id,
                trigger_source=trigger_source,
            )

    async def _update_ocg_from_arguider_locked(
        self,
        project_id: UUID,
        arguider_analysis: Dict[str, Any],
        document_id: Optional[UUID],
        actor_id: Optional[UUID],
        trigger_source: str,
    ) -> Optional[Dict[str, Any]]:
        """Implementação real — sempre executada sob _get_project_lock(project_id)."""
        logger.info(
            "ocg_updater.start",
            project_id=str(project_id),
            actor_id=str(actor_id) if actor_id else None,
        )

        # === FASE A: leitura + LLM SEM advisory lock cross-process ===
        # Mudança 2026-05-05: chamada LLM movida pra FORA do advisory lock.
        # Antes: pg_advisory_xact_lock era pego ANTES do _call_llm; LLM lento
        # (DeepSeek com prompt 27k+ chars leva 30s-3min) segurava o lock e
        # bloqueava o dispatcher de ingestão (que usa A MESMA chave de lock
        # `hashtextextended(project_id, 0)`). Resultado: fila de reanalyze
        # travava com wait_ms_dispatch crescendo (128s → 227s observados).
        #
        # Padrão correto: ler snapshot, chamar LLM (slow, sem lock), depois
        # acquirir lock pra re-load + apply_deltas + commit. Como OCG é
        # monotônico (§2.4) e deltas são path-replace, o re-load tolera
        # avanço concorrente — apply_deltas aplica nas chaves que existirem
        # no OCG fresh, e os filter_negative_score_deltas comparam contra o
        # OCG atual (mais seguro).

        # 1. Carregar snapshot do OCG (sem lock cross-process)
        ocg_snapshot = await self._load_current_ocg(project_id)
        if not ocg_snapshot:
            logger.warning("ocg_updater.ocg_not_found", project_id=str(project_id))
            # DT-AUDITORIA-002: Em vez de falhar, retornar status especial
            # indicando que OCG não está pronto (personas ainda analisando).
            # Caller pode colocar documento em fila de retry ou status "awaiting_ocg".
            return {
                "status": "awaiting_ocg",
                "project_id": str(project_id),
                "message": "OCG não disponível. Personas ainda estão analisando. Retry automático em breve.",
                "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
            }

        snapshot_version = ocg_snapshot.version
        current_ocg_data = json.loads(ocg_snapshot.ocg_data) if ocg_snapshot.ocg_data else {}

        # 2. Tentar chamar LLM para atualizar OCG.
        # Se falhar ou demorar >60s, usar scores das personas como fallback (provider-agnóstico).
        # DT-002 (perf): Fallback automático evita travamentos em LLM lento (DeepSeek com 25k+ tokens).
        import asyncio as _asyncio
        import time as _time_llm
        llm_result = None
        llm_timeout_secs = 60.0  # Fallback após 60s de LLM call
        _t0_llm = _time_llm.monotonic()
        try:
            llm_result = await _asyncio.wait_for(
                self._call_llm(current_ocg_data, arguider_analysis, project_id),
                timeout=llm_timeout_secs
            )
        except _asyncio.TimeoutError:
            logger.warning(
                "ocg_updater.llm_timeout_fallback",
                project_id=str(project_id),
                timeout_secs=llm_timeout_secs,
                llm_duration_secs=_time_llm.monotonic() - _t0_llm,
            )
            llm_result = None  # Força fallback
        except Exception as exc:
            logger.error(
                "ocg_updater.llm_failed",
                project_id=str(project_id),
                error=str(exc),
            )

        # Fallback: se LLM não produziu dados, usar scores das personas
        # (provider-agnóstico: funciona com DeepSeek, Ollama, Gemma, etc.)
        if llm_result is None or not llm_result.get("updated_ocg") or not llm_result.get("changes"):
            logger.info(
                "ocg_updater.using_persona_fallback",
                project_id=str(project_id),
                llm_result_status="empty" if llm_result is None else "no_changes",
            )
            persona_scores = await self._load_persona_scores(project_id)
            if persona_scores:
                current_ocg_data.update(persona_scores)
                # DT-081 fix: garante estrutura PILLAR_SCORES existe no current_ocg_data
                # antes de gerar deltas. ocg_data legado (pré-MVP 31) pode não ter — caso
                # em que apply_deltas com op="replace" falha com "segmento não encontrado".
                # Inicializa com baseline 50 para cada PX que vai receber delta.
                if "PILLAR_SCORES" not in current_ocg_data or not isinstance(
                    current_ocg_data.get("PILLAR_SCORES"), dict
                ):
                    current_ocg_data["PILLAR_SCORES"] = {}
                for key, value in persona_scores.items():
                    if key == "overall_score" or not isinstance(value, dict):
                        continue
                    if key not in current_ocg_data["PILLAR_SCORES"]:
                        current_ocg_data["PILLAR_SCORES"][key] = {"score": 50}
                # Constrói deltas canônicos (op=replace funciona porque path agora existe)
                # NOTA: chave canônica é "new_value", não "value" — _apply_replace
                # do ocg_delta_applier lê delta.get("new_value")
                fallback_deltas = []
                for key, value in persona_scores.items():
                    if key == "overall_score":
                        continue
                    if isinstance(value, dict) and "score" in value:
                        fallback_deltas.append({
                            "op": "replace",
                            "path": f"PILLAR_SCORES.{key}.score",
                            "new_value": value["score"],
                        })
                llm_result = {
                    "_from_fallback": True,  # marcador — _parse_llm_response detecta
                    "updated_ocg": current_ocg_data,
                    "deltas": fallback_deltas,  # formato canônico (não 'changes')
                    "change_type": "EXPAND",  # fallback sempre EXPAND (OCG só cresce)
                    "context_health": {"depth": 0.5, "confidence": 0.4, "quality": 0.5},
                }
            else:
                logger.warning(
                    "ocg_updater.no_persona_scores",
                    project_id=str(project_id),
                )
                # Sem deltas pra aplicar — marca pending no snapshot e retorna.
                # Não precisa do advisory lock: única escrita é status=pending,
                # e o ocg_snapshot já não vai virar nova versão.
                await self._mark_ocg_pending(ocg_snapshot)
                await self.db.commit()
                return {
                    "ocg_id": str(ocg_snapshot.id),
                    "version_from": snapshot_version,
                    "version_to": snapshot_version,
                    "status": "ocg_pending",
                    "error": "LLM call returned no data and no persona scores available",
                }

        # === FASE B: re-load + apply_deltas + commit COM advisory lock ===
        # LLM já respondeu (slow path concluído). Agora pega o lock pra
        # serializar a escrita do incremento de versão entre workers/processos.
        # Re-carrega o OCG porque outro worker pode ter avançado entre o
        # snapshot inicial (Fase A) e agora — comum quando 5 docs do mesmo
        # projeto rodam em paralelo (INGESTION_MAX_PARALLEL_PER_PROJECT=3+).
        # Métricas de contenção (DBA F1 R3): warn quando aquisição > 100ms.
        import time as _time2
        from sqlalchemy import text as _text
        _t0_adv = _time2.monotonic()
        await self.db.execute(
            _text("SELECT pg_advisory_xact_lock(hashtextextended(:pid, 0))"),
            {"pid": str(project_id)},
        )
        _wait_ms_adv = (_time2.monotonic() - _t0_adv) * 1000
        if _wait_ms_adv > 100:
            logger.warning(
                "ocg_updater.advisory_lock_contention",
                wait_ms=round(_wait_ms_adv, 1),
                project_id=str(project_id),
                trigger_source=trigger_source,
            )

        # Re-load OCG dentro do lock — pode ter avançado durante o LLM call.
        # apply_deltas é tolerante a path-replace em chaves que existirem;
        # OCG monotônico (§2.4) garante que score só sobe, então deltas do
        # snapshot ainda fazem sentido contra o fresh.
        ocg = await self._load_current_ocg(project_id)
        if ocg is None:
            # OCG sumiu entre Fase A e B (deletado?) — defensivo.
            logger.error(
                "ocg_updater.ocg_disappeared_during_llm",
                project_id=str(project_id),
                snapshot_version=snapshot_version,
            )
            return {
                "status": "ocg_disappeared",
                "project_id": str(project_id),
                "snapshot_version": snapshot_version,
            }
        version_from = ocg.version
        if version_from != snapshot_version:
            # Outro worker rodou entre snapshot e re-load. Não é erro —
            # OCG monotônico tolera; só registramos pra observabilidade.
            logger.info(
                "ocg_updater.ocg_advanced_during_llm",
                project_id=str(project_id),
                snapshot_version=snapshot_version,
                fresh_version=version_from,
            )
        # current_ocg_data passa a refletir o OCG fresh (não o snapshot).
        current_ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
        # Re-aplicar skeleton de PILLAR_SCORES no fresh data se vier do
        # fallback path (pode ter pilar novo no fresh que o snapshot não tinha).
        if llm_result.get("_from_fallback"):
            if "PILLAR_SCORES" not in current_ocg_data or not isinstance(
                current_ocg_data.get("PILLAR_SCORES"), dict
            ):
                current_ocg_data["PILLAR_SCORES"] = {}
            for delta in (llm_result.get("deltas") or []):
                path = delta.get("path") or ""
                # path = "PILLAR_SCORES.<KEY>.score"
                parts = path.split(".")
                if len(parts) == 3 and parts[0] == "PILLAR_SCORES":
                    pillar_key = parts[1]
                    if pillar_key not in current_ocg_data["PILLAR_SCORES"]:
                        current_ocg_data["PILLAR_SCORES"][pillar_key] = {"score": 50}

        # 3. Parse da resposta (formato delta)
        deltas, change_type, context_health = self._parse_llm_response(llm_result)

        # Reforma do Arguidor (2026-04-25): GCA é construtor, não auditor.
        # O auto-CONTRACT antigo punia score por gaps/show_stoppers/poor_definitions
        # — exatamente o viés pessimista que o owner do AJA documentou no feedback
        # `feedback_gca_construtor_nao_governanca`. Aqui mantemos apenas a métrica
        # de quality muito baixa como sinal de CONTRACT, e ainda assim só em modo
        # corporate. Em solo_owner/team, change_type vem do LLM sem pressão a baixar.
        ingestion_quality = (context_health or {}).get("quality", 0.5)

        gov_mode = "solo_owner"
        try:
            gov_row = await self.db.execute(
                select(Project.governance_mode).where(Project.id == project_id)
            )
            gov_mode = gov_row.scalar() or "solo_owner"
        except Exception:  # noqa: BLE001
            pass

        if gov_mode == "corporate" and isinstance(ingestion_quality, (int, float)) and ingestion_quality < 0.3:
            logger.warning(
                "ocg_updater.change_type_forced",
                project_id=str(project_id),
                original_type=change_type,
                forced_to="CONTRACT",
                reason=f"corporate mode + quality {ingestion_quality:.2f} < 0.3",
            )
            change_type = "CONTRACT"
            if context_health.get("confidence", 0.5) > 0.5:
                context_health["confidence"] = max(0.3, context_health.get("confidence", 0.5) - 0.2)

        # Filtro defensivo — bloqueia deltas que tentem BAIXAR score de pilar.
        # Defesa em profundidade: o prompt já instrui o Arguidor a NUNCA propor
        # score_delta negativo, mas o LLM ainda erra. Aqui rejeitamos deterministicamente
        # qualquer replace em PILLAR_SCORES.*.score onde value < old_value.
        deltas, blocked_negative = _filter_negative_score_deltas(deltas, current_ocg_data)
        if blocked_negative:
            samples = [
                {"path": d.get("path"), "old": d.get("old_value"), "tried": d.get("value")}
                for d in blocked_negative[:5]
            ]
            logger.info(
                "ocg_updater.negative_score_blocked",
                project_id=str(project_id),
                count=len(blocked_negative),
                samples=samples,
            )
            # DT-083: persistir evento via audit_log_global para que a métrica
            # Prometheus `gca_ocg_negative_delta_blocked_total{project}` consiga
            # derivar a contagem por query (sem prometheus_client).
            try:
                from app.services.audit_service import AuditEvents, AuditService

                await AuditService(self.db).log_event(
                    event_type=AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED,
                    resource_type="ocg",
                    resource_id=project_id,
                    actor_id=actor_id,
                    details={
                        "project_id": str(project_id),
                        "count": len(blocked_negative),
                        "samples": samples,
                    },
                )
            except Exception as audit_err:  # noqa: BLE001
                logger.warning(
                    "ocg_updater.audit_negative_delta_emit_failed",
                    project_id=str(project_id),
                    error=str(audit_err),
                )

        # 4. Aplicar deltas localmente (deterministic, sem LLM, com optimistic concurrency)
        updated_ocg, applied, rejected = apply_deltas(current_ocg_data, deltas)

        if rejected:
            logger.warning(
                "ocg_updater.deltas_rejected",
                project_id=str(project_id),
                rejected_count=len(rejected),
                applied_count=len(applied),
                samples=[
                    {"path": r.get("path"), "op": r.get("op"), "reason": r.get("_reason")}
                    for r in rejected[:5]
                ],
            )

        # Se LLM não propôs nenhum delta válido → não criar nova versão
        if not applied:
            logger.info(
                "ocg_updater.no_changes",
                project_id=str(project_id),
                rejected_count=len(rejected),
            )
            return {
                "ocg_id": str(ocg.id),
                "version_from": version_from,
                "version_to": version_from,
                "change_type": change_type,
                "context_health": context_health,
                "changes": [],
                "rejected_count": len(rejected),
                "status": "no_changes",
            }

        # changes no formato legado (para _log_delta + audit/notif)
        changes = [
            {
                "field": d.get("path", ""),
                "old_value": d.get("old_value"),
                "new_value": d.get("new_value") if d.get("op") == "replace" else d.get("value"),
                "reasoning": d.get("reasoning", ""),
            }
            for d in applied
        ]

        # Propaga seções estruturadas do ocg_global_delta (vindas das personas
        # via consolidador n8n) pro updated_ocg top-level — alimenta UI do OCG
        # (Stack, Architecture, Compliance, Testing, Security, Data). LLM updater
        # pode escrever também nessas chaves; aqui garantimos PISO determinístico
        # com merge raso (deep 1 nível) das contribuições das personas.
        _CANONICAL_SECTIONS = {
            "STACK_RECOMMENDATION", "ARCHITECTURE_OVERVIEW", "COMPLIANCE_CHECKLIST",
            "TESTING_REQUIREMENTS", "SECURITY_PROFILE", "DATA_PROFILE",
        }
        incoming_delta = (arguider_analysis or {}).get("ocg_global_delta") or {}
        for key, value in incoming_delta.items():
            if key not in _CANONICAL_SECTIONS or not isinstance(value, dict):
                continue
            existing = updated_ocg.get(key)
            if isinstance(existing, dict):
                merged = dict(existing)
                for sk, sv in value.items():
                    if sk not in merged:
                        merged[sk] = sv
                    elif isinstance(sv, dict) and isinstance(merged[sk], dict):
                        merged[sk] = {**merged[sk], **sv}
                    elif isinstance(sv, list) and isinstance(merged[sk], list):
                        merged[sk] = merged[sk] + [v for v in sv if v not in merged[sk]]
                updated_ocg[key] = merged
            else:
                updated_ocg[key] = dict(value)

        # 5. Atualizar o registro OCG
        version_to = version_from + 1
        await self._update_ocg_record(
            ocg=ocg,
            updated_ocg=updated_ocg,
            change_type=change_type,
            context_health=context_health,
            version_to=version_to,
        )

        # 6. Registrar delta no audit log
        await self._log_delta(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=version_from,
            ocg_version_to=version_to,
            changes=changes,
            changed_by=actor_id,
            trigger_source=trigger_source,
            ocg_snapshot=updated_ocg,
        )

        # 7. Registrar billing (contrato §6.4: registrar provedor/modelo reais).
        # Se o llm_result não trouxer esses metadados é bug do caller — logar
        # como "unknown" em vez de adivinhar via DEFAULT_AI_PROVIDER, que poderia
        # atribuir custo ao provedor errado.
        tokens_in = llm_result.get("tokens_input", 0)
        tokens_out = llm_result.get("tokens_output", 0)
        provider = llm_result.get("provider") or "unknown"
        model = llm_result.get("model") or "unknown"
        if provider == "unknown" or model == "unknown":
            logger.warning(
                "ocg_updater.billing_metadata_missing",
                project_id=str(project_id),
                provider=provider,
                model=model,
            )
        await self.billing_service.log_usage(
            project_id=project_id,
            provider=provider,
            model=model,
            operation="ocg_update",
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            actor_id=actor_id,
            metadata={"version_from": version_from, "version_to": version_to},
        )

        # 8. Evento de auditoria
        await self.audit_service.log_event(
            event_type=OCG_UPDATED,
            resource_type="ocg",
            actor_id=actor_id,
            resource_id=ocg.id,
            details={
                "project_id": str(project_id),
                "version_from": version_from,
                "version_to": version_to,
                "change_type": change_type,
                "changes_count": len(changes),
            },
        )

        await self.db.commit()

        # Sincroniza Definition of Done: o OCG pode ter adicionado/removido
        # entregáveis em DELIVERABLES. Mantém project_deliverables coerente.
        #
        # Tratamento de erro granular:
        #   - SQLAlchemyError (schema desatualizado, FK violation, etc):
        #     log ERROR + rollback + propaga? Não — o OCG já está commitado;
        #     fazemos rollback APENAS das escritas pendentes do registry e
        #     logamos ERROR (não warning) para observabilidade.
        #   - Outros (bug Python, etc): log ERROR com exc_info=True para
        #     diagnóstico — isso NÃO é "best-effort silencioso", é erro real.
        from sqlalchemy.exc import SQLAlchemyError
        try:
            from app.services.deliverable_registry import DeliverableRegistry
            registry = DeliverableRegistry(self.db)
            await registry.sync_from_ocg(project_id, updated_ocg)
            await self.db.commit()  # registry usa flush(); caller commita
        except SQLAlchemyError as exc:
            await self.db.rollback()
            logger.error(
                "ocg_updater.deliverable_sync_db_error",
                project_id=str(project_id),
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            logger.error(
                "ocg_updater.deliverable_sync_unexpected_error",
                project_id=str(project_id),
                error=str(exc) or repr(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

        # MVP 13 Fase 13.3c: auto-trigger via Celery. Retry bounded +
        # ACK late preservam a execução se worker cair no meio.
        from app.tasks.pipeline import auto_generate_task
        auto_generate_task.send(str(project_id), updated_ocg)

        # Notificar GPs do projeto sobre atualização do OCG
        try:
            from app.services.notification_inapp_service import InAppNotificationService
            from app.models.base import ProjectMember
            gps_result = await self.db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.role == "gp",
                    ProjectMember.is_active == True,
                )
            )
            notif = InAppNotificationService(self.db)
            for gp in gps_result.scalars().all():
                await notif.notify(
                    user_id=gp.user_id,
                    event_type="ocg_updated",
                    title=f"OCG atualizado (v{version_from} → v{version_to})",
                    message=f"{len(changes)} mudança(s) aplicada(s). Trigger: {change_type}.",
                    project_id=project_id,
                    resource_type="ocg",
                    resource_id=ocg.id,
                    link=f"/projects/{project_id}/ocg",
                    severity="info",
                )
        except Exception as notif_err:
            logger.warning("ocg_updater.notify_failed", error=str(notif_err))

        logger.info(
            "ocg_updater.success",
            project_id=str(project_id),
            version_from=version_from,
            version_to=version_to,
            change_type=change_type,
        )

        # MVP 9 Fase 9.1.1 — após atualizar o OCG, sincroniza itens de
        # Fundação no Roadmap. Service é idempotente (deduplica por
        # nome), logo safe rodar em cada update. Falha é não-fatal:
        # o update do OCG já commitou, foundation é best-effort.
        try:
            from app.services.roadmap_foundation_service import RoadmapFoundationService
            foundation_result = await RoadmapFoundationService(self.db).sync_foundation(project_id)
            logger.info(
                "ocg_updater.foundation_synced",
                project_id=str(project_id),
                created=foundation_result.get("created", 0),
                skipped=foundation_result.get("skipped", 0),
            )
        except Exception as foundation_exc:
            logger.warning(
                "ocg_updater.foundation_sync_failed",
                project_id=str(project_id),
                error=str(foundation_exc),
            )

        # M01 hook: se o documento-trigger é resposta de iteração do questionário
        # customizado, avalia convergência (atualiza status da iteração e decide
        # se próxima iteração é necessária). Não propaga exceções — falha no hook
        # não deve derrubar o update canônico do OCG.
        try:
            if document_id is not None:
                await evaluate_convergence_after_ocg_update(
                    self.db, project_id, document_id
                )
        except Exception as hook_exc:  # noqa: BLE001
            logger.warning(
                "m01.convergence_hook_failed",
                project_id=str(project_id),
                document_id=str(document_id) if document_id else None,
                error=str(hook_exc),
            )

        return {
            "ocg_id": str(ocg.id),
            "version_from": version_from,
            "version_to": version_to,
            "change_type": change_type,
            "context_health": context_health,
            "changes": changes,
            "status": "updated",
        }

    # ------------------------------------------------------------------ #
    #  Helpers internos                                                    #
    # ------------------------------------------------------------------ #

    async def _load_current_ocg(self, project_id: UUID) -> Optional[OCG]:
        """Carrega o OCG ativo do projeto, **forçando refresh do DB**.

        Concorrência é serializada em camada superior (asyncio.Lock por
        project_id em update_ocg_from_arguider).

        ``populate_existing=True`` é crítico: com ``expire_on_commit=False``
        no AsyncSessionLocal e sessão compartilhada com Arguidor (que já
        carregou o OCG anteriormente), a identity map cacheia a entidade.
        Sem populate_existing, o ORM devolve o OCG STALE (versão antiga),
        causando lost-update mesmo com asyncio.Lock funcionando.

        with_for_update() não pode ser usado aqui — a txn fica viva durante
        a chamada LLM (30s+) e drena o pool de conexões.

        Fase 2 Simplificação: OCGGlobal fallback removido. Pipeline agora
        usa apenas OCG legacy (gerado pelo questionário). Se não existe,
        retorna None e o caller faz retry automático.
        """
        stmt = (
            select(OCG)
            .where(OCG.project_id == project_id)
            .order_by(OCG.version.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        ocg = result.scalar_one_or_none()
        if ocg:
            return ocg

        # Fase 2 Simplificação: OCGGlobal removido. Pipeline agora usa
        # apenas OCG legacy (gerado pelo questionário). Se não existe,
        # retorna None e o caller (update_ocg_from_arguider) recebe
        # "awaiting_ocg" para retry automático.
        return None

    async def _load_persona_scores(self, project_id: UUID) -> dict:
        """Carrega scores das personas a partir de ocg_individual (cumulativo, MVP 31).

        Substitui a versão legacy que dependia de GatekeeperPersonaResponse +
        DocumentRouteMap (DT-081 — DocumentRouteMap não tem project_id).

        MVP 34 (Arq-S1/DBA): JOIN com `ingested_documents` filtrando
        `deleted_at IS NULL`. Pareceres de docs soft-deleted continuam em
        `ocg_individual` (sem cascade), mas não devem influenciar OCG.

        Retorna dict no formato Pillar Scores. Provider-agnóstico.
        """
        from app.models.base import IngestedDocument, OCGIndividual
        from app.services.ocg_consolidator_service import PERSONA_TO_PILLAR

        try:
            stmt = (
                select(OCGIndividual)
                .join(
                    IngestedDocument,
                    OCGIndividual.document_id == IngestedDocument.id,
                )
                .where(OCGIndividual.project_id == project_id)
                .where(OCGIndividual.status == "completed")  # exclui personas falhas
                .where(IngestedDocument.deleted_at.is_(None))  # MVP 34: ignora docs soft-deleted
                .order_by(OCGIndividual.created_at.desc())
            )
            result = await self.db.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                logger.info(
                    "ocg_updater.no_ocg_individual_rows",
                    project_id=str(project_id),
                    detail="Pipeline n8n não populou ocg_individual ainda — projeto novo ou Celery-only",
                )
                return {}

            # Invariante §2.4 (CLAUDE.md): "OCG só expande quando recebe
            # informação de valor. Nunca contrai por análise." Por pilar,
            # tomamos o MAX por persona ao longo de TODOS os docs (melhor
            # evidência já vista), depois média dos MAX. Doc novo só pode
            # subir o score (se trouxer evidência mais forte), nunca derrubar.
            #
            # Bug histórico (corrigido): média de todas as rows incluía rows
            # de docs novos com persona pouco-informada, diluindo o pilar.
            pillar_persona_max: dict[str, dict[str, float]] = {}
            conf_blocking_detected = False

            for row in rows:
                persona_tag_lower = (row.persona_id or "").lower()

                parecer = row.parecer or {}
                score = parecer.get("score", parecer.get("avg_score", 50))
                if not isinstance(score, (int, float)):
                    score = 50

                if persona_tag_lower == "conf" and score < 60:
                    conf_blocking_detected = True
                    logger.warning(
                        "ocg_updater.conf_blocking_score",
                        project_id=str(project_id),
                        score=score,
                        detail="CONF persona com score<60 detectada no fallback",
                    )

                if persona_tag_lower not in PERSONA_TO_PILLAR:
                    continue  # AUD fica de fora — router, sem score próprio

                pillar_key = PERSONA_TO_PILLAR[persona_tag_lower]
                bucket = pillar_persona_max.setdefault(pillar_key, {})
                prev = bucket.get(persona_tag_lower)
                if prev is None or float(score) > prev:
                    bucket[persona_tag_lower] = float(score)

            if not pillar_persona_max:
                return {}

            # Média dos MAX por persona dentro de cada pilar
            result_data = {}
            for pillar_key, persona_scores in pillar_persona_max.items():
                scores_list = list(persona_scores.values())
                avg = sum(scores_list) / len(scores_list)
                result_data[pillar_key] = {"score": round(avg, 1)}

            # Overall
            all_scores = [v["score"] for v in result_data.values()]
            if all_scores:
                result_data["overall_score"] = round(sum(all_scores) / len(all_scores), 1)

            logger.info(
                "ocg_updater.persona_scores_loaded",
                project_id=str(project_id),
                pillars=len(pillar_persona_max),
                personas_used=len(rows),
                conf_blocking=conf_blocking_detected,
            )
            return result_data

        except Exception as e:
            logger.error(
                "ocg_updater.load_persona_scores_failed",
                project_id=str(project_id),
                error=str(e),
                exc_info=True,
            )
            return {}

    async def _call_llm(
        self,
        current_ocg_data: Dict[str, Any],
        arguider_analysis: Dict[str, Any],
        project_id: UUID,
    ) -> Dict[str, Any]:
        """
        Chama o LLM com o OCG atual e a análise do Arguidor.

        Criticidade (contrato §6.2): **ALTA**. Atualização do OCG é
        consolidação/arbitragem de contexto — exige modelo premium.

        DT-033: Camada Projeto (contrato §6.6 Contexto B). Ingestão
        reativa é operação diária do cliente, não desenvolvimento do
        produto — usa chave do projeto (do GP), não chave global do
        admin. Custo fica onde deve ficar.

        Retorna dict com: raw_text, tokens_input, tokens_output, provider, model.
        """
        # Resolve provider + chave DO PROJETO via AIKeyResolver.
        provider = await AIKeyResolver._resolve_project_provider(self.db, project_id)
        if not provider:
            raise ValueError(
                f"Projeto {project_id} não tem provider LLM configurado. "
                "GP deve configurar em Configurações → Provedor de IA."
            )
        api_key = await AIKeyResolver.get_project_key(self.db, project_id, provider=provider)
        # DT-023: Ollama dispensa api_key (URL local). Demais ainda exigem.
        is_ollama = provider == "ollama"
        if not is_ollama and not api_key:
            raise ValueError(
                f"Chave do provider '{provider}' não encontrada no vault do "
                f"projeto {project_id}."
            )

        # DT-023: Ollama precisa do base_url (endpoint do daemon local do GP).
        base_url = None
        if is_ollama:
            base_url = await AIKeyResolver.get_project_base_url(
                self.db, project_id, provider=provider
            )
            if not base_url:
                raise ValueError(
                    f"Provider 'ollama' configurado no projeto {project_id} sem "
                    "`base_url`. GP deve informar o endpoint do daemon Ollama "
                    "em Configurações → Provedor de IA (ex: "
                    "http://host.docker.internal:11434)."
                )

        # Guard de criticidade (contrato §6.2): atualização reativa do OCG
        # é consolidação/arbitragem — ALTA criticidade. Contrato pede
        # modelo premium. Logamos warning quando o GP usa provider
        # classificado como média/baixa — a decisão fica dele, mas o
        # audit trail fica visível no ai_usage_log + logs.
        _HIGH_CRITICALITY_PROVIDERS = {"anthropic", "openai"}  # premium reasoning
        _MEDIUM_LOW_PROVIDERS = {"deepseek", "grok", "gemini", "qwen", "ollama"}
        if provider in _MEDIUM_LOW_PROVIDERS:
            logger.warning(
                "ocg_updater.criticality_mismatch",
                project_id=str(project_id),
                provider=provider,
                message=(
                    f"OCG update é ALTA criticidade (contrato §6.2) — provider "
                    f"'{provider}' é classificado como média/baixa. GP pode reconfigurar "
                    f"um provider premium (Anthropic/OpenAI) em Configurações → Provedor de IA."
                ),
            )

        # Resolve modelo configurado (formato multi-provider ou legacy)
        from sqlalchemy import text as _text
        model = None
        try:
            row = (await self.db.execute(
                _text("SELECT settings_json FROM project_settings WHERE project_id=:pid AND setting_type='llm'"),
                {"pid": str(project_id)},
            )).fetchone()
            if row and row[0]:
                cfg = json.loads(row[0])
                for p in cfg.get("providers", []) or []:
                    if p.get("is_default") and p.get("provider") == provider:
                        model = p.get("model")
                        break
                if not model and cfg.get("provider") == provider:
                    model = cfg.get("model_preference")
        except Exception:
            pass

        # Defaults por provider (match com _call_llm do Arguidor e agent_service)
        _default_models = {
            "anthropic": "claude-opus-4-6",
            "openai": "gpt-4o",
            "deepseek": "deepseek-v4-flash",
            "grok": "grok-2",
            "gemini": "gemini-2.0-flash",
            "ollama": "llama3.1:8b",
        }
        model = model or _default_models.get(provider, "deepseek-v4-flash")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(current_ocg_data, arguider_analysis)

        logger.info(
            "ocg_updater.llm_call",
            provider=provider,
            model=model,
            prompt_len=len(user_prompt),
            project_id=str(project_id),
        )

        # Dispatch por provider: Anthropic SDK nativo, resto via httpx
        # OpenAI-compatible. DT-033 corrige o bug anterior onde provider=
        # anthropic caía no fallback genérico de DeepSeek (URL errada).
        if provider == "anthropic":
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=model,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return {
                "raw_text": response.content[0].text,
                "tokens_input": response.usage.input_tokens,
                "tokens_output": response.usage.output_tokens,
                "provider": provider,
                "model": model,
            }

        import httpx
        # DT-023: Ollama via OpenAI-compatible no daemon local do GP.
        provider_urls = {
            "deepseek": "https://api.deepseek.com/chat/completions",
            "openai": "https://api.openai.com/v1/chat/completions",
            "grok": "https://api.x.ai/v1/chat/completions",
            "ollama": f"{base_url}/v1/chat/completions" if base_url else None,
        }
        url = provider_urls.get(provider)
        if not url:
            raise ValueError(
                f"Provider '{provider}' não suportado no ocg_updater. "
                f"Suportados: anthropic, openai, deepseek, grok, ollama."
            )

        # Ollama típico não exige Authorization. Bearer só se houver api_key.
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json={
                "model": model,
                "max_tokens": settings.ANTHROPIC_MAX_TOKENS,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            })

        if resp.status_code not in (200, 201):
            raise ValueError(f"LLM API error ({resp.status_code}) no provider {provider}: {resp.text[:300]}")

        data = resp.json()
        return {
            "raw_text": data["choices"][0]["message"]["content"],
            "tokens_input": data.get("usage", {}).get("prompt_tokens", 0),
            "tokens_output": data.get("usage", {}).get("completion_tokens", 0),
            "provider": provider,
            "model": model,
        }

    def _build_system_prompt(self) -> str:
        """System prompt imperativo (DT-C1 da auditoria 2026-04-18).

        Antes: linguagem permissiva ("pode alterar"). LLMs de média
        criticidade pulavam a reavaliação de PILLAR_SCORES / context_health,
        deixando contrato §5 ("boa ingestão expande, ruim contrai")
        descumprido mesmo com o código suportando os deltas.

        Agora: regras imperativas ("DEVE avaliar", "DEVE recalcular"),
        com mapa gap→pilar como referência e obrigação de justificar
        manter scores (não só alterar).
        """
        return (
            "Você é o motor de atualização do OCG (Objeto de Contexto Global) do GCA.\n"
            "Recebe o OCG atual e a análise do Arguidor e DEVE retornar um delta que\n"
            "cumpra o contrato canônico §5:\n"
            "  • OCG EVOLUI a cada ingestão.\n"
            "  • Boa ingestão DEVE EXPANDIR contexto (raise confidence, adicionar entregáveis).\n"
            "  • Ingestão ruim ou conflitante DEVE CONTRAIR confiança (reduzir score, marcar findings críticos).\n"
            "  • Neutralidade só é aceitável quando a análise não toca nenhum pilar ou recomendação — e mesmo assim você DEVE justificar por que nada muda.\n\n"
            "## REGRAS IMPERATIVAS\n"
            "1. Use APENAS as operações 'replace' e 'append'.\n"
            "2. Formato dos deltas:\n"
            "   - replace: {op:'replace', path, old_value, new_value, reasoning}\n"
            "     * 'old_value' é OBRIGATÓRIO (optimistic concurrency — divergência rejeita o delta).\n"
            "     * 'path' em dot-notation. Exemplos válidos: 'PILLAR_SCORES.P3.score', 'PROJECT_PROFILE.frontend_stack', 'STACK_RECOMMENDATION.backend.framework', 'RISK_ANALYSIS.high_risks.0.mitigation'.\n"
            "   - append: {op:'append', path, value, reasoning} — path aponta para lista existente.\n"
            "3. Top-level keys permitidos: PROJECT_PROFILE, PILLAR_SCORES, COMPOSITE_SCORE, STACK_RECOMMENDATION, CRITICAL_FINDINGS, TESTING_REQUIREMENTS, COMPLIANCE_CHECKLIST, DELIVERABLES, ARCHITECTURE_OVERVIEW, RISK_ANALYSIS, APPROVAL_STATUS.\n\n"
            "## PILLAR_SCORES — AVALIAÇÃO OBRIGATÓRIA POR INGESTÃO\n"
            "Para CADA ingestão você DEVE:\n"
            "  (a) Mapear cada gap/show_stopper/poor_definition da análise do Arguidor contra o pilar afetado (mapa abaixo).\n"
            "  (b) Para cada pilar TOCADO pela análise, DECIDIR: EXPAND (+score), CONTRACT (-score) ou MANTER.\n"
            "  (c) Gerar delta em PILLAR_SCORES.<Pn>.score quando a análise justificar — e explicar no 'reasoning' citando o gap/show_stopper específico.\n"
            "  (d) Se decidir MANTER o score, incluir no 'reasoning' do change_type o motivo (ex: 'P4 não tocado pela análise').\n\n"
            "### Mapa gap → pilar (referência obrigatória):\n"
            "  - P1 Caso de Negócio: gaps sobre ROI, valor, stakeholders, escopo de negócio, cases de uso macro.\n"
            "  - P2 Regras/Compliance: gaps sobre LGPD, GDPR, auditoria, retenção, consentimento, políticas regulatórias.\n"
            "  - P3 Funcionalidades/Escopo: gaps sobre features faltantes, casos de uso, fronteiras do escopo.\n"
            "  - P4 Requisitos Não-Funcionais: gaps sobre performance, disponibilidade, escalabilidade, observabilidade.\n"
            "  - P5 Arquitetura/Design: gaps sobre stack técnica, perfil arquitetural, padrões, integrações.\n"
            "  - P6 Dados/Persistência: gaps sobre banco, modelo de dados, cache, mensageria, backup, classificação.\n"
            "  - P7 Segurança: gaps sobre auth, autorização, criptografia, secrets, auditoria, ameaças.\n\n"
            "## context_health — RECÁLCULO OBRIGATÓRIO\n"
            "Você DEVE recalcular {depth, confidence, quality} a cada ingestão conforme:\n"
            "  • depth: cobertura do doc sobre pilares (0 = 1 pilar, 1 = todos os 7).\n"
            "  • confidence: quão consistente o doc é com o OCG atual (1 = concorda, 0 = conflitante).\n"
            "  • quality: clareza e especificidade do doc (0 = vago/genérico, 1 = concreto/implementável).\n"
            "Se a ingestão for ruim (show_stoppers>0, informações vagas, conflitos), confidence DEVE baixar.\n\n"
            "## change_type — CLASSIFICAÇÃO OBRIGATÓRIA\n"
            "  - EXPAND: ingestão trouxe informação nova positiva; pelo menos 1 delta eleva algum score ou adiciona entregável.\n"
            "  - CONTRACT: ingestão expôs lacuna ou conflito; pelo menos 1 delta reduz score OU adiciona CRITICAL_FINDING.\n"
            "  - UPDATE: ajuste neutro (refinamento de texto). Use UPDATE somente quando nenhum pilar é tocado.\n"
            "REGRA DURA: se a análise do Arguidor traz show_stoppers > 0, change_type DEVE ser CONTRACT (não pode ser UPDATE nem EXPAND).\n\n"
            "## OUTRAS REGRAS\n"
            "- Se deltas=[], use change_type=UPDATE e EXPLIQUE no reasoning do context_health.\n"
            "- Nunca remova informação consolidada sem justificativa explícita.\n"
            "- Retorne APENAS o JSON. Sem markdown, sem comentários, sem preamble.\n\n"
            "## FORMATO DE SAÍDA (JSON obrigatório)\n"
            "{\n"
            '  "deltas": [\n'
            '    {"op":"replace", "path":"PILLAR_SCORES.P3.score", "old_value":75, "new_value":65, "reasoning":"GAP G003 (escopo ambíguo) reduz confiança em Funcionalidades/Escopo"},\n'
            '    {"op":"append", "path":"DELIVERABLES", "value":"SBOM inicial", "reasoning":"resposta ao GAP G002"}\n'
            '  ],\n'
            '  "change_type": "EXPAND" | "CONTRACT" | "UPDATE",\n'
            '  "context_health": {"depth": 0.0, "confidence": 0.0, "quality": 0.0}\n'
            "}"
        )

    def _build_user_prompt(
        self,
        current_ocg: Dict[str, Any],
        arguider_analysis: Dict[str, Any],
    ) -> str:
        from app.services.arguider_compactor import compact_arguider_for_prompt

        # Compactar OCG para prompts longos: trima textos verbosos (rationale,
        # description, mitigation, etc.) sem mexer em scores/listas/items.
        # Compactor é no-op se o OCG for pequeno o suficiente.
        compact_ocg = compact_ocg_for_prompt(current_ocg)
        ocg_str = json.dumps(compact_ocg, ensure_ascii=False, indent=2)

        # Compactar arguider_analysis (DT-081 MVP 32) — payload n8n pode chegar com 23KB.
        # Preserva imunes (criticidade='critica' e CONF score<60) + top-K por criticidade.
        arguider_compacted = compact_arguider_for_prompt(arguider_analysis, max_findings=20)
        arguider_str = json.dumps(arguider_compacted, ensure_ascii=False, indent=2)

        return (
            "## OCG ATUAL DO PROJETO (textos longos compactados; valores/scores intactos)\n\n"
            f"{ocg_str}\n\n"
            "## ANÁLISE DO ARGUIDOR (compactada — top findings por criticidade)\n\n"
            f"{arguider_str}\n\n"
            "Com base na análise do Arguidor, gere o **delta** (lista de operações replace/append) "
            "que reflete as mudanças necessárias no OCG. Retorne apenas o JSON no formato especificado pelo system prompt."
        )

    def _parse_llm_response(
        self, llm_result: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """
        Faz parse da resposta do LLM no formato delta com validação de schema.

        Retorna: (deltas, change_type, context_health)
        Em caso de erro de parse, levanta ValueError — caller marca OCG como
        ocg_pending e preserva versão atual.

        DT-081 hot-fix (2026-05-02): quando llm_result vem do fallback de
        persona_scores (marcador `_from_fallback=True`), os deltas já estão
        no formato canônico — retorna direto sem tentar parse de raw_text.

        DT-002 (2026-05-05): Adiciona validação de schema Pydantic para garantir
        JSON válido antes de tentar apply_deltas. Lenient parsing: aceita deltas
        parciais se alguns forem válidos.
        """
        # Fast-path: fallback já produz deltas canônicos
        if llm_result.get("_from_fallback"):
            deltas = llm_result.get("deltas", []) or []
            change_type = llm_result.get("change_type", "EXPAND") or "EXPAND"
            context_health = llm_result.get("context_health") or {
                "depth": 0.5, "confidence": 0.5, "quality": 0.5,
            }
            logger.info(
                "ocg_updater.parsed_from_fallback",
                deltas_count=len(deltas),
                change_type=change_type,
            )
            return deltas, change_type, context_health

        raw_text = llm_result.get("raw_text", "")

        # Tenta extrair JSON da resposta (pode ter markdown code fences)
        json_text = self._extract_json(raw_text)

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "ocg_updater.parse_failed_json",
                error=str(exc),
                raw_snippet=raw_text[:200],
            )
            raise ValueError(f"Resposta do LLM não é JSON válido: {exc}") from exc

        # Validação de schema Pydantic (lenient: tenta validar, mas aceita parcial)
        try:
            validated = OCGLLMResponseSchema.model_validate(parsed)
            deltas = [d.model_dump() for d in validated.deltas] if validated.deltas else []
            change_type = validated.change_type or "UPDATE"
            context_health = validated.context_health.model_dump() if validated.context_health else {
                "depth": 0.5, "confidence": 0.5, "quality": 0.5,
            }
            logger.info(
                "ocg_updater.parsed_with_schema_validation",
                deltas_count=len(deltas),
                change_type=change_type,
            )
        except ValidationError as ve:
            # Schema validation failed — lenient parsing: tenta extrair deltas mesmo assim
            logger.warning(
                "ocg_updater.schema_validation_failed_lenient_parse",
                error=str(ve),
            )
            deltas_raw: List[Dict[str, Any]] = parsed.get("deltas", [])
            if not isinstance(deltas_raw, list):
                logger.warning("ocg_updater.deltas_not_list", got_type=type(deltas_raw).__name__)
                deltas_raw = []
            # Filtra apenas dicts válidos
            deltas = [d for d in deltas_raw if isinstance(d, dict)]

            change_type_raw = parsed.get("change_type", "UPDATE")
            change_type: str = change_type_raw if isinstance(change_type_raw, str) else "UPDATE"

            # Defensive: LLM pode emitir context_health como string ou null
            ch_raw = parsed.get("context_health")
            context_health: Dict[str, Any] = {
                "depth": 0.5,
                "confidence": 0.5,
                "quality": 0.5,
            }
            if isinstance(ch_raw, dict):
                context_health.update(ch_raw)

        # Validação básica do change_type
        if change_type not in ("EXPAND", "CONTRACT", "UPDATE"):
            change_type = "UPDATE"

        return deltas, change_type, context_health

    def _extract_json(self, text: str) -> str:
        """Extrai o JSON de uma resposta que pode conter markdown code fences."""
        # Tenta remover ```json ... ``` ou ``` ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return match.group(1).strip()
        # Tenta encontrar o primeiro { ... } de nível superior
        start = text.find("{")
        if start != -1:
            return text[start:]
        return text.strip()

    async def _update_ocg_record(
        self,
        ocg: OCG,
        updated_ocg: Dict[str, Any],
        change_type: str,
        context_health: Dict[str, Any],
        version_to: int,
    ) -> None:
        """Atualiza o registro OCG após apply_deltas, garantindo coerência
        entre o JSON canônico (``PILLAR_SCORES.Pn_*.score``) e a representação
        colunar (``pN_*_score``, ``overall_score``, ``status``, ``is_blocking``).

        Bug histórico (corrigido aqui): a versão anterior buscava chaves
        top-level inexistentes (``updated_ocg.get("p3_score")`` /
        ``updated_ocg.get("overall_score")``). A estrutura real do OCG aninha
        scores em ``PILLAR_SCORES.P3_scope.score`` e o composite em
        ``COMPOSITE_SCORE.value``. Resultado: colunas zeradas + overall
        fossilizado no valor da geração inicial. UI lê das colunas → dogfood
        via "nada muda" mesmo com Arguidor + apply_deltas funcionando.
        """
        # MVP governance_mode (2026-04-24): em projeto solo_owner, P1
        # (business case) é "owner-declared" — não-mensurável pelo Arguidor.
        # Marcamos no JSON e EXCLUÍMOS do cálculo do composite, pra owner
        # não ser punido por ausência de cronograma absoluto/orçamento formal.
        gov_row = await self.db.execute(
            select(Project.governance_mode).where(Project.id == ocg.project_id)
        )
        governance_mode = gov_row.scalar() or "solo_owner"
        p1_owner_declared = governance_mode == "solo_owner"

        # 1. Extrair score de cada pilar do JSON canônico, gravar nas colunas
        pillars = updated_ocg.get("PILLAR_SCORES") or {}
        if p1_owner_declared and isinstance(pillars.get("P1_business_case"), dict):
            pillars["P1_business_case"]["mode"] = "owner-declared"

        # PISO determinístico — MAX-por-persona consolidado em ocg_individual
        # vira o LIMITE INFERIOR de cada pilar. LLM updater pode subir com
        # interpretação semântica, mas nunca derrubar abaixo da evidência
        # cumulativa registrada. Ignorado em REVERT_DOCUMENT_DELETE.
        # Atualiza TODAS as variantes de chave do pilar no JSON (P2_rules,
        # P2_compliance, p2_rules_score etc) — histórico tem múltiplas grafias.
        if change_type != "REVERT_DOCUMENT_DELETE":
            try:
                fallback_scores = await self._load_persona_scores(ocg.project_id)
                _DB_KEY_BY_NUM = {
                    1: "p1_business_score", 2: "p2_rules_score",
                    3: "p3_features_score", 4: "p4_nfr_score",
                    5: "p5_architecture_score", 6: "p6_data_score",
                    7: "p7_security_score",
                }
                _CANONICAL_BY_NUM = {
                    1: "P1_business_case", 2: "P2_rules", 3: "P3_features",
                    4: "P4_nfr", 5: "P5_architecture", 6: "P6_data",
                    7: "P7_security",
                }
                for n, db_key in _DB_KEY_BY_NUM.items():
                    floor = (fallback_scores.get(db_key) or {}).get("score")
                    if floor is None:
                        continue
                    floor = float(floor)
                    current = _extract_pillar_score(pillars, n) or 0.0
                    if floor <= current:
                        continue
                    # Atualiza TODAS as variantes Px* existentes para evitar
                    # _extract_pillar_score selecionar variante não-atualizada.
                    prefix = f"P{n}_".upper()
                    short = f"P{n}".upper()
                    matched_any = False
                    for k in list(pillars.keys()):
                        if not isinstance(k, str):
                            continue
                        ku = k.upper()
                        if ku == short or ku.startswith(prefix):
                            if isinstance(pillars[k], dict):
                                pillars[k]["score"] = floor
                            else:
                                pillars[k] = {"score": floor}
                            matched_any = True
                    if not matched_any:
                        pillars[_CANONICAL_BY_NUM[n]] = {"score": floor}
                    logger.info(
                        "ocg_updater.floor_applied",
                        project_id=str(ocg.project_id),
                        pillar=db_key,
                        llm_score=current,
                        floor_max_per_persona=floor,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ocg_updater.floor_failed",
                    project_id=str(ocg.project_id),
                    error=str(exc),
                )

        # Invariante §2.4 (CLAUDE.md): "OCG só expande, nunca contrai por
        # análise". Único caminho legítimo de contração: revert de doc
        # soft-deleted (change_type='REVERT_DOCUMENT_DELETE'). Em ingestão
        # normal, se LLM/fallback retornar score menor que o atual, mantém
        # o atual — defesa em camada contra dilução.
        is_revert = change_type == "REVERT_DOCUMENT_DELETE"
        pillar_scores: Dict[int, float] = {}
        _PILLAR_KEY_BY_NUM = {
            1: "P1_business_case", 2: "P2_rules", 3: "P3_features",
            4: "P4_nfr", 5: "P5_architecture", 6: "P6_data", 7: "P7_security",
        }
        for n, col in _PILLAR_COLUMNS.items():
            score = _extract_pillar_score(pillars, n)
            if score is None:
                continue
            current = getattr(ocg, col, None)
            if (
                not is_revert
                and current is not None
                and float(score) < float(current)
            ):
                # Contração indevida — preserva o atual (monotonicidade).
                logger.info(
                    "ocg_updater.contraction_blocked",
                    project_id=str(ocg.project_id),
                    pillar=col,
                    incoming=score,
                    kept=current,
                    change_type=change_type,
                )
                score = float(current)
                key = _PILLAR_KEY_BY_NUM.get(n)
                if key and isinstance(pillars.get(key), dict):
                    pillars[key]["score"] = score
            setattr(ocg, col, score)
            pillar_scores[n] = score

        # 2. Recalcular overall: média ponderada normalizada pelos pesos dos
        #    pilares EFETIVAMENTE presentes (defesa contra OCG parcial).
        # Em solo_owner, P1 sai do denominador do composite.
        overall_new: Optional[float] = None
        composite_pillars = {
            n: s for n, s in pillar_scores.items()
            if not (p1_owner_declared and n == 1)
        }
        if composite_pillars:
            total_weight = sum(_PILLAR_WEIGHTS[n] for n in composite_pillars)
            if total_weight > 0:
                weighted_sum = sum(
                    composite_pillars[n] * _PILLAR_WEIGHTS[n] for n in composite_pillars
                )
                overall_new = round(weighted_sum / total_weight, 2)
                ocg.overall_score = overall_new
                # Espelha no JSON em 3 lugares pra coerência total:
                # - coluna ocg.overall_score (já feito acima)
                # - COMPOSITE_SCORE.value (UI/CodeGen lêem de lá)
                # - overall_score top-level (campo legacy, UI antigo lê — bug
                #   visto em dogfood 2026-05-04 mostrava 57.3 stale enquanto
                #   coluna e COMPOSITE_SCORE estavam em 63.03).
                updated_ocg["overall_score"] = overall_new
                comp = updated_ocg.get("COMPOSITE_SCORE")
                if isinstance(comp, dict):
                    comp["value"] = overall_new
                    if p1_owner_declared:
                        comp["p1_excluded"] = True
                        comp["p1_mode"] = "owner-declared"
                else:
                    updated_ocg["COMPOSITE_SCORE"] = {
                        "value": overall_new,
                        **({"p1_excluded": True, "p1_mode": "owner-declared"} if p1_owner_declared else {}),
                    }

        # 3. Fallback: se o LLM emitiu overall_score top-level (raro, formato
        #    legado) e não conseguimos derivar dos pilares, respeita.
        if overall_new is None:
            legacy_overall = updated_ocg.get("overall_score")
            if legacy_overall is not None:
                try:
                    ocg.overall_score = float(legacy_overall)
                except (TypeError, ValueError):
                    pass

        # 4. Status + is_blocking canônicos (P2<70 OR P7<70 → BLOCKED)
        new_status, is_blocking = _compute_status(pillar_scores, ocg.overall_score)
        ocg.status = new_status
        ocg.is_blocking = is_blocking
        updated_ocg["APPROVAL_STATUS"] = new_status

        # 5. Persistir JSON, change_type, context_health, version
        ocg.ocg_data = json.dumps(updated_ocg, ensure_ascii=False)
        ocg.change_type = change_type
        ocg.context_health = json.dumps(context_health, ensure_ascii=False)
        ocg.version = version_to
        ocg.updated_at = datetime.now(timezone.utc)

        self.db.add(ocg)
        await self.db.flush()

    async def _log_delta(
        self,
        project_id: UUID,
        document_id: Optional[UUID],
        ocg_version_from: int,
        ocg_version_to: int,
        changes: List[Dict[str, Any]],
        changed_by: Optional[UUID] = None,
        trigger_source: str = "document_ingestion",
        ocg_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra delta sempre — document_id opcional (updates não-ingestão também contam)."""
        fields_changed: Dict[str, Any] = {}
        for change in changes:
            field = change.get("field", "unknown")
            fields_changed[field] = {
                "old": change.get("old_value"),
                "new": change.get("new_value"),
                "reasoning": change.get("reasoning", ""),
            }

        summary_parts = [
            f"{c.get('field', '?')}: {c.get('reasoning', '')}"
            for c in changes[:5]
        ]
        change_summary = "; ".join(summary_parts) if summary_parts else f"Mudança via {trigger_source}"

        delta_entry = OCGDeltaLog(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=ocg_version_from,
            ocg_version_to=ocg_version_to,
            fields_changed=json.dumps(fields_changed, ensure_ascii=False),
            change_summary=change_summary,
            changed_by=changed_by,
            trigger_source=trigger_source,
            ocg_snapshot=json.dumps(ocg_snapshot, ensure_ascii=False) if ocg_snapshot else None,
        )
        self.db.add(delta_entry)
        await self.db.flush()

    async def _mark_ocg_pending(self, ocg: OCG) -> None:
        """
        Marca o OCG como ocg_pending quando o LLM falha.
        Preserva todos os dados atuais — nunca corrompe o OCG.
        """
        ocg.status = "ocg_pending"
        ocg.updated_at = datetime.now(timezone.utc)
        self.db.add(ocg)
        await self.db.flush()
        logger.warning(
            "ocg_updater.marked_pending",
            ocg_id=str(ocg.id),
            version=ocg.version,
        )
