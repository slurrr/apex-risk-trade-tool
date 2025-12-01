import asyncio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.api.routes_trade import get_order_manager
from backend.trading.order_manager import OrderManager

router = APIRouter(tags=["stream"])


@router.websocket("/ws/stream")
async def stream_updates(
    websocket: WebSocket,
    manager: OrderManager = Depends(get_order_manager),
) -> None:
    """Push gateway events to the UI (orders, positions, ticker/account)."""
    await websocket.accept()
    gateway = manager.gateway
    queue = gateway.register_subscriber()

    # send initial snapshots so UI renders quickly
    try:
        initial_orders = await manager.list_orders()
        initial_positions = await manager.list_positions()
        await websocket.send_json({"type": "orders", "payload": initial_orders})
        await websocket.send_json({"type": "positions", "payload": initial_positions})
    except Exception:
        # snapshots are best-effort; continue streaming
        pass

    try:
        while True:
            event = await queue.get()
            msg = event
            if event.get("type") == "positions":
                normalized = []
                for pos in event.get("payload") or []:
                    norm = manager._normalize_position(pos)  # reuse same shape as REST
                    if norm:
                        normalized.append(norm)
                msg = {"type": "positions", "payload": normalized}
            elif event.get("type") == "orders":
                normalized = []
                for o in event.get("payload") or []:
                    norm = manager._normalize_order(o)
                    if norm and not norm.get("id"):
                        norm["id"] = o.get("_cache_id") or o.get("clientOrderId") or o.get("orderId") or o.get("order_id")
                    if norm:
                        normalized.append(norm)
                msg = {"type": "orders", "payload": normalized}
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        gateway.unregister_subscriber(queue)
