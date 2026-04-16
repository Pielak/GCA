"""Router de notificações in-app por usuário."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.services.notification_inapp_service import InAppNotificationService
from app.services.notification_ws_manager import manager as ws_manager

router = APIRouter(tags=["notifications"])


def _to_dict(n) -> dict:
    return {
        "id": str(n.id),
        "event_type": n.event_type,
        "title": n.title,
        "message": n.message,
        "link": n.link,
        "severity": n.severity,
        "project_id": str(n.project_id) if n.project_id else None,
        "resource_type": n.resource_type,
        "resource_id": str(n.resource_id) if n.resource_id else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 30,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista notificações do usuário logado (padrão: todas, mais recentes primeiro)."""
    svc = InAppNotificationService(db)
    items = await svc.list_for_user(current_user_id, unread_only=unread_only, limit=min(max(limit, 1), 100))
    return {"notifications": [_to_dict(n) for n in items]}


@router.get("/notifications/count")
async def count_unread(
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Quantidade de notificações não lidas (usado pelo badge do sino)."""
    svc = InAppNotificationService(db)
    return {"unread": await svc.count_unread(current_user_id)}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Marca uma notificação específica como lida."""
    svc = InAppNotificationService(db)
    ok = await svc.mark_read(current_user_id, notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notificação não encontrada ou já lida")
    return {"success": True}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Marca todas as notificações do usuário como lidas."""
    svc = InAppNotificationService(db)
    affected = await svc.mark_all_read(current_user_id)
    return {"success": True, "marked": affected}


@router.websocket("/notifications/ws")
async def notifications_ws(websocket: WebSocket, token: str):
    """WebSocket de notificações em tempo real (substitui poll de 60s).

    Cliente conecta com ?token=<JWT>. Após autenticar, recebe payloads
    JSON sempre que InAppNotificationService.notify cria uma notificação
    para esse usuário. Mensagens têm formato:
        {"type": "notification.created", "id", "title", "message", ...}

    Frontend deve manter o poll como fallback caso a conexão caia (com
    backoff de reconexão). Mensagens criadas enquanto desconectado são
    obtidas via GET /notifications no próximo fetch.
    """
    # Auth via query param: WebSocket não suporta header Authorization
    # padronizado em todos browsers. Token é validado antes do accept().
    from app.core.security import verify_token
    try:
        payload = verify_token(token, token_type="access")
        if not payload:
            raise ValueError("token inválido")
        user_id = UUID(payload.get("sub"))
    except Exception:
        # 1008 = Policy Violation; nunca chamamos accept() antes
        await websocket.close(code=1008)
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            # Mantém a conexão viva. Cliente pode mandar pings ('{"type":"ping"}')
            # para manter sticky session pass-through em proxies.
            msg = await websocket.receive_text()
            if msg and '"ping"' in msg:
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await ws_manager.disconnect(user_id, websocket)
