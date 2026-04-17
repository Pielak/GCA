"""FastAPI dependency — exige que o projeto tenha setup completo antes de
executar endpoints do pipeline (ingestion, arguider, codegen, qa, etc.).

Retorna 412 Precondition Failed com detalhe estruturado indicando exatamente
quais dos 3 pré-requisitos estão pendentes.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.routers.project_setup_router import _check_setup_status


async def require_project_setup_complete(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bloqueia execução se o projeto não completou os 3 pré-requisitos.

    Extrai project_id dos path params. Endpoint que usa essa dep DEVE ter
    `project_id` no path (ex.: `/projects/{project_id}/...`).
    """
    project_id_raw = request.path_params.get("project_id")
    if not project_id_raw:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="require_project_setup_complete usada em endpoint sem {project_id} no path",
        )
    try:
        project_id = UUID(str(project_id_raw))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id inválido no path",
        )

    setup = await _check_setup_status(db, project_id)
    if setup["ready_to_activate"]:
        return setup

    missing = []
    if not setup["repo_configured"]:
        missing.append("repositorio_git")
    if not setup["llm_configured"]:
        missing.append("configuracao_llm")
    if not setup["questionnaire_submitted"]:
        missing.append("questionario_submetido")

    raise HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail={
            "code": "project_setup_incomplete",
            "message": (
                "Este projeto ainda não completou os pré-requisitos obrigatórios. "
                "Configure repositório com PAT, provedor IA com API key, e submeta o questionário técnico."
            ),
            "missing": missing,
        },
    )
