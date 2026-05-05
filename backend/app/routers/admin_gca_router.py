"""
Admin GCA Router — Parametrização de pilares, thresholds, agentes e provedores de IA.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, validator
from typing import Dict, Optional, List
from datetime import datetime, timezone
import structlog

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token, require_admin
from app.core.config import settings
from uuid import UUID

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["admin-gca"])


# Valores padrão de configuração
DEFAULT_PILLAR_WEIGHTS = {
    "P1": 10, "P2": 15, "P3": 20, "P4": 20, "P5": 15, "P6": 10, "P7": 10,
}
DEFAULT_THRESHOLDS = {
    # Per-pilar: score abaixo deste valor marca o pilar como BLOQUEANTE.
    # Decisão GP 2 (2026-05-04): CodeGen exige TODOS os pilares >= 95.
    # Defaults alinham com SCORE_MATURIDADE em ocg_gate.py.
    # Admin pode relaxar em settings se quiser ver BLOCKED em outro limiar.
    "p1_blocking_threshold": 95,
    "p2_blocking_threshold": 95,
    "p3_blocking_threshold": 95,
    "p4_blocking_threshold": 95,
    "p5_blocking_threshold": 95,
    "p6_blocking_threshold": 95,
    "p7_blocking_threshold": 95,
    # Composite (overall): bandas de status do projeto inteiro.
    # ready=95 alinha com SCORE_MATURIDADE (CodeGen liberado quando overall >=95
    # E todos os pilares >=95 — Decisão GP 2).
    "ready_threshold": 95,
    "needs_review_threshold": 75,
    "at_risk_threshold": 50,
}
DEFAULT_AGENT_CONFIG = {
    "model": "claude-opus-4-0-20250514",
    "max_tokens": 4096,
    "temperature": 0.3,
}

# Estado em memória (em produção, usar tabela pillar_configuration)
_current_settings = {
    "pillar_weights": dict(DEFAULT_PILLAR_WEIGHTS),
    "score_thresholds": dict(DEFAULT_THRESHOLDS),
    "agent_config": dict(DEFAULT_AGENT_CONFIG),
}


class PillarWeightsRequest(BaseModel):
    P1: int
    P2: int
    P3: int
    P4: int
    P5: int
    P6: int
    P7: int

    @validator("P7")
    def validate_sum(cls, v, values):
        total = sum(values.get(f"P{i}", 0) for i in range(1, 7)) + v
        if total != 100:
            raise ValueError(f"Soma dos pesos deve ser exatamente 100, recebido: {total}")
        return v


class ThresholdsRequest(BaseModel):
    """Thresholds completos por pilar + bandas de composite.

    Cada p{N}_blocking_threshold (0-100): se o score do pilar P{N} ficar
    ABAIXO desse valor, o pilar é marcado como BLOQUEANTE no Gatekeeper.
    Use 0 para "não bloqueia individualmente" (pilar entra só na média).
    """
    p1_blocking_threshold: int = 95
    p2_blocking_threshold: int = 95
    p3_blocking_threshold: int = 95
    p4_blocking_threshold: int = 95
    p5_blocking_threshold: int = 95
    p6_blocking_threshold: int = 95
    p7_blocking_threshold: int = 95
    ready_threshold: int = 95
    needs_review_threshold: int = 75
    at_risk_threshold: int = 50

    @validator(
        "p1_blocking_threshold", "p2_blocking_threshold", "p3_blocking_threshold",
        "p4_blocking_threshold", "p5_blocking_threshold", "p6_blocking_threshold",
        "p7_blocking_threshold", "ready_threshold", "needs_review_threshold",
        "at_risk_threshold",
    )
    def in_range(cls, v):
        if v < 0 or v > 100:
            raise ValueError(f"threshold deve estar em [0, 100], recebido {v}")
        return v


@router.get("/admin/gca/settings")
async def get_gca_settings(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Configurações atuais do GCA: pesos dos pilares, thresholds, agentes."""
    return _current_settings


@router.put("/admin/gca/settings/pillar-weights")
async def update_pillar_weights(
    req: PillarWeightsRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza pesos dos pilares. Soma deve ser exatamente 100."""
    _current_settings["pillar_weights"] = {
        "P1": req.P1, "P2": req.P2, "P3": req.P3, "P4": req.P4,
        "P5": req.P5, "P6": req.P6, "P7": req.P7,
    }
    logger.info(
        "admin_gca.pesos_atualizados",
        actor=str(current_user_id),
        weights=_current_settings["pillar_weights"],
    )
    return {"success": True, "pillar_weights": _current_settings["pillar_weights"]}


@router.put("/admin/gca/settings/thresholds")
async def update_thresholds(
    req: ThresholdsRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza thresholds de score (todos os 7 pilares + bandas de composite)."""
    _current_settings["score_thresholds"] = {
        "p1_blocking_threshold": req.p1_blocking_threshold,
        "p2_blocking_threshold": req.p2_blocking_threshold,
        "p3_blocking_threshold": req.p3_blocking_threshold,
        "p4_blocking_threshold": req.p4_blocking_threshold,
        "p5_blocking_threshold": req.p5_blocking_threshold,
        "p6_blocking_threshold": req.p6_blocking_threshold,
        "p7_blocking_threshold": req.p7_blocking_threshold,
        "ready_threshold": req.ready_threshold,
        "needs_review_threshold": req.needs_review_threshold,
        "at_risk_threshold": req.at_risk_threshold,
    }
    logger.info(
        "admin_gca.thresholds_atualizados",
        actor=str(current_user_id),
        thresholds=_current_settings["score_thresholds"],
    )
    return {"success": True, "score_thresholds": _current_settings["score_thresholds"]}


# ============================================================================
# Provedores de IA
# ============================================================================

AVAILABLE_PROVIDERS = {
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
        "default_model": "claude-sonnet-4-6",
        "api_url": "https://api.anthropic.com",
    },
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "default_model": "gpt-4o",
        "api_url": "https://api.openai.com",
    },
    "gemini": {
        "name": "Google Gemini",
        "models": ["gemini-2.0-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_model": "gemini-2.0-pro",
        "api_url": "https://generativelanguage.googleapis.com",
    },
    "deepseek": {
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "api_url": "https://api.deepseek.com",
    },
    "grok": {
        "name": "xAI Grok",
        "models": ["grok-3", "grok-3-mini"],
        "default_model": "grok-3-mini",
        "api_url": "https://api.x.ai",
    },
    "qwen": {
        "name": "Alibaba Qwen (DashScope)",
        "models": [
            "qwen-turbo",
            "qwen-plus",
            "qwen-max",
            "qwen-long",
            "qwen2.5-coder-32b-instruct",
        ],
        "default_model": "qwen-plus",
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
}

# Cache em memória (populado do banco na primeira leitura)
_ai_providers: Dict[str, dict] = {}
_ai_providers_loaded: bool = False


def _mask_key(key: str) -> str:
    """Mascara API key para exibição: mostra últimos 6 caracteres."""
    if not key or len(key) <= 6:
        return "****"
    return f"{'*' * (len(key) - 6)}{key[-6:]}"


async def _load_ai_providers_from_db(db):
    """Carrega provedores de IA do banco para o cache em memória."""
    global _ai_providers, _ai_providers_loaded
    if _ai_providers_loaded:
        return

    from sqlalchemy import select
    from app.models.base import SystemSettings
    import json

    result = await db.execute(
        select(SystemSettings).where(SystemSettings.setting_key.like("ai_provider:%"))
    )
    rows = result.scalars().all()
    for row in rows:
        provider_id = row.setting_key.replace("ai_provider:", "")
        try:
            _ai_providers[provider_id] = json.loads(row.setting_value)
        except Exception:
            pass

    _ai_providers_loaded = True

    # Atualizar settings em runtime com keys do banco
    if rows:
        from app.core.config import settings
        for pid, config in _ai_providers.items():
            api_key = config.get("api_key")
            if api_key:
                # Setar API key (criar atributo se não existir)
                key_attr = f"{pid.upper()}_API_KEY"
                object.__setattr__(settings, key_attr, api_key)
            model = config.get("model")
            if model:
                # Setar modelo do provider
                model_attr = f"{pid.upper()}_MODEL"
                object.__setattr__(settings, model_attr, model)
            if config.get("is_default"):
                object.__setattr__(settings, "DEFAULT_AI_PROVIDER", pid)
                if model:
                    object.__setattr__(settings, "DEFAULT_AI_MODEL", model)

        logger.info("admin_gca.ai_providers_loaded_from_db", count=len(rows))


async def _save_ai_provider_to_db(db, provider_id: str, config: dict, user_id=None):
    """Persiste configuração do provedor no banco."""
    from sqlalchemy import select
    from app.models.base import SystemSettings
    import json

    key = f"ai_provider:{provider_id}"
    result = await db.execute(select(SystemSettings).where(SystemSettings.setting_key == key))
    existing = result.scalar_one_or_none()

    if existing:
        existing.setting_value = json.dumps(config, default=str)
        existing.updated_by = user_id
    else:
        row = SystemSettings(
            setting_key=key,
            setting_value=json.dumps(config, default=str),
            updated_by=user_id,
        )
        db.add(row)

    await db.commit()


class AIProviderConfigRequest(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    enabled: bool = True


class AIProviderDefaultRequest(BaseModel):
    provider: str
    model: Optional[str] = None


@router.get("/admin/gca/ai-providers")
async def list_ai_providers(
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lista provedores de IA disponíveis e configurados."""
    from app.core.config import settings

    # Carregar do banco na primeira chamada
    await _load_ai_providers_from_db(db)

    providers = []
    for pid, info in AVAILABLE_PROVIDERS.items():
        # Verificar se tem key configurada (em memória ou .env)
        mem_config = _ai_providers.get(pid)
        env_key = getattr(settings, f"{pid.upper()}_API_KEY", None)

        configured = bool(mem_config) or bool(env_key)
        key_source = "admin" if mem_config else ("env" if env_key else None)
        masked_key = None
        if mem_config:
            masked_key = _mask_key(mem_config.get("api_key", ""))
        elif env_key:
            masked_key = _mask_key(env_key)

        is_default = (
            (mem_config and mem_config.get("is_default")) or
            (not any(c.get("is_default") for c in _ai_providers.values()) and settings.DEFAULT_AI_PROVIDER == pid)
        )

        providers.append({
            "id": pid,
            "name": info["name"],
            "models": info["models"],
            "default_model": info["default_model"],
            "configured": configured,
            "enabled": mem_config.get("enabled", True) if mem_config else configured,
            "key_source": key_source,
            "masked_key": masked_key,
            "selected_model": mem_config.get("model", info["default_model"]) if mem_config else (settings.DEFAULT_AI_MODEL if is_default else info["default_model"]),
            "is_default": is_default,
            "tested_at": mem_config.get("tested_at") if mem_config else None,
            "test_status": mem_config.get("test_status") if mem_config else None,
        })

    return {"providers": providers}


@router.put("/admin/gca/ai-providers")
async def configure_ai_provider(
    req: AIProviderConfigRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Configura ou atualiza um provedor de IA com API key."""
    if req.provider not in AVAILABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provedor '{req.provider}' não suportado")

    info = AVAILABLE_PROVIDERS[req.provider]
    model = req.model or info["default_model"]
    if model not in info["models"]:
        raise HTTPException(status_code=400, detail=f"Modelo '{model}' não disponível para {info['name']}")

    config = {
        "api_key": req.api_key,
        "model": model,
        "enabled": req.enabled,
        "configured_at": datetime.now(timezone.utc).isoformat(),
        "configured_by": str(current_user_id),
    }

    _ai_providers[req.provider] = config

    # Persistir no banco
    await _save_ai_provider_to_db(db, req.provider, config, current_user_id)

    # Atualizar settings em runtime para o AIService usar
    from app.core.config import settings
    key_attr = f"{req.provider.upper()}_API_KEY"
    if hasattr(settings, key_attr):
        object.__setattr__(settings, key_attr, req.api_key)

    logger.info(
        "admin_gca.ai_provider_configured",
        provider=req.provider,
        model=model,
        actor=str(current_user_id),
    )

    return {
        "success": True,
        "provider": req.provider,
        "model": model,
        "masked_key": _mask_key(req.api_key),
    }


@router.post("/admin/gca/ai-providers/test")
async def test_ai_provider(
    req: AIProviderConfigRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Testa conexão com um provedor de IA."""
    if req.provider not in AVAILABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provedor '{req.provider}' não suportado")

    import httpx

    # Carregar providers do banco caso necessário
    await _load_ai_providers_from_db(db)

    info = AVAILABLE_PROVIDERS[req.provider]
    model = req.model or info["default_model"]
    test_prompt = "Respond with exactly: OK"

    # Resolver API key: se 'use_existing' ou mascarada, buscar a real do cache/banco
    api_key = req.api_key
    if not api_key or api_key == "use_existing" or api_key.startswith("*"):
        mem_config = _ai_providers.get(req.provider)
        if mem_config and mem_config.get("api_key"):
            api_key = mem_config["api_key"]
        else:
            from app.core.config import settings as s
            env_key = getattr(s, f"{req.provider.upper()}_API_KEY", None)
            if env_key:
                api_key = env_key
            else:
                raise HTTPException(status_code=400, detail="API key não encontrada. Configure primeiro.")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if req.provider == "anthropic":
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={"model": model, "max_tokens": 10, "messages": [{"role": "user", "content": test_prompt}]},
                )
            elif req.provider == "openai":
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 10, "messages": [{"role": "user", "content": test_prompt}]},
                )
            elif req.provider == "deepseek":
                resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 10, "messages": [{"role": "user", "content": test_prompt}]},
                )
            elif req.provider == "grok":
                resp = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 10, "messages": [{"role": "user", "content": test_prompt}]},
                )
            elif req.provider == "gemini":
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": test_prompt}]}]},
                )
            else:
                raise HTTPException(status_code=400, detail="Teste não implementado para este provedor")

        success = resp.status_code in (200, 201)
        now = datetime.now(timezone.utc).isoformat()

        # Salvar resultado do teste (memória + banco)
        if req.provider in _ai_providers:
            _ai_providers[req.provider]["tested_at"] = now
            _ai_providers[req.provider]["test_status"] = "ok" if success else "error"
            await _save_ai_provider_to_db(db, req.provider, _ai_providers[req.provider], current_user_id)

        logger.info(
            "admin_gca.ai_provider_tested",
            provider=req.provider,
            model=model,
            success=success,
            status_code=resp.status_code,
        )

        if success:
            return {"success": True, "message": f"Conexão com {info['name']} ({model}) OK", "tested_at": now}
        else:
            error_detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            return {"success": False, "message": f"Erro: {error_detail}", "tested_at": now}

    except httpx.TimeoutException:
        return {"success": False, "message": "Timeout — provedor não respondeu em 15 segundos"}
    except Exception as e:
        return {"success": False, "message": f"Erro de conexão: {str(e)[:200]}"}


@router.put("/admin/gca/ai-providers/default")
async def set_default_provider(
    req: AIProviderDefaultRequest,
    current_user_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Define o provedor padrão para o pipeline OCG."""
    if req.provider not in AVAILABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provedor '{req.provider}' não suportado")

    # Verificar se está configurado
    mem_config = _ai_providers.get(req.provider)
    env_key = getattr(settings, f"{req.provider.upper()}_API_KEY", None)
    if not mem_config and not env_key:
        raise HTTPException(status_code=400, detail=f"Provedor '{req.provider}' não tem API key configurada")

    # Carregar do banco caso necessário
    await _load_ai_providers_from_db(db)

    # Remover flag de outros e persistir
    for pid in _ai_providers:
        _ai_providers[pid]["is_default"] = False
        await _save_ai_provider_to_db(db, pid, _ai_providers[pid], current_user_id)

    # Setar como padrão
    if mem_config:
        _ai_providers[req.provider]["is_default"] = True
        if req.model:
            _ai_providers[req.provider]["model"] = req.model
        await _save_ai_provider_to_db(db, req.provider, _ai_providers[req.provider], current_user_id)

    # Atualizar settings em runtime (já importado no topo)
    object.__setattr__(settings, "DEFAULT_AI_PROVIDER", req.provider)
    if req.model:
        object.__setattr__(settings, "DEFAULT_AI_MODEL", req.model)

    logger.info("admin_gca.default_ai_provider_set", provider=req.provider, actor=str(current_user_id))

    return {"success": True, "default_provider": req.provider, "model": req.model}
