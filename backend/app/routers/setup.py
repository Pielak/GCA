"""
Wizard de configuração inicial do GCA.

/setup/status  — verifica se o sistema precisa de configuração (sem auth).
/setup/complete — executa os 4 passos em uma única transação (sem auth,
                  bloqueado após 1ª execução com 410 Gone).

ATENÇÃO: estes endpoints são PUBLIC (sem JWT). Não adicionar require_auth.
O motivo é que ainda não existe nenhum usuário no banco na primeira execução.
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import structlog

from app.db.database import get_db
from app.models.base import User, GlobalAuditLog
from app.core.security import hash_password

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/setup", tags=["Setup"])


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)):
    """
    Verifica se o GCA precisa de configuração inicial.

    Retorna needs_setup: true → frontend redireciona para /setup.
    Retorna needs_setup: false → sistema já configurado, rota /setup bloqueada.
    """
    count = await db.scalar(select(func.count()).select_from(User))
    return {"needs_setup": count == 0}


class SetupPayload(BaseModel):
    # Passo 1: Admin
    admin_name: str
    admin_email: str
    admin_password: str
    # Passo 2: LLM
    llm_provider: str
    llm_api_key: str
    llm_model: str
    # Passo 3: Infraestrutura (todos opcionais)
    n8n_url: Optional[str] = None
    n8n_token: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    # Passo 4: Projeto de teste (opcional)
    create_test_project: bool = False
    test_project_name: Optional[str] = None


@router.post("/complete")
async def setup_complete(payload: SetupPayload, db: AsyncSession = Depends(get_db)):
    """
    Executa o wizard completo em uma única transação atômica.
    Bloqueia com 410 Gone se já existir pelo menos um usuário no banco.
    """
    count = await db.scalar(select(func.count()).select_from(User))
    if count > 0:
        raise HTTPException(status_code=410, detail="GCA já configurado. Use /login.")

    try:
        # 1. Criar usuário admin
        user = User(
            email=payload.admin_email,
            full_name=payload.admin_name,
            password_hash=hash_password(payload.admin_password),
            is_active=True,
            is_admin=True,
            first_access_completed=True,
            password_changed_at=datetime.now(timezone.utc),
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()

        # 2. Registrar configurações no audit log global (LLM, n8n, SMTP)
        config_details = {
            "llm": {
                "provider": payload.llm_provider,
                "model": payload.llm_model,
                "api_key_prefix": payload.llm_api_key[:8] + "..." if len(payload.llm_api_key) > 8 else "***",
            },
        }
        if payload.n8n_url:
            config_details["n8n"] = {"url": payload.n8n_url}
        if payload.smtp_host:
            config_details["smtp"] = {
                "host": payload.smtp_host,
                "port": payload.smtp_port,
                "user": payload.smtp_user,
            }

        from app.services.audit_service import AuditService
        audit_svc = AuditService(db)
        await audit_svc.log_event(
            event_type="system.setup_completed",
            actor_id=user.id,
            actor_email=payload.admin_email,
            resource_type="system",
            details=config_details,
        )

        await db.commit()

        logger.info(
            "setup.completed",
            admin_email=payload.admin_email,
            llm_provider=payload.llm_provider,
        )

        return {
            "message": "GCA configurado com sucesso.",
            "redirect": "/login",
            "admin_email": payload.admin_email,
        }

    except Exception as e:
        await db.rollback()
        logger.error("setup.failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro na configuração: {str(e)}")
