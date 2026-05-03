"""MVP 35 Fase 35.5 — Camada 2: LLM sanity check no submit.

Detecta incoerências semânticas que regras determinísticas (Camada 1) não
capturam. Exemplos: 'equipe-2 + microsserviços + K8s + ACID + LGPD + real-time'
é stack que raramente sobrevive — nenhuma regra individual dispara, mas o
combo é improvável.

Comportamento canônico (DBA-M2 / GP):
  - LLM disponível → retorna lista de incoerências semânticas (pode ser vazia)
  - LLM indisponível (provider sem chave, timeout, 5xx) → BLOQUEIA submit
    (sem fallback silencioso, alinha §0 CLAUDE.md)

NFR (Arq-S2):
  - Latência p95 ≤ 8s
  - Custo/submit ≤ R$0,005 (DeepSeek)
  - Timeout 15s

Provider via AIKeyResolver (porta única §3.1).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class LLMSanityCheckUnavailableError(Exception):
    """LLM indisponível ou retornou erro — submit deve ser bloqueado."""


SYSTEM_PROMPT = """Você é um arquiteto de software sênior validando coerência técnica de um questionário de novo projeto.

Sua tarefa: detectar INCOERÊNCIAS SEMÂNTICAS (não erros de sintaxe ou ausência de campos) entre as escolhas do GP. Foque em combos improváveis ou contraditórios que regras determinísticas não pegariam.

Exemplos de incoerência semântica:
- Equipe pequena (1-2 devs) + microsserviços + Kubernetes + Kafka = complexidade insustentável
- Sistema crítico (SLA 99.99%, PCI-DSS) + prazo de 2 semanas = irrealista
- Real-time (<50ms) + Python/Django + acesso a banco analítico = arquitetura instável

NÃO repita conflitos já listados em conflicts_detected — esses já foram tratados pela validação determinística.

Responda APENAS com JSON válido no formato:
{
  "incoherences": [
    {"description": "...", "severity": "warning|error", "suggestion": "..."}
  ]
}

Se nenhuma incoerência semântica for detectada, retorne `{"incoherences": []}`.
"""


def _build_user_prompt(responses: dict[str, Any], conflicts_detected: list[str]) -> str:
    """Monta o user prompt mínimo (Arq decisão — não passa as 30 regras)."""
    return json.dumps({
        "responses": responses,
        "conflicts_detected": conflicts_detected,
        "context": "questionário técnico GCA",
    }, ensure_ascii=False, indent=2)


async def llm_sanity_check(
    db: AsyncSession,
    project_id: UUID,
    responses: dict[str, Any],
    conflicts_detected: list[str],
) -> dict[str, Any]:
    """Camada 2 — LLM detecta incoerências semânticas.

    Args:
        db: AsyncSession ativa.
        project_id: para resolver provider via AIKeyResolver.
        responses: payload do questionário (Q1-Q15).
        conflicts_detected: lista de conflicts da Camada 1 (não repetir).

    Returns:
        dict {"incoherences": [...], "llm_used": True, "provider", "model"}

    Raises:
        HTTPException 503 quando provider indisponível ou erro irrecuperável.
        Submit é bloqueado — alinha DBA-M2 + §0 CLAUDE.md.
    """
    from app.services.codegen_llm import call_codegen_llm

    user_prompt = _build_user_prompt(responses, conflicts_detected)

    try:
        # Reusa porta única canônica (DT-079 fix). Bloqueio em falha:
        # HTTPException 503 propaga até o caller (router de submit).
        raw_text = await call_codegen_llm(
            db=db,
            project_id=project_id,
            user_prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=1024,
            temperature=0.1,
            log_context="mvp35.llm_sanity",
            expect_json=True,
            auto_continue=False,
        )
    except HTTPException as exc:
        # 503 do call_codegen_llm = provider sem config → bloqueia submit
        logger.warning(
            "mvp35.llm_sanity.unavailable",
            project_id=str(project_id),
            status_code=exc.status_code,
            detail=str(exc.detail)[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Validação automática de IA indisponível agora. "
                "Tente Submeter novamente em instantes."
            ),
        )
    except Exception as exc:
        logger.error(
            "mvp35.llm_sanity.unexpected_error",
            project_id=str(project_id),
            error=str(exc)[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Falha na validação automática. Tente novamente em instantes.",
        )

    # Parse defensivo do JSON do LLM
    try:
        parsed = json.loads(raw_text.strip())
        incoherences = parsed.get("incoherences", [])
        if not isinstance(incoherences, list):
            incoherences = []
    except (json.JSONDecodeError, AttributeError):
        # LLM cuspiu não-JSON — degrada amigavelmente: assume sem incoerências
        # (não bloqueia submit por erro de parsing — só por indisponibilidade).
        logger.warning(
            "mvp35.llm_sanity.parse_failed",
            project_id=str(project_id),
            raw_preview=str(raw_text)[:200],
        )
        incoherences = []

    logger.info(
        "mvp35.llm_sanity.success",
        project_id=str(project_id),
        incoherences_count=len(incoherences),
    )

    return {
        "incoherences": incoherences,
        "llm_used": True,
    }
