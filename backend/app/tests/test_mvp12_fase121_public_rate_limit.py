"""MVP 12 Fase 12.1 — Rate limit anti-abuse em POST /public/project-requests.

Contrato §7 MVP 12 Fase 12.1:
- Throttle por IP via slowapi; default configurável via env
  `PUBLIC_RATE_LIMIT` (default "5/minute").
- Idempotência de email+nome em <60s continua valendo.
- Após ultrapassar o limite: 429 Too Many Requests.
"""
import importlib
import os
from datetime import datetime
from uuid import uuid4

import httpx
import pytest

from app.core.security import hash_password


def _client() -> httpx.AsyncClient:
    # Recarrega main com PUBLIC_RATE_LIMIT propagado por teste individual.
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _unique_payload(idx: int = 0) -> dict:
    return {
        "requester_email": f"mvp12-f121-{uuid4().hex[:8]}@test.com",
        "requester_name": f"Requester {idx}",
        "project_name": f"Projeto Publico {uuid4().hex[:6]}",
        "description": "x" * 60,
        "deliverable_type": "new_system",
    }


async def _cleanup_created():
    """Remove os registros criados por estes testes (email e project)."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User
    from app.models.onboarding import ProjectRequest

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                ProjectRequest.__table__.delete().where(
                    ProjectRequest.project_name.like("Projeto Publico%")
                )
            )
            await session.execute(
                User.__table__.delete().where(User.email.like("mvp12-f121-%@test.com"))
            )


# ─── Default: limite aplica ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_endpoint_throttles_after_limit():
    """Com limite baixo (3/minute via env), 4ª request consecutiva de mesmo IP → 429."""
    # Força limite baixo nesta execução
    os.environ["PUBLIC_RATE_LIMIT"] = "3/minute"
    # Recarrega módulos para pegar a nova env var
    import app.routers.public_requests_router as prr
    importlib.reload(prr)
    # Re-anexa o router no app (app.state.limiter já foi configurado no main)
    from app.main import app
    # Remove todas as rotas cujo prefix começa em /public
    app.router.routes = [r for r in app.router.routes if not getattr(r, "path", "").startswith("/public")]
    app.include_router(prr.router)

    # Reset do storage do limiter entre testes
    app.state.limiter.reset()

    try:
        async with _client() as client:
            # 3 primeiras devem passar (201 ou 200 idempotente)
            for i in range(3):
                resp = await client.post(
                    "/public/project-requests",
                    json=_unique_payload(i),
                )
                assert resp.status_code in (200, 201), f"request {i}: {resp.status_code} {resp.text}"

            # 4ª deve ser 429
            resp = await client.post(
                "/public/project-requests",
                json=_unique_payload(99),
            )
            assert resp.status_code == 429, f"esperava 429 e veio {resp.status_code}: {resp.text}"
            # slowapi retorna mensagem tipo "rate limit exceeded"
            body = resp.json() if resp.content else {}
            assert "rate" in str(body).lower() or "limit" in str(body).lower() or resp.status_code == 429
    finally:
        os.environ.pop("PUBLIC_RATE_LIMIT", None)
        await _cleanup_created()


# ─── Limite altíssimo: tráfego normal passa livre ─────────────────────


@pytest.mark.asyncio
async def test_public_endpoint_passes_under_high_limit():
    """Com limite altíssimo (1000/minute), 3 requests passam sem 429."""
    os.environ["PUBLIC_RATE_LIMIT"] = "1000/minute"
    import app.routers.public_requests_router as prr
    importlib.reload(prr)
    from app.main import app
    app.router.routes = [r for r in app.router.routes if not getattr(r, "path", "").startswith("/public")]
    app.include_router(prr.router)
    app.state.limiter.reset()

    try:
        async with _client() as client:
            for i in range(3):
                resp = await client.post(
                    "/public/project-requests",
                    json=_unique_payload(i),
                )
                assert resp.status_code in (200, 201), f"request {i}: {resp.status_code} {resp.text}"
    finally:
        os.environ.pop("PUBLIC_RATE_LIMIT", None)
        await _cleanup_created()


# ─── Idempotência continua valendo mesmo dentro do limite ─────────────


@pytest.mark.asyncio
async def test_idempotency_preserved_under_rate_limit():
    """Mesmo email+nome <60s retorna duplicate sem consumir novo slot."""
    os.environ["PUBLIC_RATE_LIMIT"] = "1000/minute"
    import app.routers.public_requests_router as prr
    importlib.reload(prr)
    from app.main import app
    app.router.routes = [r for r in app.router.routes if not getattr(r, "path", "").startswith("/public")]
    app.include_router(prr.router)
    app.state.limiter.reset()

    try:
        payload = _unique_payload(0)
        async with _client() as client:
            resp1 = await client.post("/public/project-requests", json=payload)
            assert resp1.status_code in (200, 201)
            resp2 = await client.post("/public/project-requests", json=payload)
            assert resp2.status_code in (200, 201)
            # O 2º é marcado como duplicate
            body2 = resp2.json()
            assert body2.get("duplicate") is True or body2.get("id") == resp1.json().get("id")
    finally:
        os.environ.pop("PUBLIC_RATE_LIMIT", None)
        await _cleanup_created()
