import asyncio
import time
from typing import Any, Dict, Optional

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from backend.core.logging import get_logger

logger = get_logger(__name__)


class HyperliquidGateway:
    _TIMEFRAME_MS: dict[str, int] = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "2h": 7_200_000,
        "4h": 14_400_000,
        "8h": 28_800_000,
        "12h": 43_200_000,
        "1d": 86_400_000,
    }
    _TERMINAL_ORDER_STATUSES = {
        "canceled",
        "cancelled",
        "filled",
        "rejected",
        "margin canceled",
        "margin cancelled",
    }

    def __init__(
        self,
        base_url: str = "https://api.hyperliquid.xyz",
        user_address: Optional[str] = None,
        agent_private_key: Optional[str] = None,
        info_client: Optional[Any] = None,
        exchange_client: Optional[Any] = None,
        ws_info_client: Optional[Any] = None,
    ) -> None:
        self.venue = "hyperliquid"
        self._base_url = base_url.rstrip("/")
        self._user_address = (user_address or "").strip()
        self._agent_private_key = (agent_private_key or "").strip()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._configs: dict[str, dict[str, Any]] = {}
        self._coin_to_asset: dict[str, int] = {}
        self._mids_cache: dict[str, float] = {}
        self._mids_cached_at: float = 0.0
        self._ws_running = False
        self._ws_subscription_ids: list[tuple[dict[str, Any], int]] = []
        self._ws_monitor_task: Optional[asyncio.Task] = None
        self._account_refresh_task: Optional[asyncio.Task] = None
        self._account_refresh_interval = 15.0
        self._ws_orders: dict[str, dict[str, Any]] = {}
        self._ws_orders_raw: list[dict[str, Any]] = []
        self._ws_positions: dict[str, dict[str, Any]] = {}
        self._info = info_client or Info(base_url=self._base_url, skip_ws=True, timeout=8)
        self._ws_info = ws_info_client
        self._exchange: Optional[Any] = exchange_client
        if self._exchange is None and self._agent_private_key:
            wallet = Account.from_key(self._agent_private_key)
            self._exchange = Exchange(
                wallet=wallet,
                base_url=self._base_url,
                account_address=self._user_address or None,
                timeout=8,
            )

    def _coin_from_symbol(self, symbol: str) -> str:
        text = (symbol or "").strip().upper()
        if not text:
            raise ValueError("symbol is required")
        if "-" in text:
            return text.split("-")[0]
        return text

    def _symbol_from_coin(self, coin: str) -> str:
        return f"{coin.upper()}-USDC"

    def _require_user_address(self) -> str:
        user = (self._user_address or "").strip()
        if not user:
            raise ValueError("HL_USER_ADDRESS is required for Hyperliquid private account data.")
        return user

    def _extract_price_decimals(self, value: float) -> int:
        text = f"{value:.12f}".rstrip("0").rstrip(".")
        if "." not in text:
            return 0
        return len(text.split(".")[1])

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _normalize_hl_side(side: str) -> str:
        side_norm = (side or "").upper()
        return "BUY" if side_norm in {"B", "BUY", "LONG"} else "SELL"

    @staticmethod
    def _wire_safe_float(value: Any) -> float:
        """
        Hyperliquid SDK float_to_wire() rejects tiny binary drift.
        Canonicalize to an 8-decimal string and parse back before submit.
        """
        return float(f"{float(value):.8f}")

    @classmethod
    def _is_terminal_status(cls, status: Any) -> bool:
        text = str(status or "").strip().lower()
        if not text:
            return False
        if text in cls._TERMINAL_ORDER_STATUSES:
            return True
        return "cancel" in text

    @staticmethod
    def _normalize_order_type(raw_type: Any) -> str:
        text = str(raw_type or "").strip().upper().replace("-", " ").replace("_", " ")
        if "TAKE" in text and "PROFIT" in text:
            return "TAKE_PROFIT_MARKET"
        if "STOP" in text:
            return "STOP_MARKET"
        if text == "TRIGGER":
            return "STOP_MARKET"
        return text.replace(" ", "_") or "LIMIT"

    def _target_kind_from_order(self, order: dict[str, Any]) -> Optional[str]:
        order_type = self._normalize_order_type(order.get("type") or order.get("orderType"))
        if order_type.startswith("TAKE_PROFIT"):
            return "tp"
        if order_type.startswith("STOP"):
            return "sl"
        return None

    def _normalize_order_row(self, row: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not isinstance(row, dict):
            return None
        order = row.get("order") if isinstance(row.get("order"), dict) else row
        coin = str(order.get("coin") or row.get("coin") or "").upper().strip()
        if not coin:
            return None
        oid = order.get("oid") or row.get("oid") or row.get("orderId")
        if oid is None:
            return None
        order_type = self._normalize_order_type(order.get("orderType") or row.get("orderType") or row.get("type"))
        trigger_px = (
            order.get("triggerPx")
            or row.get("triggerPx")
            or row.get("triggerPrice")
            or (order.get("trigger") or {}).get("triggerPx")
        )
        reduce_only = bool(order.get("reduceOnly") if order.get("reduceOnly") is not None else row.get("reduceOnly"))
        normalized = {
            "orderId": str(oid),
            "clientOrderId": order.get("cloid") or row.get("cloid"),
            "symbol": self._symbol_from_coin(coin),
            "coin": coin,
            "side": self._normalize_hl_side(str(order.get("side") or row.get("side") or "")),
            "size": order.get("sz") or row.get("sz") or order.get("origSz") or row.get("origSz"),
            "price": order.get("limitPx") or row.get("limitPx"),
            "status": row.get("status") or order.get("status") or "OPEN",
            "reduceOnly": reduce_only,
            "type": order_type,
            "orderType": order_type,
            "triggerPrice": trigger_px,
            "isPositionTpsl": bool(
                row.get("isPositionTpsl")
                or (order.get("isTrigger") or row.get("isTrigger")) and reduce_only
                or order_type.startswith(("STOP", "TAKE_PROFIT"))
            ),
            "timestamp": row.get("timestamp") or order.get("timestamp"),
            "raw": row,
        }
        return normalized

    async def _fetch_frontend_open_orders(self) -> list[dict[str, Any]]:
        user = self._require_user_address()
        fetcher = getattr(self._info, "frontend_open_orders", None)
        if callable(fetcher):
            rows = await asyncio.to_thread(fetcher, user)
        else:
            rows = await asyncio.to_thread(self._info.open_orders, user)
        payload = rows if isinstance(rows, list) else []
        normalized: list[dict[str, Any]] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            parsed = self._normalize_order_row(row)
            if parsed:
                normalized.append(parsed)
        return normalized

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _publish_event(self, event: Dict[str, Any]) -> None:
        if not self._subscribers or not self._loop:
            return
        for q in list(self._subscribers):
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                continue

    def _schedule_coro(self, coro_factory) -> None:
        if not self._loop:
            return
        try:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(coro_factory()))
        except Exception:
            return

    async def load_configs(self) -> None:
        try:
            meta = await asyncio.to_thread(self._info.meta)
            mids = await self._get_all_mids(force=True)
        except Exception as exc:
            logger.warning("hl_load_configs_failed", extra={"event": "hl_load_configs_failed", "error": str(exc)})
            self._configs = {}
            return

        universe = []
        if isinstance(meta, dict):
            universe = meta.get("universe") or []
        elif isinstance(meta, list):
            universe = meta
        mapped: dict[str, dict[str, Any]] = {}
        coin_to_asset: dict[str, int] = {}
        for idx, item in enumerate(universe or []):
            if not isinstance(item, dict):
                continue
            coin = str(item.get("name") or item.get("coin") or "").upper().strip()
            if not coin:
                continue
            coin_to_asset[coin] = idx
            symbol = self._symbol_from_coin(coin)
            sz_decimals_raw = item.get("szDecimals")
            try:
                sz_decimals = int(sz_decimals_raw) if sz_decimals_raw is not None else 0
            except Exception:
                sz_decimals = 0
            step_size = 10 ** (-max(0, sz_decimals))
            mid = mids.get(coin)
            if mid is not None and mid > 0:
                px_decimals = min(8, max(0, self._extract_price_decimals(mid)))
            else:
                px_decimals = 2
            tick_size = 10 ** (-px_decimals)
            mapped[symbol] = {
                "symbol": symbol,
                "coin": coin,
                "tickSize": float(tick_size),
                "stepSize": float(step_size),
                "minOrderSize": float(step_size),
                "maxOrderSize": 0.0,
                "maxLeverage": float(item.get("maxLeverage") or 0.0),
                "baseAsset": coin,
                "quoteAsset": "USDC",
                "status": "ENABLED",
                "raw": item,
            }
        self._configs = mapped
        self._coin_to_asset = coin_to_asset

    async def ensure_configs_loaded(self) -> None:
        if not self._configs:
            await self.load_configs()
        if not self._configs:
            raise ValueError("Hyperliquid symbol metadata unavailable.")

    async def _ensure_ws_info(self) -> Optional[Any]:
        if self._ws_info is not None:
            return self._ws_info
        try:
            self._ws_info = await asyncio.to_thread(
                lambda: Info(base_url=self._base_url, skip_ws=False, timeout=8),
            )
        except Exception as exc:
            logger.warning("hl_ws_info_init_failed", extra={"event": "hl_ws_info_init_failed", "error": str(exc)})
            self._ws_info = None
        return self._ws_info

    def _ws_alive(self) -> bool:
        ws_manager = getattr(self._ws_info, "ws_manager", None)
        if ws_manager is None:
            return False
        try:
            return bool(ws_manager.is_alive())
        except Exception:
            return False

    async def _subscribe_streams(self) -> None:
        info = await self._ensure_ws_info()
        if info is None:
            return
        self._ws_subscription_ids = []
        subscriptions = [{"type": "allMids"}]
        user = (self._user_address or "").strip()
        if user:
            subscriptions.append({"type": "orderUpdates", "user": user})
            subscriptions.append({"type": "userEvents", "user": user})
        for sub in subscriptions:
            try:
                sub_id = info.subscribe(sub, self._ws_callback_router)
                self._ws_subscription_ids.append((sub, sub_id))
            except Exception as exc:
                logger.warning(
                    "hl_ws_subscribe_failed",
                    extra={"event": "hl_ws_subscribe_failed", "subscription": sub.get("type"), "error": str(exc)},
                )

    async def start_streams(self) -> None:
        if self._ws_running:
            return
        self._ws_running = True
        await self._subscribe_streams()
        if self._loop and (self._ws_monitor_task is None or self._ws_monitor_task.done()):
            self._ws_monitor_task = self._loop.create_task(self._ws_monitor_loop())
        # Seed the stream with current snapshot values.
        self._schedule_coro(self._seed_stream_state)

    async def _seed_stream_state(self) -> None:
        try:
            orders = await self.refresh_account_orders_from_rest()
            if orders:
                self._publish_event({"type": "orders_raw", "payload": orders})
                self._publish_event({"type": "orders", "payload": orders})
        except Exception:
            pass
        try:
            positions = await self.get_open_positions(force_rest=True, publish=False)
            if positions:
                self._publish_event({"type": "positions", "payload": positions})
        except Exception:
            pass
        try:
            summary = await self.get_account_summary()
            self._publish_event({"type": "account", "payload": summary})
        except Exception:
            pass

    async def _ws_monitor_loop(self) -> None:
        while self._ws_running:
            try:
                await asyncio.sleep(5)
                if not self._ws_running:
                    break
                if self._ws_info is None:
                    await self._subscribe_streams()
                    continue
                if not self._ws_alive():
                    info = self._ws_info
                    disconnect = getattr(info, "disconnect_websocket", None)
                    if callable(disconnect):
                        try:
                            await asyncio.to_thread(disconnect)
                        except Exception:
                            pass
                    self._ws_info = None
                    await self._subscribe_streams()
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def stop_streams(self) -> None:
        self._ws_running = False
        for task in (self._ws_monitor_task, self._account_refresh_task):
            if task and not task.done():
                task.cancel()
        self._ws_monitor_task = None
        self._account_refresh_task = None
        info = self._ws_info
        self._ws_subscription_ids = []
        if info is not None:
            disconnect = getattr(info, "disconnect_websocket", None)
            if callable(disconnect):
                try:
                    await asyncio.to_thread(disconnect)
                except Exception:
                    pass
        self._ws_info = None

    def start_account_refresh(self, interval: Optional[float] = None) -> None:
        if interval is not None:
            self._account_refresh_interval = interval
        if not self._loop:
            return
        if self._account_refresh_task is None or self._account_refresh_task.done():
            self._account_refresh_task = self._loop.create_task(self._account_refresh_loop())

    async def _account_refresh_loop(self) -> None:
        interval = max(5.0, float(self._account_refresh_interval or 15.0))
        while True:
            try:
                await asyncio.sleep(interval)
                summary = await self.get_account_summary()
                self._publish_event({"type": "account", "payload": summary})
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    def clear_runtime_state(self) -> None:
        self._subscribers.clear()
        self._mids_cache.clear()
        self._mids_cached_at = 0.0
        self._ws_orders.clear()
        self._ws_orders_raw = []
        self._ws_positions.clear()

    def register_subscriber(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unregister_subscriber(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _ws_callback_router(self, ws_msg: dict[str, Any]) -> None:
        if not isinstance(ws_msg, dict):
            return
        channel = str(ws_msg.get("channel") or "").lower()
        if channel == "allmids":
            self._on_ws_all_mids(ws_msg)
            return
        if channel == "orderupdates":
            self._on_ws_order_updates(ws_msg)
            return
        if channel == "user":
            self._schedule_coro(self._seed_stream_state)

    def _on_ws_all_mids(self, ws_msg: dict[str, Any]) -> None:
        payload = ws_msg.get("data")
        if not isinstance(payload, dict):
            return
        now = time.time()
        changed = False
        for coin, price in payload.items():
            parsed = self._to_float(price)
            if parsed is None or parsed <= 0:
                continue
            self._mids_cache[str(coin).upper()] = parsed
            changed = True
        if changed:
            self._mids_cached_at = now

    def _on_ws_order_updates(self, ws_msg: dict[str, Any]) -> None:
        payload = ws_msg.get("data")
        rows = payload if isinstance(payload, list) else ([payload] if isinstance(payload, dict) else [])
        batch: list[dict[str, Any]] = []
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self._normalize_order_row(row)
            if not parsed:
                continue
            batch.append(parsed)
            oid = str(parsed.get("orderId") or "")
            if not oid:
                continue
            if self._is_terminal_status(parsed.get("status")):
                if oid in self._ws_orders:
                    self._ws_orders.pop(oid, None)
                    changed = True
            else:
                self._ws_orders[oid] = parsed
                changed = True
        if not changed and not batch:
            return
        self._ws_orders_raw = list(self._ws_orders.values())
        self._publish_event({"type": "orders_raw", "payload": batch or self._ws_orders_raw})
        self._publish_event({"type": "orders", "payload": list(self._ws_orders.values())})

    async def list_symbols(self) -> list[Dict[str, Any]]:
        await self.ensure_configs_loaded()
        return list(self._configs.values())

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        coin = self._coin_from_symbol(symbol)
        return self._configs.get(self._symbol_from_coin(coin))

    async def get_account_summary(self) -> Dict[str, float]:
        user = self._require_user_address()
        payload = await asyncio.to_thread(self._info.user_state, user)
        if not isinstance(payload, dict):
            return {"total_equity": 0.0, "total_upnl": 0.0, "available_margin": 0.0}

        margin = payload.get("marginSummary") or {}
        account_value = margin.get("accountValue")
        total_upnl = margin.get("totalNtlPos")
        withdrawable = payload.get("withdrawable")

        def _f(value: Any) -> float:
            parsed = self._to_float(value)
            return float(parsed) if parsed is not None else 0.0

        return {
            "total_equity": _f(account_value),
            "total_upnl": _f(total_upnl),
            "available_margin": _f(withdrawable),
        }

    async def get_account_equity(self) -> float:
        summary = await self.get_account_summary()
        return float(summary.get("total_equity") or 0.0)

    async def get_mark_price(self, symbol: str) -> float:
        price, _ = await self.get_reference_price(symbol)
        return price

    async def get_reference_price(self, symbol: str) -> tuple[float, str]:
        coin = self._coin_from_symbol(symbol)
        mids = await self._get_all_mids(force=False)
        mid = mids.get(coin)
        if mid is not None and mid > 0:
            return float(mid), "mid"
        raise ValueError(f"No reference price available for {coin}")

    async def get_symbol_last_price(self, symbol: str) -> float:
        price, _ = await self.get_reference_price(symbol)
        return price

    async def fetch_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[Dict[str, Any]]:
        coin = self._coin_from_symbol(symbol)
        interval = (timeframe or "").strip().lower()
        if interval not in self._TIMEFRAME_MS:
            raise ValueError(f"Unsupported timeframe '{timeframe}' for Hyperliquid candles.")
        safe_limit = max(1, min(int(limit), 500))
        now_ms = int(time.time() * 1000)
        interval_ms = self._TIMEFRAME_MS[interval]
        start_ms = now_ms - (safe_limit + 2) * interval_ms
        rows = await asyncio.to_thread(
            self._info.candles_snapshot,
            coin,
            interval,
            start_ms,
            now_ms,
        )
        candles: list[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            try:
                candles.append(
                    {
                        "open_time": int(row.get("t") or row.get("T") or 0),
                        "open": float(row.get("o")),
                        "high": float(row.get("h")),
                        "low": float(row.get("l")),
                        "close": float(row.get("c")),
                        "volume": float(row.get("v")) if row.get("v") is not None else None,
                    }
                )
            except Exception:
                continue
        candles.sort(key=lambda c: c.get("open_time", 0))
        if len(candles) > safe_limit:
            candles = candles[-safe_limit:]
        return candles

    async def get_depth_snapshot(self, symbol: str, *, levels: int = 25) -> Dict[str, Any]:
        coin = self._coin_from_symbol(symbol)
        book = await asyncio.to_thread(self._info.l2_snapshot, coin)
        raw_levels = book.get("levels") if isinstance(book, dict) else None
        bids: list[dict[str, float]] = []
        asks: list[dict[str, float]] = []
        if isinstance(raw_levels, list) and len(raw_levels) >= 2:
            for row in raw_levels[0][: max(1, int(levels))]:
                if not isinstance(row, dict):
                    continue
                try:
                    bids.append({"px": float(row.get("px")), "size": float(row.get("sz"))})
                except Exception:
                    continue
            for row in raw_levels[1][: max(1, int(levels))]:
                if not isinstance(row, dict):
                    continue
                try:
                    asks.append({"px": float(row.get("px")), "size": float(row.get("sz"))})
                except Exception:
                    continue
        return {"bids": bids, "asks": asks}

    async def get_open_positions(self, force_rest: bool = False, publish: bool = False) -> list[Dict[str, Any]]:
        user = self._require_user_address()
        payload = await asyncio.to_thread(self._info.user_state, user)
        if not isinstance(payload, dict):
            return []
        positions = payload.get("assetPositions") or []
        normalized: list[Dict[str, Any]] = []
        for row in positions:
            if not isinstance(row, dict):
                continue
            pos = row.get("position") or row
            if not isinstance(pos, dict):
                continue
            coin = str(pos.get("coin") or "").upper().strip()
            if not coin:
                continue
            size_raw = pos.get("szi")
            size_val = self._to_float(size_raw)
            if size_val is None or abs(size_val) <= 0:
                continue
            item = {
                "positionId": coin,
                "symbol": self._symbol_from_coin(coin),
                "positionSide": "LONG" if size_val > 0 else "SHORT",
                "size": abs(size_val),
                "entryPrice": pos.get("entryPx"),
                "unrealizedPnl": pos.get("unrealizedPnl"),
            }
            normalized.append(item)
            self._ws_positions[coin] = item
        if publish:
            self._publish_event({"type": "positions", "payload": normalized})
        return normalized

    async def get_open_orders(self, force_rest: bool = False, publish: bool = False) -> list[Dict[str, Any]]:
        orders = await self._fetch_frontend_open_orders()
        if orders:
            self._ws_orders = {str(o.get("orderId")): o for o in orders if o.get("orderId")}
            self._ws_orders_raw = list(orders)
        if publish:
            self._publish_event({"type": "orders", "payload": orders})
            self._publish_event({"type": "orders_raw", "payload": orders})
        return orders

    def get_account_orders_snapshot(self) -> list[Dict[str, Any]]:
        return list(self._ws_orders_raw)

    async def refresh_account_orders_from_rest(self) -> list[Dict[str, Any]]:
        return await self.get_open_orders(force_rest=True, publish=False)

    async def _get_all_mids(self, force: bool = False) -> dict[str, float]:
        now = time.time()
        if not force and self._mids_cache and (now - self._mids_cached_at) < 10:
            return dict(self._mids_cache)
        payload = await asyncio.to_thread(self._info.all_mids)
        mids: dict[str, float] = {}
        if isinstance(payload, dict):
            for coin, price in payload.items():
                parsed = self._to_float(price)
                if parsed is None:
                    continue
                mids[str(coin).upper()] = parsed
        self._mids_cache = mids
        self._mids_cached_at = now
        return dict(mids)

    async def build_order_payload(self, **kwargs):
        symbol = kwargs.get("symbol")
        side = str(kwargs.get("side") or "").upper()
        size = float(kwargs.get("size") or 0)
        entry_price = float(kwargs.get("entry_price") or 0)
        reduce_only = bool(kwargs.get("reduce_only", False))
        tp = kwargs.get("tp")
        stop = kwargs.get("stop")
        if size <= 0 or entry_price <= 0:
            raise ValueError("Invalid size or entry price for Hyperliquid order.")
        coin = self._coin_from_symbol(symbol)
        await self.ensure_configs_loaded()
        asset = self._coin_to_asset.get(coin)
        if asset is None:
            raise ValueError(f"Unknown Hyperliquid asset for symbol {symbol}.")
        payload = {
            "coin": coin,
            "asset": int(asset),
            "is_buy": side in {"BUY", "LONG"},
            "price": float(entry_price),
            "size": float(size),
            "reduce_only": reduce_only,
            "tif": "Gtc",
        }
        warning = None
        if tp is not None or stop is not None:
            warning = "Hyperliquid TP/SL attach-on-entry is not implemented yet; submit targets separately."
        return payload, warning

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        exchange = self._require_exchange()
        resp = await asyncio.to_thread(
            exchange.order,
            payload["coin"],
            bool(payload["is_buy"]),
            self._wire_safe_float(payload["size"]),
            self._wire_safe_float(payload["price"]),
            {"limit": {"tif": str(payload.get("tif") or "Gtc")}},
            bool(payload.get("reduce_only", False)),
        )
        oid = self._extract_oid(resp)
        if oid is None:
            return {"exchange_order_id": None, "raw": resp}
        return {"exchange_order_id": str(oid), "raw": resp}

    async def cancel_order(self, order_id: str, client_id: Optional[str] = None) -> Dict[str, Any]:
        exchange = self._require_exchange()
        if not str(order_id).isdigit():
            raise ValueError("Hyperliquid cancel currently requires numeric order id.")
        oid = int(order_id)
        orders = await self.get_open_orders()
        target = next((o for o in orders if str(o.get("orderId")) == str(order_id)), None)
        if not target:
            raise ValueError(f"Order {order_id} not found.")
        coin = self._coin_from_symbol(str(target.get("symbol") or ""))
        resp = await asyncio.to_thread(exchange.cancel, coin, oid)
        return {"canceled": True, "order_id": str(order_id), "raw": resp}

    async def place_close_order(
        self,
        symbol: str,
        side: str,
        size: float,
        close_type: str,
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        exchange = self._require_exchange()
        if size <= 0:
            raise ValueError("Close size must be greater than 0.")
        coin = self._coin_from_symbol(symbol)
        side_norm = (side or "").upper()
        is_buy = side_norm in {"SHORT", "SELL"}
        close_type_norm = (close_type or "").lower()
        if close_type_norm == "market":
            safe_size = self._wire_safe_float(size)
            safe_price = self._wire_safe_float(limit_price) if limit_price is not None else None
            resp = await asyncio.to_thread(exchange.market_close, coin, safe_size, safe_price)
            return {"exchange_order_id": str(self._extract_oid(resp) or ""), "client_id": None, "raw": resp}
        if limit_price is None or limit_price <= 0:
            raise ValueError("Limit close requires a valid limit_price.")
        resp = await asyncio.to_thread(
            exchange.order,
            coin,
            bool(is_buy),
            self._wire_safe_float(size),
            self._wire_safe_float(limit_price),
            {"limit": {"tif": "Gtc"}},
            True,
        )
        return {"exchange_order_id": str(self._extract_oid(resp) or ""), "client_id": None, "raw": resp}

    async def cancel_tpsl_orders(
        self, *, symbol: Optional[str], cancel_tp: bool = False, cancel_sl: bool = False
    ) -> Dict[str, Any]:
        if not cancel_tp and not cancel_sl:
            return {"canceled": [], "errors": []}
        exchange = self._require_exchange()
        orders = await self.refresh_account_orders_from_rest()
        target_coin = self._coin_from_symbol(symbol) if symbol else None
        canceled: list[str] = []
        errors: list[dict[str, Any]] = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            order_coin = str(order.get("coin") or self._coin_from_symbol(str(order.get("symbol") or ""))).upper()
            if target_coin and order_coin != target_coin:
                continue
            kind = self._target_kind_from_order(order)
            if kind == "tp" and not cancel_tp:
                continue
            if kind == "sl" and not cancel_sl:
                continue
            if kind not in {"tp", "sl"}:
                continue
            oid_raw = order.get("orderId")
            if oid_raw is None or not str(oid_raw).isdigit():
                continue
            oid = int(str(oid_raw))
            try:
                await asyncio.to_thread(exchange.cancel, order_coin, oid)
                canceled.append(str(oid))
            except Exception as exc:
                errors.append({"order_id": str(oid), "error": str(exc)})
        if canceled:
            await self.refresh_account_orders_from_rest()
        return {"canceled": canceled, "errors": errors}

    async def update_targets(self, **kwargs) -> Dict[str, Any]:
        symbol = kwargs.get("symbol") or ""
        side = str(kwargs.get("side") or "").upper()
        size = float(kwargs.get("size") or 0)
        take_profit = kwargs.get("take_profit")
        stop_loss = kwargs.get("stop_loss")
        cancel_existing = bool(kwargs.get("cancel_existing", False))
        cancel_tp = bool(kwargs.get("cancel_tp", False))
        cancel_sl = bool(kwargs.get("cancel_sl", False))

        if size <= 0:
            raise ValueError("Position size unavailable for TP/SL update")
        if take_profit is None and stop_loss is None and not cancel_existing and not cancel_tp and not cancel_sl:
            raise ValueError("No TP/SL updates requested.")

        exchange = self._require_exchange()
        coin = self._coin_from_symbol(symbol)
        close_is_buy = side in {"SHORT", "SELL"}

        canceled: Optional[Dict[str, Any]] = None
        if cancel_existing or cancel_tp or cancel_sl:
            canceled = await self.cancel_tpsl_orders(
                symbol=symbol,
                cancel_tp=cancel_existing or cancel_tp,
                cancel_sl=cancel_existing or cancel_sl,
            )

        placements: list[dict[str, Any]] = []
        requested = []
        if take_profit is not None:
            requested.append(("tp", float(take_profit)))
        if stop_loss is not None:
            requested.append(("sl", float(stop_loss)))

        for kind, trigger_px in requested:
            safe_trigger = self._wire_safe_float(trigger_px)
            order_type = {"trigger": {"isMarket": True, "triggerPx": safe_trigger, "tpsl": kind}}
            resp = await asyncio.to_thread(
                exchange.order,
                coin,
                bool(close_is_buy),
                self._wire_safe_float(size),
                safe_trigger,
                order_type,
                True,
            )
            placements.append(
                {
                    "kind": kind,
                    "trigger_price": safe_trigger,
                    "order_id": str(self._extract_oid(resp) or ""),
                    "raw": resp,
                }
            )
        await self.refresh_account_orders_from_rest()
        return {"symbol": symbol, "canceled": canceled, "placed": placements}

    def _require_exchange(self) -> Any:
        if self._exchange is None:
            raise ValueError("HL_AGENT_PRIVATE_KEY is required for Hyperliquid signed actions.")
        return self._exchange

    def _extract_oid(self, response: Any) -> Optional[int]:
        if not isinstance(response, dict):
            return None
        payload = response.get("response") or response
        data = payload.get("data") if isinstance(payload, dict) else None
        statuses = data.get("statuses") if isinstance(data, dict) else None
        if not isinstance(statuses, list):
            return None
        for status in statuses:
            if not isinstance(status, dict):
                continue
            resting = status.get("resting") or {}
            filled = status.get("filled") or {}
            for obj in (resting, filled):
                if not isinstance(obj, dict):
                    continue
                oid = obj.get("oid") or obj.get("orderId")
                if oid is not None:
                    try:
                        return int(oid)
                    except Exception:
                        continue
        return None
