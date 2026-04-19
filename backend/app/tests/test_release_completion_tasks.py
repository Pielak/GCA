"""MVP 7 Fase 4 — testes rápidos de ReleaseCompletionTask.

Cobertura mínima: schema funciona, insert/read OK, status transita
pra done com completed_at/by. Endpoint end-to-end é coberto via smoke
manual — aqui só o modelo + flow de marcação.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import Release, ReleaseApplicationLog, ReleaseCompletionTask
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


async def _seed_release(db, *, destructive=True, tag=None) -> Release:
    r = Release(
        tag=tag or f"v9.9.9-{uuid4().hex[:6]}",
        title="Destrutiva teste completion",
        is_destructive=destructive,
        status="pending",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@pytest.mark.asyncio
async def test_completion_task_insert_and_read(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="rel-task-1")
    rel = await _seed_release(db_session)

    t = ReleaseCompletionTask(
        release_id=rel.id,
        project_id=project.id,
        kind="questionnaire_field",
        title="Preencha campo novo",
        description="O release adicionou campo X ao questionário",
        payload='{"field":"X"}',
        status="pending",
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)

    found = (await db_session.execute(
        select(ReleaseCompletionTask).where(ReleaseCompletionTask.id == t.id)
    )).scalar_one()
    assert found.status == "pending"
    assert found.payload == '{"field":"X"}'


@pytest.mark.asyncio
async def test_completion_task_mark_done(db_session):
    org = await create_test_organization(db_session)
    project = await create_test_project(db_session, organization_id=org.id, slug="rel-task-2")
    rel = await _seed_release(db_session)
    actor = await create_test_user(db_session, is_admin=True)

    t = ReleaseCompletionTask(
        release_id=rel.id,
        project_id=project.id,
        kind="ocg_field",
        title="T",
        status="pending",
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)

    # Simula o que o endpoint faz
    t.status = "done"
    t.completed_at = datetime.now(timezone.utc)
    t.completed_by = actor.id
    db_session.add(ReleaseApplicationLog(
        release_id=rel.id,
        event_type="completion_task_fulfilled",
        project_id=project.id,
        actor_id=actor.id,
    ))
    await db_session.commit()
    await db_session.refresh(t)

    assert t.status == "done"
    assert t.completed_by == actor.id
    assert t.completed_at is not None

    logs = (await db_session.execute(
        select(ReleaseApplicationLog).where(
            ReleaseApplicationLog.release_id == rel.id,
            ReleaseApplicationLog.event_type == "completion_task_fulfilled",
        )
    )).scalars().all()
    assert len(logs) == 1
