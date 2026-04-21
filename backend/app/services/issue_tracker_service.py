"""MVP 20 Fase 20.1a — Service orquestrador do Issue Tracker Bridge.

Skeleton em 20.1a: só manipulação CRUD do modelo `ExternalIssue` +
resolução de adapter a partir do registry. Adapters concretos (Jira,
Trello) entram em 20.1b e 20.1c.

Fluxo canônico alto-nível (preparado aqui, executado nas sub-fases):
  1. Módulo aprovado pelo GP → `create_external_issue` orquestra:
     a. resolve ProviderConfig do projeto (de project_settings ainda em 20.1d)
     b. chama `IssueTrackerPort.create_issue` via adapter registrado
     c. persiste `ExternalIssue` com external_id retornado
     d. emite `GlobalAuditLog.EXTERNAL_ISSUE_CREATED`
  2. Webhook do provider chega → `apply_webhook_event`:
     a. adapter valida assinatura (`verify_webhook`)
     b. adapter normaliza em IssueEvent (`parse_webhook`)
     c. service atualiza `ExternalIssue` (idempotente via UNIQUE)
     d. emite `GlobalAuditLog.EXTERNAL_ISSUE_STATUS_SYNCED`

Compartimentalização §2.2: toda query aqui filtra por project_id;
service nunca aceita query cross-project.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ExternalIssue
from app.services.ports.issue_tracker_port import (
    CanonicalStatus,
    IssuePayload,
    IssueTrackerConfigError,
    get_adapter,
    registered_providers,
)


logger = structlog.get_logger(__name__)


# ─── CRUD canônico sobre ExternalIssue ────────────────────────────────


async def list_external_issues(
    db: AsyncSession,
    project_id: UUID,
    *,
    status: Optional[CanonicalStatus] = None,
) -> list[ExternalIssue]:
    """Lista issues externas do projeto. Compartimentalizado por project_id.

    Uso: UI do painel de integrações + geração da Seção 4 do ERS (futuro
    enriquecimento com links pro tracker).
    """
    q = select(ExternalIssue).where(ExternalIssue.project_id == project_id)
    if status is not None:
        q = q.where(ExternalIssue.status_canonical == status)
    q = q.order_by(ExternalIssue.created_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_external_issue_by_external_id(
    db: AsyncSession,
    project_id: UUID,
    provider: str,
    external_id: str,
) -> Optional[ExternalIssue]:
    """Busca por chave natural (project_id + provider + external_id).

    Usado por webhook handler pra upsert idempotente — UNIQUE na migration
    035 garante que o match é único.
    """
    q = (
        select(ExternalIssue)
        .where(ExternalIssue.project_id == project_id)
        .where(ExternalIssue.provider == provider)
        .where(ExternalIssue.external_id == external_id)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def upsert_from_payload(
    db: AsyncSession,
    *,
    project_id: UUID,
    provider: str,
    module_candidate_id: Optional[UUID],
    payload: IssuePayload,
    created_by: Optional[UUID] = None,
) -> ExternalIssue:
    """Cria ou atualiza ExternalIssue a partir de payload canônico.

    Idempotência: se já existe (project_id, provider, external_id), atualiza
    os campos mutáveis (status, url, title, provider_specific, synced_at).
    Se não existe, cria. Respeita UNIQUE canônica da migration 035.

    Regra binária #7 do MVP 20: `status_canonical` vem do adapter (que já
    aplicou `status_mapping` do projeto). Service confia no adapter.
    """
    existing = await get_external_issue_by_external_id(
        db, project_id, provider, payload.external_id
    )
    now = datetime.now(timezone.utc)

    if existing is not None:
        existing.title = payload.title
        existing.url = payload.url
        existing.status_canonical = payload.status_canonical
        existing.status_raw = payload.status_raw
        existing.priority = payload.priority
        existing.provider_specific = payload.provider_specific or {}
        existing.synced_at = now
        if payload.status_canonical in ("done", "cancelled") and existing.closed_at is None:
            existing.closed_at = now
        # module_candidate_id não é sobrescrito por webhook —
        # vínculo é estabelecido na criação.
        await db.flush()
        return existing

    fresh = ExternalIssue(
        project_id=project_id,
        module_candidate_id=module_candidate_id,
        provider=provider,
        external_id=payload.external_id,
        url=payload.url,
        title=payload.title,
        status_canonical=payload.status_canonical,
        status_raw=payload.status_raw,
        priority=payload.priority,
        provider_specific=payload.provider_specific or {},
        created_by=created_by,
        synced_at=now,
        closed_at=now if payload.status_canonical in ("done", "cancelled") else None,
    )
    db.add(fresh)
    await db.flush()
    return fresh


# ─── Resolução de adapter ─────────────────────────────────────────────


def resolve_adapter(provider: str):
    """Wrapper que valida e retorna adapter registrado.

    Motivo do wrapper (em vez de caller chamar `get_adapter` direto): o
    service é o ponto onde a mensagem de erro é traduzida em exceção
    HTTP-friendly pro router.
    """
    if provider not in registered_providers():
        raise IssueTrackerConfigError(
            f"Provider '{provider}' não disponível. "
            f"Providers registrados: {registered_providers() or '[nenhum adapter configurado]'}"
        )
    return get_adapter(provider)


# ─── Placeholders para sub-fases 20.1b/c/d ────────────────────────────
# Estes métodos têm assinatura canônica mas ainda não orquestram
# chamada ao adapter — serão preenchidos quando JiraAdapter entrar.


async def create_issue_from_module(
    db: AsyncSession,
    *,
    project_id: UUID,
    module_candidate_id: UUID,
    provider: str,
    config,  # ProviderConfig — evita import circular em annotation
    actor_id: Optional[UUID] = None,
) -> ExternalIssue:
    """Cria issue no tracker externo a partir de módulo aprovado do GCA.

    Fluxo canônico:
      1. Carrega ModuleCandidate (valida project_id, compartimentalização).
      2. Resolve adapter via registry.
      3. Chama adapter.create_issue() com título/descrição canônicos.
      4. Faz upsert do ExternalIssue vinculado ao módulo.
      5. Emite EXTERNAL_ISSUE_CREATED no audit.

    Caller (router ou hook de aprovação de módulo) é responsável por
    fornecer o `ProviderConfig`. Service não toca em vault/settings —
    isso vive na Fase 20.1d (UI + config).
    """
    from app.models.base import ModuleCandidate
    from app.services.audit_service import AuditEvents, AuditService

    adapter = resolve_adapter(provider)

    # Carrega módulo validando compartimentalização.
    mod = (await db.execute(
        select(ModuleCandidate)
        .where(ModuleCandidate.id == module_candidate_id)
        .where(ModuleCandidate.project_id == project_id)
    )).scalar_one_or_none()
    if mod is None:
        raise ValueError(
            f"Módulo {module_candidate_id} não pertence ao projeto {project_id} "
            f"ou não existe"
        )

    # Título canônico: "<prefixo RF/RNF/BR>-<id curto> — nome".
    prefix = {
        "functional": "RF", "non_functional": "RNF",
        "business_rule": "BR",
    }.get(mod.requirement_category, "REQ")
    short = str(mod.id)[:8]
    title = f"{prefix}-{short} — {mod.name}"

    # Descrição em markdown com rastreabilidade ao GCA.
    description = (
        f"**Origem**: GCA · módulo `{mod.id}`\n\n"
        f"**Tipo**: `{mod.module_type}` · **Prioridade**: `{mod.priority}` · "
        f"**Status GCA**: `{mod.status}`\n\n"
        f"{mod.description or '_(sem descrição)_'}\n\n"
        f"---\n"
        f"_Issue criada automaticamente pelo GCA ao aprovar o módulo. "
        f"Atualizações de status são sincronizadas via webhook._"
    )

    # Priority canônica a partir do módulo (se mapeável).
    priority_map = {"high": "high", "medium": "medium", "low": "low"}
    priority = priority_map.get(mod.priority)

    payload = await adapter.create_issue(
        config,
        title=title,
        description_markdown=description,
        priority=priority,  # type: ignore[arg-type]
        labels=[f"gca", f"type-{mod.module_type}"],
    )

    issue = await upsert_from_payload(
        db, project_id=project_id, provider=provider,
        module_candidate_id=module_candidate_id,
        payload=payload, created_by=actor_id,
    )

    # Audit.
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEvents.EXTERNAL_ISSUE_CREATED,
        resource_type="external_issue",
        actor_id=actor_id,
        resource_id=issue.id,
        details={
            "project_id": str(project_id),
            "module_candidate_id": str(module_candidate_id),
            "provider": provider,
            "external_id": payload.external_id,
            "url": payload.url,
        },
    )

    logger.info(
        "issue_tracker.created_from_module",
        project_id=str(project_id),
        module_id=str(module_candidate_id),
        provider=provider,
        external_id=payload.external_id,
    )
    return issue


async def apply_webhook_event(
    db: AsyncSession,
    *,
    provider: str,
    config,  # ProviderConfig
    headers: dict[str, str],
    raw_body: bytes,
    payload: dict,
) -> Optional[ExternalIssue]:
    """Processa webhook recebido do provider.

    Fluxo:
      1. Adapter valida assinatura (verify_webhook) — se falhar, retorna None.
      2. Adapter normaliza em IssueEvent (parse_webhook).
      3. Service resolve project_id do evento e aplica upsert idempotente.
      4. Emite EXTERNAL_ISSUE_STATUS_SYNCED no audit.

    Retorna a row de ExternalIssue atualizada, ou None quando:
      - Assinatura inválida (caller responde 401).
      - Evento não-relevante (parse_webhook retornou None).
      - Issue deletada externamente (marcamos cancelled e retornamos).
    """
    from app.services.audit_service import AuditEvents, AuditService

    adapter = resolve_adapter(provider)

    if not adapter.verify_webhook(config, headers, raw_body):
        logger.warning("issue_tracker.webhook.invalid_signature",
                        provider=provider)
        return None

    event = adapter.parse_webhook(config, payload)
    if event is None:
        return None

    project_id = UUID(event.project_id)

    if event.event_type == "issue_deleted":
        # Marca como cancelled preservando auditabilidade (não deletamos).
        existing = await get_external_issue_by_external_id(
            db, project_id, provider, event.external_id,
        )
        if existing is not None:
            existing.status_canonical = "cancelled"
            existing.status_raw = "deleted-externally"
            existing.synced_at = datetime.now(timezone.utc)
            existing.closed_at = existing.closed_at or datetime.now(timezone.utc)
            await db.flush()
        return existing

    # Busca estado real via adapter pra ter payload completo
    # (webhook costuma ter dados parciais).
    try:
        current = await adapter.get_issue(config, event.external_id)
    except Exception as exc:
        logger.warning("issue_tracker.webhook.get_issue_failed",
                        provider=provider,
                        external_id=event.external_id,
                        error=str(exc))
        # Fallback: usa dados do próprio webhook.
        from app.services.ports.issue_tracker_port import IssuePayload
        current = IssuePayload(
            external_id=event.external_id,
            url=None,
            title=event.title or "(título não disponível)",
            status_canonical=event.status_canonical or "todo",
            status_raw=event.status_raw or "",
        )

    issue = await upsert_from_payload(
        db, project_id=project_id, provider=provider,
        module_candidate_id=None,  # mantém vínculo preexistente se houver
        payload=current,
    )

    # Audit.
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEvents.EXTERNAL_ISSUE_STATUS_SYNCED,
        resource_type="external_issue",
        actor_id=None,  # ação veio do provider, não de um usuário humano
        resource_id=issue.id,
        details={
            "project_id": str(project_id),
            "provider": provider,
            "external_id": event.external_id,
            "status_canonical": current.status_canonical,
            "status_raw": current.status_raw,
            "event_type": event.event_type,
        },
    )
    return issue
