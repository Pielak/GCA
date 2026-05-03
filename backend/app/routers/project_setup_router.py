"""Endpoints para checklist de configuracao obrigatoria do projeto."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, exists, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.models.base import Project, ProjectSettings, ProjectGitConfig, Questionnaire, TechnicalQuestionnaire

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


async def _questionnaire_state(db: AsyncSession, project_id: UUID) -> tuple[bool, bool]:
    """Retorna (submitted, approved) do questionário mais recente do projeto.

    Suporta AMBOS:
    - Questionnaire (modelo antigo, PDF-based com responses JSON em string)
    - TechnicalQuestionnaire (modelo novo, dinâmico com responses JSONB)

    Estados:
      - submitted = existe Questionnaire/TechnicalQuestionnaire preenchido/submetido
      - approved  = o Questionnaire passou na verificação (approved=True)
                  OU TechnicalQuestionnaire tem status="submitted"

    A UI usa os dois para distinguir 3 estados no badge da aba:
      missing → ○ âmbar      (nunca submetido)
      submitted & !approved → ⚠ amarelo (submetido mas com bloqueadores)
      approved → ✓ emerald   (OK, OCG pode ser gerado)
    """
    # Verificar Questionnaire antigo (PDF-based)
    result = await db.execute(
        select(Questionnaire)
        .where(
            Questionnaire.project_id == project_id,
            Questionnaire.responses.isnot(None),
            Questionnaire.responses != "",
            Questionnaire.responses != "{}",
        )
        .order_by(Questionnaire.submitted_at.desc())
        .limit(1)
    )
    q_old = result.scalar_one_or_none()

    # Verificar TechnicalQuestionnaire novo (dinâmico).
    # MVP 35 (DBA-S3 + Gate 2 A-S3): filtro explícito status='submitted'
    # já exclui 'archived' (deletado via Ingestão). Sem isso, ORDER BY
    # status DESC poderia retornar archived acima de submitted vazio.
    # Adicionalmente, NÃO conta 'validated' (pré-submit) como submitted —
    # o questionário precisa estar terminal para liberar o pipeline.
    result = await db.execute(
        select(TechnicalQuestionnaire)
        .where(
            TechnicalQuestionnaire.project_id == project_id,
            TechnicalQuestionnaire.status == "submitted",
        )
        .order_by(TechnicalQuestionnaire.submitted_at.desc())
        .limit(1)
    )
    q_new = result.scalar_one_or_none()

    # Se nenhum dos dois foi submetido, retorna false/false
    if q_old is None and q_new is None:
        return False, False

    # Se algum foi submetido, submitted=True
    submitted = q_old is not None or q_new is not None

    # Approved se: Questionnaire antigo foi aprovado OU TechnicalQuestionnaire foi submetido
    approved = (q_old is not None and q_old.approved) or (q_new is not None)

    return submitted, approved


async def _check_setup_status(db: AsyncSession, project_id: UUID) -> dict:
    """Retorna status completo de configuracao do projeto.

    MVP 35 (decisão GP): pipeline liberado nesta ordem hierárquica:
      1. repo_configured (Git/similar)
      2. llm_configured (chave LLM válida)
      3. questionnaire_approved AND questionnaire_submitted (questionário
         APROVADO E submetido — sem approved, o gate fecha mesmo com submitted=True)

    Antes (pré-MVP 35): gate só exigia `submitted`. Quando GP deleta
    questionnaire na Ingestão (MVP 35 cascata), Questionnaire.approved
    vira False mas submitted continuava True por compatibilidade do
    Questionnaire legacy. Resultado: ready_to_activate ficava True
    erroneamente, pipeline continuava liberado. Fix: exigir approved+submitted.
    """
    repo_configured = await _has_repo_configured(db, project_id)
    llm_configured = await _has_llm_configured(db, project_id)
    questionnaire_submitted, questionnaire_approved = await _questionnaire_state(db, project_id)
    ready_to_activate = (
        repo_configured
        and llm_configured
        and questionnaire_submitted
        and questionnaire_approved  # MVP 35: precisa estar APROVADO também
    )
    return {
        "repo_configured": repo_configured,
        "llm_configured": llm_configured,
        "questionnaire_submitted": questionnaire_submitted,
        "questionnaire_approved": questionnaire_approved,
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
