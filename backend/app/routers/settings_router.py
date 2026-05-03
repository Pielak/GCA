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
    """Payload pra adicionar/atualizar provedor LLM no projeto.

    DT-023: aceita Ollama (local) — `api_key` opcional e `base_url`
    obrigatório quando `provider == "ollama"`. Demais provedores
    continuam exigindo `api_key` e ignoram `base_url`.
    """
    provider: str  # anthropic, openai, grok, deepseek, gemini, ollama
    api_key: str | None = None  # opcional para ollama (sem auth ou com proxy externo)
    model_preference: str | None = None
    base_url: str | None = None  # obrigatório para ollama; ignorado pelos demais


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

def _normalize_llm_settings(raw: dict | None) -> dict:
    """Converte o settings_json de LLM para o formato multi-provider atual.

    Formato novo (suportado):
        {"providers": [{"provider": ..., "model": ..., "is_default": ...,
                        "last_validated_at": ..., "last_validation_ok": ...}],
         "default_provider": "deepseek"}

    Formato legado (ainda lido para retrocompat com projetos existentes):
        {"provider": "deepseek", "model_preference": "deepseek-chat"}
      → convertido para 1 item na lista, marcado como default.
    """
    if not raw:
        return {"providers": [], "default_provider": None}

    # Formato novo já?
    if isinstance(raw.get("providers"), list):
        providers = raw["providers"]
        default = raw.get("default_provider")
        # Garante um default coerente: se ninguém está marcado, o primeiro vence
        if providers and not any(p.get("is_default") for p in providers):
            providers[0]["is_default"] = True
            default = providers[0].get("provider")
        if not default:
            for p in providers:
                if p.get("is_default"):
                    default = p.get("provider")
                    break
        return {"providers": providers, "default_provider": default}

    # Formato legado → converter
    legacy_provider = raw.get("provider")
    legacy_model = raw.get("model_preference") or raw.get("model")
    if not legacy_provider:
        return {"providers": [], "default_provider": None}
    return {
        "providers": [{
            "provider": legacy_provider,
            "model": legacy_model,
            "is_default": True,
            "last_validated_at": None,
            "last_validation_ok": None,
        }],
        "default_provider": legacy_provider,
    }


async def _load_llm_providers(db: AsyncSession, project_id: UUID) -> dict:
    """Carrega e normaliza os provedores LLM do projeto."""
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "llm",
        )
    )
    obj = result.scalar_one_or_none()
    if not obj or not obj.settings_json:
        return {"providers": [], "default_provider": None}
    try:
        return _normalize_llm_settings(json.loads(obj.settings_json))
    except (json.JSONDecodeError, TypeError):
        return {"providers": [], "default_provider": None}


async def _save_llm_providers(db: AsyncSession, project_id: UUID, user_id: UUID, data: dict) -> None:
    """Persiste o bloco de provedores LLM no settings_json."""
    settings_obj = await _get_or_create_settings(db, project_id, "llm")
    # Normaliza antes de gravar — garante coerência do default.
    normalized = _normalize_llm_settings(data)
    settings_obj.settings_json = json.dumps(normalized)
    settings_obj.updated_by = user_id
    await db.commit()


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

    # LLM agora suporta múltiplos provedores (um marcado como padrão).
    # Cada item ganha `api_key_configured` baseado no vault. O shape
    # retornado é o novo (providers + default_provider) — o formato legado
    # `provider`/`model_preference` foi migrado por _normalize_llm_settings.
    llm_raw = settings_map.get("llm", {})
    llm_normalized = _normalize_llm_settings(llm_raw)
    enriched_providers = []
    for p in llm_normalized["providers"]:
        pname = p.get("provider")
        enriched_providers.append({
            **p,
            "api_key_configured": f"llm_api_key:{pname}" in secret_types if pname else False,
        })
    llm = {
        "providers": enriched_providers,
        "default_provider": llm_normalized["default_provider"],
        # Chaves de retrocompat para código frontend/CLI que ainda lê o formato antigo.
        # Refletem o provider default.
        "provider": llm_normalized["default_provider"] or "",
        "api_key_configured": any(
            p.get("is_default") and p.get("api_key_configured") for p in enriched_providers
        ),
    }

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
    """Adiciona ou atualiza um provedor LLM no projeto.

    Comportamento (novo formato multi-provider):
    - Se já existe o provider no projeto: atualiza model e (se veio chave nova) chave.
    - Se é novo: adiciona. Se é o primeiro da lista, vira default.
    - Default nunca é trocado automaticamente por este endpoint — use
      POST /settings/llm/providers/{provider}/default.
    """
    user_id = permissions["user_id"]
    valid_providers = ("anthropic", "openai", "grok", "deepseek", "gemini", "ollama")
    if req.provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Provider inválido. Aceitos: {', '.join(valid_providers)}")

    # DT-023: regras específicas por provider para chave/URL
    is_ollama = req.provider == "ollama"
    if is_ollama:
        if not req.base_url or not req.base_url.strip():
            raise HTTPException(
                status_code=400,
                detail="Ollama exige `base_url` (ex: http://host.docker.internal:11434 quando o GCA roda em Docker e Ollama no host).",
            )
        # Sanity: deve começar com http(s) — evita configuração silenciosamente errada
        bu = req.base_url.strip()
        if not (bu.startswith("http://") or bu.startswith("https://")):
            raise HTTPException(
                status_code=400,
                detail="`base_url` deve começar com http:// ou https://.",
            )
    else:
        if not req.api_key or not req.api_key.strip():
            raise HTTPException(
                status_code=400,
                detail=f"Provedor '{req.provider}' exige `api_key`.",
            )

    # Model deve ser um identificador técnico — o Chrome às vezes autofilla
    # esse campo com email/nome do usuário por heurística de contexto.
    # DT-023: Ollama usa modelos com `:` (ex: `llama3.1:8b`) — permitir esse char.
    if req.model_preference:
        m = req.model_preference.strip()
        if "@" in m or " " in m or len(m) > 120:
            raise HTTPException(
                status_code=400,
                detail="Modelo parece inválido (contém @, espaço ou é longo demais). Exemplos válidos: claude-opus-4-6, gpt-4o, deepseek-chat, gemini-2.0-flash, llama3.1:8b. Deixe vazio para usar o padrão do provedor.",
            )

    data = await _load_llm_providers(db, project_id)
    providers = data["providers"]
    existing = next((p for p in providers if p.get("provider") == req.provider), None)

    if existing:
        # Update do mesmo provider: modelo novo (se veio), invalida validação
        # anterior se a chave/URL mudou.
        existing["model"] = req.model_preference
        if is_ollama and req.base_url:
            existing["base_url"] = req.base_url.strip()
            existing["last_validated_at"] = None
            existing["last_validation_ok"] = None
        if req.api_key:
            existing["last_validated_at"] = None
            existing["last_validation_ok"] = None
    else:
        is_first = len(providers) == 0
        new_entry = {
            "provider": req.provider,
            "model": req.model_preference,
            "is_default": is_first,
            "last_validated_at": None,
            "last_validation_ok": None,
        }
        # DT-023: persiste base_url só pro Ollama (demais ignoram pra
        # não vazar config errada se alguém preencher por engano).
        if is_ollama and req.base_url:
            new_entry["base_url"] = req.base_url.strip()
        providers.append(new_entry)
        if is_first:
            data["default_provider"] = req.provider

    await _save_llm_providers(db, project_id, user_id, data)

    # Salvar API key no vault. Vazio/None = manter a atual (ou nenhuma pro Ollama).
    if req.api_key and req.api_key.strip():
        await vault.store_secret(db, project_id, "llm_api_key", req.provider, req.api_key.strip(), user_id)

    return {"success": True}


@router.delete("/projects/{project_id}/settings/llm/providers/{provider}")
async def remove_llm_provider(
    project_id: UUID,
    provider: str,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Remove um provedor do projeto (chave no vault + item da lista)."""
    user_id = permissions["user_id"]
    data = await _load_llm_providers(db, project_id)
    providers = data["providers"]
    item = next((p for p in providers if p.get("provider") == provider), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Provedor '{provider}' não está configurado neste projeto.")

    was_default = bool(item.get("is_default"))
    providers.remove(item)
    # Se o removido era o default, promove o primeiro restante.
    if was_default and providers:
        providers[0]["is_default"] = True
        data["default_provider"] = providers[0].get("provider")
    elif not providers:
        data["default_provider"] = None

    await _save_llm_providers(db, project_id, user_id, data)
    # Remove chave do vault. O vault não tem delete público claro, então
    # sobrescreve com string vazia — suficiente para o resolver retornar None.
    try:
        await vault.store_secret(db, project_id, "llm_api_key", provider, "", user_id)
    except Exception:
        pass
    return {"success": True, "default_provider": data["default_provider"]}


@router.post("/projects/{project_id}/settings/llm/providers/{provider}/default")
async def set_llm_default_provider(
    project_id: UUID,
    provider: str,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Marca um provedor já configurado como o padrão do projeto."""
    user_id = permissions["user_id"]
    data = await _load_llm_providers(db, project_id)
    providers = data["providers"]
    item = next((p for p in providers if p.get("provider") == provider), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Provedor '{provider}' não está configurado neste projeto.")
    for p in providers:
        p["is_default"] = (p.get("provider") == provider)
    data["default_provider"] = provider
    await _save_llm_providers(db, project_id, user_id, data)
    return {"success": True, "default_provider": provider}


@router.post("/projects/{project_id}/settings/llm/validate")
async def validate_llm_settings(
    project_id: UUID,
    provider: Optional[str] = None,
    permissions: dict = Depends(require_action("project:edit")),
    db: AsyncSession = Depends(get_db),
):
    """Valida a API key de um provedor LLM do projeto.

    Se `provider` é omitido (query param), valida o **default** do projeto.
    Se `provider` é passado, valida aquele específico (útil para a UI
    multi-provider testar cada um independentemente).

    Grava `last_validated_at` e `last_validation_ok` no settings_json
    para a UI mostrar "validada há X minutos" sem precisar re-executar.

    Classificação (contrato §6.2): **baixa** — ping em `/v1/models`.
    """
    import time
    from datetime import datetime, timezone as _tz

    user_id = permissions["user_id"]
    data = await _load_llm_providers(db, project_id)
    providers = data["providers"]
    if not providers:
        raise HTTPException(status_code=400, detail="Nenhum provedor LLM configurado neste projeto.")

    # Determina qual provider validar. Default = o marcado como padrão.
    target = provider or data["default_provider"]
    target_item = next((p for p in providers if p.get("provider") == target), None)
    if not target_item:
        raise HTTPException(status_code=404, detail=f"Provedor '{target}' não está configurado neste projeto.")

    api_key = await vault.get_secret(db, project_id, "llm_api_key", target)
    is_ollama = target == "ollama"
    base_url = (target_item.get("base_url") or "").rstrip("/")

    async def _persist_validation(ok: Optional[bool]) -> None:
        """Atualiza last_validated_at e last_validation_ok no provider testado."""
        for p in providers:
            if p.get("provider") == target:
                p["last_validated_at"] = datetime.now(_tz.utc).isoformat()
                p["last_validation_ok"] = ok
                break
        await _save_llm_providers(db, project_id, user_id, {"providers": providers, "default_provider": data["default_provider"]})

    # DT-023: Ollama não exige chave (URL local), demais sim.
    if not is_ollama and not api_key:
        await _persist_validation(False)
        raise HTTPException(status_code=400, detail=f"Chave do provedor '{target}' não encontrada no vault.")
    if is_ollama and not base_url:
        await _persist_validation(False)
        raise HTTPException(status_code=400, detail="Provedor 'ollama' está sem `base_url` configurado. Edite o provedor e informe a URL (ex: http://host.docker.internal:11434).")

    # Endpoints /v1/models (ou equivalente) aceitos por provider.
    # DT-023: Ollama usa GET /api/tags (lista modelos locais instalados).
    # Auth opcional via Bearer quando o GP configurar uma chave (ex: reverse
    # proxy na frente do daemon).
    ollama_headers: dict = {}
    if api_key:
        ollama_headers["Authorization"] = f"Bearer {api_key}"

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
            "default_model": "deepseek-v4-flash",
        },
        "grok": {
            "url": "https://api.x.ai/v1/models",
            "headers": {"Authorization": f"Bearer {api_key}"},
            "default_model": "grok-2",
        },
        "gemini": {
            "url": f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            "headers": {},
            "default_model": "gemini-2.0-flash",
        },
        "ollama": {
            "url": f"{base_url}/api/tags",
            "headers": ollama_headers,
            "default_model": "llama3.1:8b",
        },
    }

    if target not in provider_config:
        await _persist_validation(None)
        return {
            "valid": None,
            "provider": target,
            "provider_supported": False,
            "detail": (
                f"Teste automático ainda não implementado para o provedor "
                f"'{target}'. Suportados hoje: anthropic, openai, deepseek, grok, gemini."
            ),
        }

    cfg = provider_config[target]
    start = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(cfg["url"], headers=cfg["headers"])
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            await _persist_validation(True)
            logger.info("llm.validate_ok", project_id=str(project_id), provider=target, latency_ms=latency_ms)
            return {
                "valid": True,
                "provider": target,
                "model": target_item.get("model") or cfg["default_model"],
                "latency_ms": latency_ms,
            }

        if resp.status_code in (401, 403):
            error_code = "invalid_key"
            detail = (
                f"O provedor {target} rejeitou a chave (HTTP {resp.status_code}). "
                f"Verifique em Configurações → Provedor de IA e salve uma chave nova."
            )
        elif resp.status_code == 429:
            error_code = "rate_limited"
            detail = f"Provedor {target} retornou rate limit. Tente novamente em alguns segundos."
        else:
            error_code = "provider_error"
            detail = f"Provedor {target} retornou HTTP {resp.status_code}."

        await _persist_validation(False)
        logger.warning("llm.validate_failed", project_id=str(project_id), provider=target, status=resp.status_code)
        return {
            "valid": False,
            "provider": target,
            "latency_ms": latency_ms,
            "error": error_code,
            "detail": detail,
        }

    except httpx.TimeoutException:
        await _persist_validation(False)
        return {
            "valid": False,
            "provider": target,
            "error": "timeout",
            "detail": f"Timeout ao contatar {target}. Verifique sua rede.",
        }
    except Exception as e:
        await _persist_validation(False)
        logger.error("llm.validate_error", project_id=str(project_id), provider=target, error=str(e)[:300])
        return {
            "valid": False,
            "provider": target,
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
