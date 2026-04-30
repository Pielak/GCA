"""Endpoints para Pilares Vivos — Análise viva consolidada de 7 personas"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.services.pilares_vivos_service import PilaresVivosService

router = APIRouter(tags=["Pilares Vivos"])


@router.post("/projects/{project_id}/pilares/regenerar")
async def regenerar_pilares(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_action("project:edit")),
):
    """Regenera documento Pilares Vivos com análise das 7 personas.

    Fluxo:
    1. Resumir 87 Gatekeeper items
    2. Obter respostas Questionário Técnico
    3. Chamar Arquiteto (hub central) para desenhar arquitetura
    4. Chamar 6 personas em paralelo com sub-tasks do Arquiteto
    5. Consolidar documento em 7 seções
    6. Salvar no BD + histórico

    Tempo estimado: 45-60 segundos (chamadas paralelas ao LLM).
    """
    user_id = user_context.get("user_id")

    result = await PilaresVivosService.regenerar_pilares(
        db=db,
        project_id=project_id,
        user_id=user_id,
    )

    if not result["sucesso"]:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Falha ao regenerar Pilares Vivos",
                "erro": result.get("erro"),
            },
        )

    return {
        "sucesso": True,
        "documento": result.get("documento"),
        "tempo_total": result.get("tempo_total"),
        "pilares_id": result.get("pilares_id"),
    }


@router.get("/projects/{project_id}/pilares")
async def obter_pilares(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Obtém documento Pilares Vivos mais recente do projeto."""
    from app.models.base import PilaresVivos
    from sqlalchemy import select

    result = await db.execute(
        select(PilaresVivos).where(PilaresVivos.project_id == project_id)
    )
    pilares = result.scalar_one_or_none()

    if not pilares:
        raise HTTPException(
            status_code=404,
            detail="Pilares Vivos não encontrado. Execute regeneração primeiro.",
        )

    return {
        "id": str(pilares.id),
        "projeto_id": str(pilares.project_id),
        "documento": pilares.documento,
        "gerado_em": pilares.gerado_em.isoformat() if pilares.gerado_em else None,
        "regenerado_em": pilares.regenerado_em.isoformat() if pilares.regenerado_em else None,
        "gerado_por": str(pilares.gerado_por),
    }


@router.get("/projects/{project_id}/pilares/historia")
async def obter_pilares_historia(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Obtém histórico de versões anteriores de Pilares Vivos."""
    from app.models.base import PilaresVivosHistory
    from sqlalchemy import select

    result = await db.execute(
        select(PilaresVivosHistory)
        .where(PilaresVivosHistory.project_id == project_id)
        .order_by(PilaresVivosHistory.archived_em.desc())
        .limit(10)
    )
    historico = result.scalars().all()

    return [
        {
            "id": str(h.id),
            "gerado_em": h.gerado_em.isoformat() if h.gerado_em else None,
            "archived_em": h.archived_em.isoformat() if h.archived_em else None,
            "personas_modificadas": h.personas_modificadas or [],
            "resumo_mudancas": h.resumo_mudancas,
        }
        for h in historico
    ]
