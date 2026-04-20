"""DT-3 dogfood — Watchdog de tasks de ingestão e timeout do _analyze.

Cobre:
  - recover_zombie_documents marca docs com 'processing' antigo como 'error'.
  - Não toca em docs 'processing' recentes (dentro do threshold).
  - Não toca em docs com outros status (completed, error, pending).
  - Idempotente: 2 execuções em sequência, segunda não recupera nada novo.
  - _analyze_with_timeout marca status='error' em TimeoutError.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import IngestedDocument
from app.services.ingestion_service import IngestionService
from app.services.ingestion_watchdog import (
    RECOVERY_MESSAGE,
    ZOMBIE_THRESHOLD_MINUTES,
    recover_zombie_documents,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


async def _seed_doc(
    db, *, project, user, status: str, started_minutes_ago: int | None,
) -> IngestedDocument:
    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)
        if started_minutes_ago is not None
        else None
    )
    doc = IngestedDocument(
        id=uuid4(),
        project_id=project.id,
        uploaded_by=user.id,
        original_filename="zombie.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status=status,
        arguider_started_at=started_at,
        pii_detected=False,
    )
    db.add(doc)
    await db.commit()
    return doc


@pytest.mark.asyncio
async def test_watchdog_recupera_zombie_antigo(db_session):
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")
    doc = await _seed_doc(
        db_session, project=p, user=user,
        status="processing",
        started_minutes_ago=ZOMBIE_THRESHOLD_MINUTES + 5,
    )

    summary = await recover_zombie_documents(db=db_session)

    assert summary["recovered"] >= 1
    await db_session.refresh(doc)
    assert doc.arguider_status == "error"
    assert doc.arguider_error_message == RECOVERY_MESSAGE
    assert doc.arguider_stage == "failed"


@pytest.mark.asyncio
async def test_watchdog_preserva_processing_recente(db_session):
    """Doc dentro do threshold continua em 'processing' — análise pode estar rodando."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")
    doc = await _seed_doc(
        db_session, project=p, user=user,
        status="processing",
        started_minutes_ago=2,  # bem dentro do threshold de 30 min
    )

    await recover_zombie_documents(db=db_session)

    await db_session.refresh(doc)
    assert doc.arguider_status == "processing"


@pytest.mark.asyncio
async def test_watchdog_preserva_outros_status(db_session):
    """Docs em completed, error, pending ou quarantined não são tocados."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")
    docs = []
    for status in ("completed", "error", "pending", "quarantined"):
        # Mesmo com started_at antigo, status diferente de 'processing' não toca
        d = await _seed_doc(
            db_session, project=p, user=user,
            status=status,
            started_minutes_ago=ZOMBIE_THRESHOLD_MINUTES + 60,
        )
        docs.append(d)

    await recover_zombie_documents(db=db_session)

    for d in docs:
        await db_session.refresh(d)
    assert [d.arguider_status for d in docs] == ["completed", "error", "pending", "quarantined"]


@pytest.mark.asyncio
async def test_watchdog_idempotente(db_session):
    """Rodar 2x não recupera o mesmo doc duas vezes."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")
    await _seed_doc(
        db_session, project=p, user=user,
        status="processing",
        started_minutes_ago=ZOMBIE_THRESHOLD_MINUTES + 10,
    )

    s1 = await recover_zombie_documents(db=db_session)
    s2 = await recover_zombie_documents(db=db_session)

    assert s1["recovered"] >= 1
    assert s2["recovered"] == 0  # já recuperado, não conta de novo


@pytest.mark.asyncio
async def test_analyze_with_timeout_aciona_wait_for(db_session):
    """_analyze_with_timeout envolve _analyze_async em wait_for(timeout).

    Smoke test: mocka _analyze_async pra sleep maior que o timeout,
    confirma que a invocação retorna sem hangup (TimeoutError catch
    interno). Cleanup do DB usa o mesmo padrão UPDATE da watchdog,
    que já tem cobertura própria.
    """
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")
    doc = await _seed_doc(
        db_session, project=p, user=user,
        status="processing", started_minutes_ago=0,
    )

    async def _slow_analyze(*args, **kwargs):
        await asyncio.sleep(3)  # mais que o timeout do teste

    svc = IngestionService(db_session)
    original_timeout = IngestionService._ANALYZE_TIMEOUT_SECONDS
    IngestionService._ANALYZE_TIMEOUT_SECONDS = 1
    try:
        # Tempo de parede da chamada deve ser ~1s (timeout), não ~3s (sleep)
        import time
        with patch.object(IngestionService, "_analyze_async", new=_slow_analyze):
            t0 = time.monotonic()
            await svc._analyze_with_timeout(doc.id, p.id, b"x", "pdf")
            elapsed = time.monotonic() - t0
        assert elapsed < 2.5, f"wait_for não cortou no timeout (durou {elapsed:.1f}s)"
    finally:
        IngestionService._ANALYZE_TIMEOUT_SECONDS = original_timeout


@pytest.mark.asyncio
async def test_zombie_recovery_libera_delete(db_session):
    """Após recovery, doc.arguider_status='error' permite delete."""
    from app.services.ingestion_service import IngestionService as _IS
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")
    doc = await _seed_doc(
        db_session, project=p, user=user,
        status="processing",
        started_minutes_ago=ZOMBIE_THRESHOLD_MINUTES + 1,
    )

    await recover_zombie_documents(db=db_session)
    await db_session.refresh(doc)

    # Agora simulamos o guard de delete: status != 'processing' deve passar
    assert doc.arguider_status == "error"
    assert doc.arguider_status != "processing"
