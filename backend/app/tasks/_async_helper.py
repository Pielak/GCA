"""Helper único pra rodar corrotinas dentro de tasks Celery.

Centraliza o padrão de event loop isolado por task. Antes ficava
duplicado em pipeline.py e scaffold.py — cada cópia divergiu e tinha
bugs sutis (fallback que tentava re-await da mesma coroutine).

Bug histórico (2026-05-05): ForkPoolWorker reusa estado entre tasks.
A primeira task fechava o loop com `loop.close()` mas não removia o
loop do estado global do asyncio nem fazia dispose do pool SQLAlchemy.
Próxima task criava novo loop, mas:
  - asyncpg dentro da coroutine chamava `asyncio.get_event_loop()` e
    pegava o loop antigo fechado → `Event loop is closed`.
  - SQLAlchemy pool guardava conexões atreladas ao loop antigo →
    `got Future attached to a different loop`.

Fix:
  1. `asyncio.set_event_loop(loop)` registra o novo loop como current.
  2. `engine.dispose()` async no início descarta conexões velhas.
  3. Sem fallback bugado de re-await.
"""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine


def run_coro_isolated(coro: Coroutine[Any, Any, Any]) -> Any:
    """Roda corrotina num event loop isolado, com pool SQLAlchemy fresco."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _dispose_then_run():
            try:
                from app.db.database import engine
                await engine.dispose()
            except Exception:  # noqa: BLE001
                pass
            return await coro

        return loop.run_until_complete(_dispose_then_run())
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)
