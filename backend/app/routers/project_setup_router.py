"""Endpoints para checklist de configuracao obrigatoria do projeto."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import Project, ProjectSettings, ProjectGitConfig, Questionnaire

router = APIRouter(tags=["Project Setup"])


async def _has_repo_configured(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem repositorio git configurado."""
    result = await db.execute(
        select(exists().where(ProjectGitConfig.project_id == project_id))
    )
    return result.scalar()


async def _has_llm_configured(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem LLM configurado via ProjectSettings."""
    result = await db.execute(
        select(exists().where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "llm",
        ))
    )
    return result.scalar()


async def _has_questionnaire_submitted(db: AsyncSession, project_id: UUID) -> bool:
    """Verifica se o projeto tem questionário com respostas submetidas.

    Retorna True se existe Questionnaire cujas responses não sejam nulas,
    vazias ou iguais a '{}'.
    """
    result = await db.execute(
        select(exists().where(
            Questionnaire.project_id == project_id,
            Questionnaire.responses.isnot(None),
            Questionnaire.responses != "",
            Questionnaire.responses != "{}",
        ))
    )
    return result.scalar()


async def _check_setup_status(db: AsyncSession, project_id: UUID) -> dict:
    """Retorna status completo de configuracao do projeto."""
    repo_configured = await _has_repo_configured(db, project_id)
    llm_configured = await _has_llm_configured(db, project_id)
    questionnaire_submitted = await _has_questionnaire_submitted(db, project_id)
    ready_to_activate = repo_configured and llm_configured and questionnaire_submitted
    return {
        "repo_configured": repo_configured,
        "llm_configured": llm_configured,
        "questionnaire_submitted": questionnaire_submitted,
        "ready_to_activate": ready_to_activate,
    }


@router.get("/projects/{project_id}/setup-status")
async def get_setup_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:view")),
):
    """Retorna o status de configuracao obrigatoria do projeto."""
    return await _check_setup_status(db, project_id)


@router.post("/projects/{project_id}/activate-project")
async def activate_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_action("project:edit")),
):
    """Ativa o projeto apos verificar que todas as configuracoes obrigatorias estao presentes."""
    status = await _check_setup_status(db, project_id)
    if not status["ready_to_activate"]:
        missing = []
        if not status["repo_configured"]:
            missing.append("repositorio_git")
        if not status["llm_configured"]:
            missing.append("configuracao_llm")
        if not status["questionnaire_submitted"]:
            missing.append("questionario_submetido")
        raise HTTPException(
            status_code=400,
            detail={"message": "Configuracao incompleta", "missing": missing},
        )

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado")

    if project.status != "initializing":
        raise HTTPException(
            status_code=400,
            detail=f"Projeto nao pode ser ativado no status atual: {project.status}",
        )

    project.status = "active"
    await db.commit()
    return {"success": True, "status": "active"}
