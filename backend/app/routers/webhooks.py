"""Webhooks Router — n8n Integration"""
from fastapi import APIRouter, HTTPException, Request, status, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import json
import hmac
import hashlib

from app.db.database import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# Request/Response Models
class ValidationRule(BaseModel):
    field: str
    conflict: str
    severity: str  # blocker, warning
    suggestion: str


class GapDetection(BaseModel):
    field: str
    gap: str
    severity: str
    suggestion: str


class StackIncompatibility(BaseModel):
    backend: str
    frontend: str
    compatible: bool
    suggestion: str


class N8nAnalysisPayload(BaseModel):
    projectId: str
    gp_email: str
    responses: Dict[str, Any]


class N8nAnalysisResult(BaseModel):
    projectId: str
    questionnaireStatus: str  # Pendente, Incompleto, OK
    adherenceScore: int
    approved: bool
    validations: Dict[str, Any]
    observations: str
    restrictions: str
    highlightedFields: List[str]


@router.post("/questionnaire")
async def handle_questionnaire_webhook(payload: N8nAnalysisPayload) -> N8nAnalysisResult:
    """
    n8n webhook handler for questionnaire analysis.
    Receives submitted questionnaire, performs intelligent validation, and returns analysis.

    This is the core intelligence hub that:
    1. Validates technical logic (15+ rules)
    2. Detects gaps (8+ rules)
    3. Checks stack compatibility
    4. Calculates adherence score (85% threshold)
    5. Generates observations & restrictions
    """
    try:
        logger.info(
            "webhook.questionnaire_received",
            projectId=payload.projectId,
            gp_email=payload.gp_email,
        )

        # Extract responses
        responses = payload.responses

        # Analyze questionnaire
        result = analyze_questionnaire(responses)

        logger.info(
            "webhook.questionnaire_analyzed",
            projectId=payload.projectId,
            adherenceScore=result["adherenceScore"],
            approved=result["approved"],
        )

        return N8nAnalysisResult(
            projectId=payload.projectId,
            questionnaireStatus=result["status"],
            adherenceScore=result["adherenceScore"],
            approved=result["approved"],
            validations=result["validations"],
            observations=result["observations"],
            restrictions=result["restrictions"],
            highlightedFields=result["highlightedFields"],
        )

    except Exception as e:
        logger.error("webhook.questionnaire_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar questionário: {str(e)}",
        )


def analyze_questionnaire(responses: Dict[str, Any]) -> Dict[str, Any]:
    """
    Technology Verification Pipeline — Validação profunda pré-OCG.

    Aceita tanto formato numérico (chaves "1"–"49") quanto formato
    nomeado legado (chaves como "frontend_stack").

    Pipeline de 8 fases:
    1. Completude (campos obrigatórios)
    2. Compatibilidade de Stack (linguagem ↔ framework ↔ banco ↔ arquitetura)
    3. Consistência Arquitetural (perfis, modelos, entregáveis)
    4. Viabilidade Tecnológica (combinações impossíveis/arriscadas)
    5. Consistência Cross-Pillar (P1-P7 sem contradições)
    6. Segurança e Compliance
    7. Coerência de Entregáveis
    8. Validações de Projeto Existente (se aplicável)

    Retorna análise completa incluindo A.12 real (Q50-Q54).
    """
    from app.services.technology_verification_service import TechnologyVerificationService

    pipeline = TechnologyVerificationService(responses)
    return pipeline.run_full_pipeline()


def _as_list(value) -> list:
    """Garante que o valor seja lista (para campos multi-select)."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    return []


@router.post("/questionnaire-result")
async def handle_questionnaire_n8n_result(payload: N8nAnalysisPayload) -> dict:
    """
    Webhook handler for n8n callback with Qwen AI enhanced analysis results.

    n8n calls this endpoint after completing analysis with Qwen AI.
    This allows us to:
    1. Receive enhanced analysis from Qwen AI
    2. Update questionnaire in database with results
    3. Store Qwen insights for future reference

    Expected payload from n8n:
    {
        "projectId": "proj-123",
        "gp_email": "gp@example.com",
        "responses": {...},
        "questionnaire_id": "uuid",
        "adherenceScore": 85,
        "approved": true,
        "validations": {...},
        "observations": "...",
        "restrictions": "...",
        "highlightedFields": [...]
    }
    """
    try:
        logger.info(
            "webhook.questionnaire_result_received",
            projectId=payload.projectId,
            gp_email=payload.gp_email,
        )

        # Atualizar questionário no BD com resultados do n8n
        from app.db.database import AsyncSessionLocal
        from app.services.n8n_service import N8nService

        async with AsyncSessionLocal() as db:
            updated = await N8nService.update_questionnaire_with_n8n_results(
                db=db,
                questionnaire_id=payload.responses.get("questionnaire_id", payload.projectId),
                n8n_results=payload.responses,
            )

        return {
            "status": "updated" if updated else "received",
            "message": "Resultado do questionário processado",
            "projectId": payload.projectId,
        }

    except Exception as e:
        logger.error("webhook.questionnaire_result_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar resultado do n8n: {str(e)}",
        )


# ============================================================================
# OCG Result Callback
# ============================================================================

@router.post("/ocg-result")
async def ocg_result_callback(payload: Dict[str, Any]) -> dict:
    """
    Webhook callback for OCG result from agent pipeline.

    Called by n8n after complete 8-agent analysis:
    - Agent 0: Analyzer
    - Agents 1-7: Pillar Specialists (parallel)
    - Agent 8: Consolidator

    Expected payload:
    {
        "ocg_id": "uuid",
        "questionnaire_id": "uuid",
        "project_id": "uuid or null",
        "generated_at": "ISO datetime",
        "PROJECT_PROFILE": {...},
        "PILLAR_SCORES": {...},
        "COMPOSITE_SCORE": {...},
        "STACK_RECOMMENDATION": {...},
        "CRITICAL_FINDINGS": [...],
        "TESTING_REQUIREMENTS": {...},
        "COMPLIANCE_CHECKLIST": [...],
        "DELIVERABLES": {...},
        "ARCHITECTURE_OVERVIEW": {...},
        "RISK_ANALYSIS": {...},
        "APPROVAL_STATUS": {...}
    }
    """
    try:
        ocg_id = payload.get("ocg_id")
        questionnaire_id = payload.get("questionnaire_id")

        logger.info(
            "webhook.ocg_result_received",
            ocg_id=ocg_id,
            questionnaire_id=questionnaire_id,
        )

        # OCG já persistido pelo agente consolidador
        # Callback notifica GP e atualiza status do questionário
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select, update
        from app.models.base import Questionnaire, User
        from app.services.email_service import EmailService

        async with AsyncSessionLocal() as db:
            # Atualizar status do questionário
            q_id = payload.get("questionnaire_id")
            if q_id:
                from uuid import UUID
                stmt = update(Questionnaire).where(
                    Questionnaire.id == UUID(q_id)
                ).values(status="ocg_generated")
                await db.execute(stmt)
                await db.commit()

                # Buscar GP para notificação
                q_result = await db.execute(
                    select(Questionnaire).where(Questionnaire.id == UUID(q_id))
                )
                questionnaire = q_result.scalar_one_or_none()
                if questionnaire and questionnaire.gp_email:
                    try:
                        project_name = payload.get("PROJECT_PROFILE", {}).get("project_name", "Projeto")
                        overall_score = payload.get("COMPOSITE_SCORE", {}).get("overall", 0)
                        EmailService.send_email(
                            to_email=questionnaire.gp_email,
                            subject=f"GCA — OCG gerado para {project_name} (Score: {overall_score})",
                            html_content=f"""
                            <div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
                                <div style="background: #1e1b4b; padding: 20px; border-radius: 12px 12px 0 0;">
                                    <h2 style="color: #c4b5fd; margin: 0;">OCG Gerado com Sucesso</h2>
                                </div>
                                <div style="background: #1e293b; padding: 24px; border-radius: 0 0 12px 12px; color: #cbd5e1;">
                                    <p>O OCG do projeto <strong>{project_name}</strong> foi gerado pelos 8 agentes de IA.</p>
                                    <p>Score composto: <strong>{overall_score}/100</strong></p>
                                    <p><a href="https://gca.code-auditor.com.br/login" style="color: #a78bfa;">Acessar GCA</a></p>
                                </div>
                            </div>
                            """,
                        )
                    except Exception as email_err:
                        logger.warning("webhook.ocg_email_failed", error=str(email_err))

        return {
            "status": "processed",
            "message": "Resultado OCG recebido, questionário atualizado, GP notificado",
            "ocg_id": ocg_id,
        }

    except Exception as e:
        logger.error("webhook.ocg_result_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar resultado OCG: {str(e)}",
        )


# ============================================================================
# n8n Pipeline v2 — Ingestão via Personas distribuídas
# ============================================================================

def _verify_hmac(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


class IngestionCompletePayload(BaseModel):
    ingestion_id: str
    project_id: str
    status: str  # completed|failed|partial
    overall_score: Optional[int] = None
    blocked: bool = False
    blocking_reason: Optional[str] = None
    personas_executed: List[str] = []
    personas_failed: List[str] = []
    ocg_individual: Dict[str, Any] = {}
    ocg_global_delta: Dict[str, Any] = {}
    conflicts_resolved: List[Dict[str, Any]] = []
    consolidated_findings: List[Dict[str, Any]] = []
    consolidated_recommendations: List[Dict[str, Any]] = []
    execution_summary: Dict[str, Any] = {}


@router.post("/ingestion-complete")
async def ingestion_complete(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Callback do Consolidador n8n — recebe resultado final da ingestão."""
    from app.core.config import settings
    body = await request.body()
    signature = request.headers.get("x-n8n-signature", "") or request.headers.get("X-N8N-Signature", "")
    secret = getattr(settings, "N8N_CALLBACK_SECRET", "")

    # Validação HMAC é opcional se não houver signature (fallback para desenvolvimento)
    if signature and secret:
        if not _verify_hmac(body, signature, secret):
            logger.warning("webhook.ingestion_complete_hmac_failed")
            raise HTTPException(status_code=401, detail="HMAC inválido")
    elif secret and not signature:
        # Secret configurado mas signature ausente — warn mas permite
        logger.warning("webhook.ingestion_complete_hmac_missing", detail="N8N_CALLBACK_SECRET configured but no signature provided")

    payload = IngestionCompletePayload(**json.loads(body))

    logger.info(
        "webhook.ingestion_complete",
        ingestion_id=payload.ingestion_id,
        project_id=payload.project_id,
        status=payload.status,
        overall_score=payload.overall_score,
        personas_ok=len(payload.personas_executed),
        personas_failed=len(payload.personas_failed),
        blocked=payload.blocked,
    )

    from sqlalchemy import text

    try:
        doc_id = payload.ingestion_id
        project_id = payload.project_id

        if payload.status in ("completed", "partial"):
            await db.execute(text("""
                UPDATE ingested_documents SET
                    arguider_status = :status,
                    arguider_stage = 'completed',
                    arguider_progress_percent = 100,
                    arguider_completed_at = NOW(),
                    ocg_updated = TRUE,
                    updated_at = NOW()
                WHERE id = :doc_id
            """), {"doc_id": doc_id, "status": "completed"})

            ocg_data = json.dumps({
                "overall_score": payload.overall_score,
                "blocked": payload.blocked,
                "blocking_reason": payload.blocking_reason,
                "personas_executed": payload.personas_executed,
                "ocg_individual": payload.ocg_individual,
                "ocg_global_delta": payload.ocg_global_delta,
                "consolidated_findings": payload.consolidated_findings,
                "execution_summary": payload.execution_summary,
            }, ensure_ascii=False)

            await db.execute(text("""
                UPDATE ocg SET
                    ocg_data = :ocg_data,
                    overall_score = :score,
                    status = CASE WHEN :blocked THEN 'blocked' ELSE 'active' END,
                    version = version + 1,
                    change_type = 'EXPAND',
                    updated_at = NOW()
                WHERE project_id = :project_id
            """), {
                "ocg_data": ocg_data,
                "score": payload.overall_score,
                "blocked": payload.blocked,
                "project_id": project_id,
            })

        else:
            await db.execute(text("""
                UPDATE ingested_documents SET
                    arguider_status = 'error',
                    arguider_stage = 'failed',
                    arguider_error_message = :error,
                    updated_at = NOW()
                WHERE id = :doc_id
            """), {
                "doc_id": doc_id,
                "error": f"Pipeline n8n: {payload.status}. Failed: {payload.personas_failed}",
            })

        await db.commit()

        logger.info(
            "webhook.ingestion_complete_processed",
            ingestion_id=doc_id,
            status=payload.status,
        )

        return {"status": "processed", "ingestion_id": doc_id}

    except Exception as e:
        logger.error("webhook.ingestion_complete_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class AccumulatePayload(BaseModel):
    persona_result: Dict[str, Any]
    persona_tag: str
    valid: bool


@router.post("/internal/ingestion/{ingestion_id}/accumulate")
async def accumulate_persona_result(
    ingestion_id: str,
    payload: AccumulatePayload,
    db: AsyncSession = Depends(get_db),
):
    """Accumulator para resultados de personas — usado pelo Consolidador n8n.

    Armazena resultado no Redis, incrementa contador, retorna se todos chegaram.
    """
    import redis
    from app.core.config import settings

    r = redis.Redis(
        host=getattr(settings, "REDIS_HOST", "redis"),
        port=int(getattr(settings, "REDIS_PORT", 6379)),
        db=int(getattr(settings, "N8N_REDIS_DB", 2)),
    )

    result_json = json.dumps(payload.persona_result, ensure_ascii=False)
    r.rpush(f"gca:ingestion:{ingestion_id}:results", result_json)
    received = r.incr(f"gca:ingestion:{ingestion_id}:received_count")
    expected = int(r.get(f"gca:ingestion:{ingestion_id}:expected_count") or 0)
    project_id = (r.get(f"gca:ingestion:{ingestion_id}:project_id") or b"").decode()

    all_received = received >= expected and expected > 0

    logger.info(
        "webhook.accumulate",
        ingestion_id=ingestion_id,
        persona_tag=payload.persona_tag,
        valid=payload.valid,
        received=received,
        expected=expected,
        all_received=all_received,
    )

    all_results = []
    if all_received:
        raw_results = r.lrange(f"gca:ingestion:{ingestion_id}:results", 0, -1)
        all_results = [json.loads(rr) for rr in raw_results]
        r.delete(
            f"gca:ingestion:{ingestion_id}:results",
            f"gca:ingestion:{ingestion_id}:received_count",
            f"gca:ingestion:{ingestion_id}:expected_count",
            f"gca:ingestion:{ingestion_id}:project_id",
            f"gca:ingestion:{ingestion_id}:shared_context",
        )

    return {
        "received_count": received,
        "expected_count": expected,
        "all_received": all_received,
        "all_results": all_results,
        "project_id": project_id,
    }


# ============================================================================
# Endpoints internos para n8n — HMAC, Redis, Logging
# ============================================================================

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime

_pipeline_log_handler = None

def _get_pipeline_logger():
    global _pipeline_log_handler
    pl = logging.getLogger("gca.pipeline")
    if not _pipeline_log_handler:
        log_dir = Path("/home/luiz/GCA/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        _pipeline_log_handler = TimedRotatingFileHandler(
            log_dir / "pipeline.log",
            when="D",
            interval=1,
            backupCount=3,
            encoding="utf-8",
        )
        _pipeline_log_handler.setFormatter(
            logging.Formatter("%(message)s")
        )
        pl.addHandler(_pipeline_log_handler)
        pl.setLevel(logging.INFO)
    return pl


class PipelineLogEntry(BaseModel):
    ts: Optional[str] = None
    ingestion_id: Optional[str] = None
    workflow: Optional[str] = None
    node: Optional[str] = None
    event: str  # success|error|gate_passed|gate_failed|dispatched|callback_sent|started|completed
    persona_tag: Optional[str] = None
    duration_ms: Optional[int] = None
    detail: Optional[str] = None
    error: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


@router.post("/internal/pipeline-log")
async def pipeline_log(entries: List[PipelineLogEntry] | PipelineLogEntry):
    """Recebe log entries do pipeline n8n e appenda no arquivo rotativo.

    Formato humanly-readable:
    [DD/MM/YYYY HH:MM:SS] [WORKFLOW/NODE] EVENT (persona) ingestion=ID — detalhe
    """
    pl = _get_pipeline_logger()
    if isinstance(entries, PipelineLogEntry):
        entries = [entries]

    EVENT_ICONS = {
        "started": "▶",
        "completed": "✓",
        "success": "✓",
        "failed": "✗",
        "error": "✗",
        "gate_passed": "✓",
        "gate_failed": "✗",
        "dispatched": "→",
        "callback_sent": "↩",
        "persona_result_received": "←",
    }

    for entry in entries:
        # Parse timestamp ISO → DD/MM/YYYY HH:MM:SS local
        ts_str = entry.ts or datetime.utcnow().isoformat() + "Z"
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_human = dt.strftime("%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError):
            ts_human = ts_str

        icon = EVENT_ICONS.get(entry.event, "•")
        wf = entry.workflow or "?"
        node = entry.node or "?"
        persona = f" [{entry.persona_tag}]" if entry.persona_tag else ""
        ingestion = f" ingestion={entry.ingestion_id}" if entry.ingestion_id else ""
        duration = f" ({entry.duration_ms}ms)" if entry.duration_ms else ""

        # Linha principal
        msg = f"[{ts_human}] {icon} {wf}/{node}{persona} {entry.event.upper()}{ingestion}{duration}"
        if entry.detail:
            msg += f" — {entry.detail}"
        if entry.error:
            msg += f" | ERROR: {entry.error}"

        pl.info(msg)

    return {"logged": len(entries)}


class HmacVerifyRequest(BaseModel):
    body_raw: str
    signature: str
    secret_name: str  # GCA_WEBHOOK_SECRET|NORMALIZER_SECRET|CONFERENTE_SECRET|SPECIALIST_SECRET|N8N_CALLBACK_SECRET


class HmacSignRequest(BaseModel):
    body_raw: str
    secret_name: str


_SECRETS_MAP = None

def _load_secrets():
    global _SECRETS_MAP
    if _SECRETS_MAP is None:
        from app.core.config import settings
        _SECRETS_MAP = {
            "GCA_WEBHOOK_SECRET": getattr(settings, "GCA_WEBHOOK_SECRET", ""),
            "NORMALIZER_SECRET": getattr(settings, "NORMALIZER_SECRET", ""),
            "CONFERENTE_SECRET": getattr(settings, "CONFERENTE_SECRET", ""),
            "SPECIALIST_SECRET": getattr(settings, "SPECIALIST_SECRET", ""),
            "N8N_CALLBACK_SECRET": getattr(settings, "N8N_CALLBACK_SECRET", ""),
        }
    return _SECRETS_MAP


@router.post("/internal/hmac/verify")
async def hmac_verify(req: HmacVerifyRequest):
    """Verifica HMAC sem que o n8n precise de crypto ou $env."""
    secrets = _load_secrets()
    secret = secrets.get(req.secret_name, "")
    if not secret:
        return {"valid": False, "error": f"Secret '{req.secret_name}' não configurado"}
    expected = "sha256=" + hmac.new(
        secret.encode(), req.body_raw.encode(), hashlib.sha256
    ).hexdigest()
    valid = hmac.compare_digest(expected, req.signature or "")
    return {"valid": valid}


@router.post("/internal/hmac/sign")
async def hmac_sign(req: HmacSignRequest):
    """Assina body com HMAC sem que o n8n precise de crypto ou $env."""
    secrets = _load_secrets()
    secret = secrets.get(req.secret_name, "")
    if not secret:
        raise HTTPException(status_code=400, detail=f"Secret '{req.secret_name}' não configurado")
    sig = "sha256=" + hmac.new(
        secret.encode(), req.body_raw.encode(), hashlib.sha256
    ).hexdigest()
    return {"signature": sig}


class RedisBulkSetRequest(BaseModel):
    keys: Dict[str, str]
    ttl_seconds: int = 3600


@router.post("/internal/redis/bulk-set")
async def redis_bulk_set(req: RedisBulkSetRequest):
    """Seta múltiplas chaves no Redis (para Conferente setar expected_count, etc.)."""
    import redis as redis_lib
    from app.core.config import settings

    r = redis_lib.Redis(
        host=getattr(settings, "REDIS_HOST", "redis"),
        port=int(getattr(settings, "REDIS_PORT", 6379)),
        db=int(getattr(settings, "N8N_REDIS_DB", 2)),
    )
    for key, value in req.keys.items():
        r.setex(key, req.ttl_seconds, value)
    return {"set": len(req.keys), "ttl": req.ttl_seconds}
