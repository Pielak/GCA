"""Endpoints PÚBLICOS (sem autenticação) para self-service de projetos.

Permite que qualquer pessoa solicite um novo projeto a partir da página
de login. O Admin recebe notificação in-app e decide aprovar/rejeitar
via Admin → Gestão de Projetos (mesma tela que já existe).

Por que público:
    A pessoa que solicita pode não ter ainda conta no GCA. Se o Admin
    aprovar, a conta é criada/ativada e a senha temporária é enviada
    por email.

Anti-abuse mínimo:
    - Pydantic valida tamanhos.
    - Slug único garantido por DB.
    - Mesmo email + mesmo project_name em <60s = duplicate skipped (idempotente).
"""
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import get_db
from app.models.base import User
from app.models.onboarding import (
    DeliverableType,
    ProjectRequest,
    ProjectRequestStatus,
)
from app.core.security import hash_password

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/public", tags=["public"])


def _slugify(text: str, max_len: int = 80) -> str:
    """Slug ASCII curto e único-friendly (caller adiciona sufixo se colidir)."""
    s = unicodedata.normalize("NFD", text or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).lower().strip()
    s = re.sub(r"\s+", "-", s)
    return (s or "projeto")[:max_len].rstrip("-")


class ProjectRequestPublic(BaseModel):
    """Form da página /solicitar-projeto."""
    requester_email: EmailStr
    requester_name: str = Field(..., min_length=2, max_length=255)
    project_name: str = Field(..., min_length=3, max_length=255)
    description: str = Field("", max_length=2000)
    deliverable_type: str = Field(
        "new_system",
        description="new_system | mobile_app | module | enhancement | integration | modernization | etl | maintenance",
    )


@router.post("/project-requests", status_code=201)
async def create_public_project_request(
    req: ProjectRequestPublic,
    db: AsyncSession = Depends(get_db),
):
    """Solicitação self-service de novo projeto, vinda da página de login.

    Fluxo:
        1. Encontra ou cria User pelo email (status inativo até admin aprovar).
        2. Gera slug único (sufixo numérico se colidir).
        3. Cria ProjectRequest status='pending'.
        4. Notifica todos os admins via in-app (best-effort).

    Idempotência simples: mesmo email + mesmo project_name em <60s →
    devolve a request já existente sem duplicar.
    """
    # 1. User: encontra ou cria
    email_norm = req.requester_email.lower().strip()
    result = await db.execute(select(User).where(User.email == email_norm))
    user = result.scalar_one_or_none()

    if not user:
        # Cria User inativo (admin ativa ao aprovar; senha temporária na ativação)
        user = User(
            id=uuid4(),
            email=email_norm,
            full_name=req.requester_name.strip()[:255],
            password_hash=hash_password(uuid4().hex),  # senha aleatória — usuário troca via reset
            is_active=False,  # pendente de aprovação
            is_admin=False,
            first_access_completed=False,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        await db.flush()
        logger.info(
            "public_project_request.user_created",
            user_id=str(user.id),
            email=email_norm,
        )

    # 2. Idempotência: mesma combinação em <60s
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    dup_check = await db.execute(
        select(ProjectRequest).where(
            ProjectRequest.gp_id == user.id,
            ProjectRequest.project_name == req.project_name,
            ProjectRequest.requested_at >= cutoff,
        ).limit(1)
    )
    existing = dup_check.scalar_one_or_none()
    if existing:
        return {
            "id": str(existing.id),
            "status": existing.status.value if hasattr(existing.status, "value") else str(existing.status),
            "message": "Solicitação já existente (mesmo nome e email nos últimos 60s).",
            "duplicate": True,
        }

    # 3. Slug único
    base_slug = _slugify(req.project_name)
    slug = base_slug
    suffix = 1
    while True:
        slug_check = await db.execute(
            select(ProjectRequest).where(ProjectRequest.project_slug == slug).limit(1)
        )
        if not slug_check.scalar_one_or_none():
            break
        suffix += 1
        slug = f"{base_slug}-{suffix}"
        if suffix > 100:  # circuit breaker — improvável mas seguro
            slug = f"{base_slug}-{uuid4().hex[:6]}"
            break

    # 4. Validar deliverable_type
    try:
        DeliverableType(req.deliverable_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"deliverable_type inválido: {req.deliverable_type}",
        )

    # 5. Criar ProjectRequest
    pr = ProjectRequest(
        id=uuid4(),
        gp_id=user.id,
        project_name=req.project_name.strip()[:255],
        project_slug=slug,
        description=req.description.strip()[:2000],
        deliverable_type=req.deliverable_type,
        status=ProjectRequestStatus.PENDING,
        requested_at=datetime.utcnow(),
    )
    db.add(pr)
    await db.commit()

    logger.info(
        "public_project_request.created",
        request_id=str(pr.id),
        slug=slug,
        gp_email=email_norm,
        project_name=req.project_name,
    )

    # 6. Notificar admins (best-effort)
    try:
        from app.services.notification_inapp_service import InAppNotificationService
        admins_res = await db.execute(
            select(User).where(User.is_admin == True, User.is_active == True)
        )
        admins = list(admins_res.scalars().all())
        notif = InAppNotificationService(db)
        for admin in admins:
            await notif.notify(
                user_id=admin.id,
                event_type="project_request_received",
                title=f"Nova solicitação: {req.project_name}",
                message=f"Solicitada por {req.requester_name} ({email_norm}). Aprove ou rejeite em Gestão de Projetos.",
                resource_type="project_request",
                resource_id=pr.id,
                link="/admin/projects",
                severity="info",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "public_project_request.notify_admins_failed",
            error=str(exc),
            request_id=str(pr.id),
        )

    return {
        "id": str(pr.id),
        "slug": slug,
        "status": "pending",
        "message": "Solicitação enviada com sucesso. Você receberá um email quando o admin aprovar.",
    }
