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
    tpsl_refresh_lock = asyncio.Lock()
    pending_tpsl_refresh = False

    async def _force_tpsl_refresh():
        nonlocal pending_tpsl_refresh
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

    def _extract_tpsl_from_orders(payload: list[dict]) -> dict[str, dict[str, float]]:
        """Build a symbol->tp/sl map from any STOP/TAKE_PROFIT orders in the payload (no reduceOnly requirement)."""
        result: dict[str, dict[str, float]] = {}
        for o in payload or []:
            if not isinstance(o, dict):
                continue
            sym = o.get("symbol") or o.get("market")
            if not sym:
                continue
            otype = (o.get("type") or "").upper()
            if "STOP" not in otype and "TAKE_PROFIT" not in otype:
                continue
            status = str(o.get("status") or o.get("orderStatus") or "").lower()
            if any(key in status for key in ("cancel", "filled", "triggered")):
                continue
            trig = o.get("triggerPrice") or o.get("price")
            try:
                trig_val = float(trig) if trig is not None else None
            except Exception:
                trig_val = trig
            if trig_val is None:
                continue
            entry = result.setdefault(sym, {})
            if "TAKE_PROFIT" in otype:
                entry["take_profit"] = trig_val
            if "STOP" in otype:
                entry["stop_loss"] = trig_val
        return result

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
                logger.info(
                    "ws_orders_raw_event",
                    extra={
                        "event": "ws_orders_raw_event",
                        "count": len(raw_orders),
                        "position_tpsl": position_tpsl_count,
                        "first_type": (raw_orders[0].get("type") if raw_orders else None),
                        "first_status": (raw_orders[0].get("status") if raw_orders else None),
                        "first_symbol": (raw_orders[0].get("symbol") if raw_orders else None),
                        "first_is_position_tpsl": (raw_orders[0].get("isPositionTpsl") if raw_orders else None),
                        "first_trigger": (raw_orders[0].get("triggerPrice") if raw_orders else None),
                    },
                )
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
                if refresh_needed:
                    await _force_tpsl_refresh()
                logger.info(
                    "ws_orders_raw_tpsl_map_built",
                    extra={
                        "event": "ws_orders_raw_tpsl_map_built",
                        "symbols": list(manager._tpsl_targets_by_symbol.keys()),
                        "orders_count": len(raw_orders),
                        "position_tpsl": position_tpsl_count,
                    },
                )
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
                logger.info("ws_disconnect", extra={"event": "ws_disconnect"})
                break
            except Exception as exc:
                logger.warning("ws_send_failed", extra={"event": "ws_send_failed", "error": str(exc)})
                break
    except WebSocketDisconnect:
        logger.info("ws_disconnect", extra={"event": "ws_disconnect"})
    finally:
        gateway.unregister_subscriber(queue)
