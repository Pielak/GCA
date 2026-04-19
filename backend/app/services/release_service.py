"""MVP 7 — service de entrega versionada preservando dados do usuário.

Fluxo:
  1. Cada release vive em backend/releases/<tag>.yaml (shipada com código).
  2. Ao startup, load_declared_releases lê todos os YAMLs e, pra cada
     tag ainda não presente na tabela `releases`, cria registro em
     status='pending'.
  3. apply_nondestructive_pending varre pending is_destructive=False
     e marca applied (sem pedir permissão) — migrations SQL reais já
     rodam antes do startup via docker-compose; a release só documenta.
  4. Releases destrutivas ficam pending até Admin chamar apply_release
     manualmente (Fase 2 — snapshot + migrations + applied).

Rastreabilidade ticket → release: release_items referencia tickets,
MVPs, DTs. Cada item tem affected_roles que o frontend usa pra
segmentar changelog.

Auditoria: cada aplicação gera entrada em release_application_log e
em audit_log_global (via audit_service).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Release, ReleaseApplicationLog, ReleaseItem


RELEASES_DIR = Path("/app/releases")  # montado em backend/releases via docker-compose
VALID_ROLES = {"admin", "gp", "dev", "tester", "qa", "all"}
VALID_KINDS = {"mvp", "mvp_emenda", "ticket", "feature", "fix", "schema_change"}


# ─── Parsing e validação de YAML declarado ────────────────────────────────

def _parse_release_yaml(path: Path) -> dict:
    """Lê YAML + valida campos mínimos. Levanta ValueError em inconsistência."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: YAML deve ser um objeto de topo.")

    tag = data.get("tag")
    title = data.get("title")
    if not tag or not isinstance(tag, str):
        raise ValueError(f"{path.name}: campo 'tag' obrigatório.")
    if not title or not isinstance(title, str):
        raise ValueError(f"{path.name}: campo 'title' obrigatório.")

    items = data.get("items") or []
    if not isinstance(items, list):
        raise ValueError(f"{path.name}: 'items' deve ser lista.")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"{path.name}: items[{i}] deve ser objeto.")
        if it.get("kind") not in VALID_KINDS:
            raise ValueError(f"{path.name}: items[{i}].kind inválido: {it.get('kind')}")
        if not it.get("title"):
            raise ValueError(f"{path.name}: items[{i}].title obrigatório.")
        roles = it.get("affected_roles", ["all"])
        if not isinstance(roles, list) or not all(r in VALID_ROLES for r in roles):
            raise ValueError(f"{path.name}: items[{i}].affected_roles inválido.")

    return {
        "tag": tag,
        "title": title,
        "body": data.get("body"),
        "is_destructive": bool(data.get("is_destructive", False)),
        "items": items,
        "source_yaml": path.name,
    }


def load_declared_releases(releases_dir: Optional[Path] = None) -> list[dict]:
    """Lê todos os backend/releases/*.yaml como dicts validados.
    Ordenação por tag (string) — releases devem usar semver."""
    d = releases_dir or RELEASES_DIR
    if not d.exists():
        return []
    out = []
    for yml in sorted(d.glob("*.yaml")):
        try:
            out.append(_parse_release_yaml(yml))
        except (yaml.YAMLError, ValueError) as e:
            # Log e continua — release inválida não derruba o startup.
            import structlog
            structlog.get_logger(__name__).error(
                "release.yaml_invalid", path=str(yml), error=str(e),
            )
    return out


# ─── Sync do YAML declarado com tabela releases ──────────────────────────

async def sync_declared_releases(db: AsyncSession, releases_dir: Optional[Path] = None) -> list[Release]:
    """Pra cada tag declarada no YAML que ainda não está em `releases`,
    cria em status='pending'. Retorna a lista de releases recém-criadas."""
    declared = load_declared_releases(releases_dir)
    if not declared:
        return []

    existing_tags = {
        r for r in (await db.execute(select(Release.tag))).scalars().all()
    }

    created: list[Release] = []
    for d in declared:
        if d["tag"] in existing_tags:
            continue
        rel = Release(
            tag=d["tag"],
            title=d["title"],
            body=d.get("body"),
            is_destructive=d["is_destructive"],
            status="pending",
            source_yaml=d["source_yaml"],
        )
        db.add(rel)
        await db.flush()

        for idx, it in enumerate(d.get("items", [])):
            db.add(ReleaseItem(
                release_id=rel.id,
                kind=it["kind"],
                ref_id=it.get("ref_id"),
                title=it["title"],
                description=it.get("description"),
                affected_roles=json.dumps(it.get("affected_roles", ["all"])),
                display_order=idx,
            ))
        created.append(rel)

    if created:
        await db.commit()
    return created


# ─── Aplicação de releases ────────────────────────────────────────────────

async def apply_nondestructive_pending(db: AsyncSession) -> list[Release]:
    """Aplica automaticamente releases is_destructive=False em status=pending.

    Chamado no startup (lifespan hook). As migrations SQL reais já
    correm via `upgrade.sh` / docker entrypoint antes do backend subir;
    este método só marca a release como aplicada pra dar entrada no
    changelog + registra event_log.
    """
    pending = (await db.execute(
        select(Release).where(
            Release.status == "pending",
            Release.is_destructive.is_(False),
        ).order_by(Release.declared_at.asc())
    )).scalars().all()

    applied: list[Release] = []
    now = datetime.now(timezone.utc)
    for r in pending:
        r.status = "applied"
        r.applied_at = now
        # applied_by = None → auto-aplicada pelo sistema (não há ator)
        db.add(ReleaseApplicationLog(
            release_id=r.id,
            event_type="applied",
            metadata_json=json.dumps({"trigger": "startup_auto", "destructive": False}),
        ))
        applied.append(r)

    if applied:
        await db.commit()
    return applied


async def apply_destructive_release(
    db: AsyncSession,
    *,
    release_id: UUID,
    actor_id: UUID,
    snapshots: Optional[list[dict]] = None,
) -> Release:
    """Aplica release destrutiva (triggerada manualmente por Admin na F2).

    Pré-condição: caller já disparou snapshots DT-063 e passa a lista
    (snapshot_id + project_id) pra registrar no log.
    """
    rel = (await db.execute(
        select(Release).where(Release.id == release_id)
    )).scalar_one_or_none()
    if not rel:
        raise ValueError("Release não encontrada.")
    if rel.status != "pending":
        raise ValueError(f"Release não está pending (status={rel.status}).")
    if not rel.is_destructive:
        raise ValueError("Use apply_nondestructive_pending para releases não-destrutivas.")

    # Registrar snapshots no log
    if snapshots:
        for s in snapshots:
            db.add(ReleaseApplicationLog(
                release_id=rel.id,
                event_type="snapshot_taken",
                project_id=s.get("project_id"),
                actor_id=actor_id,
                metadata_json=json.dumps({"snapshot_id": str(s.get("snapshot_id"))}),
            ))

    rel.status = "applied"
    rel.applied_at = datetime.now(timezone.utc)
    rel.applied_by = actor_id

    db.add(ReleaseApplicationLog(
        release_id=rel.id,
        event_type="applied",
        actor_id=actor_id,
        metadata_json=json.dumps({
            "trigger": "admin_manual",
            "destructive": True,
            "snapshot_count": len(snapshots or []),
        }),
    ))

    await db.commit()
    await db.refresh(rel)
    return rel


async def mark_rollback(
    db: AsyncSession,
    *,
    release_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    snapshot_id: Optional[UUID] = None,
) -> None:
    """Registra rollback de um projeto via snapshot pré-release.
    Não altera status da release — rollback é por-projeto."""
    rel = (await db.execute(
        select(Release).where(Release.id == release_id)
    )).scalar_one_or_none()
    if not rel:
        raise ValueError("Release não encontrada.")

    db.add(ReleaseApplicationLog(
        release_id=rel.id,
        event_type="rolled_back",
        project_id=project_id,
        actor_id=actor_id,
        metadata_json=json.dumps({"snapshot_id": str(snapshot_id) if snapshot_id else None}),
    ))
    await db.commit()


# ─── Leitura ──────────────────────────────────────────────────────────────

async def list_releases(
    db: AsyncSession,
    *,
    status_filter: Optional[str] = None,
) -> list[Release]:
    q = select(Release).order_by(Release.declared_at.desc())
    if status_filter:
        q = q.where(Release.status == status_filter)
    return list((await db.execute(q)).scalars().all())


async def get_release_with_items(
    db: AsyncSession, release_id: UUID
) -> tuple[Release, list[ReleaseItem]]:
    rel = (await db.execute(
        select(Release).where(Release.id == release_id)
    )).scalar_one_or_none()
    if not rel:
        raise ValueError("Release não encontrada.")
    items = list((await db.execute(
        select(ReleaseItem)
        .where(ReleaseItem.release_id == release_id)
        .order_by(ReleaseItem.display_order.asc())
    )).scalars().all())
    return rel, items


async def get_application_log(
    db: AsyncSession, release_id: UUID
) -> list[ReleaseApplicationLog]:
    return list((await db.execute(
        select(ReleaseApplicationLog)
        .where(ReleaseApplicationLog.release_id == release_id)
        .order_by(ReleaseApplicationLog.created_at.asc())
    )).scalars().all())


def items_visible_to_role(items: Iterable[ReleaseItem], role: str) -> list[ReleaseItem]:
    """Filtra itens cuja affected_roles inclui 'all' ou o papel requerido."""
    out = []
    for it in items:
        try:
            roles = json.loads(it.affected_roles or "[]")
        except (ValueError, TypeError):
            roles = []
        if "all" in roles or role in roles:
            out.append(it)
    return out
