import asyncio
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.api.routes_trade import get_order_manager
from backend.trading.order_manager import OrderManager

router = APIRouter(tags=["stream"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/stream")
async def stream_updates(
    websocket: WebSocket,
    manager: OrderManager = Depends(get_order_manager),
) -> None:
    """Push gateway events to the UI (orders, positions, ticker/account)."""
    await websocket.accept()
    gateway = manager.gateway
    queue = gateway.register_subscriber()
    is_apex_gateway = (getattr(gateway, "venue", "apex") or "").lower() == "apex"
    tpsl_refresh_lock = asyncio.Lock()
    pending_tpsl_refresh = False

    async def _force_tpsl_refresh():
        nonlocal pending_tpsl_refresh
        if not is_apex_gateway:
            return
        async with tpsl_refresh_lock:
            if pending_tpsl_refresh:
                return
            pending_tpsl_refresh = True

        async def _run():
            nonlocal pending_tpsl_refresh
            try:
                snapshot = await gateway.refresh_account_orders_from_rest()
                if snapshot:
                    try:
                        manager._reconcile_tpsl(snapshot)
                    except Exception:
                        pass
                    try:
                        positions = await manager.list_positions()
                        await websocket.send_json({"type": "positions", "payload": positions})
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(
                    "tpsl_refresh_failed",
                    extra={"event": "tpsl_refresh_failed", "error": str(exc)},
                )
            finally:
                pending_tpsl_refresh = False

        asyncio.create_task(_run())

    # send initial snapshots so UI renders quickly
    try:
        # prefer WS caches for initial payloads to avoid REST overrides
        initial_orders = list(getattr(gateway, "_ws_orders_raw", []) or [])
        # reconcile TP/SL map from current account raw orders (authoritative on connect)
        try:
            manager._reconcile_tpsl(initial_orders)
        except Exception:
            pass
        # push initial positions using whatever map we have
        try:
            initial_positions = await manager.list_positions()
            await websocket.send_json({"type": "positions", "payload": initial_positions})
        except Exception:
            pass

        initial_positions_raw = list(getattr(gateway, "_ws_positions", {}).values())
        initial_positions: list[dict] = []
        if initial_positions_raw:
            for pos in initial_positions_raw:
                norm = manager._normalize_position(pos, tpsl_map=manager._tpsl_targets_by_symbol)
                if norm:
                    initial_positions.append(norm)
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
                    norm = manager._normalize_position(pos, tpsl_map=manager._tpsl_targets_by_symbol)  # reuse same shape as REST (includes local targets)
                    if norm:
                        normalized.append(norm)
                msg = {"type": "positions", "payload": normalized}
            elif event.get("type") == "orders_raw":
                # Reconcile TP/SL map from raw account orders payload (contains TP/SL orders)
                raw_orders = event.get("payload") or []
                position_tpsl_count = sum(
                    1
                    for o in raw_orders
                    if isinstance(o, dict)
                    and o.get("isPositionTpsl")
                    and str(o.get("type") or "").upper().startswith(("STOP", "TAKE_PROFIT"))
                )
                # logger.info(
                #     "ws_orders_raw_event",
                #     extra={
                #         "event": "ws_orders_raw_event",
                #         "count": len(raw_orders),
                #         "position_tpsl": position_tpsl_count,
                #         "first_type": (raw_orders[0].get("type") if raw_orders else None),
                #         "first_status": (raw_orders[0].get("status") if raw_orders else None),
                #         "first_symbol": (raw_orders[0].get("symbol") if raw_orders else None),
                #         "first_is_position_tpsl": (raw_orders[0].get("isPositionTpsl") if raw_orders else None),
                #         "first_trigger": (raw_orders[0].get("triggerPrice") if raw_orders else None),
                #     },
                # )
                refresh_needed = False
                try:
                    refresh_needed = manager._reconcile_tpsl(raw_orders)
                except Exception:
                    refresh_needed = False
                try:
                    positions = await manager.list_positions()
                    await websocket.send_json({"type": "positions", "payload": positions})
                except Exception:
                    pass
                if refresh_needed and is_apex_gateway:
                    await _force_tpsl_refresh()
                # logger.info(
                #     "ws_orders_raw_tpsl_map_built",
                #     extra={
                #         "event": "ws_orders_raw_tpsl_map_built",
                #         "symbols": list(manager._tpsl_targets_by_symbol.keys()),
                #         "orders_count": len(raw_orders),
                #         "position_tpsl": position_tpsl_count,
                #     },
                # )
                # push normalized positions using updated TP/SL map
                try:
                    cached_positions = list(getattr(gateway, "_ws_positions", {}).values())
                    normalized_positions = []
                    for pos in cached_positions:
                        norm = manager._normalize_position(pos, tpsl_map=manager._tpsl_targets_by_symbol)
                        if norm:
                            normalized_positions.append(norm)
                    await websocket.send_json({"type": "positions", "payload": normalized_positions})
                except Exception:
                    pass
                try:
                    cached_positions = list(getattr(gateway, "_ws_positions", {}).values())
                    normalized_positions = []
                    for pos in cached_positions:
                        norm = manager._normalize_position(pos, tpsl_map=manager._tpsl_targets_by_symbol)
                        if norm:
                            normalized_positions.append(norm)
                    await websocket.send_json({"type": "positions", "payload": normalized_positions})
                except Exception:
                    pass
            elif event.get("type") == "orders":
                # Forward orders event without touching TP/SL map (no TP/SL data here)
                normalized = []
                for o in event.get("payload") or []:
                    norm = manager._normalize_order(o)
                    if norm and not norm.get("id"):
                        norm["id"] = o.get("_cache_id") or o.get("clientOrderId") or o.get("orderId") or o.get("order_id")
                    if norm:
                        normalized.append(norm)
                msg = {"type": "orders", "payload": normalized}
            elif event.get("type") == "account":
                msg = {"type": "account", "payload": event.get("payload")}
            try:
                await websocket.send_json(msg)
            except WebSocketDisconnect:
                # logger.info("ws_disconnect", extra={"event": "ws_disconnect"})
                break
            except Exception as exc:
                logger.warning("ws_send_failed", extra={"event": "ws_send_failed", "error": str(exc)})
                break
    except WebSocketDisconnect:
        # logger.info("ws_disconnect", extra={"event": "ws_disconnect"})
        pass
    finally:
        gateway.unregister_subscriber(queue)
