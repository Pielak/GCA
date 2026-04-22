"""MVP 20 Fase 20.1d + Fix pós-MVP 22 — Endpoints HTTP de integrações externas.

Endpoints canônicos:

  Issue Tracker — Config (autenticados, GP+Admin):
    GET  /api/v1/projects/:id/integrations/issue-tracker
    PUT  /api/v1/projects/:id/integrations/issue-tracker
    PUT  /api/v1/projects/:id/integrations/issue-tracker/credentials/:provider/:key
    DELETE /api/v1/projects/:id/integrations/issue-tracker/credentials/:provider/:key

  Issue Tracker — Consulta (autenticados, membro aceito):
    GET  /api/v1/projects/:id/external-issues

  Issue Tracker — Webhook (PÚBLICO com signing secret):
    POST /api/v1/integrations/webhooks/issue-tracker/:provider/:project_id

  Notifier (Slack + Teams) — Config (autenticados, GP+Admin):
    GET  /api/v1/projects/:id/integrations/notifier
    PUT  /api/v1/projects/:id/integrations/notifier
    PUT  /api/v1/projects/:id/integrations/notifier/credentials/:provider/:key
    DELETE /api/v1/projects/:id/integrations/notifier/credentials/:provider/:key

RBAC preservado (§4.1):
- Leitura de config sanitizada: GP + Admin.
- Escrita: GP + Admin.
- Webhook: público; adapter valida assinatura antes de qualquer escrita.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectMember, User
from app.services.integration_config_service import (
    build_provider_config,
    delete_credential,
    get_safe_config_for_display,
    save_settings_json,
    set_credential,
)
from app.services.issue_tracker_service import (
    apply_webhook_event,
    list_external_issues,
)
from app.services.notifier_service import (
    ALL_CANONICAL_EVENTS,
    delete_notifier_credential,
    get_safe_notifier_config_for_display,
    save_settings_json as save_notifier_settings_json,
    set_notifier_credential,
)
from app.services.ports.issue_tracker_port import (
    IssueTrackerConfigError,
    registered_providers,
)
from app.services.ports.notifier_port import (
    NotifierConfigError,
    registered_notifiers,
)


router = APIRouter(tags=["integrations"])


# ─── Schemas ──────────────────────────────────────────────────────────


class ProviderSettings(BaseModel):
    """Settings por provider — tudo non-secret. Credenciais vão via vault."""
    base_url: str = Field("", max_length=500)
    default_project_key: str = Field("", max_length=200)
    status_mapping: dict[str, str] = Field(default_factory=dict)
    extra: dict = Field(default_factory=dict)


class IntegrationSettings(BaseModel):
    enabled: bool = True
    active_provider: Optional[str] = Field(
        None,
        description="Provider padrão (jira|trello); null desativa integração.",
    )
    providers: dict[str, ProviderSettings] = Field(default_factory=dict)


class CredentialWrite(BaseModel):
    value: str = Field(..., min_length=1, max_length=4000)


# ─── RBAC ─────────────────────────────────────────────────────────────


async def _require_gp_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    """GP do projeto OU Admin. Pattern canônico do produto."""
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória",
        )
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido ou inativo")
    if user.is_admin or user.is_support:
        return user
    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at or not member.is_active:
        raise HTTPException(
            status_code=403,
            detail="Apenas GP do projeto ou Admin pode alterar integrações",
        )
    if member.role not in ("gp",) and not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas GP do projeto ou Admin pode alterar integrações",
        )
    return user


async def _require_member_or_admin(
    project_id: UUID,
    user_id: Optional[UUID],
    db: AsyncSession,
) -> User:
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória",
        )
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Usuário inválido ou inativo")
    if user.is_admin or user.is_support:
        return user
    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not member or not member.accepted_at or not member.is_active:
        raise HTTPException(
            status_code=403,
            detail="Apenas membros aceitos do projeto ou Admin",
        )
    return user


# ─── Endpoints de config ──────────────────────────────────────────────


@router.get("/projects/{project_id}/integrations/issue-tracker")
async def get_issue_tracker_config(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retorna config sanitizada (sem credenciais em plaintext)."""
    await _require_gp_or_admin(project_id, user_id, db)
    return await get_safe_config_for_display(db, project_id)


@router.put("/projects/{project_id}/integrations/issue-tracker")
async def update_issue_tracker_settings(
    project_id: UUID,
    payload: IntegrationSettings = Body(...),
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Atualiza settings non-secret do issue tracker para o projeto."""
    user = await _require_gp_or_admin(project_id, user_id, db)

    # Valida active_provider contra registry canônico.
    if payload.active_provider and payload.active_provider not in registered_providers():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{payload.active_provider}' não disponível. "
                f"Registrados: {registered_providers()}"
            ),
        )

    # Serializa dataclass-like payload pra dict JSON-safe.
    providers_dict: dict = {}
    for prov_name, prov_settings in payload.providers.items():
        if prov_name not in ("jira", "trello"):
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{prov_name}' não suportado em V1 (jira, trello).",
            )
        providers_dict[prov_name] = prov_settings.dict()

    data = {
        "enabled": payload.enabled,
        "active_provider": payload.active_provider,
        "providers": providers_dict,
    }
    await save_settings_json(db, project_id, data, updated_by=user.id)
    await db.commit()
    return await get_safe_config_for_display(db, project_id)


@router.put("/projects/{project_id}/integrations/issue-tracker/credentials/{provider}/{cred_key}")
async def put_credential(
    project_id: UUID,
    provider: str,
    cred_key: str,
    payload: CredentialWrite = Body(...),
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Armazena 1 credencial no vault (encrypted). Whitelist por provider."""
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        await set_credential(
            db, project_id, provider, cred_key, payload.value,
            updated_by=user.id,
        )
    except IssueTrackerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return {"success": True, "provider": provider, "credential": cred_key}


@router.delete("/projects/{project_id}/integrations/issue-tracker/credentials/{provider}/{cred_key}")
async def delete_cred(
    project_id: UUID,
    provider: str,
    cred_key: str,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_gp_or_admin(project_id, user_id, db)
    await delete_credential(db, project_id, provider, cred_key)
    await db.commit()
    return {"success": True, "provider": provider, "credential": cred_key}


# ─── Endpoints de Notifier (Slack + Teams) ────────────────────────────


class NotifierProviderSettings(BaseModel):
    """Settings por provider de notifier — tudo non-secret.

    `opted_in_events` é lista de event_types canônicos; None ou lista vazia
    = opted in em todos (default). `link_only_mode` degrada o card pra
    link-only (cliente regulado). `gca_base_url` é usado pra montar link
    profundo pro GCA no card.
    """
    channel: str = Field("", max_length=100)
    opted_in_events: Optional[list[str]] = Field(default=None)
    link_only_mode: bool = Field(default=False)
    gca_base_url: str = Field("", max_length=500)
    extra: dict = Field(default_factory=dict)


class NotifierSettings(BaseModel):
    enabled: bool = True
    active_provider: Optional[str] = Field(
        None,
        description="Provider padrão (slack|teams); null desativa notifier.",
    )
    providers: dict[str, NotifierProviderSettings] = Field(default_factory=dict)


@router.get("/projects/{project_id}/integrations/notifier")
async def get_notifier_config(
    project_id: UUID,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retorna config do notifier sanitizada (sem credenciais)."""
    await _require_gp_or_admin(project_id, user_id, db)
    return await get_safe_notifier_config_for_display(db, project_id)


@router.put("/projects/{project_id}/integrations/notifier")
async def update_notifier_settings(
    project_id: UUID,
    payload: NotifierSettings = Body(...),
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Atualiza settings non-secret do notifier (Slack/Teams)."""
    user = await _require_gp_or_admin(project_id, user_id, db)

    if payload.active_provider and payload.active_provider not in registered_notifiers():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{payload.active_provider}' não disponível. "
                f"Registrados: {registered_notifiers()}"
            ),
        )

    providers_dict: dict = {}
    for prov_name, prov_settings in payload.providers.items():
        if prov_name not in ("slack", "teams"):
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{prov_name}' não suportado em V1 (slack, teams).",
            )
        # Valida whitelist de eventos canônicos — filtra desconhecidos silenciosamente.
        serialized = prov_settings.dict()
        opted = serialized.get("opted_in_events")
        if opted:
            serialized["opted_in_events"] = [
                e for e in opted if e in ALL_CANONICAL_EVENTS
            ]
        providers_dict[prov_name] = serialized

    data = {
        "enabled": payload.enabled,
        "active_provider": payload.active_provider,
        "providers": providers_dict,
    }
    await save_notifier_settings_json(db, project_id, data, updated_by=user.id)
    await db.commit()
    return await get_safe_notifier_config_for_display(db, project_id)


@router.put("/projects/{project_id}/integrations/notifier/credentials/{provider}/{cred_key}")
async def put_notifier_credential(
    project_id: UUID,
    provider: str,
    cred_key: str,
    payload: CredentialWrite = Body(...),
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Armazena 1 credencial do notifier no vault (encrypted)."""
    user = await _require_gp_or_admin(project_id, user_id, db)
    try:
        await set_notifier_credential(
            db, project_id, provider, cred_key, payload.value,
            updated_by=user.id,
        )
    except NotifierConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return {"success": True, "provider": provider, "credential": cred_key}


@router.delete("/projects/{project_id}/integrations/notifier/credentials/{provider}/{cred_key}")
async def delete_notifier_cred(
    project_id: UUID,
    provider: str,
    cred_key: str,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_gp_or_admin(project_id, user_id, db)
    await delete_notifier_credential(db, project_id, provider, cred_key)
    await db.commit()
    return {"success": True, "provider": provider, "credential": cred_key}


# ─── Listagem de issues (leitura) ─────────────────────────────────────


@router.get("/projects/{project_id}/external-issues")
async def list_issues(
    project_id: UUID,
    status_filter: Optional[str] = None,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lista issues externas vinculadas ao projeto."""
    await _require_member_or_admin(project_id, user_id, db)
    items = await list_external_issues(
        db, project_id,
        status=status_filter if status_filter else None,  # type: ignore[arg-type]
    )
    return {
        "count": len(items),
        "issues": [
            {
                "id": str(i.id),
                "provider": i.provider,
                "external_id": i.external_id,
                "url": i.url,
                "title": i.title,
                "status_canonical": i.status_canonical,
                "status_raw": i.status_raw,
                "priority": i.priority,
                "module_candidate_id": str(i.module_candidate_id) if i.module_candidate_id else None,
                "synced_at": i.synced_at.isoformat() if i.synced_at else None,
                "closed_at": i.closed_at.isoformat() if i.closed_at else None,
            }
            for i in items
        ],
    }


# ─── Webhook receiver (público com signing secret) ───────────────────


@router.post("/integrations/webhooks/issue-tracker/{provider}/{project_id}")
async def receive_webhook(
    provider: str,
    project_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recebe webhook do provider (Jira, Trello).

    Público — segurança é 100% via HMAC do adapter. Sem signing secret
    configurado, o adapter retorna False e respondemos 401.

    Compartimentalização §2.2: `project_id` vem no path; adapter
    valida que o payload é deste projeto via `config.extra.gca_project_id`.
    """
    if provider not in registered_providers():
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider}' não disponível.",
        )

    raw_body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido (não é JSON)")

    config = await build_provider_config(db, project_id, provider=provider)
    if config is None:
        raise HTTPException(
            status_code=400,
            detail="Integração não configurada ou credenciais ausentes.",
        )

    # Headers normalizados (case-insensitive via FastAPI Request).
    headers = {k: v for k, v in request.headers.items()}

    try:
        issue = await apply_webhook_event(
            db, provider=provider, config=config,
            headers=headers, raw_body=raw_body, payload=payload,
        )
    except Exception as exc:
        # Adapter ou service pode levantar em casos extremos — logamos e
        # respondemos 500 genérico (nunca exibir interno pra webhook público).
        import structlog
        structlog.get_logger(__name__).warning(
            "webhook.processing_error",
            provider=provider,
            project_id=str(project_id),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Erro ao processar webhook")

    if issue is None:
        # Assinatura inválida OU evento irrelevante.
        return {"accepted": False, "reason": "invalid_signature_or_irrelevant"}

    await db.commit()
    return {
        "accepted": True,
        "issue_id": str(issue.id),
        "external_id": issue.external_id,
        "status": issue.status_canonical,
    }
