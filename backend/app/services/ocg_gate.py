"""
OCG Maturity Gate — verifica se o OCG está maduro o suficiente para CodeGen.

Conceito canônico (GP, 2026-05-02):
  "OCG fica estático e só cresce com informação útil. CodeGen é liberado
  para gerar código quando OCG estiver maduro, com >=95% de contexto."

3 níveis de bloqueio (HTTP 409):
  - hard_block:   is_blocking=true (CONF marcou bloqueante)
  - insufficient: overall_score < 60 (mínimo absoluto)
  - immature:     overall_score < 95 (abaixo do limiar de maturidade)
"""
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OCG

logger = structlog.get_logger(__name__)

# Limiares canônicos (não literais nos endpoints — sempre usar a constante)
SCORE_MINIMO_ABSOLUTO = 60   # abaixo disso: insufficient
SCORE_MATURIDADE = 95        # abaixo disso: immature; >= disso: liberado


async def check_ocg_maturity_gate(
    project_id: UUID,
    db: AsyncSession,
) -> None:
    """
    Verifica se o OCG do projeto permite geração de código.

    Levanta HTTPException(409) com payload estruturado se bloqueado.
    Retorna None silenciosamente se OK.

    O caller (endpoints de CodeGen) deve chamar isto na ENTRADA do método,
    antes de qualquer hardcode de provider (DT-079) — para não agravar a
    dívida pré-existente.

    Parâmetros:
      project_id: UUID do projeto
      db: AsyncSession ativa

    Levanta:
      HTTPException(409) se OCG bloqueado/insuficiente/imaturo
      HTTPException(404) se OCG não existe para o projeto
    """
    # Lê OCG mais recente do projeto (idx_ocg_project_id cobre o filtro)
    stmt = (
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(OCG.version.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    ocg = result.scalar_one_or_none()

    if ocg is None:
        logger.warning(
            "ocg_gate.sem_ocg",
            project_id=str(project_id),
        )
        raise HTTPException(
            status_code=404,
            detail={
                "blocked": True,
                "block_level": "no_ocg",
                "message": (
                    f"Projeto {project_id} não tem OCG. "
                    "GP deve completar o questionário primeiro para gerar o OCG inicial."
                ),
            },
        )

    overall_score = ocg.overall_score or 0
    is_blocking = bool(ocg.is_blocking)

    logger.info(
        "ocg_gate.verificando",
        project_id=str(project_id),
        ocg_version=ocg.version,
        overall_score=overall_score,
        is_blocking=is_blocking,
    )

    # Nível 1: hard_block (CONF marcou bloqueante)
    if is_blocking:
        logger.warning(
            "ocg_gate.hard_block",
            project_id=str(project_id),
            overall_score=overall_score,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "blocked": True,
                "block_level": "hard_block",
                "overall_score": overall_score,
                "score_required": SCORE_MATURIDADE,
                "blocking_reason": (
                    "OCG marcado como bloqueante (provavelmente CONF score < 60 ou "
                    "violação de governança). CodeGen recusa enquanto bloqueio não "
                    "for resolvido. Verificar status do OCG e ingerir documentos "
                    "que enderecem os findings de conformidade."
                ),
            },
        )

    # Nível 2: insufficient (abaixo do mínimo absoluto)
    if overall_score < SCORE_MINIMO_ABSOLUTO:
        logger.warning(
            "ocg_gate.insufficient",
            project_id=str(project_id),
            overall_score=overall_score,
            score_minimo=SCORE_MINIMO_ABSOLUTO,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "blocked": True,
                "block_level": "insufficient",
                "overall_score": overall_score,
                "score_required": SCORE_MATURIDADE,
                "blocking_reason": (
                    f"OCG insuficiente (score={overall_score}). Score mínimo "
                    f"absoluto: {SCORE_MINIMO_ABSOLUTO}. CodeGen exige contexto "
                    f"mínimo. Continue ingerindo documentos para amadurecer o OCG."
                ),
            },
        )

    # Nível 3: immature (abaixo do limiar de maturidade)
    if overall_score < SCORE_MATURIDADE:
        logger.warning(
            "ocg_gate.immature",
            project_id=str(project_id),
            overall_score=overall_score,
            score_maturidade=SCORE_MATURIDADE,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "blocked": True,
                "block_level": "immature",
                "overall_score": overall_score,
                "score_required": SCORE_MATURIDADE,
                "blocking_reason": (
                    f"OCG imaturo (score={overall_score}). CodeGen exige score "
                    f">= {SCORE_MATURIDADE} (contexto >= 95%) para gerar código "
                    f"válido. Continue ingerindo documentos para amadurecer o "
                    f"OCG. Aproximação atual: {overall_score}/{SCORE_MATURIDADE}."
                ),
            },
        )

    # OK — OCG maduro
    logger.info(
        "ocg_gate.liberado",
        project_id=str(project_id),
        overall_score=overall_score,
    )
    return None
