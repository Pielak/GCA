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


class FigmaSettingsRequest(BaseModel):
    api_token: str
    team_id: str | None = None


class SemgrepSettingsRequest(BaseModel):
    api_token: str


class SonarQubeSettingsRequest(BaseModel):
    url: str
    api_token: str
    project_key: str | None = None


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
    """Valida a API key do LLM provider configurado no projeto.

    Classificação de criticidade (contrato §6.2): **baixa** — é só um ping no
    endpoint `/v1/models` do provedor para confirmar que a chave é aceita.
    Não consolida nada, não custa tokens. Camada Projeto (contrato §6.6,
    Contexto B) — usa chave do GP via vault, nunca a chave global do admin.

    Retorna estrutura explícita:
      - `{valid: True,  provider, model, latency_ms}` se o provedor aceitou a chave.
      - `{valid: False, provider, error, detail}` se rejeitou ou falhou rede.
      - `{valid: None,  provider, provider_supported: False, detail}` se o
        provedor é válido mas o GCA ainda não implementou teste real dele.
        Evita falso-positivo que ocorria no código anterior para deepseek/grok.
    """
    import time

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

    # Endpoints /v1/models aceitos por provider. Anthropic usa header próprio;
    # OpenAI e compatíveis (deepseek, grok) usam Bearer. Gemini tem formato
    # distinto e fica como teste manual (provider_supported=False) até
    # o adapter multi-provider do MVP 3.
    provider_config = {
        "anthropic": {
            "url": "https://api.anthropic.com/v1/models",
            "headers": {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            "default_model": "claude-haiku-4-5-20251001",
        },
        "openai": {
            "url": "https://api.openai.com/v1/models",
            "headers": {"Authorization": f"Bearer {api_key}"},
            "default_model": "gpt-4o-mini",
        },
        "deepseek": {
            "url": "https://api.deepseek.com/v1/models",
            "headers": {"Authorization": f"Bearer {api_key}"},
            "default_model": "deepseek-chat",
        },
        "grok": {
            "url": "https://api.x.ai/v1/models",
            "headers": {"Authorization": f"Bearer {api_key}"},
            "default_model": "grok-2",
        },
    }

    # Gemini, ollama e providers não previstos: não forçar teste que gere falso-positivo.
    if provider not in provider_config:
        return {
            "valid": None,
            "provider": provider,
            "provider_supported": False,
            "detail": (
                f"Teste automático ainda não implementado para o provedor "
                f"'{provider}'. A chave foi salva no vault, mas você precisa "
                f"validar manualmente chamando seu próprio endpoint. "
                f"Suportados hoje: anthropic, openai, deepseek, grok."
            ),
        }

    cfg = provider_config[provider]
    start = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(cfg["url"], headers=cfg["headers"])
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            logger.info(
                "llm.validate_ok",
                project_id=str(project_id),
                provider=provider,
                latency_ms=latency_ms,
            )
            return {
                "valid": True,
                "provider": provider,
                "model": llm_config.get("model_preference") or cfg["default_model"],
                "latency_ms": latency_ms,
            }

        # Humaniza o erro pelo status code
        if resp.status_code in (401, 403):
            error_code = "invalid_key"
            detail = (
                f"O provedor {provider} rejeitou a chave (HTTP {resp.status_code}). "
                f"Verifique em Configurações → LLM se a chave está correta e não expirou."
            )
        elif resp.status_code == 429:
            error_code = "rate_limited"
            detail = f"Provedor {provider} retornou rate limit. Tente novamente em alguns segundos."
        else:
            error_code = "provider_error"
            detail = f"Provedor {provider} retornou HTTP {resp.status_code}."

        logger.warning(
            "llm.validate_failed",
            project_id=str(project_id),
            provider=provider,
            status=resp.status_code,
        )
        return {
            "valid": False,
            "provider": provider,
            "latency_ms": latency_ms,
            "error": error_code,
            "detail": detail,
        }

    except httpx.TimeoutException:
        return {
            "valid": False,
            "provider": provider,
            "error": "timeout",
            "detail": f"Timeout ao contatar {provider}. Verifique sua rede.",
        }
    except Exception as e:
        logger.error(
            "llm.validate_error",
            project_id=str(project_id),
            provider=provider,
            error=str(e)[:300],
        )
        return {
            "valid": False,
            "provider": provider,
            "error": "network_error",
            "detail": str(e)[:300],
        }


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


# ============================================================================
# Figma Integration
# ============================================================================

@router.post("/projects/{project_id}/settings/figma")
async def save_figma_settings(
    project_id: UUID,
    req: FigmaSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Salvar token Figma para integracao de design."""
    user_id = permissions["user_id"]

    settings_obj = await _get_or_create_settings(db, project_id, "figma")
    settings_obj.settings_json = json.dumps({
        "team_id": req.team_id,
        "configured": True,
    })
    settings_obj.updated_by = user_id
    await db.commit()

    await vault.store_secret(db, project_id, "figma_token", "main", req.api_token, user_id)

    return {"success": True}


@router.post("/projects/{project_id}/settings/figma/validate")
async def validate_figma_settings(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Validar token Figma testando contra a API."""
    import httpx

    token = await vault.get_secret(db, project_id, "figma_token", "main")
    if not token:
        return {"valid": False, "error": "Token Figma nao configurado"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.figma.com/v1/me",
                headers={"X-Figma-Token": token},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"valid": True, "user": data.get("handle", ""), "email": data.get("email", "")}
            else:
                return {"valid": False, "error": f"Figma API retornou {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


# ============================================================================
# Notifications (Slack / Discord)
# ============================================================================

class NotificationSettingsRequest(BaseModel):
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None


@router.post("/projects/{project_id}/settings/notifications")
async def save_notification_settings(
    project_id: UUID,
    req: NotificationSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Configurar webhooks de notificacao (Slack/Discord)."""
    user_id = permissions["user_id"]
    settings_obj = await _get_or_create_settings(db, project_id, "notifications")
    settings_obj.settings_json = json.dumps({
        "slack_webhook_url": req.slack_webhook_url,
        "discord_webhook_url": req.discord_webhook_url,
    })
    settings_obj.updated_by = user_id
    await db.commit()
    return {"success": True}


@router.post("/projects/{project_id}/settings/notifications/test")
async def test_notification(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Envia notificacao de teste para canais configurados."""
    from app.services.notification_service import NotificationService
    service = NotificationService()
    result = await service.notify_pipeline_event(
        db, project_id,
        event="pipeline_complete",
        item_title="Teste de Notificacao",
        details="Se voce recebeu esta mensagem, as notificacoes estao funcionando!",
    )
    return result


# ============================================================================
# SAST Tools (Semgrep / SonarQube)
# ============================================================================

@router.post("/projects/{project_id}/settings/semgrep")
async def save_semgrep_settings(
    project_id: UUID,
    req: SemgrepSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Salvar token Semgrep para SAST."""
    user_id = permissions["user_id"]
    settings_obj = await _get_or_create_settings(db, project_id, "semgrep")
    settings_obj.settings_json = json.dumps({"configured": True})
    settings_obj.updated_by = user_id
    await db.commit()
    await vault.store_secret(db, project_id, "semgrep_token", "main", req.api_token, user_id)
    return {"success": True}


@router.post("/projects/{project_id}/settings/sonarqube")
async def save_sonarqube_settings(
    project_id: UUID,
    req: SonarQubeSettingsRequest,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Salvar configuracao SonarQube."""
    user_id = permissions["user_id"]
    settings_obj = await _get_or_create_settings(db, project_id, "sonarqube")
    settings_obj.settings_json = json.dumps({"url": req.url, "project_key": req.project_key})
    settings_obj.updated_by = user_id
    await db.commit()
    await vault.store_secret(db, project_id, "sonarqube_token", "main", req.api_token, user_id)
    return {"success": True}
