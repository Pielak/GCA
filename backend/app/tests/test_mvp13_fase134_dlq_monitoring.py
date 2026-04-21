"""MVP 13 Fase 13.4 — Testes + monitoring + retry policy + DLQ visibility.

Contrato §7 MVP 13 Fase 13.4:
- Retry policy bounded (já em place desde 13.1: max_retries + delay).
- Signal handlers capturam task_failure/task_retry/task_success via
  logs estruturados.
- DLQ visibility via `get_dlq_entries()` + endpoint admin
  `/admin/celery/dlq`.
- Endpoint admin `/admin/celery/workers` complementa `/health`.
"""
import httpx
import pytest

from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ─── Signal handlers ──────────────────────────────────────────────────


def test_get_dlq_entries_comeca_vazia():
    from app.celery_app import _DLQ_LOG_ENTRIES, get_dlq_entries
    # Limpa qualquer resquício de outro teste
    _DLQ_LOG_ENTRIES.clear()
    assert get_dlq_entries() == []


def test_on_task_failure_grava_entrada_com_campos_canonicos():
    """Quando signal task_failure é emitido, DLQ ganha entry estruturada."""
    from app.celery_app import _on_task_failure, _DLQ_LOG_ENTRIES, get_dlq_entries
    _DLQ_LOG_ENTRIES.clear()

    class FakeSender:
        name = "app.tasks.pipeline.fake_task"

    _on_task_failure(
        sender=FakeSender(),
        task_id="deadbeef-1234",
        exception=ValueError("boom"),
        args=["arg1", {"nested": "dict"}],
    )

    entries = get_dlq_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["task_id"] == "deadbeef-1234"
    assert e["task_name"] == "app.tasks.pipeline.fake_task"
    assert e["exception_type"] == "ValueError"
    assert e["exception_msg"] == "boom"
    assert len(e["args"]) == 2


def test_dlq_cap_em_200_entradas():
    """Handler não deixa lista crescer sem limite."""
    from app.celery_app import _on_task_failure, _DLQ_LOG_ENTRIES
    _DLQ_LOG_ENTRIES.clear()

    class FakeSender:
        name = "t"

    for i in range(250):
        _on_task_failure(
            sender=FakeSender(),
            task_id=f"tid-{i}",
            exception=RuntimeError(f"err{i}"),
            args=[],
        )

    assert len(_DLQ_LOG_ENTRIES) == 200
    # Mantém últimas — primeira deve ser a 50 (250-200).
    assert _DLQ_LOG_ENTRIES[0]["task_id"] == "tid-50"
    assert _DLQ_LOG_ENTRIES[-1]["task_id"] == "tid-249"


def test_get_dlq_entries_respeita_limit():
    from app.celery_app import _on_task_failure, _DLQ_LOG_ENTRIES, get_dlq_entries
    _DLQ_LOG_ENTRIES.clear()

    class FakeSender:
        name = "t"

    for i in range(10):
        _on_task_failure(
            sender=FakeSender(),
            task_id=f"id-{i}",
            exception=Exception(f"e{i}"),
            args=[],
        )

    recent = get_dlq_entries(limit=3)
    assert len(recent) == 3
    assert [e["task_id"] for e in recent] == ["id-7", "id-8", "id-9"]


# ─── Retry policy das tasks ───────────────────────────────────────────


@pytest.mark.parametrize("task_name,max_retries,delay", [
    ("app.tasks.pipeline.pipeline_ingest_task", 2, 30),
    ("app.tasks.pipeline.propagate_task", 2, 30),
    ("app.tasks.pipeline.regenerate_backlog_task", 2, 30),
    ("app.tasks.pipeline.reevaluate_gatekeeper_task", 2, 30),
    ("app.tasks.pipeline.auto_generate_task", 2, 30),
    ("app.tasks.pipeline.external_repo_fallback_task", 2, 60),
])
def test_retry_policy_bounded(task_name, max_retries, delay):
    import app.tasks.pipeline  # noqa: F401
    from app.celery_app import celery_app
    task = celery_app.tasks[task_name]
    assert task.max_retries == max_retries
    assert task.default_retry_delay == delay


def test_retry_infinito_proibido_contrato():
    """Contrato §7 MVP 13: retry infinito proibido, DLQ obrigatória."""
    import app.tasks.pipeline  # noqa: F401
    from app.celery_app import celery_app

    for name, task in celery_app.tasks.items():
        if name.startswith("app.tasks.pipeline."):
            assert task.max_retries is not None, f"{name} sem max_retries"
            assert task.max_retries <= 5, f"{name} max_retries={task.max_retries} excede limite saudável"


# ─── Endpoints admin ───────────────────────────────────────────────────


async def _create_admin() -> str:
    """Cria admin canário e retorna token."""
    from datetime import datetime
    from uuid import uuid4

    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    uid = uuid4()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(
                id=uid,
                email=f"mvp13-f134-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="F134 Admin",
                is_active=True, is_admin=True,
                created_at=datetime.utcnow(),
            ))
    return uid, create_access_token(data={"sub": str(uid)})


async def _cleanup_admin(uid):
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(User.__table__.delete().where(User.id == uid))


@pytest.mark.asyncio
async def test_admin_dlq_endpoint_retorna_estrutura_canonica():
    """GET /api/v1/admin/celery/dlq retorna {count, entries}."""
    from app.celery_app import _DLQ_LOG_ENTRIES, _on_task_failure

    uid, token = await _create_admin()
    try:
        # Popula 2 falhas
        _DLQ_LOG_ENTRIES.clear()

        class FakeSender:
            name = "app.tasks.pipeline.test_fail"

        _on_task_failure(sender=FakeSender(), task_id="a1", exception=ValueError("boom"), args=[])
        _on_task_failure(sender=FakeSender(), task_id="a2", exception=RuntimeError("dead"), args=[])

        async with _client() as client:
            resp = await client.get(
                "/api/v1/admin/celery/dlq?limit=10",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == 2
        assert len(body["entries"]) == 2
        assert body["entries"][0]["task_id"] == "a1"
        assert body["entries"][1]["exception_type"] == "RuntimeError"
    finally:
        await _cleanup_admin(uid)


@pytest.mark.asyncio
async def test_admin_workers_endpoint_retorna_broker_e_workers():
    uid, token = await _create_admin()
    try:
        async with _client() as client:
            resp = await client.get(
                "/api/v1/admin/celery/workers",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "broker" in body
        assert "workers" in body
        assert "reachable" in body["broker"]
        assert "workers" in body["workers"]
    finally:
        await _cleanup_admin(uid)


@pytest.mark.asyncio
async def test_admin_dlq_requer_admin():
    """Non-admin: 403 ou similar."""
    from datetime import datetime
    from uuid import uuid4
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    uid = uuid4()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(
                id=uid,
                email=f"mvp13-f134-nonadmin-{uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="Non-admin",
                is_active=True, is_admin=False,
                created_at=datetime.utcnow(),
            ))
    try:
        token = create_access_token(data={"sub": str(uid)})
        async with _client() as client:
            resp = await client.get(
                "/api/v1/admin/celery/dlq",
                headers={"Authorization": f"Bearer {token}"},
            )
        # require_admin levanta 403
        assert resp.status_code in (401, 403)
    finally:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(User.__table__.delete().where(User.id == uid))
