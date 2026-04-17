"""Testes de contração de OCG ao deletar documento (MVP 2 §7).

Verifica `IngestionService._contract_ocg_for_deleted_document`:
- doc sem deltas → no-op
- doc com deltas → reverte campos ao valor antigo e grava delta de
  `trigger_source='document_removal'`
- campo posteriormente tocado por outro delta → fica em `fields_skipped`
  (não é revertido, preserva contribuição posterior)
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    IngestedDocument, Organization, Project, Questionnaire, User, OCG, OCGDeltaLog,
)
from app.services.ingestion_service import IngestionService

pytestmark = pytest.mark.asyncio


async def _seed_project(db: AsyncSession, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Retorna (project_id, user_id) — user é reusado para uploaded_by dos docs."""
    user = User(
        id=uuid.uuid4(),
        email=f"{slug}@test.local",
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
    return proj.id, user.id


async def _seed_doc(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    doc = IngestedDocument(
        id=uuid.uuid4(),
        project_id=project_id,
        filename=f"{uuid.uuid4().hex}.md",
        original_filename="x.md",
        file_type="markdown",
        file_hash=uuid.uuid4().hex,
        file_size_bytes=10,
        uploaded_by=user_id,
        arguider_status="completed",
    )
    db.add(doc)
    await db.flush()
    return doc.id


async def _seed_ocg(db: AsyncSession, project_id: uuid.UUID, data: dict, version: int = 1):
    q = Questionnaire(
        id=uuid.uuid4(),
        project_id=project_id,
        gp_email="seed@test.local",
        responses=json.dumps({"1": "seed"}),
        status="ok",
    )
    db.add(q)
    await db.flush()
    ocg = OCG(
        id=uuid.uuid4(),
        questionnaire_id=q.id,
        project_id=project_id,
        version=version,
        ocg_data=json.dumps(data, ensure_ascii=False),
    )
    db.add(ocg)
    await db.flush()
    return ocg


async def _seed_delta(
    db: AsyncSession,
    project_id: uuid.UUID,
    document_id: uuid.UUID | None,
    fields_changed: dict,
    version_to: int,
    created_at: datetime | None = None,
):
    delta = OCGDeltaLog(
        id=uuid.uuid4(),
        project_id=project_id,
        document_id=document_id,
        ocg_version_from=version_to - 1,
        ocg_version_to=version_to,
        fields_changed=json.dumps(fields_changed, ensure_ascii=False),
        trigger_source="document_ingestion",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(delta)
    await db.flush()
    return delta


async def test_contraction_noop_when_doc_has_no_deltas(db_session: AsyncSession):
    project_id, user_id = await _seed_project(db_session, "nodeltas")
    doc_id = await _seed_doc(db_session, project_id, user_id)

    service = IngestionService(db_session)
    result = await service._contract_ocg_for_deleted_document(project_id, doc_id)

    assert result == {"fields_reverted": [], "fields_skipped": []}


async def test_contraction_reverts_field_when_no_later_delta(db_session: AsyncSession):
    project_id, user_id = await _seed_project(db_session, "revert")
    doc_id = await _seed_doc(db_session, project_id, user_id)
    await _seed_ocg(db_session, project_id, {"stack": "FastAPI"}, version=2)
    await _seed_delta(
        db_session, project_id, doc_id,
        fields_changed={"stack": {"old": None, "new": "FastAPI"}},
        version_to=2,
    )

    service = IngestionService(db_session)
    result = await service._contract_ocg_for_deleted_document(project_id, doc_id)

    assert "stack" in result["fields_reverted"]
    assert result["fields_skipped"] == []
    assert result["version_from"] == 2
    assert result["version_to"] == 3


async def test_contraction_skips_field_touched_by_later_delta(db_session: AsyncSession):
    project_id, user_id = await _seed_project(db_session, "skip")
    doc_a = await _seed_doc(db_session, project_id, user_id)
    doc_b = await _seed_doc(db_session, project_id, user_id)
    await _seed_ocg(db_session, project_id, {"stack": "Spring Boot"}, version=3)

    now = datetime.now(timezone.utc)
    # doc A introduziu "FastAPI"
    await _seed_delta(
        db_session, project_id, doc_a,
        fields_changed={"stack": {"old": None, "new": "FastAPI"}},
        version_to=2,
        created_at=now - timedelta(minutes=10),
    )
    # doc B (posterior) mudou para "Spring Boot"
    await _seed_delta(
        db_session, project_id, doc_b,
        fields_changed={"stack": {"old": "FastAPI", "new": "Spring Boot"}},
        version_to=3,
        created_at=now - timedelta(minutes=5),
    )

    service = IngestionService(db_session)
    result = await service._contract_ocg_for_deleted_document(project_id, doc_a)

    # Campo tocado posteriormente por doc B — não reverte.
    assert "stack" in result["fields_skipped"]
    assert result["fields_reverted"] == []


async def test_contraction_records_removal_delta(db_session: AsyncSession):
    project_id, user_id = await _seed_project(db_session, "delta_log")
    doc_id = await _seed_doc(db_session, project_id, user_id)
    await _seed_ocg(db_session, project_id, {"runtime": "python3.11"}, version=2)
    await _seed_delta(
        db_session, project_id, doc_id,
        fields_changed={"runtime": {"old": "python3.10", "new": "python3.11"}},
        version_to=2,
    )

    service = IngestionService(db_session)
    await service._contract_ocg_for_deleted_document(project_id, doc_id)
    await db_session.flush()

    # Um delta de document_removal foi adicionado
    from sqlalchemy import select
    result = await db_session.execute(
        select(OCGDeltaLog).where(
            OCGDeltaLog.project_id == project_id,
            OCGDeltaLog.trigger_source == "document_removal",
        )
    )
    removals = list(result.scalars().all())
    assert len(removals) == 1
    assert removals[0].document_id is None  # doc será deletado
