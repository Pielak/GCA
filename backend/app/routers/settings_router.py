"""
Settings Router — Configurações SMTP, LLM e n8n por projeto
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import structlog

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectSettings
from app.services.vault_service import VaultService
from app.dependencies.require_action import require_action

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["settings"])
vault = VaultService()


# ============================================================================
# Request/Response Models
# ============================================================================

class SmtpSettingsRequest(BaseModel):
    host: str
    port: int = 587
    use_tls: bool = True
    username: str
    password: str
    from_email: str
    from_name: str = "GCA"


class LlmSettingsRequest(BaseModel):
    provider: str  # anthropic, openai, grok, deepseek
    api_key: str
    model_preference: str | None = None


class N8nSettingsRequest(BaseModel):
    webhook_url: str
    api_token: str | None = None
    workflow_id: str | None = None


class SmtpTestRequest(BaseModel):
    to_email: str


# ============================================================================
# Helper
# ============================================================================

async def _get_or_create_settings(db: AsyncSession, project_id: UUID, setting_type: str) -> ProjectSettings:
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == setting_type,
        )
    )
    settings_obj = result.scalar_one_or_none()
    if not settings_obj:
        settings_obj = ProjectSettings(
            project_id=project_id,
            setting_type=setting_type,
            settings_json="{}",
        )
        db.add(settings_obj)
    return settings_obj


# ============================================================================
# GET all settings
# ============================================================================

@router.get("/projects/{project_id}/settings")
async def get_project_settings(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna todas configurações do projeto. Secrets mascarados."""
    result = await db.execute(
        select(ProjectSettings).where(ProjectSettings.project_id == project_id)
    )
    all_settings = result.scalars().all()

    settings_map = {}
    for s in all_settings:
        try:
            settings_map[s.setting_type] = json.loads(s.settings_json)
        except json.JSONDecodeError:
            settings_map[s.setting_type] = {}

    # Verificar quais secrets estão configurados
    secrets = await vault.list_secrets(db, project_id)
    secret_types = {f"{s['secret_type']}:{s['secret_key']}" for s in secrets}

    # Marcar secrets como configurados (sem revelar valor)
    smtp = settings_map.get("smtp", {})
    smtp["password_configured"] = "smtp_password:main" in secret_types

    llm = settings_map.get("llm", {})
    provider = llm.get("provider", "")
    llm["api_key_configured"] = f"llm_api_key:{provider}" in secret_types if provider else False

    n8n = settings_map.get("n8n", {})
    n8n["api_token_configured"] = "n8n_token:main" in secret_types

    return {
        "smtp": smtp,
        "llm": llm,
        "n8n": n8n,
    }


# ============================================================================
# SMTP
# ============================================================================

@router.post("/projects/{project_id}/settings/smtp")
async def save_smtp_settings(
    project_id: UUID,
    req: SmtpSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Salva configurações SMTP do projeto."""
    user_id = permissions["user_id"]
    settings_obj = await _get_or_create_settings(db, project_id, "smtp")
    settings_obj.settings_json = json.dumps({
        "host": req.host,
        "port": req.port,
        "use_tls": req.use_tls,
        "username": req.username,
        "from_email": req.from_email,
        "from_name": req.from_name,
    })
    settings_obj.updated_by = user_id
    await db.commit()

    # Salvar senha no vault
    await vault.store_secret(db, project_id, "smtp_password", "main", req.password, user_id)

    return {"success": True}


@router.post("/projects/{project_id}/settings/smtp/test")
async def test_smtp_settings(
    project_id: UUID,
    req: SmtpTestRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Testa SMTP enviando email de teste."""
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "smtp",
        )
    )
    settings_obj = result.scalar_one_or_none()
    if not settings_obj:
        raise HTTPException(status_code=400, detail="SMTP não configurado")

    smtp_config = json.loads(settings_obj.settings_json)
    password = await vault.get_secret(db, project_id, "smtp_password", "main")

    if not password:
        raise HTTPException(status_code=400, detail="Senha SMTP não encontrada no vault")

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText("Este é um email de teste do GCA.", "plain", "utf-8")
        msg["Subject"] = "GCA — Teste SMTP"
        msg["From"] = f"{smtp_config.get('from_name', 'GCA')} <{smtp_config['from_email']}>"
        msg["To"] = req.to_email

        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            if smtp_config.get("use_tls"):
                server.starttls()
            server.login(smtp_config["username"], password)
            server.send_message(msg)

        return {"success": True, "message": f"Email de teste enviado para {req.to_email}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# LLM
# ============================================================================

@router.post("/projects/{project_id}/settings/llm")
async def save_llm_settings(
    project_id: UUID,
    req: LlmSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Salva configurações LLM do projeto."""
    user_id = permissions["user_id"]
    valid_providers = ("anthropic", "openai", "grok", "deepseek")
    if req.provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider inválido. Aceitos: {', '.join(valid_providers)}")

    settings_obj = await _get_or_create_settings(db, project_id, "llm")
    settings_obj.settings_json = json.dumps({
        "provider": req.provider,
        "model_preference": req.model_preference,
    })
    settings_obj.updated_by = user_id
    await db.commit()

    # Salvar API key no vault
    await vault.store_secret(db, project_id, "llm_api_key", req.provider, req.api_key, user_id)

    return {"success": True}


@router.post("/projects/{project_id}/settings/llm/validate")
async def validate_llm_settings(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Valida a API key do LLM provider."""
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "llm",
        )
    )
    settings_obj = result.scalar_one_or_none()
    if not settings_obj:
        raise HTTPException(status_code=400, detail="LLM não configurado")

    llm_config = json.loads(settings_obj.settings_json)
    provider = llm_config.get("provider")
    api_key = await vault.get_secret(db, project_id, "llm_api_key", provider)

    if not api_key:
        raise HTTPException(status_code=400, detail="API key não encontrada no vault")

    # Teste simples por provider
    try:
        import httpx
        if provider == "anthropic":
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                )
            if resp.status_code == 200:
                return {"valid": True, "model": llm_config.get("model_preference", "claude-opus-4-6")}
            return {"valid": False, "error": f"Anthropic retornou {resp.status_code}"}

        elif provider == "openai":
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code == 200:
                return {"valid": True, "model": llm_config.get("model_preference", "gpt-4")}
            return {"valid": False, "error": f"OpenAI retornou {resp.status_code}"}

        return {"valid": True, "model": llm_config.get("model_preference", provider)}

    except Exception as e:
        return {"valid": False, "error": str(e)}


# ============================================================================
# N8N
# ============================================================================

@router.post("/projects/{project_id}/settings/n8n")
async def save_n8n_settings(
    project_id: UUID,
    req: N8nSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Salva configurações n8n do projeto."""
    user_id = permissions["user_id"]
    settings_obj = await _get_or_create_settings(db, project_id, "n8n")
    settings_obj.settings_json = json.dumps({
        "webhook_url": req.webhook_url,
        "workflow_id": req.workflow_id,
    })
    settings_obj.updated_by = user_id
    await db.commit()

    if req.api_token:
        await vault.store_secret(db, project_id, "n8n_token", "main", req.api_token, user_id)

    return {"success": True}
