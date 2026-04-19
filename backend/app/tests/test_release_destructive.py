"""MVP 7 Fase 2 — testes da aplicação destrutiva + rollback por projeto.

Cobertura:
- apply_destructive_release: valida pending + is_destructive; rejeita
  não-destrutiva; registra snapshots + 'applied' no log
- apply_destructive_release sem snapshots (caller pode optar)
- mark_rollback registra evento por projeto sem alterar status da release
- Erro quando release não existe / não está pending

A integração real com DT-063 (project_backup_service) é validada no
smoke endpoint-a-endpoint do router; aqui o service é testado de
forma isolada.
"""
from uuid import uuid4

import json as _json
import pytest
from sqlalchemy import select

from app.models.base import Release, ReleaseApplicationLog
from app.services import release_service as svc
from app.tests.factories import create_test_organization, create_test_project, create_test_user


async def _seed_pending_release(db, *, is_destructive: bool, tag: str = None) -> Release:
    rel = Release(
        tag=tag or f"v9.9-{uuid4().hex[:6]}",
        title="Destrutiva teste",
        is_destructive=is_destructive,
        status="pending",
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel


@pytest.mark.asyncio
async def test_apply_destructive_registers_snapshots_and_marks_applied(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    rel = await _seed_pending_release(db_session, is_destructive=True)
    org = await create_test_organization(db_session)
    p1 = await create_test_project(db_session, organization_id=org.id, slug="rel-dest-p1")
    p2 = await create_test_project(db_session, organization_id=org.id, slug="rel-dest-p2")

    # Simula snapshots (Fase 2 router cria via backup_svc; aqui testamos
    # só o release_service recebendo os ids prontos; snapshot_id aleatório
    # é ok pq não há FK pra ProjectBackup)
    snaps = [
        {"project_id": p1.id, "snapshot_id": uuid4()},
        {"project_id": p2.id, "snapshot_id": uuid4()},
    ]
    applied = await svc.apply_destructive_release(
        db_session, release_id=rel.id, actor_id=actor.id, snapshots=snaps,
    )
    assert applied.status == "applied"
    assert applied.applied_by == actor.id
    assert applied.applied_at is not None

    logs = (await db_session.execute(
        select(ReleaseApplicationLog).where(ReleaseApplicationLog.release_id == rel.id)
    )).scalars().all()
    events = [l.event_type for l in logs]
    # 2 snapshot_taken + 1 applied
    assert events.count("snapshot_taken") == 2
    assert events.count("applied") == 1

    applied_log = next(l for l in logs if l.event_type == "applied")
    meta = _json.loads(applied_log.metadata_json or "{}")
    assert meta.get("trigger") == "admin_manual"
    assert meta.get("destructive") is True
    assert meta.get("snapshot_count") == 2


@pytest.mark.asyncio
async def test_apply_destructive_rejects_non_destructive(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    rel = await _seed_pending_release(db_session, is_destructive=False)
    with pytest.raises(ValueError, match="não-destrutivas"):
        await svc.apply_destructive_release(
            db_session, release_id=rel.id, actor_id=actor.id, snapshots=[],
        )


@pytest.mark.asyncio
async def test_apply_destructive_rejects_non_pending(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    rel = await _seed_pending_release(db_session, is_destructive=True)
    rel.status = "applied"
    await db_session.commit()

    with pytest.raises(ValueError, match="pending"):
        await svc.apply_destructive_release(
            db_session, release_id=rel.id, actor_id=actor.id, snapshots=[],
        )


@pytest.mark.asyncio
async def test_apply_destructive_not_found(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    with pytest.raises(ValueError, match="não encontrada"):
        await svc.apply_destructive_release(
            db_session, release_id=uuid4(), actor_id=actor.id, snapshots=[],
        )


@pytest.mark.asyncio
async def test_apply_destructive_no_snapshots(db_session):
    """Permitido passar snapshots=[] (ex: admin optou por não snapshotar).
    Release aplica, mas log só terá 'applied'."""
    actor = await create_test_user(db_session, is_admin=True)
    rel = await _seed_pending_release(db_session, is_destructive=True)
    await svc.apply_destructive_release(
        db_session, release_id=rel.id, actor_id=actor.id, snapshots=[],
    )
    logs = (await db_session.execute(
        select(ReleaseApplicationLog).where(ReleaseApplicationLog.release_id == rel.id)
    )).scalars().all()
    events = [l.event_type for l in logs]
    assert "snapshot_taken" not in events
    assert events.count("applied") == 1


@pytest.mark.asyncio
async def test_mark_rollback_registers_event_without_changing_status(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="rel-rb")
    rel = await _seed_pending_release(db_session, is_destructive=True)
    rel.status = "applied"
    await db_session.commit()

    snapshot_id = uuid4()
    await svc.mark_rollback(
        db_session, release_id=rel.id, project_id=project.id,
        actor_id=actor.id, snapshot_id=snapshot_id,
    )

    refreshed = (await db_session.execute(
        select(Release).where(Release.id == rel.id)
    )).scalar_one()
    assert refreshed.status == "applied"  # status global NÃO muda

    logs = (await db_session.execute(
        select(ReleaseApplicationLog).where(
            ReleaseApplicationLog.release_id == rel.id,
            ReleaseApplicationLog.event_type == "rolled_back",
        )
    )).scalars().all()
    assert len(logs) == 1
    assert logs[0].project_id == project.id
    meta = _json.loads(logs[0].metadata_json or "{}")
    assert meta.get("snapshot_id") == str(snapshot_id)


@pytest.mark.asyncio
async def test_mark_rollback_release_not_found(db_session):
    actor = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="rel-rb2")
    with pytest.raises(ValueError, match="não encontrada"):
        await svc.mark_rollback(
            db_session, release_id=uuid4(), project_id=project.id,
            actor_id=actor.id, snapshot_id=uuid4(),
        )
