"""
Admin Router
Rotas de admin para gerenciar projetos e tenants
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr
import structlog
import secrets
import string

from app.db.database import get_db
from app.services.admin_service import AdminService
from app.services.email_service import EmailService
from app.middleware.auth import get_current_user_from_token, require_admin
from app.models.base import User
from app.models.onboarding import DeliverableType
from app.core.security import hash_password

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["admin"])


# ========== REQUEST MODELS ==========

class CreateProjectRequest(BaseModel):
    """Request to create new project"""
    project_name: str
    project_slug: str
    description: str = None
    deliverable_type: DeliverableType  # Gate bloqueante — obrigatório


class RejectProjectRequest(BaseModel):
    """Request to reject a project"""
    reason: str


class TicketResponseRequest(BaseModel):
    """Request to respond to a support ticket"""
    message: str
    resolve: bool = False


class WebhookTestRequest(BaseModel):
    """Request to test a webhook integration"""
    integration_type: str  # teams, slack, discord
    webhook_url: str


class InviteAdminRequest(BaseModel):
    """Request to invite a new admin user"""
    email: EmailStr
    full_name: str


class InviteAdminResponse(BaseModel):
    """Response from admin invitation"""
    success: bool
    message: str
    user_id: str = None


# ========== PROJECT MANAGEMENT ==========

@router.post("/projects")
async def create_project(
    req: CreateProjectRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin creates new project request
    Transitions from pending → approved → active
    """
    try:
        service = AdminService(db)

        # Cria solicitação
        project = await service.create_project_request(
            gp_id=current_user_id,
            project_name=req.project_name,
            project_slug=req.project_slug,
            description=req.description,
            deliverable_type=req.deliverable_type
        )

        return {
            "status": "pending",
            "project_id": str(project.id),
            "project_name": project.project_name,
            "project_slug": project.project_slug,
            "deliverable_type": project.deliverable_type.value if hasattr(project.deliverable_type, 'value') else (project.deliverable_type or "new_system"),
            "schema_name": project.schema_name,
            "message": "Solicitação de projeto criada. Aguardando aprovação do administrador.",
            "next_step": "admin_approval"
        }

    except ValueError as e:
        logger.warning("admin.create_project_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.create_project_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar projeto"
        )


@router.get("/deliverable-types")
async def get_deliverable_types():
    """Retorna os tipos de entregável disponíveis (gate bloqueante)"""
    labels = {
        "new_system": "Sistema web novo",
        "mobile_app": "Aplicação mobile",
        "module": "Módulo funcional / Extensão de ecossistema",
        "enhancement": "Melhoria em sistema existente",
        "integration": "Integração com sistema legado",
        "modernization": "Modernização / Refatoração",
        "etl": "ETL / ELT / Integração de dados",
        "maintenance": "Sustentação evolutiva",
    }
    descriptions = {
        "new_system": "Projeto standalone criado do zero, sem dependência de sistemas existentes",
        "mobile_app": "Aplicativo para dispositivos móveis (iOS, Android, híbrido)",
        "module": "Módulo com domínio próprio que complementa um ecossistema existente (ex: seção de investimentos em internet banking)",
        "enhancement": "Alteração ou evolução de funcionalidades já existentes em um sistema",
        "integration": "Conectar sistemas distintos via APIs, filas ou protocolos de dados",
        "modernization": "Refatoração arquitetural, migração de stack ou decomposição de monolito",
        "etl": "Pipeline de extração, transformação e carga de dados entre sistemas",
        "maintenance": "Correções contínuas, ajustes evolutivos e sustentação operacional",
    }
    return [
        {"value": dt.value, "label": labels[dt.value], "description": descriptions[dt.value]}
        for dt in DeliverableType
    ]


@router.get("/projects/pending")
async def get_pending_projects(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin visualiza todas as solicitações pendentes de projeto.
    Inclui dados do GP para exibição na tabela.
    """
    try:
        service = AdminService(db)
        projects = await service.get_pending_projects()

        # Batch: slugs dos requests aprovados → projeto real em `projects`
        # (se existir). Permite detectar órfãos (request APPROVED sem projeto).
        from app.models.base import Project as _Project
        slugs = [p.project_slug for p in projects if p.project_slug]
        proj_rows = (await db.execute(
            select(_Project.slug, _Project.id, _Project.status)
            .where(_Project.slug.in_(slugs))
        )).all() if slugs else []
        proj_by_slug = {r.slug: {"id": str(r.id), "status": r.status} for r in proj_rows}

        result = []
        for p in projects:
            # Buscar dados do GP
            gp_result = await db.execute(select(User).where(User.id == p.gp_id))
            gp = gp_result.scalar_one_or_none()

            # Parse requirements_json (vem como string do wizard) p/ admin ver Q&A
            import json as _json
            try:
                requirements = _json.loads(p.requirements_json) if p.requirements_json else {}
            except (ValueError, TypeError):
                requirements = {}

            request_status = p.status.value if hasattr(p.status, 'value') else str(p.status)
            linked = proj_by_slug.get(p.project_slug)
            # Derivar project_status (vindo de `projects`) quando APPROVED.
            # Se APPROVED mas projeto não existe → órfão (deletado hard no passado).
            if request_status.lower() == "approved":
                project_lifecycle_status = linked["status"] if linked else "orphan"
                project_real_id = linked["id"] if linked else None
            else:
                project_lifecycle_status = None
                project_real_id = None

            result.append({
                "id": str(p.id),
                "gp_id": str(p.gp_id),
                "project_name": p.project_name,
                "project_slug": p.project_slug,
                "description": p.description or "",
                "deliverable_type": p.deliverable_type.value if hasattr(p.deliverable_type, 'value') else (p.deliverable_type or "new_system"),
                "custom_deliverable_type": p.custom_deliverable_type or "",
                "requirements": requirements,
                "status": request_status,
                # Novos campos — lifecycle do projeto real (active|paused|inactive|archived|orphan|None)
                "project_lifecycle_status": project_lifecycle_status,
                "project_id": project_real_id,
                "gp_name": gp.full_name if gp else "",
                "gp_email": gp.email if gp else "",
                "requested_at": p.requested_at.isoformat() if p.requested_at else "",
                "rejection_reason": p.rejection_reason or "",
            })

        pending_count = sum(1 for p in result if p["status"] == "pending")
        return {"pending_projects": result, "count": len(result), "pending_count": pending_count}

    except Exception as e:
        logger.error("admin.get_pending_projects_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar projetos pendentes"
        )


@router.post("/projects/{project_id}/approve")
async def approve_project(
    project_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin approves project and provisions tenant
    """
    try:
        service = AdminService(db)

        project = await service.approve_project_request(
            request_id=project_id,
            admin_id=current_user_id
        )

        return {
            "status": "approved",
            "project_id": str(project.id),
            "project_slug": project.project_slug,
            "schema_name": project.schema_name,
            "approved_at": project.approved_at.isoformat(),
            "message": "Projeto aprovado e ambiente provisionado",
            "next_step": "gp_onboarding",
            "gp_onboarding_url": f"/projects/{project.project_slug}/onboarding"
        }

    except ValueError as e:
        logger.warning("admin.approve_project_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.approve_project_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao aprovar projeto"
        )


@router.post("/projects/{project_id}/reject")
async def reject_project(
    project_id: UUID,
    req: RejectProjectRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin rejects project request with reason
    """
    try:
        service = AdminService(db)

        project = await service.reject_project_request(
            request_id=project_id,
            admin_id=current_user_id,
            reason=req.reason
        )

        return {
            "status": "rejected",
            "project_id": str(project.id),
            "project_slug": project.project_slug,
            "rejection_reason": project.rejection_reason,
            "rejected_at": project.approved_at.isoformat(),
            "message": "Solicitação de projeto rejeitada"
        }

    except ValueError as e:
        logger.warning("admin.reject_project_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.reject_project_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao rejeitar projeto"
        )


class ProjectMessageRequest(BaseModel):
    """Mensagem do admin para o GP do projeto"""
    message: str
    project_name: str


@router.post("/projects/{project_id}/message")
async def send_message_to_gp(
    project_id: UUID,
    req: ProjectMessageRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin envia mensagem ao GP de um projeto pendente.
    Subject: "Edição de Projeto - [Nome do Projeto]"
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Mensagem é obrigatória")
    if len(req.message) > 1000:
        raise HTTPException(status_code=400, detail="Mensagem deve ter no máximo 1000 caracteres")

    from app.models.onboarding import ProjectRequest
    result = await db.execute(select(ProjectRequest).where(ProjectRequest.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Buscar GP
    gp_result = await db.execute(select(User).where(User.id == project.gp_id))
    gp = gp_result.scalar_one_or_none()
    if not gp:
        raise HTTPException(status_code=404, detail="Gerente de Projeto não encontrado")

    # Buscar admin que está enviando
    admin_result = await db.execute(select(User).where(User.id == current_user_id))
    admin_user = admin_result.scalar_one_or_none()
    admin_name = admin_user.full_name if admin_user else "Administrador GCA"

    # Enviar email
    subject = f"Edição de Projeto - {req.project_name}"
    body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1e1b4b; padding: 20px; border-radius: 12px 12px 0 0;">
            <h2 style="color: #c4b5fd; margin: 0;">GCA — Edição de Projeto</h2>
        </div>
        <div style="background: #1e293b; padding: 24px; border-radius: 0 0 12px 12px; color: #cbd5e1;">
            <p>Olá <strong>{gp.full_name}</strong>,</p>
            <p>O administrador <strong>{admin_name}</strong> enviou uma mensagem sobre o projeto <strong>{req.project_name}</strong>:</p>
            <div style="background: #0f172a; padding: 16px; border-radius: 8px; border-left: 4px solid #7c3aed; margin: 16px 0;">
                <p style="margin: 0; white-space: pre-wrap;">{req.message}</p>
            </div>
            <p>Por favor, acesse o GCA para revisar e atualizar as informações solicitadas.</p>
            <hr style="border-color: #334155; margin: 20px 0;" />
            <p style="color: #64748b; font-size: 12px;">Este e-mail foi enviado automaticamente pelo GCA — Gestão de Codificação Assistida.</p>
        </div>
    </div>
    """

    try:
        success, error = EmailService.send_email(
            to_email=gp.email,
            subject=subject,
            html_content=body,
        )
        if not success:
            logger.warning("admin.message_email_failed", email=gp.email, error=error)
            return {"success": True, "message": f"Mensagem registrada, mas o envio de e-mail falhou: {error}", "email_sent": False}
    except Exception as e:
        logger.warning("admin.message_email_error", error=str(e))
        return {"success": True, "message": "Mensagem registrada, mas o envio de e-mail falhou", "email_sent": False}

    logger.info("admin.message_sent_to_gp", project_id=str(project_id), gp_email=gp.email)
    return {"success": True, "message": f"Mensagem enviada para {gp.email}", "email_sent": True}


@router.delete("/projects/{project_id}")
async def delete_project_request(
    project_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin exclui uma solicitação de projeto pendente."""
    from app.models.onboarding import ProjectRequest
    result = await db.execute(select(ProjectRequest).where(ProjectRequest.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    await db.delete(project)
    await db.commit()
    logger.info("admin.project_request_deleted", project_id=str(project_id))
    return {"success": True, "message": "Solicitação de projeto excluída"}


# ========== USER MANAGEMENT ==========

@router.get("/users")
async def list_users(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin lista todos os usuários do sistema com seus papéis por projeto.

    Para cada não-admin, retorna `project_roles: [{project_id, project_name,
    project_slug, role}]` para a UI exibir pills "papel @ projeto". Admins
    são da camada administrativa e não têm projetos (regra de negócio do
    GCA — Admin nunca atua em projetos, ver memória RBAC_RULES).
    """
    try:
        from app.models.base import Project, ProjectMember

        service = AdminService(db)
        users = await service.list_users()

        # Uma única query lateral para todos os memberships ativos —
        # evita N+1. Inclui só projetos não arquivados.
        memberships_res = await db.execute(
            select(
                ProjectMember.user_id,
                ProjectMember.role,
                Project.id,
                Project.name,
                Project.slug,
                Project.short_slug,
            )
            .join(Project, Project.id == ProjectMember.project_id)
            .where(
                ProjectMember.is_active == True,  # noqa: E712
                Project.status != "archived",
            )
        )
        # Agrupa por user_id
        memberships_by_user: dict = {}
        for row in memberships_res.all():
            user_id, role, p_id, p_name, p_slug, p_short_slug = row
            memberships_by_user.setdefault(str(user_id), []).append({
                "project_id": str(p_id),
                "project_name": p_name,
                "project_slug": p_short_slug or p_slug,
                "role": role,
            })

        return {
            "users": [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "full_name": u.full_name,
                    "is_active": u.is_active,
                    "is_admin": u.is_admin,
                    "created_at": u.created_at.isoformat(),
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                    # Admin → vazio (sistema, não projetos). Demais → lista por projeto.
                    "project_roles": [] if u.is_admin else memberships_by_user.get(str(u.id), []),
                }
                for u in users
            ],
            "count": len(users)
        }

    except Exception as e:
        logger.error("admin.list_users_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar usuários"
        )


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin resets user password and generates temporary password
    Automatically sends email to user with temporary password
    """
    try:
        service = AdminService(db)
        result = await service.reset_user_password(user_id)

        # Send email with temporary password
        email_success, email_error = EmailService.send_admin_password_reset_email(
            to_email=result["email"],
            user_name=result.get("full_name", result["email"].split("@")[0]),
            temp_password=result["temp_password"]
        )

        return {
            "status": "password_reset",
            "user_id": result["user_id"],
            "email": result["email"],
            "temp_password": result["temp_password"],
            "reset_at": result["reset_at"],
            "email_sent": email_success,
            "email_error": email_error,
            "message": "Senha redefinida com sucesso. Email enviado ao usuário.",
            "instructions": "Usuário deve alterar a senha no primeiro login"
        }

    except ValueError as e:
        logger.warning("admin.reset_password_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.reset_password_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao redefinir senha"
        )


@router.post("/users/{user_id}/lock")
async def lock_user(
    user_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin locks (deactivates) a user account
    Locked users cannot login
    """
    try:
        service = AdminService(db)
        result = await service.lock_user(user_id, actor_id=current_user_id)

        return {
            "status": "user_locked",
            "user_id": result["user_id"],
            "email": result["email"],
            "is_active": result["is_active"],
            "locked_at": result["locked_at"],
            "message": "Conta do usuário bloqueada. Não poderá fazer login até ser desbloqueada."
        }

    except PermissionError as e:
        # MVP 11 Fase 11.3 — guard de último Admin ou self-lock
        logger.warning("admin.lock_user_blocked", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        logger.warning("admin.lock_user_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.lock_user_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao bloquear usuário"
        )


@router.post("/users/{user_id}/unlock")
async def unlock_user(
    user_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin unlocks (reactivates) a user account
    Unlocked users can login again
    """
    try:
        service = AdminService(db)
        result = await service.unlock_user(user_id)

        return {
            "status": "user_unlocked",
            "user_id": result["user_id"],
            "email": result["email"],
            "is_active": result["is_active"],
            "unlocked_at": result["unlocked_at"],
            "message": "Conta do usuário desbloqueada. Pode fazer login novamente."
        }

    except ValueError as e:
        logger.warning("admin.unlock_user_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.unlock_user_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao desbloquear usuário"
        )


# ========== SUSPICIOUS ACCESS MONITORING ==========

@router.get("/suspicious-access")
async def get_suspicious_access(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin views all blocked users due to suspicious access attempts
    Shows: user, project, attempt count, when blocked
    """
    try:
        service = AdminService(db)
        attempts = await service.get_suspicious_access_attempts()

        return {
            "suspicious_accesses": [
                {
                    "access_attempt_id": str(a.id),
                    "user_id": str(a.user_id),
                    "user_email": a.user.email,
                    "user_name": a.user.full_name,
                    "project_id": str(a.project_id),
                    "project_name": a.project.name,
                    "attempt_number": a.attempt_number,
                    "blocked": a.blocked,
                    "blocked_at": a.blocked_at.isoformat() if a.blocked_at else None,
                    "created_at": a.created_at.isoformat()
                }
                for a in attempts
            ],
            "count": len(attempts),
            "message": "Lista de usuários bloqueados por tentativas de acesso suspeitas"
        }

    except Exception as e:
        logger.error("admin.get_suspicious_access_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar tentativas de acesso suspeitas"
        )


@router.post("/suspicious-access/{access_attempt_id}/unblock")
async def unblock_suspicious_access(
    access_attempt_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin unblocks a user who was locked due to suspicious access attempts
    User can login again after unblocking
    """
    try:
        service = AdminService(db)
        result = await service.unlock_suspicious_access(access_attempt_id)

        return {
            "status": "suspicious_access_unblocked",
            "access_attempt_id": result["access_attempt_id"],
            "user_id": result["user_id"],
            "project_id": result["project_id"],
            "blocked": result["blocked"],
            "unblocked_at": result["unblocked_at"],
            "message": "Usuário desbloqueado e pode fazer login novamente."
        }

    except ValueError as e:
        logger.warning("admin.unblock_suspicious_access_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.unblock_suspicious_access_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao desbloquear acesso suspeito"
        )


# ========== SAC - SUPPORT TICKETS ==========

@router.get("/tickets")
async def list_tickets(
    status: str = Query(None, description="Filter by status: ABERTO, EM_ANÁLISE, AGUARDANDO_FEEDBACK, RESOLVIDO"),
    severity: str = Query(None, description="Filter by severity: BAIXO, MÉDIO, ALTO, CRÍTICO"),
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin lists all support tickets
    Can filter by status and severity
    """
    try:
        service = AdminService(db)
        tickets = await service.get_all_tickets(status=status, severity=severity)

        return {
            "tickets": [
                {
                    "id": str(t.id),
                    "user_id": str(t.user_id),
                    "user_email": t.user.email,
                    "user_name": t.user.full_name,
                    "project_id": str(t.project_id),
                    "project_name": t.project.name,
                    "title": t.title,
                    "description": t.description[:200] + "..." if len(t.description) > 200 else t.description,
                    "severity": t.severity,
                    "status": t.status,
                    "created_at": t.created_at.isoformat(),
                    "first_response_at": t.first_response_at.isoformat() if t.first_response_at else None,
                    "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                    "response_count": len(t.responses)
                }
                for t in tickets
            ],
            "count": len(tickets),
            "filters": {
                "status": status,
                "severity": severity
            }
        }

    except Exception as e:
        logger.error("admin.list_tickets_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar tickets"
        )


@router.get("/tickets/{ticket_id}")
async def get_ticket_details(
    ticket_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin gets full details of a support ticket
    Includes all responses/replies
    """
    try:
        service = AdminService(db)
        ticket = await service.get_ticket_details(ticket_id)

        return {
            "ticket": {
                "id": str(ticket.id),
                "user_id": str(ticket.user_id),
                "user_email": ticket.user.email,
                "user_name": ticket.user.full_name,
                "project_id": str(ticket.project_id),
                "project_name": ticket.project.name,
                "title": ticket.title,
                "description": ticket.description,
                "error_message": ticket.error_message,
                "erratic_behavior": ticket.erratic_behavior,
                "severity": ticket.severity,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat(),
                "first_response_at": ticket.first_response_at.isoformat() if ticket.first_response_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                "responses": [
                    {
                        "response_id": str(r.id),
                        "responder_id": str(r.responder_id) if r.responder_id else None,
                        "responder_email": r.responder.email if r.responder else None,
                        "message": r.message,
                        "is_resolution": r.is_resolution,
                        "created_at": r.created_at.isoformat()
                    }
                    for r in ticket.responses
                ]
            }
        }

    except ValueError as e:
        logger.warning("admin.get_ticket_details_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.get_ticket_details_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar detalhes do ticket"
        )


@router.post("/tickets/{ticket_id}/respond")
async def respond_to_ticket(
    ticket_id: UUID,
    req: TicketResponseRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin/GP responds to a support ticket
    Can optionally mark as resolved (resolve=True)
    """
    try:
        service = AdminService(db)
        result = await service.respond_to_ticket(
            ticket_id=ticket_id,
            responder_id=current_user_id,
            message=req.message,
            resolve=req.resolve
        )

        return {
            "status": "response_added",
            "response_id": result["response_id"],
            "ticket_id": result["ticket_id"],
            "ticket_status": result["ticket_status"],
            "message": result["message"],
            "is_resolution": result["is_resolution"],
            "responded_at": result["responded_at"],
            "notification": "Usuário será notificado desta resposta por email" if not req.resolve else "Ticket marcado como resolvido"
        }

    except ValueError as e:
        logger.warning("admin.respond_to_ticket_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.respond_to_ticket_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao responder ticket"
        )


# ========== DASHBOARD EXECUTIVO ==========

@router.get("/dashboard/metrics")
async def get_dashboard_metrics(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Executive dashboard with system metrics
    Shows: project count, ticket metrics, security alerts, system health
    """
    try:
        service = AdminService(db)
        metrics = await service.get_dashboard_metrics()

        return {
            "status": "success",
            "data": metrics,
            "message": "Métricas do painel executivo obtidas com sucesso"
        }

    except Exception as e:
        logger.error("admin.dashboard_metrics_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar métricas do painel"
        )


# ========== INTEGRATIONS & ALERTS ==========

@router.post("/integrations/webhook-test")
async def test_webhook(
    req: WebhookTestRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Test a webhook integration (Teams, Slack, Discord)
    Sends a test message to verify the webhook is working
    """
    try:
        service = AdminService(db)
        result = await service.test_webhook(req.integration_type, req.webhook_url)

        return {
            "status": "webhook_test_completed",
            "integration_type": req.integration_type,
            "success": result["success"],
            "status_code": result.get("status_code"),
            "message": result.get("message", result.get("error")),
            "tested_at": result["tested_at"]
        }

    except Exception as e:
        logger.error("admin.webhook_test_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao testar webhook"
        )


@router.get("/alerts/history")
async def get_alerts_history(
    alert_type: str = Query(None, description="Filter by alert type"),
    severity: str = Query(None, description="Filter by severity: info, warning, critical"),
    status: str = Query(None, description="Filter by status: pending, sent, failed, acknowledged"),
    limit: int = Query(50, description="Number of alerts to retrieve (max 100)"),
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin views system alerts history
    Can filter by type, severity, and status
    """
    try:
        # Limit max to 100
        if limit > 100:
            limit = 100

        service = AdminService(db)
        alerts = await service.get_alerts_history(
            alert_type=alert_type,
            severity=severity,
            status=status,
            limit=limit
        )

        return {
            "alerts": [
                {
                    "id": str(a.id),
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "title": a.title,
                    "message": a.message,
                    "status": a.status,
                    "sent_to_teams": a.sent_to_teams,
                    "sent_to_slack": a.sent_to_slack,
                    "sent_via_email": a.sent_via_email,
                    "created_at": a.created_at.isoformat(),
                    "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                    "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None
                }
                for a in alerts
            ],
            "count": len(alerts),
            "filters": {
                "alert_type": alert_type,
                "severity": severity,
                "status": status
            }
        }

    except Exception as e:
        logger.error("admin.alerts_history_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar histórico de alertas"
        )


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin acknowledges an alert as resolved/reviewed
    """
    try:
        service = AdminService(db)
        result = await service.acknowledge_alert(alert_id, current_user_id)

        return {
            "status": "alert_acknowledged",
            "alert_id": result["alert_id"],
            "alert_status": result["status"],
            "acknowledged_at": result["acknowledged_at"],
            "message": "Alerta marcado como confirmado"
        }

    except ValueError as e:
        logger.warning("admin.acknowledge_alert_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("admin.acknowledge_alert_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao confirmar alerta"
        )


# ========== ADMIN USER MANAGEMENT ==========

# Helper movido para `app.core.security.generate_temporary_password` em
# 2026-04-22 — evita duplicação com project_team_service.
from app.core.security import generate_temporary_password  # noqa: E402  (re-export)


@router.post("/invite-admin", response_model=InviteAdminResponse)
async def invite_admin_user(
    request: InviteAdminRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
) -> InviteAdminResponse:
    """
    Invite a new admin user via email with temporary password.
    Creates an InvitationToken (expires 7 days). User is NOT created until
    they validate the temp password and set a permanent one.
    """
    from app.models.base import InvitationToken
    from datetime import timedelta

    try:
        # require_admin already verified admin status

        # Get current user for name
        stmt = select(User).where(User.id == current_user_id)
        result = await db.execute(stmt)
        current_user = result.scalar_one_or_none()

        # Check if user already exists
        stmt = select(User).where(User.email == request.email)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário com este email já existe")

        # Check if active invitation already exists
        stmt = select(InvitationToken).where(
            InvitationToken.email == request.email,
            InvitationToken.is_used == False,
            InvitationToken.expires_at > datetime.now(timezone.utc),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Já existe convite ativo para este email")

        # Generate token and temporary password
        invite_token = secrets.token_urlsafe(32)
        temp_password = generate_temporary_password()

        # Create InvitationToken (NOT the user yet)
        invitation = InvitationToken(
            id=uuid4(),
            email=request.email,
            full_name=request.full_name,
            role="admin",
            token=invite_token,
            temporary_password_hash=hash_password(temp_password),
            invited_by_id=current_user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(invitation)
        await db.commit()

        # Send email with link to AcceptInvitationPage
        activation_link = f"https://gca.code-auditor.com.br/accept-invitation?token={invite_token}"
        invited_by_name = current_user.full_name or current_user.email or "Administrator"

        success, error = EmailService.send_admin_invitation_email(
            to_email=request.email,
            invited_by_name=invited_by_name,
            temporary_password=temp_password,
            activation_link=activation_link
        )

        if not success:
            logger.warning("admin.invite_email_failed", email=request.email, error=error)
            return InviteAdminResponse(
                success=True,
                message=f"Convite criado mas envio de email falhou: {error}. Token: {invite_token}",
                user_id=str(invitation.id)
            )

        logger.info("admin.invite_admin_success", email=request.email, invited_by=invited_by_name)

        return InviteAdminResponse(
            success=True,
            message=f"Convite enviado para {request.email}. Senha temporária expira em 7 dias.",
            user_id=str(invitation.id)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.invite_admin_error", error=str(e), email=request.email)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao convidar usuário admin")


# ============================================================================
# Audit Log
# ============================================================================

@router.get("/audit")
async def get_audit_log(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """Get global audit log entries."""
    try:
        from app.models.base import GlobalAuditLog
        result = await db.execute(
            select(GlobalAuditLog).order_by(GlobalAuditLog.created_at.desc()).offset(skip).limit(limit)
        )
        events = result.scalars().all()
        return {
            "events": [
                {
                    "id": str(e.id),
                    "action": e.event_type,
                    "detail": e.details or "",
                    "level": "info",
                    "actor": e.actor_email or str(e.actor_id) if e.actor_id else "system",
                    "actorRole": "admin",
                    "target": e.resource_type or "",
                    "projectId": str(e.resource_id) if e.resource_id else None,
                    "projectName": None,
                    "hash": e.current_hash or "",
                    "prevHash": e.previous_hash or "",
                    "correlationId": str(e.correlation_id) if e.correlation_id else None,
                    "timestamp": e.created_at.isoformat() if e.created_at else "",
                }
                for e in events
            ]
        }
    except Exception as e:
        return {"events": []}


@router.get("/audit/verify-chain")
async def verify_audit_chain(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 500,
):
    """Verifica integridade da cadeia de auditoria (hash chain)."""
    from app.services.audit_service import AuditService
    audit = AuditService(db)
    result = await audit.verify_chain(limit=limit)
    return result


# ============================================================================
# Activity Log por Projeto (Admin sem papel)
# ============================================================================

@router.get("/projects/{project_id}/activity-log")
async def get_project_activity_log(
    project_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """
    Log de atividades de um projeto. Disponível para Admin mesmo sem papel no projeto.
    Retorna apenas metadados (sem dados funcionais como OCG, código, documentos).
    """
    try:
        from app.models.base import GlobalAuditLog
        result = await db.execute(
            select(GlobalAuditLog)
            .where(GlobalAuditLog.resource_id == project_id)
            .order_by(GlobalAuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        events = result.scalars().all()
        return {
            "project_id": str(project_id),
            "events": [
                {
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "actor_email": e.actor_email,
                    "resource_type": e.resource_type,
                    "created_at": e.created_at.isoformat() if e.created_at else "",
                }
                for e in events
            ],
        }
    except Exception as e:
        return {"project_id": str(project_id), "events": []}


# ============================================================================
# User Activation/Deactivation
# ============================================================================

@router.post("/users/{user_id}/block")
async def block_user(
    user_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Desativar usuário (apenas admin). Não pode desativar a si mesmo.

    MVP 11 Fase 11.3: bloqueia pré-ação caso o target seja o último
    Admin ativo da instância (preserva soberania).
    """
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Fase 11.3 — guard pré-check de último admin ativo
    from app.services.admin_management_service import guard_last_admin_on_action
    try:
        await guard_last_admin_on_action(db, user)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    user.is_active = False
    await db.commit()
    logger.info("admin.user_blocked", user_id=str(user_id), email=user.email)
    return {"success": True, "message": f"Usuário {user.email} desativado"}


@router.post("/users/{user_id}/unblock")
async def unblock_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reativar usuário (apenas admin)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.is_active = True
    await db.commit()
    logger.info("admin.user_unblocked", user_id=str(user_id), email=user.email)
    return {"success": True, "message": f"Usuário {user.email} reativado"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Excluir usuário (apenas admin).

    Política:
      - Não pode excluir a si mesmo.
      - BLOQUEIA (409) se o user é GP de project_request APPROVED/ACTIVE
        OU membro ativo de projeto não-arquivado. Admin precisa primeiro
        substituir/transferir o GP antes de excluir.
      - Limpa proativamente o que dá: project_requests pendentes/rejeitadas,
        memberships, invites, tokens. Campos de auditoria (approved_by,
        created_by, etc) viram NULL para preservar histórico.
    """
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Você não pode excluir sua própria conta")

    from sqlalchemy import text
    from app.models.onboarding import ProjectRequest, ProjectRequestStatus
    from app.models.base import Project, ProjectMember

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    email = user.email

    # MVP 11 Fase 11.3 — guard pré-check de último admin ativo
    from app.services.admin_management_service import guard_last_admin_on_action
    try:
        await guard_last_admin_on_action(db, user)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # === BLOQUEIO 1: GP de project_request APPROVED ou ACTIVE ===
    blocking_reqs = (await db.execute(
        select(ProjectRequest.project_name, ProjectRequest.project_slug, ProjectRequest.status).where(
            ProjectRequest.gp_id == user_id,
            ProjectRequest.status.in_([
                ProjectRequestStatus.APPROVED,
                ProjectRequestStatus.ACTIVE,
            ]),
        )
    )).all()
    if blocking_reqs:
        names = [f"{r[0]} ({r[1]})" for r in blocking_reqs]
        raise HTTPException(
            status_code=409,
            detail=(
                f"Usuário '{email}' não pode ser excluído — é GP do(s) projeto(s) ativo(s): "
                f"{', '.join(names)}. Substitua o GP em Gestão de Projetos primeiro."
            ),
        )

    # === BLOQUEIO 2: membership ativo em projeto não-arquivado ===
    blocking_members = (await db.execute(
        select(Project.name, Project.short_slug, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user_id,
            ProjectMember.is_active == True,  # noqa: E712
            Project.status != "archived",
        )
    )).all()
    if blocking_members:
        names = [f"{m[0]} ({m[1] or '?'} como {m[2]})" for m in blocking_members]
        raise HTTPException(
            status_code=409,
            detail=(
                f"Usuário '{email}' não pode ser excluído — é membro ativo de: "
                f"{', '.join(names)}. Remova-o do(s) projeto(s) primeiro."
            ),
        )

    # === LIMPEZA: tudo que tem FK pra users e é seguro deletar/nullificar ===
    # Cada operação é defensiva (IF EXISTS / WHERE) — algumas tabelas podem
    # nem existir em ambientes mais antigos.
    cleanup_sql = [
        # DELETE — registros que só fazem sentido com o user vivo
        ("DELETE FROM project_requests WHERE gp_id = :uid", "project_requests pendentes/rejeitadas"),
        ("DELETE FROM project_members WHERE user_id = :uid", "memberships"),
        ("DELETE FROM invitation_tokens WHERE invited_by_id = :uid", "invitation_tokens"),
        ("DELETE FROM team_invites WHERE user_id = :uid", "team_invites"),
        ("DELETE FROM project_invites WHERE invited_by_user_id = :uid OR accepted_by_user_id = :uid", "project_invites"),
        ("DELETE FROM onboarding_progress WHERE gp_id = :uid", "onboarding_progress"),
        ("DELETE FROM user_notifications WHERE user_id = :uid", "user_notifications"),
        ("DELETE FROM user_project_context WHERE user_id = :uid", "user_project_context"),
        ("DELETE FROM reset_tokens WHERE user_id = :uid", "reset_tokens"),
        ("DELETE FROM access_attempts WHERE user_id = :uid", "access_attempts"),
        # SET NULL — preserva histórico/auditoria
        ("UPDATE project_requests SET approved_by = NULL WHERE approved_by = :uid", "project_requests.approved_by"),
        ("UPDATE gatekeeper_items SET resolved_by = NULL WHERE resolved_by = :uid", "gatekeeper_items"),
        ("UPDATE ingested_documents SET uploaded_by = NULL WHERE uploaded_by = :uid", "ingested_documents"),
        ("UPDATE module_candidates SET approved_by = NULL WHERE approved_by = :uid", "module_candidates.approved_by"),
        ("UPDATE module_candidates SET rejected_by = NULL WHERE rejected_by = :uid", "module_candidates.rejected_by"),
        ("UPDATE project_external_repos SET added_by = NULL WHERE added_by = :uid", "project_external_repos.added_by"),
        ("UPDATE project_external_repos SET approved_by_gp = NULL WHERE approved_by_gp = :uid", "project_external_repos.approved_by_gp"),
        ("UPDATE project_member_roles SET assigned_by = NULL WHERE assigned_by = :uid", "project_member_roles"),
        ("UPDATE project_secrets SET created_by = NULL WHERE created_by = :uid", "project_secrets"),
        ("UPDATE project_settings SET updated_by = NULL WHERE updated_by = :uid", "project_settings"),
        ("UPDATE pipeline_audit_entries SET user_id = NULL WHERE user_id = :uid", "pipeline_audit_entries"),
        ("UPDATE test_artifacts SET created_by = NULL WHERE created_by = :uid", "test_artifacts.created_by"),
        ("UPDATE test_artifacts SET last_edited_by = NULL WHERE last_edited_by = :uid", "test_artifacts.last_edited_by"),
        ("UPDATE test_execution_logs SET executed_by = NULL WHERE executed_by = :uid", "test_execution_logs.executed_by"),
        ("UPDATE test_execution_logs SET test_created_by = NULL WHERE test_created_by = :uid", "test_execution_logs.test_created_by"),
        ("UPDATE test_execution_logs SET test_edited_by = NULL WHERE test_edited_by = :uid", "test_execution_logs.test_edited_by"),
        # FKs com ON DELETE CASCADE/SET NULL nativo (organization_members, support_tickets,
        # ai_usage_log, audit_log_global, ocg, ocg_delta_log, system_alerts,
        # system_settings, ticket_responses, project_releases, project_deliverables,
        # project_members.invited_by) já tratam sozinhas — não precisa SQL aqui.
    ]

    try:
        for sql, _ in cleanup_sql:
            await db.execute(text(sql), {"uid": user_id})
        await db.delete(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("admin.user_delete_failed", user_id=str(user_id), error=str(e))
        # Mensagem mais útil: pegar o nome da constraint que falhou
        msg = str(e)
        if "violates foreign key constraint" in msg:
            import re
            match = re.search(r'constraint "([^"]+)"', msg)
            cname = match.group(1) if match else "desconhecida"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Não foi possível excluir '{email}' — restou referência em "
                    f"'{cname}'. Avise o time de backend para tratar essa FK."
                ),
            )
        raise HTTPException(status_code=409, detail=f"Não foi possível excluir: {msg[:200]}")

    logger.info("admin.user_deleted", user_id=str(user_id), email=email)
    return {"success": True, "message": f"Usuário {email} excluído"}


# ─── Gestão de camada administrativa (2026-04-19) ────────────────────────

class AdminFlagRequest(BaseModel):
    is_admin: bool


class AdminInviteRequest(BaseModel):
    email: EmailStr
    full_name: str
    activation_link: str | None = None


@router.patch("/users/{user_id}/admin-flag")
async def set_admin_flag_endpoint(
    user_id: UUID,
    payload: AdminFlagRequest,
    actor_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Promove ou rebaixa o papel de Admin. Último admin ativo não pode
    se auto-rebaixar (anti-órfão). is_support fica independente."""
    from app.services import admin_management_service as svc
    try:
        updated = await svc.set_admin_flag(
            db, target_user_id=user_id, new_value=payload.is_admin, actor_id=actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {
        "id": str(updated.id),
        "email": updated.email,
        "full_name": updated.full_name,
        "is_admin": bool(updated.is_admin),
        "is_support": bool(updated.is_support),
    }


@router.post("/invitations/admin", status_code=201)
async def invite_admin_endpoint(
    payload: AdminInviteRequest,
    actor_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Convida novo administrador (ou promove user existente pelo email).
    Tenta enviar email com senha temp; se falha, retorna a senha pro
    admin comunicar manualmente."""
    from app.services import admin_management_service as svc
    try:
        result = await svc.invite_admin(
            db,
            email=payload.email,
            full_name=payload.full_name,
            actor_id=actor_id,
            activation_link=payload.activation_link or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return result


# ─── Lifecycle de projeto (2026-04-19) ───────────────────────────────────

class ProjectStatusRequest(BaseModel):
    status: str
    reason: str | None = None


@router.patch("/projects/{project_id}/status")
async def set_project_lifecycle_status(
    project_id: UUID,
    payload: ProjectStatusRequest,
    actor_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Altera lifecycle do projeto: active | paused | inactive.

    Nunca deleta dados — projetos inativos/pausados preservam OCG,
    questionário, backlog, documentos, backups, tickets. Scheduler de
    backup (DT-063) só roda em 'active'; paused/inactive para o
    auto-backup mas mantém os existentes.
    """
    from app.services import admin_management_service as svc
    try:
        project = await svc.set_project_status(
            db,
            project_id=project_id,
            new_status=payload.status,
            actor_id=actor_id,
            reason=payload.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {
        "id": str(project.id),
        "slug": project.slug,
        "name": project.name,
        "status": project.status,
    }


@router.post("/projects/requests/{request_id}/cleanup-orphan")
async def cleanup_orphan_project_request(
    request_id: UUID,
    _actor_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove `project_requests` APPROVED cuja linha em `projects` não
    existe mais (órfão — efeito colateral de deleção hard feita no
    passado). Valida antes de deletar: se o projeto existe, recusa.

    Limpa FKs dependentes de `project_requests`:
    - onboarding_progress (rascunho do wizard)
    - team_invites (convites pendentes/rejeitados)
    Ambas sem ON DELETE CASCADE no schema original, precisam DELETE
    explícito antes.
    """
    from sqlalchemy import text
    from app.models.base import Project as _Project
    from app.models.onboarding import ProjectRequest

    req = (await db.execute(
        select(ProjectRequest).where(ProjectRequest.id == request_id)
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    # Confirma que é órfão: projeto real não existe
    linked = (await db.execute(
        select(_Project).where(_Project.slug == req.project_slug)
    )).scalar_one_or_none()
    if linked is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Projeto ainda existe em 'projects' — não é órfão. "
                "Use PATCH /admin/projects/{id}/status com 'inactive' para "
                "desativar preservando os dados."
            ),
        )

    project_name = req.project_name
    try:
        # Limpa FKs sem CASCADE. Inclusive `onboarding_progress` e
        # `team_invites`, que amarram ao project_requests.id.
        await db.execute(
            text("DELETE FROM onboarding_progress WHERE project_id = :rid"),
            {"rid": request_id},
        )
        await db.execute(
            text("DELETE FROM team_invites WHERE project_id = :rid"),
            {"rid": request_id},
        )
        await db.delete(req)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("admin.orphan_cleanup_failed", request_id=str(request_id), error=str(e))
        # Se outra FK não mapeada aparecer, responde útil em vez de
        # "Network Error" no frontend.
        msg = str(e)
        if "foreign key constraint" in msg.lower():
            import re
            m = re.search(r'constraint "([^"]+)"', msg)
            cname = m.group(1) if m else "desconhecida"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Órfão tem referência em '{cname}'. O backend precisa "
                    f"limpar essa FK antes — reporte esse nome ao time de backend."
                ),
            )
        raise HTTPException(status_code=500, detail=f"Falha ao limpar órfão: {msg[:200]}")

    logger.info("admin.orphan_request_cleaned", request_id=str(request_id), name=project_name)
    return {"success": True, "cleaned": project_name}


# ─── MVP 13 Fase 13.4: Celery DLQ inspection (admin only) ─────────────


@router.get("/celery/dlq")
async def get_celery_dlq(
    limit: int = 50,
    current_user_id: UUID = Depends(require_admin),
):
    """Retorna últimas falhas permanentes de tasks Celery.

    Lista dicts com task_id, task_name, exception_type, exception_msg
    e args (truncados em 200 chars). Populada pelo signal handler
    `_on_task_failure` em `celery_app.py`. Fonte canônica pro admin
    inspecionar tasks que estouraram retry policy.
    """
    from app.celery_app import get_dlq_entries
    entries = get_dlq_entries(limit=limit)
    return {"count": len(entries), "entries": entries}


@router.get("/celery/workers")
async def get_celery_workers(current_user_id: UUID = Depends(require_admin)):
    """Inspeciona workers Celery ativos via `inspect ping`.

    Retorna lista de nodes online + count. Complementa /health com
    detalhes que só Admin precisa.
    """
    from app.celery_app import check_workers_alive, check_broker_connection
    broker = check_broker_connection(timeout=1.0)
    workers = (
        check_workers_alive(timeout=1.5) if broker["reachable"]
        else {"workers": 0, "nodes": [], "error": "broker_unreachable"}
    )
    return {"broker": broker, "workers": workers}
