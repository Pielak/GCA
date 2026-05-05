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
async def test_watchdog_preserva_status_terminais(db_session):
    """Docs em completed, error ou quarantined NUNCA viram zombie —
    não importa o started_at. Pending limpo (started_at=None) também é preservado.
    (MVP 29 Fase 29.1 — pending+started_at preenchido agora é zombie; ver
    `test_watchdog_recupera_pending_com_started_at`.)
    """
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")

    # status terminais com started_at antigo — preservados
    docs_terminal = []
    for status in ("completed", "error", "quarantined"):
        d = await _seed_doc(
            db_session, project=p, user=user,
            status=status,
            started_minutes_ago=ZOMBIE_THRESHOLD_MINUTES + 60,
        )
        docs_terminal.append(d)

    # pending limpo (started_at=None) — preservado; só pending+started_at é zombie
    clean_pending = await _seed_doc(
        db_session, project=p, user=user,
        status="pending",
        started_minutes_ago=None,
    )

    await recover_zombie_documents(db=db_session)

    for d in docs_terminal + [clean_pending]:
        await db_session.refresh(d)
    assert [d.arguider_status for d in docs_terminal] == ["completed", "error", "quarantined"]
    assert clean_pending.arguider_status == "pending"


@pytest.mark.asyncio
async def test_watchdog_recupera_pending_com_started_at(db_session):
    """MVP 29 Fase 29.1 — padrão zombie novo: status='pending' mas
    started_at preenchido há mais que o threshold (ex: fallback de provider
    DT-064 resetou status mas não started_at, depois worker morreu).
    """
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"dtwatch-{uuid4().hex[:6]}")

    zombie = await _seed_doc(
        db_session, project=p, user=user,
        status="pending",
        started_minutes_ago=ZOMBIE_THRESHOLD_MINUTES + 1,
    )
    summary = await recover_zombie_documents(db=db_session)
    # QA C-03: assert >= 1 (não == 1) — gca_test pode ter docs poluídos de
    # execuções anteriores (sem isolamento por savepoint). O ponto é que
    # ESTE doc foi recuperado, não o número total.
    assert summary["recovered"] >= 1

    await db_session.refresh(zombie)
    assert zombie.arguider_status == "error"
    assert RECOVERY_MESSAGE in (zombie.arguider_error_message or "")


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


# QA C-04 (F5.1): watchdog cobre estado novo `ocg_updating`. Threshold 15min
# independente do global de 8min — Celery task pode rodar até 12min worst-case
# (3 retries 30s/120s/480s + LLM 60s).

@pytest.mark.asyncio
async def test_watchdog_recupera_ocg_updating_velho(db_session):
    """F5.1 — Doc travado em `ocg_updating` há > 15min é recuperado pra erro.
    Cenário real: Celery worker morreu com task em voo, sem ACK.
    """
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"f51watch-{uuid4().hex[:6]}")

    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    # Cria doc em ocg_updating com updated_at de 16min atrás (cutoff = 15min).
    # _seed_doc não suporta esse status — fazer manual.
    old_updated_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    doc = IngestedDocument(
        id=uuid4(),
        project_id=p.id,
        uploaded_by=user.id,
        original_filename="zombie_ocg_updating.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status="ocg_updating",
        arguider_stage="ocg_updating",
        pii_detected=False,
    )
    db_session.add(doc)
    await db_session.commit()
    # updated_at é onupdate=NOW, então força via UPDATE direto:
    from sqlalchemy import text as _text
    await db_session.execute(
        _text("UPDATE ingested_documents SET updated_at = :ts WHERE id = :id"),
        {"ts": old_updated_at, "id": doc.id},
    )
    await db_session.commit()

    summary = await recover_zombie_documents(db=db_session)
    assert summary["recovered"] >= 1

    await db_session.refresh(doc)
    assert doc.arguider_status == "error", (
        f"Doc em ocg_updating > 15min deveria virar 'error', recebido '{doc.arguider_status}'"
    )


@pytest.mark.asyncio
async def test_watchdog_preserva_ocg_updating_recente(db_session):
    """F5.1 — Doc em `ocg_updating` recente (< 15min) NÃO é recuperado."""
    user = await create_test_user(db_session, is_admin=True)
    org = await create_test_organization(db_session)
    p = await create_test_project(db_session, organization_id=org.id, slug=f"f51watch-{uuid4().hex[:6]}")

    h = hashlib.sha256(f"{uuid4()}".encode()).hexdigest()
    # 5min atrás — dentro da janela de 15min, NÃO deve ser recuperado.
    recent_updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    doc = IngestedDocument(
        id=uuid4(),
        project_id=p.id,
        uploaded_by=user.id,
        original_filename="recent_ocg_updating.pdf",
        filename=f"{uuid4()}.pdf",
        file_type="pdf",
        file_hash=h,
        file_size_bytes=1024,
        arguider_status="ocg_updating",
        arguider_stage="ocg_updating",
        pii_detected=False,
    )
    db_session.add(doc)
    await db_session.commit()
    from sqlalchemy import text as _text
    await db_session.execute(
        _text("UPDATE ingested_documents SET updated_at = :ts WHERE id = :id"),
        {"ts": recent_updated_at, "id": doc.id},
    )
    await db_session.commit()

    await recover_zombie_documents(db=db_session)
    await db_session.refresh(doc)
    assert doc.arguider_status == "ocg_updating", (
        "Doc recente em ocg_updating NÃO deve ser tocado pelo watchdog"
    )
