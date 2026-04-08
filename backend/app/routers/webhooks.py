"""Webhooks Router — n8n Integration"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import structlog
import json

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

        # TODO: In future, update questionnaire in DB with n8n results
        # For now, just log and acknowledge

        return {
            "status": "received",
            "message": "Questionnaire result received from n8n",
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

        # OCG already persisted by consolidator agent
        # This callback is mainly for notifications/logging

        # TODO: Send email notification with OCG summary
        # TODO: Update questionnaire status to 'analyzed'
        # TODO: Trigger code generator if approved

        return {
            "status": "processed",
            "message": "OCG result received and processed",
            "ocg_id": ocg_id,
        }

    except Exception as e:
        logger.error("webhook.ocg_result_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar resultado OCG: {str(e)}",
        )
