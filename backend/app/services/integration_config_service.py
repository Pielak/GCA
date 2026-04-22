"""MVP 20 Fase 20.1d — Service de config de integrações externas.

Compõe `ProviderConfig` a partir de:
  - `ProjectSettings` (setting_type='issue_tracker') — JSON não-secreto
    com provider, base_url, default_project_key, status_mapping, extra.
  - `ProjectSecret` (secret_type='issue_tracker_credentials',
    secret_key=provider) — credenciais encrypted via vault.

Tese do MVP 20: adapter pattern. Service puro de composição; ele NÃO
chama API externa — quem faz é o adapter.

Registration de adapters: `register_builtin_adapters()` é chamado no
startup do app (main.py) e registra JiraAdapter + TrelloAdapter no
registry canônico da porta.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectSettings
from app.services.ports.issue_tracker_port import (
    IssueTrackerConfigError,
    ProviderConfig,
    register_adapter,
    registered_providers,
)
from app.services.vault_service import VaultService


logger = structlog.get_logger(__name__)


SETTING_TYPE = "issue_tracker"
SECRET_TYPE = "issue_tracker_credentials"

# Credenciais esperadas por provider (validação declarativa).
_REQUIRED_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "jira": ("email", "api_token"),
    "trello": ("api_key", "api_token"),
}

# Credenciais opcionais (não bloqueiam config, mas viabilizam webhook).
_OPTIONAL_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "jira": ("webhook_secret",),
    "trello": ("webhook_secret",),
}


def register_builtin_adapters() -> None:
    """Registra adapters built-in no registry canônico da porta.

    Chamado no startup do app. Idempotente — registrar 2x substitui a
    instância anterior (útil em hot-reload de dev).
    """
    from app.services.adapters.jira_adapter import JiraAdapter
    from app.services.adapters.trello_adapter import TrelloAdapter

    register_adapter(JiraAdapter())
    register_adapter(TrelloAdapter())
    logger.info("integrations.adapters_registered",
                 providers=registered_providers())


# ─── Load / Save config ───────────────────────────────────────────────


async def load_settings_json(
    db: AsyncSession,
    project_id: UUID,
) -> dict:
    """Retorna o JSON de settings do issue tracker, ou {} se ausente."""
    q = (
        select(ProjectSettings)
        .where(ProjectSettings.project_id == project_id)
        .where(ProjectSettings.setting_type == SETTING_TYPE)
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        return {}
    try:
        return json.loads(row.settings_json or "{}")
    except (TypeError, ValueError):
        logger.warning("integrations.settings.invalid_json",
                        project_id=str(project_id))
        return {}


async def save_settings_json(
    db: AsyncSession,
    project_id: UUID,
    settings_data: dict,
    updated_by: Optional[UUID] = None,
) -> None:
    """Upsert canônico em ProjectSettings."""
    q = (
        select(ProjectSettings)
        .where(ProjectSettings.project_id == project_id)
        .where(ProjectSettings.setting_type == SETTING_TYPE)
    )
    row = (await db.execute(q)).scalar_one_or_none()
    payload = json.dumps(settings_data, ensure_ascii=False)
    if row is None:
        db.add(ProjectSettings(
            project_id=project_id,
            setting_type=SETTING_TYPE,
            settings_json=payload,
            updated_by=updated_by,
        ))
    else:
        row.settings_json = payload
        row.updated_by = updated_by
    await db.flush()


# ─── ProviderConfig composition ───────────────────────────────────────


async def build_provider_config(
    db: AsyncSession,
    project_id: UUID,
    *,
    provider: Optional[str] = None,
) -> Optional[ProviderConfig]:
    """Compõe `ProviderConfig` final (settings + credenciais do vault).

    Retorna None se:
      - Não há settings configurado OR
      - Settings não habilitado OR
      - Provider inválido OR
      - Credenciais obrigatórias ausentes no vault.

    `provider` explícito permite forçar um provider específico (útil em
    webhooks onde o endpoint diz qual é). Quando None, usa o
    `active_provider` do settings.
    """
    data = await load_settings_json(db, project_id)
    if not data:
        return None

    selected = provider or data.get("active_provider")
    if not selected:
        return None
    if not data.get("enabled", True):
        return None

    per_provider = (data.get("providers") or {}).get(selected) or {}
    base_url = per_provider.get("base_url") or ""
    default_project_key = per_provider.get("default_project_key") or ""
    status_mapping = per_provider.get("status_mapping") or {}
    extra = per_provider.get("extra") or {}
    # Contrato canônico: o `project_id` do GCA é embutido no `extra`
    # pra que o adapter consiga resolver o webhook (decisão binária #1).
    extra.setdefault("gca_project_id", str(project_id))

    # Carrega credenciais do vault.
    vault = VaultService()
    credentials: dict[str, str] = {}
    required = _REQUIRED_CREDENTIALS.get(selected, ())
    optional = _OPTIONAL_CREDENTIALS.get(selected, ())
    for key in required + optional:
        value = await vault.get_secret(
            db, project_id, SECRET_TYPE, f"{selected}:{key}",
        )
        if value:
            credentials[key] = value

    # Valida credenciais obrigatórias — sem elas não há config útil.
    missing = [k for k in required if not credentials.get(k)]
    if missing:
        logger.info("integrations.config.missing_credentials",
                     project_id=str(project_id),
                     provider=selected,
                     missing=missing)
        return None

    return ProviderConfig(
        credentials=credentials,
        base_url=base_url,
        default_project_key=default_project_key,
        status_mapping=status_mapping,
        extra=extra,
    )


# ─── API de alto nível pra router ────────────────────────────────────


async def get_safe_config_for_display(
    db: AsyncSession,
    project_id: UUID,
) -> dict:
    """Retorna config SEM credenciais (safe pra exibir no /settings).

    Formato do payload:
      {
        "enabled": bool,
        "active_provider": "jira" | "trello" | null,
        "providers": {
            "jira": { "base_url": ..., "default_project_key": ..., ... },
            "trello": {...},
        },
        "has_credentials": {
            "jira": {"email": true, "api_token": true, "webhook_secret": false},
            "trello": {...},
        },
      }
    """
    data = await load_settings_json(db, project_id)
    enabled = data.get("enabled", False)
    active = data.get("active_provider")
    providers = data.get("providers") or {}

    # Checa presença de cada credential (sem revelar valor).
    vault = VaultService()
    has_credentials: dict[str, dict[str, bool]] = {}
    for prov in ("jira", "trello"):
        flags: dict[str, bool] = {}
        for key in _REQUIRED_CREDENTIALS.get(prov, ()) + _OPTIONAL_CREDENTIALS.get(prov, ()):
            val = await vault.get_secret(
                db, project_id, SECRET_TYPE, f"{prov}:{key}",
            )
            flags[key] = bool(val)
        has_credentials[prov] = flags

    return {
        "enabled": enabled,
        "active_provider": active,
        "providers": providers,
        "has_credentials": has_credentials,
        "registered_providers": registered_providers(),
    }


async def set_credential(
    db: AsyncSession,
    project_id: UUID,
    provider: str,
    cred_key: str,
    value: str,
    updated_by: Optional[UUID] = None,
) -> None:
    """Armazena 1 credencial no vault (encrypted).

    `cred_key` é a chave específica do provider — ex: 'email', 'api_token',
    'webhook_secret'. Valida contra whitelist por provider.
    """
    allowed = set(
        _REQUIRED_CREDENTIALS.get(provider, ())
        + _OPTIONAL_CREDENTIALS.get(provider, ())
    )
    if cred_key not in allowed:
        raise IssueTrackerConfigError(
            f"Credencial '{cred_key}' não é válida para {provider}. "
            f"Aceitas: {sorted(allowed)}"
        )
    vault = VaultService()
    ok = await vault.store_secret(
        db, project_id, SECRET_TYPE, f"{provider}:{cred_key}",
        value, created_by=updated_by,
    )
    if not ok:
        raise IssueTrackerConfigError(
            f"Falha ao armazenar credencial '{cred_key}' no vault"
        )


async def delete_credential(
    db: AsyncSession,
    project_id: UUID,
    provider: str,
    cred_key: str,
) -> None:
    """Remove credencial do vault (útil pra rotação ou revogação)."""
    vault = VaultService()
    await vault.delete_secret(
        db, project_id, SECRET_TYPE, f"{provider}:{cred_key}",
    )
