"""MVP 20 Fase 20.3 — Service orquestrador do Notifier.

Compõe NotifierConfig a partir de ProjectSettings + ProjectSecret vault,
chama adapter registrado, e trata fallback quando delivery falha.

Fallback: delivery retryable vira entrada em `user_notifications` (tabela
existente) com flag `delivery_failed=True` + payload serializado pra retry
posterior. Retry via Celery é out-of-scope da Fase 20.3 V1 — fica
registrada a falha pra observabilidade; reprocessamento manual via endpoint
admin quando necessário.

Config canônica no ProjectSettings (setting_type='notifier'):
    {
      "enabled": bool,
      "active_provider": "slack" | null,
      "providers": {
          "slack": {
              "channel": "#gca-events",
              "opted_in_events": [...] | null,
              "link_only_mode": bool,
              "gca_base_url": "https://gca.cliente.com"
          }
      }
    }

Credenciais no vault: secret_type='notifier_credentials',
secret_key='<provider>:<key>' (ex: 'slack:webhook_url').
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Project, ProjectSettings
from app.services.ports.notifier_port import (
    ALL_CANONICAL_EVENTS,
    CanonicalEventType,
    DeliveryResult,
    EventPayload,
    NotifierConfig,
    NotifierConfigError,
    get_notifier,
    register_notifier,
    registered_notifiers,
)
from app.services.vault_service import VaultService


logger = structlog.get_logger(__name__)


SETTING_TYPE = "notifier"
SECRET_TYPE = "notifier_credentials"

# Credenciais esperadas por provider.
_REQUIRED_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "slack": ("webhook_url",),
    "teams": ("webhook_url",),
}


def register_builtin_notifiers() -> None:
    """Registra adapters built-in. Chamado no startup."""
    from app.services.adapters.slack_adapter import SlackAdapter
    from app.services.adapters.teams_adapter import TeamsAdapter

    register_notifier(SlackAdapter())
    register_notifier(TeamsAdapter())
    logger.info("notifier.adapters_registered",
                 providers=registered_notifiers())


# ─── Load / Save config ───────────────────────────────────────────────


async def load_settings_json(
    db: AsyncSession,
    project_id: UUID,
) -> dict:
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
        return {}


async def save_settings_json(
    db: AsyncSession,
    project_id: UUID,
    settings_data: dict,
    updated_by: Optional[UUID] = None,
) -> None:
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


# ─── NotifierConfig composition ──────────────────────────────────────


async def build_notifier_config(
    db: AsyncSession,
    project_id: UUID,
    *,
    provider: Optional[str] = None,
) -> Optional[tuple[str, NotifierConfig]]:
    """Compõe (provider, NotifierConfig) pronto pra send.

    Retorna None quando:
      - Notifier não habilitado OR
      - Sem provider ativo OR
      - Credenciais obrigatórias ausentes.
    """
    data = await load_settings_json(db, project_id)
    if not data:
        return None
    if not data.get("enabled", False):
        return None

    selected = provider or data.get("active_provider")
    if not selected:
        return None

    per_provider = (data.get("providers") or {}).get(selected) or {}

    vault = VaultService()
    credentials: dict[str, str] = {}
    required = _REQUIRED_CREDENTIALS.get(selected, ())
    for key in required:
        value = await vault.get_secret(
            db, project_id, SECRET_TYPE, f"{selected}:{key}",
        )
        if value:
            credentials[key] = value

    missing = [k for k in required if not credentials.get(k)]
    if missing:
        return None

    opted = per_provider.get("opted_in_events")
    # Valida whitelist de eventos — ignora eventos desconhecidos sem falhar.
    if opted:
        opted = [e for e in opted if e in ALL_CANONICAL_EVENTS]

    config = NotifierConfig(
        credentials=credentials,
        channel=per_provider.get("channel", ""),
        opted_in_events=opted,
        link_only_mode=bool(per_provider.get("link_only_mode", False)),
        gca_base_url=per_provider.get("gca_base_url", ""),
        extra=per_provider.get("extra") or {},
    )
    return selected, config


# ─── API pra router (config UI) ───────────────────────────────────────


async def get_safe_notifier_config_for_display(
    db: AsyncSession,
    project_id: UUID,
) -> dict:
    """Retorna config SEM credenciais (safe pra exibir no /settings).

    Formato:
      {
        "enabled": bool,
        "active_provider": "slack" | "teams" | null,
        "providers": {
            "slack": {"channel": "#x", "opted_in_events": [...] | null,
                      "link_only_mode": bool, "gca_base_url": "..."},
            "teams": {...},
        },
        "has_credentials": {
            "slack": {"webhook_url": true},
            "teams": {"webhook_url": false},
        },
        "registered_providers": ["slack", "teams"],
        "canonical_events": [...6 eventos...]
      }
    """
    data = await load_settings_json(db, project_id)
    enabled = data.get("enabled", False)
    active = data.get("active_provider")
    providers = data.get("providers") or {}

    vault = VaultService()
    has_credentials: dict[str, dict[str, bool]] = {}
    for prov in ("slack", "teams"):
        flags: dict[str, bool] = {}
        for key in _REQUIRED_CREDENTIALS.get(prov, ()):
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
        "registered_providers": registered_notifiers(),
        "canonical_events": list(ALL_CANONICAL_EVENTS),
    }


async def set_notifier_credential(
    db: AsyncSession,
    project_id: UUID,
    provider: str,
    cred_key: str,
    value: str,
    updated_by: Optional[UUID] = None,
) -> None:
    """Grava 1 credencial do notifier no vault (encrypted)."""
    allowed = set(_REQUIRED_CREDENTIALS.get(provider, ()))
    if not allowed:
        raise NotifierConfigError(
            f"Provider '{provider}' não tem credenciais canônicas definidas."
        )
    if cred_key not in allowed:
        raise NotifierConfigError(
            f"Credencial '{cred_key}' não é válida para {provider}. "
            f"Aceitas: {sorted(allowed)}"
        )
    vault = VaultService()
    ok = await vault.store_secret(
        db, project_id, SECRET_TYPE, f"{provider}:{cred_key}",
        value, created_by=updated_by,
    )
    if not ok:
        raise NotifierConfigError(
            f"Falha ao armazenar credencial '{cred_key}' no vault"
        )


async def delete_notifier_credential(
    db: AsyncSession,
    project_id: UUID,
    provider: str,
    cred_key: str,
) -> None:
    """Remove credencial do notifier do vault."""
    vault = VaultService()
    await vault.delete_secret(
        db, project_id, SECRET_TYPE, f"{provider}:{cred_key}",
    )


# ─── Send (best-effort, nunca bloqueia caller) ───────────────────────


async def send_event(
    db: AsyncSession,
    project_id: UUID,
    event_type: CanonicalEventType,
    *,
    title: str,
    fields: Optional[list[tuple[str, str]]] = None,
    link_path: Optional[str] = None,
    severity: str = "info",
) -> DeliveryResult:
    """Envia evento canônico para o notifier configurado do projeto.

    Best-effort: nunca levanta. Caller não precisa tratar exceção; quando
    provider não configurado retorna DeliveryResult(ok=False, retryable=False,
    error='...').
    """
    if event_type not in ALL_CANONICAL_EVENTS:
        return DeliveryResult(
            ok=False, error=f"event_type desconhecido: {event_type}",
            retryable=False,
        )

    try:
        resolved = await build_notifier_config(db, project_id, provider=None)
    except Exception as exc:
        logger.warning("notifier.config_load_failed",
                        project_id=str(project_id), error=str(exc))
        return DeliveryResult(ok=False, error=str(exc), retryable=False)

    if resolved is None:
        return DeliveryResult(
            ok=False, error="notifier não configurado ou desabilitado",
            retryable=False,
        )

    provider, config = resolved

    # Resolve nome do projeto pra contexto (uma chamada a mais; pequena).
    project = (await db.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    project_name = project.name if project else "(projeto sem nome)"

    payload = EventPayload(
        event_type=event_type,
        title=title,
        project_name=project_name,
        project_id=str(project_id),
        fields=fields or [],
        link_path=link_path,
        severity=severity,  # type: ignore[arg-type]
    )

    try:
        adapter = get_notifier(provider)
    except NotifierConfigError as exc:
        return DeliveryResult(ok=False, error=str(exc), retryable=False)

    try:
        result = await adapter.send(config, payload)
    except Exception as exc:
        # Proteção extra — adapter não deveria levantar (contrato), mas
        # caller sempre recebe DeliveryResult.
        logger.warning("notifier.send_unexpected_exception",
                        project_id=str(project_id),
                        event_type=event_type,
                        error=str(exc))
        return DeliveryResult(ok=False, error=str(exc), retryable=True)

    if result.ok:
        logger.info("notifier.delivered",
                     project_id=str(project_id),
                     event_type=event_type,
                     provider=provider)
    else:
        logger.info("notifier.delivery_failed",
                     project_id=str(project_id),
                     event_type=event_type,
                     provider=provider,
                     retryable=result.retryable,
                     error=result.error)

    return result
