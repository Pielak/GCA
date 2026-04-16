"""ConnectionManager para WebSockets de notificação in-app (F5).

Mantém em memória um mapa ``{user_id: set[WebSocket]}`` — um usuário pode
ter múltiplas abas abertas, todas recebem broadcast.

Limitações:
    - Per-process: deploy multi-worker (gunicorn N) não compartilha mapa.
      Para multi-worker, plug Redis pub/sub aqui (broadcast vira publish
      no canal `user:{uid}`; cada worker subscribes e re-broadcasta para
      suas conexões locais).
    - Mensagens não são persistidas — se o usuário não estiver conectado
      no momento do notify, a mensagem WebSocket é perdida (mas a
      notificação está no DB e o frontend faz fetch inicial via REST).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Dict, Set
from uuid import UUID

from fastapi import WebSocket
import structlog

logger = structlog.get_logger(__name__)


class NotificationWebSocketManager:
    """Singleton manager de conexões WebSocket por user_id."""

    def __init__(self) -> None:
        self._connections: Dict[UUID, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[user_id].add(ws)
        logger.info(
            "ws_notif.connected",
            user_id=str(user_id),
            total_connections=sum(len(s) for s in self._connections.values()),
        )

    async def disconnect(self, user_id: UUID, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.get(user_id, set()).discard(ws)
            if user_id in self._connections and not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("ws_notif.disconnected", user_id=str(user_id))

    async def broadcast_to_user(
        self,
        user_id: UUID,
        payload: Dict[str, Any],
    ) -> int:
        """Envia payload JSON para TODAS as conexões ativas do usuário.

        Retorna a quantidade de conexões que receberam. Falhas individuais
        (ex: cliente desconectou silenciosamente) são limpas do registry.
        """
        message = json.dumps(payload, default=str, ensure_ascii=False)
        delivered = 0
        dead: list[WebSocket] = []

        # Snapshot da lista para não segurar lock durante o send
        async with self._lock:
            conns = list(self._connections.get(user_id, set()))

        for ws in conns:
            try:
                await ws.send_text(message)
                delivered += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ws_notif.send_failed",
                    user_id=str(user_id),
                    error=str(exc),
                )
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.get(user_id, set()).discard(ws)
                if user_id in self._connections and not self._connections[user_id]:
                    del self._connections[user_id]

        return delivered

    def has_connections(self, user_id: UUID) -> bool:
        return bool(self._connections.get(user_id))


# Singleton de processo
manager = NotificationWebSocketManager()
