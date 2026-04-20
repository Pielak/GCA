"""MVP 13 Fase 13.2 — Lifespan + worker lifecycle + /health expandido.

Contrato §7 MVP 13 Fase 13.2:
- `/health` reporta status do broker Celery + contagem de workers.
- Backend não inicia worker no próprio processo (worker é serviço
  `gca-celery-worker` separado via docker-compose).
- Falha de broker é aviso no startup, não fatal — endpoints sem fila
  seguem respondendo.
"""
from unittest.mock import patch

import httpx
import pytest

from app.main import app


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ─── /health inclui celery ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_inclui_bloco_celery():
    async with _client() as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "celery" in body
    assert "broker" in body["celery"]
    assert "workers" in body["celery"]


@pytest.mark.asyncio
async def test_health_broker_reachable_reporta_true():
    """Quando check_broker_connection retorna reachable=True, health reflete."""
    fake_broker = {"broker": "redis://fake:6379/1", "reachable": True, "error": None}
    fake_workers = {"workers": 1, "nodes": ["celery@x"], "error": None}
    with patch("app.celery_app.check_broker_connection", return_value=fake_broker):
        with patch("app.celery_app.check_workers_alive", return_value=fake_workers):
            async with _client() as client:
                resp = await client.get("/health")
    body = resp.json()
    assert body["celery"]["broker"]["reachable"] is True
    assert body["celery"]["workers"]["workers"] == 1
    assert body["celery"]["workers"]["nodes"] == ["celery@x"]


@pytest.mark.asyncio
async def test_health_broker_unreachable_nao_derruba_endpoint():
    """Backend continua respondendo mesmo se broker estiver fora."""
    fake_broker = {"broker": "redis://dead:6379/1", "reachable": False, "error": "ConnectionError: no route"}
    with patch("app.celery_app.check_broker_connection", return_value=fake_broker):
        async with _client() as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"  # backend OK
    assert body["celery"]["broker"]["reachable"] is False
    assert body["celery"]["workers"]["workers"] == 0
    assert body["celery"]["workers"]["error"] == "broker_unreachable"


# ─── Helpers de check ─────────────────────────────────────────────────


def test_check_broker_connection_shape():
    from app.celery_app import check_broker_connection
    result = check_broker_connection(timeout=0.5)
    # Campos obrigatórios do contrato
    assert "broker" in result
    assert "reachable" in result
    assert "error" in result
    assert isinstance(result["reachable"], bool)


def test_check_workers_alive_shape():
    from app.celery_app import check_workers_alive
    result = check_workers_alive(timeout=0.5)
    assert "workers" in result
    assert "nodes" in result
    assert "error" in result
    assert isinstance(result["workers"], int)
    assert isinstance(result["nodes"], list)


def test_check_broker_connection_com_broker_inexistente():
    """Broker inexistente: reachable=False + error populado, sem raise."""
    from app.celery_app import celery_app, check_broker_connection
    original = celery_app.conf.broker_url
    celery_app.conf.broker_url = "redis://does-not-exist:6399/1"
    try:
        result = check_broker_connection(timeout=0.5)
        assert result["reachable"] is False
        assert result["error"] is not None
    finally:
        celery_app.conf.broker_url = original


def test_check_workers_alive_sem_workers_retorna_zero():
    """Quando broker OK mas inspect timeouta (mock), workers=0."""
    from app.celery_app import check_workers_alive
    with patch("app.celery_app.celery_app.control.inspect") as mock_insp:
        mock_insp.return_value.ping.return_value = None  # simulate no workers
        result = check_workers_alive(timeout=0.1)
    assert result["workers"] == 0
    assert result["nodes"] == []
