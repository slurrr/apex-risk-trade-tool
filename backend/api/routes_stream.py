import asyncio
import json
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.api.routes_trade import get_order_manager
from backend.core.ui_mock import get_ui_mock_section, is_ui_mock_enabled
from backend.trading.order_manager import OrderManager

router = APIRouter(tags=["stream"])
logger = logging.getLogger(__name__)


@router.get("/api/stream/health")
async def stream_health(manager: OrderManager = Depends(get_order_manager)) -> dict:
    """Expose stream/reconcile health metrics for diagnostics and alerting."""
    try:
        if is_ui_mock_enabled():
            venue = (getattr(manager.gateway, "venue", "apex") or "apex").lower()
            health = get_ui_mock_section(venue, "stream_health", {})
            if isinstance(health, dict):
                payload = dict(health)
                payload.setdefault("venue", venue)
                return payload
            return {"venue": venue, "ws_alive": True}
        return await manager.get_stream_health()
    except Exception as exc:
        logger.warning("stream_health_failed", extra={"event": "stream_health_failed", "error": str(exc)})
        return {"venue": (getattr(manager.gateway, "venue", "unknown") or "unknown"), "error": str(exc)}


@router.websocket("/ws/stream")
async def stream_updates(
    websocket: WebSocket,
    manager: OrderManager = Depends(get_order_manager),
) -> None:
    """Push gateway events to the UI (orders, positions, ticker/account)."""
    await websocket.accept()
    if is_ui_mock_enabled():
        venue = (getattr(manager.gateway, "venue", "apex") or "apex").lower()
        account = get_ui_mock_section(venue, "account_summary", {})
        orders = get_ui_mock_section(venue, "orders", [])
        positions = get_ui_mock_section(venue, "positions", [])
        try:
            if isinstance(account, dict):
                account_payload = dict(account)
                account_payload.setdefault("venue", venue)
                await websocket.send_json({"type": "account", "payload": account_payload})
            await websocket.send_json({"type": "orders", "payload": orders if isinstance(orders, list) else []})
            await websocket.send_json({"type": "positions", "payload": positions if isinstance(positions, list) else []})
            while True:
                await asyncio.sleep(30)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    gateway = manager.gateway
    queue = gateway.register_subscriber()
    is_apex_gateway = (getattr(gateway, "venue", "apex") or "").lower() == "apex"
    tpsl_refresh_lock = asyncio.Lock()
    pending_tpsl_refresh = False
    last_sent_by_type: dict[str, str] = {}

    async def _send_event(event_type: str, payload):
        """
        Best-effort de-duplication: skip sending identical consecutive payloads
        for the same event type to reduce WS spam during bursty updates.
        """
        try:
            snapshot = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        except Exception:
            snapshot = ""
        if snapshot and last_sent_by_type.get(event_type) == snapshot:
            return
        if snapshot:
            last_sent_by_type[event_type] = snapshot
        await websocket.send_json({"type": event_type, "payload": payload})

    async def _emit_positions_from_cache() -> None:
        cached_positions = list(getattr(gateway, "_ws_positions", {}).values())
        if not cached_positions:
            return
        normalized_positions = []
        for pos in cached_positions:
            norm = manager._normalize_position(pos, tpsl_map=manager._tpsl_targets_by_symbol)
            if norm:
                normalized_positions.append(norm)
        if normalized_positions:
            await _send_event("positions", normalized_positions)

    def _normalize_orders_for_ui(orders_payload) -> list[dict]:
        normalized: list[dict] = []
        for order in orders_payload or []:
            if not isinstance(order, dict):
                continue
            include_fn = getattr(manager, "_include_in_open_orders", None)
            if callable(include_fn) and not include_fn(order):
                continue
            norm = manager._normalize_order(order)
            if norm and not norm.get("id"):
                norm["id"] = order.get("_cache_id") or order.get("clientOrderId") or order.get("orderId") or order.get("order_id")
            if norm:
                normalized.append(norm)
        return normalized

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
        # Prefer raw account-orders when present (contains TP/SL metadata), but fall back to
        # mapped open-orders cache to avoid rendering a transient empty orders table.
        initial_orders = list(getattr(gateway, "_ws_orders_raw", []) or [])
        if not initial_orders:
            initial_orders = list(getattr(gateway, "_ws_orders", {}).values() or [])
        # reconcile TP/SL map from current account raw orders (authoritative on connect)
        try:
            manager._reconcile_tpsl(initial_orders)
        except Exception:
            pass
        # push initial positions using whatever map we have
        try:
            initial_positions = await manager.list_positions()
            await _send_event("positions", initial_positions)
        except Exception:
            pass

        initial_positions_raw = list(getattr(gateway, "_ws_positions", {}).values())
        initial_positions: list[dict] = []
        if initial_positions_raw:
            for pos in initial_positions_raw:
                norm = manager._normalize_position(pos, tpsl_map=manager._tpsl_targets_by_symbol)
                if norm:
                    initial_positions.append(norm)
        await _send_event("orders", _normalize_orders_for_ui(initial_orders))
        if initial_positions:
            await _send_event("positions", initial_positions)
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
                    await _emit_positions_from_cache()
                except Exception:
                    pass
                if refresh_needed and is_apex_gateway:
                    flap_recorder = getattr(gateway, "record_tpsl_flap_suspected", None)
                    if callable(flap_recorder):
                        try:
                            flap_recorder()
                        except Exception:
                            pass
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
            elif event.get("type") == "orders":
                # Forward orders event without touching TP/SL map (no TP/SL data here)
                msg = {"type": "orders", "payload": _normalize_orders_for_ui(event.get("payload"))}
            elif event.get("type") == "account":
                msg = {"type": "account", "payload": event.get("payload")}
            try:
                await _send_event(msg.get("type"), msg.get("payload"))
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
