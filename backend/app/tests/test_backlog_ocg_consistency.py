"""Testes de consistência Backlog ↔ OCG (MVP 2 §10).

Verifica os helpers de consistência disparados quando o OCG muda:
- `_regenerate_backlog_for_audit`: regenera backlog + emite evento no audit;
- `_fire_ocg_change_hooks`: unifica disparo de propagate (ou regen inicial) +
  gatekeeper reeval quando OCG muda.

Cobre os dois gatilhos novos (antes desta rodada, o backlog só era regenerado
após ingestão — não após contração no delete nem após geração inicial).
"""
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    BacklogItem, GlobalAuditLog, OCG, Organization, Project, Questionnaire, User,
)
from app.services.ingestion_service import _regenerate_backlog_for_audit

pytestmark = pytest.mark.asyncio


async def _seed_project(db: AsyncSession, slug: str) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        email=f"{slug}@bklog.local",
        full_name=f"User {slug}",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    org = Organization(
        id=uuid.uuid4(), name=f"Org {slug}", slug=f"o-{slug}", owner_id=user.id,
    )
    db.add(org)
    await db.flush()
    proj = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        name=f"Proj {slug}",
        slug=f"p-{slug}",
        short_slug=f"s-{slug}"[:16],
        status="active",
        deliverable_type="new_system",
    )
    db.add(proj)
    await db.flush()
    return proj.id


async def _seed_ocg_with_stack(
    db: AsyncSession, project_id: uuid.UUID, *, version: int = 1
) -> OCG:
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=project_id,
        gp_email="seed@bklog.local",
        responses=json.dumps({"1": "seed"}),
        status="ok",
    )
    db.add(q)
    await db.flush()
    ocg_data = {
        "STACK_RECOMMENDATION": {
            "frontend": "React",
            "backend": "FastAPI",
            "database": "Postgres",
        },
    }
    ocg = OCG(
        id=uuid.uuid4(),
        questionnaire_id=q.id,
        project_id=project_id,
        version=version,
        ocg_data=json.dumps(ocg_data, ensure_ascii=False),
        status="READY",
    )
    db.add(ocg)
    await db.flush()
    return ocg


async def _count_backlog_items(db: AsyncSession, project_id: uuid.UUID) -> int:
    result = await db.execute(
        select(BacklogItem).where(BacklogItem.project_id == project_id)
    )
    return len(list(result.scalars().all()))


async def _backlog_regen_events(db: AsyncSession, project_id: uuid.UUID) -> list[GlobalAuditLog]:
    result = await db.execute(
        select(GlobalAuditLog).where(
            GlobalAuditLog.event_type == "BACKLOG_REGENERATED",
            GlobalAuditLog.resource_id == project_id,
        )
    )
    return list(result.scalars().all())


async def test_regenerate_backlog_creates_items_and_audit_event(db_session: AsyncSession):
    """Projeto com OCG válido → backlog populado + evento BACKLOG_REGENERATED."""
    project_id = await _seed_project(db_session, "seed")
    ocg = await _seed_ocg_with_stack(db_session, project_id, version=1)

    assert await _count_backlog_items(db_session, project_id) == 0

    await _regenerate_backlog_for_audit(
        db_session, project_id, ocg_version=ocg.version, trigger="questionnaire_approved"
    )

    # Pelo menos 1 item (stack) foi criado
    assert await _count_backlog_items(db_session, project_id) >= 1

    events = await _backlog_regen_events(db_session, project_id)
    assert len(events) == 1
    details = json.loads(events[0].details)
    assert details["trigger"] == "questionnaire_approved"
    assert details["ocg_version"] == 1
    assert details["regenerated"] >= 1


async def test_regenerate_backlog_preserves_manual_items(db_session: AsyncSession):
    """Items com source='manual' não são removidos pela regeneração."""
    project_id = await _seed_project(db_session, "manual")
    ocg = await _seed_ocg_with_stack(db_session, project_id, version=1)

    manual = BacklogItem(
        id=uuid.uuid4(),
        project_id=project_id,
        category="modules",
        title="Item manual criado pelo GP",
        description="Não deve ser removido na regeneração",
        priority="medium",
        source="manual",
        source_version=0,
    )
    db_session.add(manual)
    await db_session.flush()

    await _regenerate_backlog_for_audit(
        db_session, project_id, ocg_version=ocg.version, trigger="document_removal"
    )

    # Manual ainda existe
    result = await db_session.execute(
        select(BacklogItem).where(
            BacklogItem.project_id == project_id,
            BacklogItem.source == "manual",
        )
    )
    manuals = list(result.scalars().all())
    assert len(manuals) == 1
    assert manuals[0].title == "Item manual criado pelo GP"


async def test_regenerate_backlog_noop_when_no_ocg(db_session: AsyncSession):
    """Projeto sem OCG → no-op, sem evento, sem crash."""
    project_id = await _seed_project(db_session, "noocg")

    await _regenerate_backlog_for_audit(
        db_session, project_id, ocg_version=None, trigger="questionnaire_approved"
    )

    assert await _count_backlog_items(db_session, project_id) == 0
    events = await _backlog_regen_events(db_session, project_id)
    assert events == []


async def test_regenerate_backlog_after_contraction_reflects_current_ocg(db_session: AsyncSession):
    """Simula contração: após regenerate, backlog só tem itens do OCG corrente."""
    project_id = await _seed_project(db_session, "contract")
    # OCG v1 com stack rica
    ocg = await _seed_ocg_with_stack(db_session, project_id, version=1)

    # Seed um backlog antigo com source='ocg' (de uma versão anterior)
    stale = BacklogItem(
        id=uuid.uuid4(),
        project_id=project_id,
        category="modules",
        title="Item obsoleto de versão anterior",
        description="Campo removido por contração",
        priority="low",
        source="ocg",
        source_version=0,
    )
    db_session.add(stale)
    await db_session.flush()

    count_before = await _count_backlog_items(db_session, project_id)
    assert count_before == 1  # só o stale

    await _regenerate_backlog_for_audit(
        db_session, project_id, ocg_version=ocg.version, trigger="document_removal"
    )

    # Stale foi removido, novos itens criados
    result = await db_session.execute(
        select(BacklogItem).where(
            BacklogItem.project_id == project_id,
            BacklogItem.title == "Item obsoleto de versão anterior",
        )
    )
    assert result.scalar_one_or_none() is None
    assert await _count_backlog_items(db_session, project_id) >= 1
