"""Lock in-process por project_id pra operações OCG-mutantes.

Motivação (DT-080 parte server-side, sessão 30): stakeholder clicou
Regenerar OCG + Re-consolidar OCG em paralelo sem feedback visual de
progresso. Ambos endpoints rodaram simultaneamente contra o mesmo
project_id; o Regenerate (pipeline síncrono de 8 agentes, 3-5min)
sobrescreveu o OCG que o Reconsolidate acabara de atualizar, violando
`feedback_ocg_cascade_top_down` ("ações OCG-mutantes devem ser
serializadas").

Escopo:
  - Previne 2ª operação OCG-mutante no MESMO project_id enquanto outra
    está in-flight — retorna HTTP 409 com metadata da operação em curso.
  - Lock é in-process (asyncio.Lock). Em deployment multi-worker
    (gunicorn N workers), workers diferentes NÃO enxergam o lock um do
    outro — pra isso precisaria Redis SETNX. Limitação aceitável no
    GCA atual (desenvolvimento/dogfood single-worker).
  - Não substitui `_PROJECT_LOCKS` interno do `ocg_updater_service`
    (esse serializa updates dentro do próprio updater). Este lock é
    mais alto nível: impede que /regenerate rode em paralelo com
    /reconsolidate, ou que edit inline rode durante ambos.

Uso:
    async with project_operation_lock(project_id, "regenerate"):
        # código da operação

Quando outra operação tenta entrar, levanta HTTPException(409).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

import structlog
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

# Registro de locks ativos por project_id.
# Valor: {"operation": str, "started_at": datetime}
_ACTIVE_OPERATIONS: dict[UUID, dict[str, Any]] = {}

# Mutex pra proteger o dict de race condition entre check e set.
_REGISTRY_MUTEX = asyncio.Lock()


@asynccontextmanager
async def project_operation_lock(
    project_id: UUID, operation: str,
) -> AsyncIterator[None]:
    """Context manager que serializa operações OCG-mutantes por project_id.

    Args:
        project_id: UUID do projeto alvo da operação.
        operation: nome human-readable da operação (ex: "regenerate",
            "reconsolidate", "ocg_edit"). Aparece na mensagem de 409.

    Raises:
        HTTPException(409): se outra operação do mesmo project_id já
            está rodando. Detail inclui `blocked_by`, `started_at`,
            `elapsed_seconds` pra cliente decidir (aguardar/cancelar).
    """
    async with _REGISTRY_MUTEX:
        existing = _ACTIVE_OPERATIONS.get(project_id)
        if existing is not None:
            elapsed = (datetime.now(timezone.utc) - existing["started_at"]).total_seconds()
            logger.warning(
                "project_operation_lock.conflict",
                project_id=str(project_id),
                requested=operation,
                blocked_by=existing["operation"],
                elapsed_s=round(elapsed, 1),
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "operation_in_progress",
                    "blocked_by": existing["operation"],
                    "started_at": existing["started_at"].isoformat(),
                    "elapsed_seconds": round(elapsed, 1),
                    "message": (
                        f"Já existe uma operação '{existing['operation']}' em "
                        f"andamento neste projeto desde "
                        f"{existing['started_at'].astimezone().strftime('%H:%M:%S')} "
                        f"(há {int(elapsed)}s). Aguarde terminar antes de iniciar "
                        f"outra operação no OCG."
                    ),
                },
            )
        _ACTIVE_OPERATIONS[project_id] = {
            "operation": operation,
            "started_at": datetime.now(timezone.utc),
        }
        logger.info(
            "project_operation_lock.acquired",
            project_id=str(project_id),
            operation=operation,
        )

    try:
        yield
    finally:
        async with _REGISTRY_MUTEX:
            existing = _ACTIVE_OPERATIONS.pop(project_id, None)
            if existing:
                elapsed = (datetime.now(timezone.utc) - existing["started_at"]).total_seconds()
                logger.info(
                    "project_operation_lock.released",
                    project_id=str(project_id),
                    operation=existing["operation"],
                    elapsed_s=round(elapsed, 1),
                )


def get_active_operation(project_id: UUID) -> dict[str, Any] | None:
    """Consulta não-bloqueante do estado atual. Retorna snapshot do dict
    (ou None se nenhuma operação). Útil pra endpoints de status/polling
    exporem "tem algo rodando?" sem tentar adquirir o lock.
    """
    op = _ACTIVE_OPERATIONS.get(project_id)
    if op is None:
        return None
    elapsed = (datetime.now(timezone.utc) - op["started_at"]).total_seconds()
    return {
        "operation": op["operation"],
        "started_at": op["started_at"].isoformat(),
        "elapsed_seconds": round(elapsed, 1),
    }
