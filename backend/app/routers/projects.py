"""Projects Router"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
import structlog

from app.db.database import get_db
from app.services.project_team_service import ProjectTeamService
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_action import require_action, resolve_user_role_in_project
from app.core.permissions import get_actions_for_role

logger = structlog.get_logger(__name__)

router = APIRouter()


# Request/Response Models
#
# Whitelist canônica de papéis de projeto (contrato §4.1 + MVP 11 Fase 11.1):
# apenas `dev`, `tester`, `qa`, `gp` são aceitos no convite. Admin é papel de
# instância, nunca é atribuído via invite de projeto; lixo (tech_lead,
# dev_senior, etc.) é rejeitado pela whitelist.
ProjectMemberInviteRole = Literal["dev", "tester", "qa", "gp"]


class InviteTeamMemberRequest(BaseModel):
    """Request: Invite user to project."""
    email: EmailStr
    role: ProjectMemberInviteRole


class InviteTeamMemberResponse(BaseModel):
    """Response: Team member invited"""
    invite_id: str
    email: str
    role: str
    status: str = "pending"
    expires_at: str
    invite_url: str


class PendingInvite(BaseModel):
    """Pending invitation"""
    invite_id: str
    email: str
    role: str
    status: str
    invited_at: str
    expires_at: str


class PendingInvitesResponse(BaseModel):
    """Response: List of pending invites"""
    invites: list[PendingInvite]


class AcceptInviteRequest(BaseModel):
    """Request: Accept project invitation"""
    token: str


class AcceptInviteResponse(BaseModel):
    """Response: Invitation accepted"""
    project_id: str
    project_name: str
    role: str
    message: str
    first_access_required: bool


@router.get("/by-slug/{slug}")
async def get_project_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Resolução pública de projeto por short_slug.
    NÃO requer autenticação — usado na tela de login por projeto.
    Retorna apenas dados públicos (id, nome, status).
    """
    from app.models.base import Project
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(Project).where(Project.short_slug == slug)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado",
        )

    if project.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Projeto arquivado",
        )

    return {
        "project_id": str(project.id),
        "name": project.name,
        "status": project.status or "active",
    }


@router.get("/")
@router.get("")
async def list_projects(
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List projects accessible to the current user (filtered by membership)."""
    from app.models.base import Project, ProjectMember, User
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Verificar se é admin
    user_result = await db.execute(select(User).where(User.id == current_user_id))
    user = user_result.scalar_one_or_none()

    if user and user.is_admin:
        # Admin vê todos os projetos — com userRole indicando se é membro ou viewer
        all_projects = await db.execute(select(Project).order_by(Project.created_at.desc()))
        projects = all_projects.scalars().all()

        # Buscar memberships do admin
        admin_members = await db.execute(
            select(ProjectMember.project_id, ProjectMember.role).where(
                ProjectMember.user_id == current_user_id,
                ProjectMember.is_active == True,
            )
        )
        admin_roles = {row.project_id: row.role for row in admin_members.all()}

        return {
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "slug": p.slug,
                    "description": p.description or "",
                    "status": p.status or "draft",
                    "userRole": admin_roles.get(p.id, "admin_viewer"),
                    "phase": 1,
                    "gatekeeperScore": 0,
                }
                for p in projects
            ]
        }

    # Usuário comum: só projetos onde é membro ativo
    result = await db.execute(
        select(ProjectMember, Project)
        .join(Project, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == current_user_id,
            ProjectMember.is_active == True,
        )
        .order_by(Project.created_at.desc())
    )
    rows = result.all()

    return {
        "projects": [
            {
                "id": str(proj.id),
                "name": proj.name,
                "slug": proj.slug,
                "description": proj.description or "",
                "status": proj.status or "draft",
                "userRole": pm.role,
                "phase": 1,
                "gatekeeperScore": 0,
            }
            for pm, proj in rows
        ]
    }


@router.get("/{project_id}")
async def get_project_detail(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe de um projeto (usado pelo ProjectDetailLayout)."""
    from app.models.base import Project, ProjectMember, User
    from sqlalchemy import select

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

    # Buscar papel do usuário no projeto
    user_result = await db.execute(select(User).where(User.id == current_user_id))
    user = user_result.scalar_one_or_none()

    role = "admin" if user and user.is_admin else None
    if not role:
        member_result = await db.execute(
            select(ProjectMember).where(
                (ProjectMember.project_id == project_id) &
                (ProjectMember.user_id == current_user_id)
            )
        )
        member = member_result.scalar_one_or_none()
        role = member.role if member else "viewer"

    return {
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description or "",
        "status": project.status or "active",
        "phase": 1,
        "language": "",
        "database": "",
        "gatekeeperScore": 0,
        "pendingIssues": 0,
        "role": role,
    }


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista membros ativos integrados do projeto.

    Regra canônica (ver `is_active_integrated_member` em
    `project_team_service.py`): `is_active AND joined_at IS NOT NULL`.
    Convidados pendentes (com invite_token e sem joined_at) são
    excluídos daqui — aparecem em `/pending-invites` separadamente.
    """
    from app.models.base import Project, ProjectMember, User
    from sqlalchemy import select

    result = await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(
            (ProjectMember.project_id == project_id) &
            (ProjectMember.is_active == True) &
            (ProjectMember.joined_at != None)
        )
        .order_by(ProjectMember.invited_at.asc())
    )
    rows = result.all()

    return {
        "members": [
            {
                "id": str(pm.id),
                "user_id": str(pm.user_id),
                "email": u.email,
                "full_name": u.full_name or u.email.split("@")[0],
                "role": pm.role,
                "joined_at": pm.joined_at.isoformat() if pm.joined_at else pm.invited_at.isoformat() if pm.invited_at else None,
                "accepted": pm.accepted_at is not None,
            }
            for pm, u in rows
        ]
    }


@router.get("/{project_id}/pending-invites")
async def list_pending_invites_alias(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Alias: lista convites pendentes (usado pelo ProjectTeamPage)."""
    invites = await ProjectTeamService.get_pending_invites(db=db, project_id=project_id)
    return {"invites": invites}


@router.post("/{project_id}/invite", response_model=InviteTeamMemberResponse)
async def invite_team_member(
    project_id: UUID,
    req: InviteTeamMemberRequest,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Invite user to join project with specific role (GP only).
    Sends invitation email with acceptance link.
    """
    user_id = permissions["user_id"]
    success, invite_token, error = await ProjectTeamService.invite_team_member(
        db=db,
        project_id=project_id,
        gp_user_id=user_id,
        email=req.email,
        role=req.role,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    invite_url = f"https://gca.com/projects/{project_id}/accept-invite?token={invite_token}"

    return InviteTeamMemberResponse(
        invite_id=invite_token,
        email=req.email,
        role=req.role,
        status="pending",
        expires_at="7 dias",
        invite_url=invite_url,
    )


@router.get("/{project_id}/invites", response_model=PendingInvitesResponse)
async def list_pending_invites(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of pending team invitations for a project (GP only).
    """
    invites = await ProjectTeamService.get_pending_invites(
        db=db,
        project_id=project_id,
    )

    return PendingInvitesResponse(invites=invites)


@router.post("/{project_id}/accept-invite", response_model=AcceptInviteResponse)
async def accept_invite(
    project_id: UUID,
    req: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Accept project invitation (no auth required, token in request).
    User accepts team invitation and joins project.
    """
    success, project_info, error = await ProjectTeamService.accept_invite(
        db=db,
        project_id=project_id,
        token=req.token,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return AcceptInviteResponse(**project_info)


@router.post("/{project_id}/invites/{invite_id}/revoke")
async def revoke_invite(
    project_id: UUID,
    invite_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoga convite pendente (somente GP do projeto).
    Spec seção 6.1: revogar convite antes de ser aceito.
    """
    user_id = permissions["user_id"]
    success, error = await ProjectTeamService.revoke_invite(
        db=db,
        project_id=project_id,
        invite_id=invite_id,
        gp_user_id=user_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return {"message": "Convite revogado com sucesso", "invite_id": str(invite_id)}


class TransferGpResponse(BaseModel):
    """MVP 11 Fase 11.2 — resposta da transferência de soberania."""
    status: str
    from_user_id: str
    to_user_id: str
    project_id: str


@router.post("/{project_id}/transfer-gp/{target_user_id}", response_model=TransferGpResponse)
async def transfer_gp_sovereignty(
    project_id: UUID,
    target_user_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 11 Fase 11.2 — transferência atômica da soberania do projeto.

    Promove outro membro a GP e rebaixa o chamador a Dev numa única transação.
    Apenas o GP atual do projeto pode invocar (enforcement duplo: RBAC
    `project:manage_team` + check de membership GP no serviço). Emite
    2 eventos `role_transferred` com mesmo `correlation_id`.
    """
    caller_id = permissions["user_id"]
    success, error = await ProjectTeamService.transfer_gp_sovereignty(
        db=db,
        project_id=project_id,
        current_gp_id=caller_id,
        target_user_id=target_user_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )
    return TransferGpResponse(
        status="gp_transferred",
        from_user_id=str(caller_id),
        to_user_id=str(target_user_id),
        project_id=str(project_id),
    )


@router.post("/{project_id}/activate")
async def activate_project_context(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Define o projeto como contexto ativo do usuário (spec seção 4.2).
    O GP vê apenas seus projetos; ao clicar, define o contexto ativo.
    """
    from sqlalchemy import select
    from datetime import datetime, timezone
    from app.models.base import ProjectMember, UserProjectContext

    # Verificar membership
    result = await db.execute(
        select(ProjectMember).where(
            (ProjectMember.project_id == project_id) &
            (ProjectMember.user_id == current_user_id) &
            (ProjectMember.is_active == True)
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro deste projeto",
        )

    # Upsert contexto
    ctx_result = await db.execute(
        select(UserProjectContext).where(UserProjectContext.user_id == current_user_id)
    )
    ctx = ctx_result.scalar_one_or_none()

    if ctx:
        ctx.active_project_id = project_id
        ctx.last_selected_at = datetime.now(timezone.utc)
    else:
        ctx = UserProjectContext(
            user_id=current_user_id,
            active_project_id=project_id,
        )
        db.add(ctx)

    await db.commit()

    logger.info("project.context_activated",
                user_id=str(current_user_id),
                project_id=str(project_id))

    return {"active_project_id": str(project_id), "message": "Contexto ativo definido"}


# ============================================================================
# Questionário e OCG por projeto
# ============================================================================

@router.get("/{project_id}/questionnaire")
async def get_project_questionnaire(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o questionário associado ao projeto (respostas + score)."""
    from sqlalchemy import select
    from app.models.base import Questionnaire
    import json

    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.project_id == project_id)
        .order_by(Questionnaire.submitted_at.desc())
        .limit(1)
    )
    q = result.scalar_one_or_none()

    if not q:
        return {"questionnaire": None, "message": "Nenhum questionário vinculado a este projeto"}

    try:
        responses = json.loads(q.responses) if q.responses else {}
    except json.JSONDecodeError:
        responses = {}

    try:
        validations = json.loads(q.validations) if q.validations else {}
    except json.JSONDecodeError:
        validations = {}

    # Deriva lista plana de issues acionáveis a partir dos 4 buckets de findings
    # (logicConflicts, gaps, incompatibilities, delivery_alignment). Cada item
    # traz título humano, perguntas afetadas, sugestão de correção, severidade
    # e pilar — pronto pra UI renderizar sem decodificar códigos técnicos.
    blocking_issues = []
    for bucket in ("logicConflicts", "gaps", "incompatibilities", "delivery_alignment"):
        for f in validations.get(bucket, []):
            sev = f.get("severity")
            if sev in ("blocker", "critical", "warning"):
                blocking_issues.append({
                    "severity": sev,
                    "rule_id": f.get("rule_id"),
                    "title": f.get("title", ""),
                    "description": f.get("description", ""),
                    "affected_questions": f.get("affected_questions", []),
                    "suggestion": f.get("suggestion", ""),
                    "pillar": f.get("pillar"),
                })
    order = {"blocker": 0, "critical": 1, "warning": 2}
    blocking_issues.sort(key=lambda x: order.get(x["severity"], 99))

    return {
        "questionnaire": {
            "id": str(q.id),
            "gp_email": q.gp_email,
            "responses": responses,
            "adherence_score": q.adherence_score,
            "status": q.status,
            "approved": q.approved,
            "validations": validations,
            "blocking_issues": blocking_issues,
            "observations": q.observations,
            "restrictions": q.restrictions,
            "submitted_at": q.submitted_at.isoformat() if q.submitted_at else None,
            "analyzed_at": q.analyzed_at.isoformat() if q.analyzed_at else None,
            # DT-020: trace do PDF submetido (nullable para questionários
            # antigos submetidos antes da migration 019).
            "uploaded_filename": getattr(q, "uploaded_filename", None),
            "file_hash": getattr(q, "file_hash", None),
            "file_size_bytes": getattr(q, "file_size_bytes", None),
            "answered_questions": getattr(q, "answered_questions", None),
        }
    }


class QuestionnaireCorrectionsRequest(BaseModel):
    # Dict {q_id: valor} — valor pode ser string (single/text) ou list[str] (multi).
    # Campos ausentes são preservados dos responses atuais.
    corrections: dict


@router.post("/{project_id}/questionnaire/correct")
async def correct_project_questionnaire(
    project_id: UUID,
    req: QuestionnaireCorrectionsRequest,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Corrige respostas específicas do último questionário do projeto.

    Alternativa ao re-upload de PDF: o GP corrige apenas as perguntas
    apontadas como bloqueadoras na aba Questionário e re-dispara a
    análise técnica, sem sair da tela.

    Fluxo:
      1. Carrega o questionário mais recente do projeto.
      2. Mergea `corrections` com `responses` existentes (patch parcial).
      3. Roda `TechnologyVerificationService` no responses mesclado.
      4. Atualiza o próprio questionário in-place (não cria novo) —
         status, approved, adherence, validations, highlighted_fields,
         observations, responses, analyzed_at.
      5. Se aprovado: dispara `_generate_ocg` (pipeline 8 agentes IA).

    Mantém o histórico mais enxuto do que criar novo Questionnaire a
    cada ajuste — cada correção é uma iteração sobre a mesma submissão.
    """
    from sqlalchemy import select
    from app.models.base import Questionnaire
    from app.services.technology_verification_service import TechnologyVerificationService
    from app.services.questionnaire_service import QuestionnaireService
    from datetime import datetime, timezone
    import asyncio
    import json

    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.project_id == project_id)
        .order_by(Questionnaire.submitted_at.desc())
        .limit(1)
    )
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=404, detail="Nenhum questionário submetido para este projeto.")

    if not req.corrections:
        raise HTTPException(status_code=400, detail="Nenhuma correção informada.")

    # Merge: responses existentes + corrections
    try:
        current_responses = json.loads(q.responses) if q.responses else {}
    except json.JSONDecodeError:
        current_responses = {}
    merged = {**current_responses, **req.corrections}

    # Re-rodar verificação tecnológica
    try:
        service = TechnologyVerificationService(merged)
        res = service.run_full_pipeline()
    except Exception as e:
        logger.error("questionnaire.correct_verification_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Falha ao re-analisar: {e}")

    approved = res["approved"]
    adherence = res["adherenceScore"]
    blockers_count = res["summary"]["blockers"]
    criticals_count = res["summary"]["criticals"]

    # Observation amigável em PT-BR
    if approved:
        new_status = "ok"
        new_obs = f"Análise aprovada após correções · Aderência {adherence}%. OCG será gerado."
    elif blockers_count > 0:
        new_status = "incomplete"
        new_obs = f"Ainda restam {blockers_count} problema(s) crítico(s). Continue ajustando as respostas abaixo."
    elif criticals_count > 0:
        new_status = "revision_needed"
        new_obs = f"Análise com {criticals_count} ponto(s) crítico(s). Revise antes de prosseguir."
    else:
        new_status = "revision_needed"
        new_obs = "Análise com observações. Revise antes de prosseguir."

    # Update in-place
    q.responses = json.dumps(merged)
    q.status = new_status
    q.approved = approved
    q.adherence_score = adherence
    q.validations = json.dumps(res["validations"])
    q.highlighted_fields = json.dumps(res["highlightedFields"])
    q.restrictions = (res.get("restrictions") or "")[:500]
    q.observations = new_obs[:500]
    q.analyzed_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(
        "questionnaire.corrected",
        project_id=str(project_id),
        questionnaire_id=str(q.id),
        corrected_fields=list(req.corrections.keys()),
        approved=approved,
        adherence=adherence,
    )

    # Se passou, dispara geração de OCG em background (mesmo padrão do submit)
    if approved:
        asyncio.create_task(
            QuestionnaireService._generate_ocg(
                questionnaire_id=q.id,
                project_id=project_id,
                gp_email=q.gp_email,
            )
        )

    return {
        "success": True,
        "questionnaire_id": str(q.id),
        "status": new_status,
        "approved": approved,
        "adherence_score": adherence,
        "blockers": blockers_count,
        "criticals": criticals_count,
        "observations": new_obs,
    }


@router.post("/{project_id}/ocg/reconsolidate")
async def reconsolidate_ocg(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Re-executa o `ocg_updater` sobre as análises Arguidor existentes (DT-039).

    Útil quando:
      - o prompt do `ocg_updater` mudou (ex: DT-035) e quer re-aplicar
        aos docs já analisados sem re-executar o Arguidor (que custa tokens)
      - o `ocg_updater` falhou em alguma ingestão (deixou `ocg_pending`)
        e quer tentar de novo agora que a config foi corrigida
      - o provider/chave do projeto mudou e quer reconsolidar com o novo

    Itera por TODAS as análises Arguidor do projeto na ordem cronológica
    e aplica deltas acumulados. Não re-chama o Arguidor (mais barato).
    """
    from sqlalchemy import select, text
    from app.models.base import ArguiderAnalysis, OCG
    from app.services.ocg_updater_service import OCGUpdaterService
    from app.services.project_operation_lock import project_operation_lock
    import json as _json

    # DT-080: lock por project_id impede esta operação rodar em paralelo
    # com /regenerate (que pode sobrescrever o resultado) ou outra
    # /reconsolidate. Levanta 409 se outra operação está em curso.
    async with project_operation_lock(project_id, "reconsolidate"):
        return await _reconsolidate_ocg_impl(project_id, db)


async def _reconsolidate_ocg_impl(project_id: UUID, db: AsyncSession):
    """Implementação real — isolada pra ficar sob project_operation_lock."""
    from sqlalchemy import select
    from app.models.base import ArguiderAnalysis, OCG
    from app.services.ocg_updater_service import OCGUpdaterService
    import json as _json

    # Verifica se tem OCG
    ocg = (await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if not ocg:
        raise HTTPException(
            status_code=400,
            detail="Projeto não tem OCG. Aprove o questionário primeiro para gerar o OCG inicial.",
        )

    # Busca todas as análises Arguidor do projeto (ordem cronológica)
    analyses = (await db.execute(
        select(ArguiderAnalysis)
        .where(ArguiderAnalysis.project_id == project_id)
        .order_by(ArguiderAnalysis.created_at.asc())
    )).scalars().all()

    if not analyses:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma análise do Arguidor encontrada — reingerir documentos antes.",
        )

    svc = OCGUpdaterService(db)
    applied = 0
    failures = []
    for a in analyses:
        try:
            analysis_dict = {
                "document_classification": _json.loads(a.document_classification) if a.document_classification else {},
                "gaps": _json.loads(a.gaps) if a.gaps else [],
                "show_stoppers": _json.loads(a.show_stoppers) if a.show_stoppers else [],
                "poor_definitions": _json.loads(a.poor_definitions) if a.poor_definitions else [],
                "improvement_suggestions": _json.loads(a.improvement_suggestions) if a.improvement_suggestions else [],
                "module_candidates": _json.loads(a.module_candidates) if a.module_candidates else [],
                "ocg_fields_to_update": _json.loads(a.ocg_fields_to_update) if a.ocg_fields_to_update else [],
            }
            await svc.update_ocg_from_arguider(
                project_id=project_id,
                arguider_analysis=analysis_dict,
                document_id=a.document_id,
                trigger_source="manual_reconsolidate",
            )
            applied += 1
        except Exception as e:
            failures.append({"analysis_id": str(a.id), "error": str(e)[:200]})
            logger.warning("ocg.reconsolidate_analysis_failed", analysis_id=str(a.id), error=str(e))

    return {
        "success": True,
        "analyses_processed": applied,
        "analyses_total": len(analyses),
        "failures": failures,
        "message": f"Reconsolidação aplicada a {applied}/{len(analyses)} análise(s).",
    }


@router.post("/{project_id}/ocg/regenerate")
async def regenerate_ocg(
    project_id: UUID,
    confirm: bool = False,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Regenera o OCG do zero a partir do questionário aprovado (DT-039).

    **Operação destrutiva:** roda o pipeline de 8 agentes IA de novo (custa
    tokens do projeto). Preserva `ocg_delta_log` como histórico. Requer
    `?confirm=true` explícito no query param — sem ele, retorna 400 com
    aviso.

    Quando usar:
      - configuração de IA mudou drasticamente (novo provider/modelo
        premium), quer re-gerar OCG inicial
      - o OCG está inconsistente e o GP quer reset
      - debug/troubleshooting em dev
    """
    from sqlalchemy import select
    from app.models.base import Questionnaire, Project
    from app.services.questionnaire_service import QuestionnaireService
    from app.services.project_operation_lock import (
        project_operation_lock,
        get_active_operation,
    )

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Operação destrutiva — chama 8 agentes IA e gera OCG novo "
                "(custo em tokens). Adicione ?confirm=true ao fazer a requisição "
                "para confirmar."
            ),
        )

    # DT-080: fail-fast se já existe operação OCG em andamento.
    # Ver `project_operation_lock` pra detalhes.
    existing = get_active_operation(project_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "operation_in_progress",
                "blocked_by": existing["operation"],
                "started_at": existing["started_at"],
                "elapsed_seconds": existing["elapsed_seconds"],
                "message": (
                    f"Já existe uma operação '{existing['operation']}' em andamento "
                    f"neste projeto (há {int(existing['elapsed_seconds'])}s). Aguarde "
                    f"ela terminar antes de disparar um Regenerar."
                ),
            },
        )

    proj = await db.get(Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Pega o questionário aprovado mais recente
    q = (await db.execute(
        select(Questionnaire)
        .where(Questionnaire.project_id == project_id, Questionnaire.approved == True)
        .order_by(Questionnaire.submitted_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not q:
        raise HTTPException(
            status_code=400,
            detail="Projeto não tem questionário aprovado. Aprove um questionário primeiro.",
        )

    # Dispara geração em background, sob o lock — previne 2ª operação OCG
    # mutante (ex: /reconsolidate) rodar em paralelo.
    import asyncio

    async def _regenerate_with_lock():
        try:
            async with project_operation_lock(project_id, "regenerate"):
                await QuestionnaireService._generate_ocg(
                    questionnaire_id=q.id,
                    project_id=project_id,
                    gp_email=q.gp_email,
                )
        except HTTPException:
            # 409 de conflito — já logado pelo lock manager
            raise
        except Exception as exc:
            logger.error(
                "ocg.regenerate_background_failed",
                project_id=str(project_id),
                questionnaire_id=str(q.id),
                error=str(exc),
            )

    asyncio.create_task(_regenerate_with_lock())

    logger.info(
        "ocg.regenerate_dispatched",
        project_id=str(project_id),
        questionnaire_id=str(q.id),
    )

    return {
        "success": True,
        "message": "Regeneração do OCG disparada em background. Verifique em alguns minutos.",
        "questionnaire_id": str(q.id),
    }


@router.get("/{project_id}/ocg")
async def get_project_ocg(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o OCG mais recente do projeto."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    result = await db.execute(
        select(OCG)
        .where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc())
        .limit(1)
    )
    ocg = result.scalar_one_or_none()

    if not ocg:
        return {
            "ocg": None,
            "message": "OCG ainda não gerado para este projeto. Aguardando análise do questionário."
        }

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except json.JSONDecodeError:
        ocg_data = {}

    return {
        "ocg": {
            "id": str(ocg.id),
            "version": getattr(ocg, 'version', 1),
            "schema_version": getattr(ocg, 'schema_version', '1.0.0'),
            "overall_score": ocg.overall_score,
            "p1_business_score": ocg.p1_business_score,
            "p2_rules_score": ocg.p2_rules_score,
            "p3_features_score": ocg.p3_features_score,
            "p4_nfr_score": ocg.p4_nfr_score,
            "p5_architecture_score": ocg.p5_architecture_score,
            "p6_data_score": ocg.p6_data_score,
            "p7_security_score": ocg.p7_security_score,
            "status": ocg.status,
            "is_blocking": ocg.is_blocking,
            "ocg_data": ocg_data,
            "generated_at": ocg.generated_at.isoformat() if ocg.generated_at else None,
        }
    }


@router.get("/{project_id}/ocg/history")
async def get_ocg_history(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de versões do OCG com autor, trigger e flag de rollback disponível."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog, User, OCG

    result = await db.execute(
        select(OCGDeltaLog, User)
        .outerjoin(User, OCGDeltaLog.changed_by == User.id)
        .where(OCGDeltaLog.project_id == project_id)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(50)
    )
    rows = result.all()

    # Versão atual para marcar qual linha permite rollback (todas exceto a atual com snapshot)
    current_ocg = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    current = current_ocg.scalar_one_or_none()
    current_version = current.version if current else 0

    return {
        "current_version": current_version,
        "history": [
            {
                "id": str(d.id),
                "version_from": d.ocg_version_from,
                "version_to": d.ocg_version_to,
                "change_summary": d.change_summary,
                "fields_changed": d.fields_changed,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "changed_by": {
                    "id": str(u.id),
                    "full_name": u.full_name or u.email.split("@")[0],
                    "email": u.email,
                } if u else None,
                "trigger_source": d.trigger_source,
                "can_rollback": d.ocg_snapshot is not None and d.ocg_version_to != current_version,
            }
            for d, u in rows
        ],
    }


@router.get("/{project_id}/ocg/snapshot/{version_to}")
async def get_ocg_snapshot(
    project_id: UUID,
    version_to: int,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna o snapshot completo do OCG na versão indicada."""
    from sqlalchemy import select
    from app.models.base import OCGDeltaLog

    result = await db.execute(
        select(OCGDeltaLog)
        .where(OCGDeltaLog.project_id == project_id, OCGDeltaLog.ocg_version_to == version_to)
        .order_by(OCGDeltaLog.created_at.desc())
        .limit(1)
    )
    delta = result.scalar_one_or_none()
    if not delta or not delta.ocg_snapshot:
        raise HTTPException(status_code=404, detail="Snapshot não disponível para essa versão")
    import json as _json
    return {"version": version_to, "snapshot": _json.loads(delta.ocg_snapshot)}


@router.post("/{project_id}/ocg/rollback/{version_to}")
async def rollback_ocg(
    project_id: UUID,
    version_to: int,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Reverte OCG para snapshot de versão anterior. Cria nova versão com trigger_source='rollback'.

    MVP 14 Fase 14.7: delega ao `OCGService.rollback_to_version`, que
    emite evento canônico `OCG_ROLLED_BACK` em `audit_log_global`.
    """
    from app.services.ocg_service import OCGService

    current_user_id = permissions["user_id"]
    try:
        result = await OCGService(db).rollback_to_version(
            project_id=project_id,
            version_to=version_to,
            actor_id=current_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"success": True, **result}


@router.post("/{project_id}/ocg/consolidate")
async def consolidate_ocg(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 14 Fase 14.8 — consolidação explícita do OCG.

    Recalcula `COMPOSITE_SCORE`/`status`/`is_blocking` a partir de
    `PILLAR_SCORES` atuais. Idempotente: se nada mudar, retorna
    `changed=False`. Emite `OCG_CONSOLIDATED` em `audit_log_global`.
    """
    from app.services.ocg_service import OCGService

    current_user_id = permissions["user_id"]
    try:
        result = await OCGService(db).consolidate_ocg(
            project_id=project_id,
            actor_id=current_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"success": True, **result}


@router.get("/{project_id}/ocg/health")
async def get_ocg_health(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Saúde do contexto OCG."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = result.scalar_one_or_none()
    if not ocg:
        return {"health": None, "message": "OCG não encontrado"}

    health = {}
    if hasattr(ocg, 'context_health') and ocg.context_health:
        try:
            health = json.loads(ocg.context_health)
        except json.JSONDecodeError:
            pass

    return {
        "health": health,
        "version": getattr(ocg, 'version', 1),
        "change_type": getattr(ocg, 'change_type', 'INITIAL'),
        "overall_score": ocg.overall_score,
        "status": ocg.status,
    }


@router.post("/{project_id}/ocg/propagate")
async def force_propagation(
    project_id: UUID,
    permissions: dict = Depends(require_action("pipeline:execute")),
    db: AsyncSession = Depends(get_db),
):
    """Forçar re-propagação do OCG para módulos dependentes."""
    from app.services.propagation_service import PropagationService
    propagator = PropagationService(db)
    result = await propagator.propagate(project_id, changes=[{"field": "MANUAL_PROPAGATION"}])
    return result


# ─── MVP 23 Fase 23.5 — RNF_CONTRACTS editável pelo GP ───────────────
# Contratos RNF canônicos do OCG (performance, security, compliance,
# availability). Leitura para qualquer papel com acesso ao projeto;
# escrita só com `project:manage_team` (GP/Admin). Validação
# determinística via `validate_contract_dict` — nunca LLM.


@router.get("/{project_id}/ocg/rnf-contracts")
async def get_rnf_contracts(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna `RNF_CONTRACTS` atual do OCG (dict canônico ou `{}`)."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg:
        raise HTTPException(
            status_code=404,
            detail="OCG do projeto não encontrado",
        )
    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}

    rnf = ocg_data.get("RNF_CONTRACTS") or {}
    if not isinstance(rnf, dict):
        rnf = {}

    return {
        "project_id": str(project_id),
        "ocg_version": ocg.version,
        "rnf_contracts": rnf,
    }


class RnfContractsPutBody(BaseModel):
    rnf_contracts: dict = Field(default_factory=dict)


@router.put("/{project_id}/ocg/rnf-contracts")
async def put_rnf_contracts(
    project_id: UUID,
    body: RnfContractsPutBody,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza `RNF_CONTRACTS` do OCG. Valida contra schema canônico;
    422 se inválido. Idempotente (mesmo payload → sem bump de versão)."""
    from sqlalchemy import select
    from app.models.base import OCG
    from app.services.rnf_contracts import validate_contract_dict
    from app.services.audit_service import AuditEvents, AuditService
    from datetime import datetime, timezone
    import json

    errors = validate_contract_dict(body.rnf_contracts)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [
                {"path": e.path, "message": e.message} for e in errors
            ]},
        )

    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg:
        raise HTTPException(
            status_code=404,
            detail="OCG do projeto não encontrado",
        )

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}

    current = ocg_data.get("RNF_CONTRACTS") or {}
    if not isinstance(current, dict):
        current = {}

    if current == body.rnf_contracts:
        return {
            "applied": False,
            "ocg_version": ocg.version,
            "rnf_contracts": current,
        }

    ocg_data["RNF_CONTRACTS"] = body.rnf_contracts
    new_version = (ocg.version or 0) + 1
    ocg.ocg_data = json.dumps(ocg_data, ensure_ascii=False)
    ocg.version = new_version
    ocg.updated_at = datetime.now(timezone.utc)
    db.add(ocg)

    actor_id = permissions["user_id"]
    await AuditService(db).log_event(
        event_type=AuditEvents.OCG_UPDATED,
        resource_type="ocg",
        actor_id=actor_id,
        resource_id=ocg.id,
        details={
            "project_id": str(project_id),
            "version_from": new_version - 1,
            "version_to": new_version,
            "source": "rnf_contracts.put",
        },
    )
    await db.commit()

    return {
        "applied": True,
        "ocg_version": new_version,
        "rnf_contracts": body.rnf_contracts,
    }


# ─── MVP 25 Fase 25.5 — Design tokens editáveis pelo GP ──────────────
# Tokens canônicos em STACK_RECOMMENDATION.frontend.design_tokens.
# Leitura para qualquer papel com acesso ao projeto; escrita só com
# `project:manage_team` (GP/Admin). Validação determinística via
# `validate_tokens_dict` — zero LLM no caminho crítico.


@router.get("/{project_id}/ocg/design-tokens")
async def get_design_tokens(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna `design_tokens` atual do OCG (dict canônico ou `{}`)."""
    from sqlalchemy import select
    from app.models.base import OCG
    import json

    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg:
        raise HTTPException(
            status_code=404,
            detail="OCG do projeto não encontrado",
        )
    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}

    frontend = (
        (ocg_data.get("STACK_RECOMMENDATION") or {}).get("frontend") or {}
    )
    tokens = frontend.get("design_tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}

    return {
        "project_id": str(project_id),
        "ocg_version": ocg.version,
        "design_tokens": tokens,
    }


class DesignTokensPutBody(BaseModel):
    design_tokens: dict = Field(default_factory=dict)


@router.put("/{project_id}/ocg/design-tokens")
async def put_design_tokens(
    project_id: UUID,
    body: DesignTokensPutBody,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza `design_tokens` do OCG. Valida contra schema canônico;
    422 se inválido. Idempotente (payload idêntico ignorando
    `generated_at` não bumpa versão).

    Lifecycle do `source`:
      - Payload anterior com source="css_ingested" + edição manual → "mixed"
      - Sem payload anterior ou anterior "manual" → preserva "manual"
      - Se o body não declarar source, assumimos "manual".
    """
    from sqlalchemy import select
    from app.models.base import OCG
    from app.services.design_tokens import validate_tokens_dict
    from app.services.audit_service import AuditEvents, AuditService
    from datetime import datetime, timezone
    import json

    errors = validate_tokens_dict(body.design_tokens)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": [
                {"path": e.path, "message": e.message} for e in errors
            ]},
        )

    row = await db.execute(
        select(OCG).where(OCG.project_id == project_id)
        .order_by(OCG.created_at.desc()).limit(1)
    )
    ocg = row.scalar_one_or_none()
    if not ocg:
        raise HTTPException(
            status_code=404,
            detail="OCG do projeto não encontrado",
        )

    try:
        ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
    except (TypeError, ValueError):
        ocg_data = {}

    stack = ocg_data.get("STACK_RECOMMENDATION")
    if not isinstance(stack, dict):
        stack = {}
    frontend = stack.get("frontend")
    if not isinstance(frontend, dict):
        frontend = {}

    current = frontend.get("design_tokens") if isinstance(frontend.get("design_tokens"), dict) else None

    incoming = dict(body.design_tokens) if body.design_tokens else {}

    # Idempotência: ignora generated_at (só carimbo do timestamp não bumpa)
    def _strip_ts(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "generated_at"}

    if current is not None and _strip_ts(current) == _strip_ts(incoming):
        return {
            "applied": False,
            "ocg_version": ocg.version,
            "design_tokens": current,
        }

    # Source lifecycle canônico
    prev_source = (current or {}).get("source")
    if "source" not in incoming:
        incoming["source"] = "mixed" if prev_source == "css_ingested" else "manual"
    incoming["generated_at"] = datetime.now(timezone.utc).isoformat()

    frontend["design_tokens"] = incoming
    stack["frontend"] = frontend
    ocg_data["STACK_RECOMMENDATION"] = stack

    new_version = (ocg.version or 0) + 1
    ocg.ocg_data = json.dumps(ocg_data, ensure_ascii=False)
    ocg.version = new_version
    ocg.updated_at = datetime.now(timezone.utc)
    db.add(ocg)

    actor_id = permissions["user_id"]
    await AuditService(db).log_event(
        event_type=AuditEvents.OCG_UPDATED,
        resource_type="ocg",
        actor_id=actor_id,
        resource_id=ocg.id,
        details={
            "project_id": str(project_id),
            "version_from": new_version - 1,
            "version_to": new_version,
            "source": "design_tokens.put",
            "tokens_source": incoming["source"],
        },
    )
    await db.commit()

    return {
        "applied": True,
        "ocg_version": new_version,
        "design_tokens": incoming,
    }


@router.get("/{project_id}/billing")
async def get_project_billing(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Resumo de gastos de IA do projeto."""
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(db)
    return await billing.get_project_summary(project_id)


@router.get("/{project_id}/billing/detail")
async def get_project_billing_detail(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Log detalhado de chamadas IA do projeto."""
    from app.services.ai_billing_service import AIBillingService
    billing = AIBillingService(db)
    entries = await billing.get_project_detail(project_id, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/{project_id}/permissions")
async def get_user_permissions(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Retorna os papeis e acoes do usuario no projeto."""
    from app.dependencies.require_action import resolve_user_roles_in_project
    from app.core.permissions import get_actions_for_roles

    roles = await resolve_user_roles_in_project(user_id, project_id, db)
    actions = get_actions_for_roles(roles)
    return {
        "roles": roles,
        "actions": sorted(actions),
        "is_read_only": roles == ["admin_viewer"] or actions <= {"project:view", "project:manage_gp"},
    }
