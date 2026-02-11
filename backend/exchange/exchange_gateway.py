import asyncio
import inspect
import random
import time
import uuid
import threading
from collections import defaultdict, deque
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple, List, Any as AnyType

import requests

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.exchange.apex_client import ApexClient

logger = get_logger(__name__)


class ExchangeGateway:
    """Wrapper around ApeX Omni SDK with cached configs and basic helpers."""

    def __init__(self, settings: Settings, client: Optional[Any] = None, public_client: Optional[Any] = None) -> None:
        self.settings = settings
        self.venue = "apex"
        self._network = (getattr(settings, "apex_network", "testnet") or "testnet").lower()
        self._testnet = self._network in {"base", "base-sepolia", "testnet-base", "testnet"}
        self.apex_enable_ws = getattr(settings, "apex_enable_ws", False)
        self._configs_cache: Dict[str, Any] = {}
        self._account_cache: Dict[str, Any] = {}
        self._ws_prices: Dict[str, float] = {}
        self._ws_price_ts: Dict[str, float] = {}
        self._ws_orders: Dict[str, Dict[str, Any]] = {}
        self._ws_positions: Dict[str, Dict[str, Any]] = {}
        self._ws_orders_raw: list[Dict[str, Any]] = []
        self._ws_orders_tpsl: list[Dict[str, Any]] = []
        self._initial_orders_raw_logged = False
        self._empty_order_snapshots: int = 0
        self._configs_loaded_at: Optional[float] = None
        self._ws_running: bool = False
        self._ws_public: Optional[Any] = None
        self._ws_private: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._reconcile_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._resubscribe_task: Optional[asyncio.Task] = None
        self._order_refresh_task: Optional[asyncio.Task] = None
        self._positions_refresh_task: Optional[asyncio.Task] = None
        self._orders_poll_task: Optional[asyncio.Task] = None
        self._positions_poll_task: Optional[asyncio.Task] = None
        self._account_refresh_task: Optional[asyncio.Task] = None
        self._account_refresh_interval: float = 15.0
        self._orders_poll_interval_seconds = max(
            1.0,
            float(getattr(settings, "apex_poll_orders_interval_seconds", 5.0) or 5.0),
        )
        self._positions_poll_interval_seconds = max(
            1.0,
            float(getattr(settings, "apex_poll_positions_interval_seconds", 5.0) or 5.0),
        )
        self._account_poll_interval_seconds = max(
            1.0,
            float(getattr(settings, "apex_poll_account_interval_seconds", 15.0) or 15.0),
        )
        self._price_cache: dict[str, dict[str, Any]] = {}
        self._last_order_event_ts: float = time.time()
        self._last_public_ws_event_ts: float = 0.0
        self._last_private_ws_event_ts: float = 0.0
        self._last_pnl_recomputed_ts: float = 0.0
        self._last_upnl_source: Optional[str] = None
        self._last_upnl_updated_ts: float = 0.0
        self._ws_snapshot_written: bool = False
        self._tpsl_client_ids: Dict[str, set[str]] = {}
        self._reconcile_audit_interval = max(
            0.0,
            float(getattr(settings, "apex_reconcile_audit_interval_seconds", 900.0) or 0.0),
        )
        self._reconcile_stale_stream_seconds = max(
            0.0,
            float(getattr(settings, "apex_reconcile_stale_stream_seconds", 90.0) or 0.0),
        )
        self._reconcile_min_gap_seconds = max(
            0.0,
            float(getattr(settings, "apex_reconcile_min_gap_seconds", 5.0) or 0.0),
        )
        self._reconcile_alert_window_seconds = max(
            0.0,
            float(getattr(settings, "apex_reconcile_alert_window_seconds", 300.0) or 0.0),
        )
        self._reconcile_alert_max_per_window = max(
            1,
            int(getattr(settings, "apex_reconcile_alert_max_per_window", 3) or 1),
        )
        self._reconcile_lock = asyncio.Lock()
        self._reconcile_count = 0
        self._last_reconcile_ts = 0.0
        self._last_reconcile_reason: Optional[str] = None
        self._last_reconcile_error: Optional[str] = None
        self._reconcile_reason_counts: dict[str, int] = {}
        self._reconcile_reason_events: dict[str, deque[float]] = defaultdict(deque)
        self._fallback_reason_events: dict[str, deque[float]] = defaultdict(deque)
        self._last_alert_by_key: dict[str, float] = {}
        self._alert_min_interval_seconds = 60.0
        self._fallback_rest_orders_used_count = 0
        self._fallback_rest_positions_used_count = 0
        self._empty_snapshot_protected_count = 0
        self._tpsl_flap_suspected_count = 0
        self._degraded_mode_warning_emitted = False
        self._stream_started_at = 0.0
        self._suspicious_orders_empty_pending = False
        self._suspicious_positions_empty_pending = False
        self._lock = threading.Lock()
        fallback_public = public_client if public_client is not None else (client if client is not None else None)
        self.apex_client = ApexClient(settings, private_client=client, public_client=fallback_public)
        self._client: Any = self.apex_client.private_client
        self._public_client: Any = self.apex_client.public_client
        self._create_order_supports_kwargs: Optional[bool] = None
        self._create_order_supported_params: Optional[set[str]] = None
        self._rest_timeout_seconds = max(0.0, float(getattr(settings, "apex_rest_timeout_seconds", 10) or 0))
        self._rest_max_retries = max(0, int(getattr(settings, "apex_rest_retries", 0) or 0))
        self._rest_retry_backoff = max(0.0, float(getattr(settings, "apex_rest_retry_backoff_seconds", 0.5) or 0))
        self._rest_retry_backoff_max = max(0.0, float(getattr(settings, "apex_rest_retry_backoff_max_seconds", 4.0) or 0))
        self._rest_retry_jitter = max(0.0, float(getattr(settings, "apex_rest_retry_jitter_seconds", 0.2) or 0))
        self._positions_empty_stale_seconds = max(
            0.0, float(getattr(settings, "apex_positions_empty_stale_seconds", 12.0) or 0)
        )
        self._orders_empty_stale_seconds = max(
            0.0, float(getattr(settings, "apex_orders_empty_stale_seconds", 12.0) or 0)
        )
        self._ws_price_stale_seconds = max(
            0.0,
            float(getattr(settings, "apex_ws_price_stale_seconds", 30.0) or 0),
        )
        self._positions_empty_since: Optional[float] = None
        self._orders_empty_since: Optional[float] = None
        if self._rest_timeout_seconds > 0:
            try:
                self._client.timeout = self._rest_timeout_seconds
            except Exception:
                pass
        self._prime_client()
        self._ticker_cache: Dict[str, Dict[str, float]] = {}
        # logger.info(
        #     "gateway_initialized",
        #     extra={
        #         "event": "gateway_initialized",
        #         "network": self._network,
        #         "testnet": self._testnet,
        #         "ws_enabled": self.apex_enable_ws,
        #     },
        # )
        if not self._testnet:
            logger.warning(
                "non_testnet_network_detected",
                extra={"event": "network_warning", "network": self._network},
            )

    def _prime_client(self) -> None:
        """
        Best practice from ApeX docs: invoke configs_v3 and get_account_v3 immediately
        after client initialization so the SDK has configuration and account context.
        """
        try:
            cfg = self._client.configs_v3()
            if isinstance(cfg, dict):
                self._account_cache.setdefault("config", cfg)
        except Exception as exc:
            logger.warning("prime_client configs_v3 failed", extra={"error": str(exc)})
        try:
            acct = self._client.get_account_v3()
            payload = self._unwrap_payload(acct)
            if isinstance(payload, dict):
                self._account_cache.update(payload)
                account_candidates: list[dict[str, Any]] = []
                account_section = payload.get("account")
                if isinstance(account_section, dict):
                    contract_account = account_section.get("contractAccount")
                    if isinstance(contract_account, dict):
                        account_candidates.append(contract_account)
                    account_candidates.append(account_section)
                contract_account = payload.get("contractAccount")
                if isinstance(contract_account, dict):
                    account_candidates.append(contract_account)
                contract_accounts = payload.get("contractAccounts") or payload.get("accounts")
                if isinstance(contract_accounts, list) and contract_accounts:
                    first = contract_accounts[0]
                    if isinstance(first, dict):
                        account_candidates.append(first)
                account = next((cand for cand in account_candidates if isinstance(cand, dict)), {})
                if account.get("totalEquityValue") is not None:
                    self._account_cache.setdefault("totalEquityValue", account.get("totalEquityValue"))
                if account.get("availableBalance") is not None:
                    self._account_cache.setdefault("availableBalance", account.get("availableBalance"))
                withdrawable = (
                    account.get("withdrawable")
                    or account.get("withdrawableAmount")
                    or account.get("availableWithdrawable")
                    or payload.get("withdrawable")
                    or payload.get("withdrawableAmount")
                    or payload.get("availableWithdrawable")
                )
                if withdrawable is not None:
                    self._account_cache.setdefault("withdrawableAmount", withdrawable)
                if account.get("totalUnrealizedPnl") is not None:
                    self._account_cache.setdefault("totalUnrealizedPnl", account.get("totalUnrealizedPnl"))
        except Exception as exc:
            logger.warning("prime_client get_account_v3 failed", extra={"error": str(exc)})

    def _should_retry_rest(self, exc: Exception) -> bool:
        if isinstance(exc, requests.exceptions.RequestException):
            return True
        msg = str(exc).lower()
        return any(
            phrase in msg
            for phrase in (
                "read timed out",
                "connection aborted",
                "connection reset",
                "remote end closed connection",
                "temporarily unavailable",
                "timeout",
            )
        )

    async def _call_private_rest(self, label: str, func, **kwargs) -> Any:
        attempt = 0
        while True:
            try:
                return await asyncio.to_thread(func, **kwargs)
            except Exception as exc:
                if not self._should_retry_rest(exc) or attempt >= self._rest_max_retries:
                    raise
                delay = self._rest_retry_backoff * (2**attempt)
                if self._rest_retry_backoff_max > 0:
                    delay = min(delay, self._rest_retry_backoff_max)
                if self._rest_retry_jitter:
                    delay += random.uniform(0.0, self._rest_retry_jitter)
                attempt += 1
                logger.warning(
                    "rest_retrying",
                    extra={
                        "event": "rest_retrying",
                        "label": label,
                        "attempt": attempt,
                        "delay": round(delay, 3),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay)

    def _supports_create_order_field(self, field: str) -> bool:
        if self._create_order_supports_kwargs is None:
            supports_kwargs = False
            params: set[str] = set()
            try:
                signature = inspect.signature(self._client.create_order_v3)
                for name, param in signature.parameters.items():
                    if param.kind == inspect.Parameter.VAR_KEYWORD:
                        supports_kwargs = True
                    elif param.kind in (
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    ):
                        params.add(name)
            except Exception:
                # Conservative fallback: unknown signature, assume kwargs-capable.
                supports_kwargs = True
                params = set()
            self._create_order_supports_kwargs = supports_kwargs
            self._create_order_supported_params = params

        if self._create_order_supports_kwargs:
            return True
        return bool(self._create_order_supported_params and field in self._create_order_supported_params)

    def _sanitize_create_order_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        unsupported_by_design = {"clientOrderId", "limitFee", "expiration"}
        trigger_type_fields = {"tpTriggerPriceType", "slTriggerPriceType", "triggerPriceType"}
        sanitized = dict(payload)
        for key in unsupported_by_design:
            sanitized.pop(key, None)
        for key in trigger_type_fields:
            if key in sanitized and not self._supports_create_order_field(key):
                sanitized.pop(key, None)
        return sanitized

    # --- WebSocket helpers ---
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _ws_base_endpoint(self) -> str:
        return self.apex_client.ws_base_endpoint()

    async def start_streams(self) -> None:
        if not self.apex_enable_ws or self._ws_running:
            return
        self._ws_running = True
        self._stream_started_at = time.time()
        if self._last_reconcile_ts <= 0:
            self._last_reconcile_ts = self._stream_started_at
        await asyncio.to_thread(self._start_public_stream)
        await asyncio.to_thread(self._start_private_stream)
        if self._loop and (self._reconcile_task is None or self._reconcile_task.done()):
            self._reconcile_task = self._loop.create_task(self._reconcile_orders_loop())
        if self._loop and (self._ping_task is None or self._ping_task.done()):
            self._ping_task = self._loop.create_task(self._ping_loop())
        if self._loop and (self._resubscribe_task is None or self._resubscribe_task.done()):
            self._resubscribe_task = self._loop.create_task(self._resubscribe_loop())

    async def stop_streams(self) -> None:
        """Stop WS streams and background tasks."""
        self._ws_running = False
        for task in (
            self._reconcile_task,
            self._ping_task,
            self._resubscribe_task,
            self._order_refresh_task,
            self._positions_refresh_task,
            self._orders_poll_task,
            self._positions_poll_task,
            self._account_refresh_task,
        ):
            if task and not task.done():
                task.cancel()
        self._reconcile_task = None
        self._ping_task = None
        self._resubscribe_task = None
        self._order_refresh_task = None
        self._positions_refresh_task = None
        self._orders_poll_task = None
        self._positions_poll_task = None
        self._account_refresh_task = None
        for ws_client in (self._ws_public, self._ws_private):
            if not ws_client:
                continue
            try:
                await asyncio.to_thread(ws_client.close)
            except Exception:
                continue
        self._ws_public = None
        self._ws_private = None

    def clear_runtime_state(self) -> None:
        """Clear runtime caches before/after venue switches."""
        with self._lock:
            self._ws_prices.clear()
            self._ws_price_ts.clear()
            self._ws_orders.clear()
            self._ws_positions.clear()
            self._ws_orders_raw = []
            self._ws_orders_tpsl = []
            self._ticker_cache.clear()
            self._price_cache.clear()
            self._subscribers.clear()
            self._last_private_ws_event_ts = 0.0
            self._last_public_ws_event_ts = 0.0
            self._last_order_event_ts = time.time()
            self._suspicious_orders_empty_pending = False
            self._suspicious_positions_empty_pending = False

    def _start_public_stream(self) -> None:
        try:
            self._ws_public = self.apex_client.create_public_ws()
            self._ws_public.all_ticker_stream(self._handle_ticker)
            # logger.info("public WS stream started")
        except Exception as exc:
            logger.warning("public WS stream failed", extra={"error": str(exc)})

    def _start_private_stream(self) -> None:
        try:
            self._ws_private = self.apex_client.create_private_ws()
            # Use SDK helper to subscribe to account info stream (handles auth/ping)
            self._ws_private.account_info_stream_v3(self._handle_account_stream)
            # logger.info("private WS stream started and subscribed", extra={"topic": "ws_zk_accounts_v3"})
        except Exception as exc:
            logger.warning("private WS stream failed", extra={"error": str(exc)})

    def register_subscriber(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unregister_subscriber(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _publish_event(self, event: Dict[str, Any]) -> None:
        if not self._subscribers or not self._loop:
            return
        for q in list(self._subscribers):
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                continue
        if event.get("type") == "orders":
            # Keep cached orders published for any new subscribers.
            self._cached_orders_last = list(self._ws_orders.values())

    def _publish_cached_orders(self) -> None:
        if not self._loop:
            return
        self._publish_event({"type": "orders", "payload": list(self._ws_orders.values())})

    def _unwrap_payload(self, resp: Any) -> Any:
        """Handle Apex responses that wrap data under result/data or return bare lists."""
        if not isinstance(resp, dict):
            return resp
        for key in ("result", "data"):
            if key in resp:
                return resp.get(key)
        return resp

    def _format_with_step(self, value: float, step: Optional[float]) -> str:
        """Format numeric to a string respecting step precision."""
        if not step or step <= 0:
            return str(value)
        step_decimal = Decimal(str(step))
        quantized = Decimal(str(value)).quantize(step_decimal, rounding=ROUND_DOWN)
        return format(quantized, "f").rstrip("0").rstrip(".") if "." in format(quantized, "f") else str(quantized)

    def _current_account_summary(self) -> Optional[Dict[str, float]]:
        with self._lock:
            total_equity = self._account_cache.get("totalEquityValue")
            available = self._account_cache.get("availableBalance")
            total_upnl = self._account_cache.get("totalUnrealizedPnl")
            withdrawable = self._account_cache.get("withdrawableAmount")
        if total_equity is None and available is None and total_upnl is None:
            return None
        if withdrawable is None:
            withdrawable = available
        summary: Dict[str, Optional[float]] = {
            "total_equity": float(total_equity) if total_equity is not None else None,
            "available_margin": float(available) if available is not None else None,
            "total_upnl": float(total_upnl) if total_upnl is not None else None,
            "withdrawable_amount": float(withdrawable) if withdrawable is not None else None,
        }
        return summary

    def _publish_account_summary_event(self) -> None:
        summary = self._current_account_summary()
        if summary:
            self._publish_event({"type": "account", "payload": summary})

    def start_account_refresh(self, interval: Optional[float] = None) -> None:
        if interval is not None:
            self._account_refresh_interval = interval
        if not self._loop:
            return
        if self._account_refresh_task is None or self._account_refresh_task.done():
            self._account_refresh_task = self._loop.create_task(self._account_refresh_loop())
        if not self.apex_enable_ws:
            if not self._degraded_mode_warning_emitted:
                self._degraded_mode_warning_emitted = True
                logger.warning(
                    "apex_ws_disabled_degraded_mode",
                    extra={
                        "event": "apex_ws_disabled_degraded_mode",
                        "poll_orders_interval_seconds": self._orders_poll_interval_seconds,
                        "poll_positions_interval_seconds": self._positions_poll_interval_seconds,
                        "poll_account_interval_seconds": self._account_poll_interval_seconds,
                    },
                )
            if self._orders_poll_task is None or self._orders_poll_task.done():
                self._orders_poll_task = self._loop.create_task(self._orders_poll_loop())
            if self._positions_poll_task is None or self._positions_poll_task.done():
                self._positions_poll_task = self._loop.create_task(self._positions_poll_loop())

    async def _account_refresh_loop(self) -> None:
        """Periodically refresh account summary so UI receives live updates."""
        default_interval = self._account_poll_interval_seconds if not self.apex_enable_ws else 15.0
        interval = max(1.0, float(self._account_refresh_interval or default_interval))
        while True:
            try:
                await asyncio.sleep(interval)
                await self.get_account_equity()
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def _orders_poll_loop(self) -> None:
        interval = max(1.0, float(self._orders_poll_interval_seconds or 5.0))
        while True:
            try:
                await asyncio.sleep(interval)
                await self.get_open_orders(force_rest=True, publish=True)
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def _positions_poll_loop(self) -> None:
        interval = max(1.0, float(self._positions_poll_interval_seconds or 5.0))
        while True:
            try:
                await asyncio.sleep(interval)
                await self.get_open_positions(force_rest=True, publish=True)
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    def _get_worst_price(self, symbol: str) -> Optional[float]:
        """Fetch worst price for symbol from documented endpoint."""
        endpoints = []
        if self.settings.apex_http_endpoint:
            endpoints.append(self.settings.apex_http_endpoint)
        endpoints.extend(
            [
                "https://testnet.omni.apex.exchange",
                "https://omni.apex.exchange",
            ]
        )
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        param_symbol = (symbol or "").replace("-", "").upper()
        for ep in endpoints:
            try:
                url = ep.rstrip("/") + "/api/v3/get-worst-price"
                resp = session.get(url, params={"symbol": param_symbol}, timeout=5)
                data = resp.json()
                result = data.get("result") or data.get("data") or data
                if isinstance(result, dict):
                    price = result.get("worstPrice") or result.get("bidOnePrice") or result.get("askOnePrice")
                    if price:
                        return float(price)
            except Exception:
                continue
        return None

    async def _get_usdt_price(self, token: str) -> float:
        """Fetch price for TOKEN-USDT via worst-price, fallback to ticker, then hardcoded 1.0 for ETH."""
        if token.upper() == "USDT":
            return 1.0
        symbol = f"{token.upper()}-USDT"
        try:
            ticker = await asyncio.to_thread(self._public_client.ticker_v3, symbol=symbol)
            result = ticker.get("result") or {}
            entries = result if isinstance(result, list) else [result]
            for entry in entries:
                price = (
                    entry.get("lastPrice")
                    or entry.get("markPrice")
                    or entry.get("price")
                )
                if price:
                    return float(price)
        except Exception as exc:
            logger.warning("ticker_v3 failed", extra={"symbol": symbol, "error": str(exc)})
        try:
            worst = await asyncio.to_thread(self._get_worst_price, symbol)
            if worst is not None:
                return worst
        except Exception:
            pass
        # Fallback: call ticker via HTTP on known endpoints without SDK
        endpoints = []
        if self.settings.apex_http_endpoint:
            endpoints.append(self.settings.apex_http_endpoint)
        endpoints.extend(
            [
                "https://testnet.omni.apex.exchange",
                "https://omni.apex.exchange",
            ]
        )
        session = requests.Session()
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        for ep in endpoints:
            try:
                url = ep.rstrip("/") + "/api/v3/ticker"
                resp = session.get(url, params={"symbol": symbol.replace("-", "")}, timeout=5)
                data = resp.json()
                result = data.get("result") or data.get("data") or data
                if isinstance(result, dict) and "data" in result:
                    result = result["data"]
                entries = result if isinstance(result, list) else [result]
                for entry in entries:
                    if isinstance(entry, dict):
                        price = entry.get("lastPrice") or entry.get("price") or entry.get("markPrice")
                        if price:
                            return float(price)
            except Exception:
                continue
        if token.upper() == "ETH":
            logger.warning("Using fallback ETH price", extra={"symbol": symbol})
            return 2000.0
        raise ValueError(f"No price for {symbol}")

    # --- WebSocket callbacks and helpers ---
    def _handle_ticker(self, message: Dict[str, Any]) -> None:
        now_ts = time.time()
        self._last_public_ws_event_ts = now_ts
        data = message.get("data") if isinstance(message, dict) else None
        # Flatten possible update wrapper
        entries: list[AnyType] = []
        if isinstance(data, dict) and "update" in data:
            entries.extend(data.get("update") or [])
        elif isinstance(data, list):
            entries.extend(data)
        elif isinstance(data, dict):
            entries.append(data)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            symbol = (
                entry.get("symbol")
                or entry.get("s")
                or self._parse_symbol_from_topic(message.get("topic"))
            )
            price = (
                entry.get("markPrice")
                or entry.get("lastPrice")
                or entry.get("price")
                or entry.get("p")
                or entry.get("xp")
            )
            if not symbol or price is None:
                continue
            try:
                price_f = float(price)
            except Exception:
                continue
            publish_positions = False
            summary_changed = False
            with self._lock:
                norm_symbol = self._normalize_symbol_value(symbol)
                self._ws_prices[norm_symbol] = price_f
                self._ws_price_ts[norm_symbol] = now_ts
                self._ticker_cache[norm_symbol] = {"price": price_f, "ts": now_ts}
                self._price_cache[norm_symbol] = {"price": price_f, "ts": now_ts, "source": "ws_ticker"}
                publish_positions = self._update_positions_pnl(norm_symbol, price_f)
                if publish_positions:
                    self._recalculate_total_upnl_locked()
                    summary_changed = True
            self._publish_event({"type": "ticker", "symbol": self._normalize_symbol_value(symbol), "price": price_f})
            if publish_positions:
                self._publish_event({"type": "positions", "payload": list(self._ws_positions.values())})
            if summary_changed:
                self._publish_account_summary_event()

    def _handle_account_stream(self, message: Dict[str, Any]) -> None:
        payload = None
        if isinstance(message, dict):
            payload = message.get("contents") or message.get("data") or message
        if not isinstance(payload, dict):
            return
        now = time.time()
        self._last_private_ws_event_ts = now
        self._last_order_event_ts = now
        accounts = payload.get("accounts") or payload.get("account") or payload.get("contractAccounts") or []
        positions, has_positions_key = self._extract_positions(payload)
        orders_raw = payload.get("orders") or payload.get("orderList") or []
        has_orders_key = any(k in payload for k in ("orders", "orderList"))

        publish_orders = False
        publish_positions = False
        summary_changed = False
        total_equity_stream = payload.get("totalEquityValue") or payload.get("totalEquity") or None
        available_balance_stream = payload.get("availableBalance") or payload.get("available_margin")
        withdrawable_stream = (
            payload.get("withdrawable")
            or payload.get("withdrawableAmount")
            or payload.get("availableWithdrawable")
        )
        total_upnl_stream = (
            payload.get("totalUnrealizedPnl")
            or payload.get("totalUnrealizedPnlUsd")
            or payload.get("totalUpnl")
        )

        if has_positions_key and not positions:
            total_upnl_stream = None

        with self._lock:
            if accounts:
                acct = accounts[0] if isinstance(accounts, list) and accounts else accounts
                if isinstance(acct, dict):
                    self._account_cache.update({"account": acct})
                    if total_equity_stream is None:
                        total_equity_stream = acct.get("totalEquityValue") or acct.get("totalEquity")
                    if available_balance_stream is None:
                        available_balance_stream = acct.get("availableBalance") or acct.get("available_margin")
                    if withdrawable_stream is None:
                        withdrawable_stream = (
                            acct.get("withdrawable")
                            or acct.get("withdrawableAmount")
                            or acct.get("availableWithdrawable")
                        )
                    if total_upnl_stream is None:
                        total_upnl_stream = (
                            acct.get("totalUnrealizedPnl")
                            or acct.get("totalUnrealizedPnlUsd")
                            or acct.get("totalUpnl")
                        )
                    # logger.info(
                    #     "account_stream_update",
                    #     extra={
                    #         "event": "account_stream_update",
                    #         "payload_keys": list(acct.keys()),
                    #         "total_equity_stream": total_equity_stream,
                    #         "available_stream": available_balance_stream,
                    #         "total_upnl_stream": total_upnl_stream,
                    #     },
                    # )
            if positions:
                mapped = {self._normalize_symbol(p): p for p in positions if isinstance(p, dict)}
                if mapped:
                    self._ws_positions = {**self._ws_positions, **mapped}
                    publish_positions = True
        if total_equity_stream is not None:
            self._account_cache["totalEquityValue"] = total_equity_stream
        if available_balance_stream is not None:
            self._account_cache["availableBalance"] = available_balance_stream
        if withdrawable_stream is not None:
            self._account_cache["withdrawableAmount"] = withdrawable_stream
        if total_upnl_stream is not None:
            self._account_cache["totalUnrealizedPnl"] = total_upnl_stream
            self._last_upnl_source = "ws_account_stream"
            self._last_upnl_updated_ts = time.time()
        if (
            total_upnl_stream is not None
            or total_equity_stream is not None
            or available_balance_stream is not None
            or withdrawable_stream is not None
        ):
            summary_changed = True
        if summary_changed:
            self._publish_account_summary_event()
        # Positions: trigger REST refresh to avoid dropping on partial WS snapshots
        if has_positions_key and self._loop and (self._positions_refresh_task is None or self._positions_refresh_task.done()):
            self._positions_refresh_task = self._loop.create_task(self._refresh_positions_now())
        # Orders: trigger REST refresh for authoritative list instead of applying partial WS payloads
        if has_orders_key and self._loop and (self._order_refresh_task is None or self._order_refresh_task.done()):
            self._order_refresh_task = self._loop.create_task(self._refresh_orders_now())
        # Cache WS orders immediately so downstream callers can see TP/SL orders before REST reconciliation.
        if orders_raw:
            try:
                mapped = self._filter_and_map_orders(orders_raw)
                if mapped:
                    self._ws_orders = mapped
            except Exception:
                pass

        if publish_positions:
            self._publish_event({"type": "positions", "payload": list(self._ws_positions.values())})
        if orders_raw:
            # cache raw account orders for TP/SL mapping and publish to subscribers
            position_tpsl_payload: list[Dict[str, Any]] = []
            canceled_tpsl_payload: list[Dict[str, Any]] = []
            # Only replace cached raw orders when the payload actually carries position TP/SL entries;
            # canceled-only snapshots should not blow away the last known TP/SL order ids.
            if isinstance(orders_raw, list):
                position_tpsl_payload = [
                    o
                    for o in orders_raw
                    if isinstance(o, dict)
                    and o.get("isPositionTpsl")
                    and str(o.get("type") or "").upper().startswith(("STOP", "TAKE_PROFIT"))
                    and str(o.get("status") or "").lower() not in {"canceled", "cancelled", "filled", "triggered"}
                ]
                canceled_tpsl_payload = [
                    o
                    for o in orders_raw
                    if isinstance(o, dict)
                    and o.get("isPositionTpsl")
                    and str(o.get("type") or "").upper().startswith(("STOP", "TAKE_PROFIT"))
                    and str(o.get("status") or "").lower() in {"canceled", "cancelled"}
                ]

            if position_tpsl_payload:
                # Merge with existing active TP/SL entries to avoid losing the opposite side on partial payloads.
                def _order_key(o: Dict[str, Any]) -> str:
                    oid = o.get("orderId") or o.get("order_id") or o.get("id")
                    cid = o.get("clientOrderId") or o.get("clientId")
                    return str(oid or cid or uuid.uuid4())

                existing_active = [
                    o
                    for o in (self._ws_orders_tpsl or [])
                    if isinstance(o, dict)
                    and str(o.get("status") or "").lower() not in {"canceled", "cancelled", "filled", "triggered"}
                ]
                combined = {_order_key(o): o for o in existing_active}
                for o in position_tpsl_payload:
                    combined[_order_key(o)] = o
                merged_tpsl = list(combined.values())
                self._ws_orders_tpsl = merged_tpsl
                self._ws_orders_raw = merged_tpsl
            elif not self._ws_orders_raw and isinstance(orders_raw, list):
                # if no cache yet, initialize it once even if no active entries
                self._ws_orders_raw = orders_raw
                self._ws_orders_tpsl = []

            # Drop any canceled TP/SL entries from the active cache.
            if canceled_tpsl_payload and self._ws_orders_tpsl:
                def _matches(cancel_entry: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
                    cid = cancel_entry.get("clientOrderId") or cancel_entry.get("clientId")
                    oid = cancel_entry.get("orderId") or cancel_entry.get("order_id") or cancel_entry.get("id")
                    cand_cid = candidate.get("clientOrderId") or candidate.get("clientId")
                    cand_oid = candidate.get("orderId") or candidate.get("order_id") or candidate.get("id")
                    if cid and cand_cid and str(cid) == str(cand_cid):
                        return True
                    if oid and cand_oid and str(oid) == str(cand_oid):
                        return True
                    return False

                self._ws_orders_tpsl = [
                    o for o in self._ws_orders_tpsl if not any(_matches(c, o) for c in canceled_tpsl_payload)
                ]
                self._ws_orders_raw = list(self._ws_orders_tpsl)

            position_tpsl_count = len(self._ws_orders_tpsl or [])
            # logger.info(
            #     "ws_orders_raw_received",
            #     extra={
            #         "event": "ws_orders_raw_received",
            #         "count": len(self._ws_orders_raw) if isinstance(self._ws_orders_raw, list) else 0,
            #         "position_tpsl": position_tpsl_count,
            #         "first_type": (self._ws_orders_tpsl[0].get("type") if self._ws_orders_tpsl else None),
            #         "first_status": (self._ws_orders_tpsl[0].get("status") if self._ws_orders_tpsl else None),
            #         "first_symbol": (self._ws_orders_tpsl[0].get("symbol") if self._ws_orders_tpsl else None),
            #         "first_is_position_tpsl": (self._ws_orders_tpsl[0].get("isPositionTpsl") if self._ws_orders_tpsl else None),
            #         "first_trigger": (
            #             self._ws_orders_tpsl[0].get("triggerPrice")
            #             if self._ws_orders_tpsl
            #             else None
            #         ),
            #     },
            # )
            if not self._initial_orders_raw_logged:
                self._initial_orders_raw_logged = True
                try:
                    # logger.info(
                    #     "orders_raw_initial_payload",
                    #     extra={
                    #         "event": "orders_raw_initial_payload",
                    #         "payload": orders_raw,
                    #     },
                    # )
                    pass
                except Exception:
                    pass
            # Publish the original payload so downstream reconcilers see canceled entries too.
            self._publish_event({"type": "orders_raw", "payload": orders_raw})

    def _parse_symbol_from_topic(self, topic: Optional[str]) -> Optional[str]:
        if not topic or not isinstance(topic, str):
            return None
        parts = topic.split(".")
        if parts:
            return parts[-1]
        return None

    def _normalize_symbol(self, payload: Dict[str, Any]) -> str:
        raw = payload.get("symbol") or payload.get("market") or payload.get("pair") or ""
        return self._normalize_symbol_value(raw)

    def _normalize_symbol_value(self, symbol: str) -> str:
        if not symbol:
            return ""
        sym = str(symbol).upper()
        if "-" in sym:
            return sym
        for quote in ("USDT", "USDC", "USDC.E", "USD"):
            if sym.endswith(quote):
                return f"{sym[:-len(quote)]}-{quote}"
        return sym

    def _update_positions_pnl(self, symbol: str, mark_price: float) -> bool:
        changed = False
        for pos in self._ws_positions.values():
            sym = self._normalize_symbol(pos)
            if sym != symbol:
                continue
            entry = (
                pos.get("entryPrice")
                or pos.get("avgPrice")
                or pos.get("avgEntryPrice")
                or pos.get("entry_price")
            )
            size = pos.get("size") or pos.get("positionSize")
            side = (pos.get("side") or pos.get("positionSide") or pos.get("direction") or "").upper()
            try:
                entry_f = float(entry)
                size_f = float(size)
            except Exception:
                continue
            pnl = (mark_price - entry_f) * size_f
            if side in {"SHORT", "SELL"}:
                pnl = -pnl
            pos["pnl"] = pnl
            changed = True
        return changed

    def _recalculate_total_upnl_locked(self) -> float:
        total = 0.0
        for pos in self._ws_positions.values():
            pnl = pos.get("pnl")
            try:
                total += float(pnl)
            except Exception:
                continue
        self._account_cache["totalUnrealizedPnl"] = total
        self._last_pnl_recomputed_ts = time.time()
        self._last_upnl_source = "ws"
        self._last_upnl_updated_ts = self._last_pnl_recomputed_ts
        return total

    def _ws_pnl_is_fresh(self, *, now: Optional[float] = None) -> bool:
        ts_now = now if now is not None else time.time()
        if not self.apex_enable_ws:
            return False
        if self._last_public_ws_event_ts <= 0 or self._last_pnl_recomputed_ts <= 0:
            return False
        ws_age = ts_now - self._last_public_ws_event_ts
        pnl_age = ts_now - self._last_pnl_recomputed_ts
        freshness = max(5.0, float(self._ws_price_stale_seconds or 0.0))
        return ws_age <= freshness and pnl_age <= freshness

    def _filter_and_map_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        mapped: Dict[str, Dict[str, Any]] = {}
        for o in orders:
            if not isinstance(o, dict):
                continue
            # Skip TP/SL reduce-only helpers; the UI has dedicated controls for these and Apex
            # does not display them alongside discretionary orders.
            if self._is_tpsl_order_payload(o):
                continue
            status = str(o.get("status") or o.get("orderStatus") or "").lower()
            if status in {"canceled", "cancelled", "filled"} or "cancel" in status:
                continue
            key = (
                o.get("orderId")
                or o.get("order_id")
                or o.get("clientOrderId")
                or o.get("clientId")
                or o.get("_cache_id")
                or uuid.uuid4().hex
            )
            key = str(key)
            o["_cache_id"] = key
            mapped[key] = o
        return mapped

    def _extract_positions(self, payload: Dict[str, Any]) -> tuple[list[Dict[str, Any]], bool]:
        if not isinstance(payload, dict):
            return [], False
        positions_lists: list[list] = []
        has_key = False
        for key in ("positions", "positionVoList", "positionVos", "positionVOs"):
            if key in payload:
                has_key = True
                val = payload.get(key) or []
                if isinstance(val, list):
                    positions_lists.append(val)
        for key, val in payload.items():
            if "position" in key.lower() and isinstance(val, list):
                has_key = True
                positions_lists.append(val)
        combined: list[Dict[str, Any]] = []
        for lst in positions_lists:
            for item in lst:
                if isinstance(item, dict) and self._is_active_position(item):
                    combined.append(item)
        return combined, has_key

    def _is_active_position(self, pos: Dict[str, Any]) -> bool:
        if not isinstance(pos, dict):
            return False
        if str(pos.get("type") or "").upper() in {"CLOSE_POSITION", "LIQUIDATION"}:
            return False
        size_raw = pos.get("size") or pos.get("positionSize")
        try:
            size_f = float(size_raw)
        except Exception:
            return False
        return size_f > 0

    # --- Cancel helpers ---
    def _extract_code_status(self, resp: Any) -> Tuple[Optional[Any], Optional[Any]]:
        if not isinstance(resp, dict):
            return None, resp if isinstance(resp, str) else None
        code = resp.get("code") or resp.get("retCode")
        status = resp.get("status") or resp.get("retMsg")
        result = resp.get("result") or resp.get("data") or {}
        if isinstance(result, dict):
            code = code or result.get("code")
            status = status or result.get("status") or result.get("retMsg")
        return code, status

    def _is_conflict_or_notfound(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return "errcode: 409" in msg or "not found" in msg or "could not decode json" in msg

    def _retry_delete_on_conflict(self, func, *args, **kwargs) -> Dict[str, Any]:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not self._is_conflict_or_notfound(exc):
                raise
            time.sleep(0.3)
            return func(*args, **kwargs)

    async def list_symbols(self) -> list[Dict[str, Any]]:
        """Return cached symbol configs; load if missing."""
        try:
            if not self._configs_cache:
                await self.load_configs()
        except Exception as exc:
            logger.warning("list_symbols_failed", extra={"event": "list_symbols_failed", "error": str(exc)})
        return list(self._configs_cache.values())

    async def get_account_summary(self) -> Dict[str, Any]:
        """Return simple account summary for UI; tolerate missing fields."""
        with self._lock:
            total_equity = self._account_cache.get("totalEquityValue")
            available = self._account_cache.get("availableBalance")
            total_upnl = self._account_cache.get("totalUnrealizedPnl")
        if total_equity is None or available is None:
            try:
                await self.get_account_equity()
            except Exception:
                pass
            with self._lock:
                if total_equity is None:
                    total_equity = self._account_cache.get("totalEquityValue")
                if available is None:
                    available = self._account_cache.get("availableBalance")
                if total_upnl is None:
                    total_upnl = self._account_cache.get("totalUnrealizedPnl")
        if total_equity is None or available is None or total_upnl is None:
            # logger.info(
            #     "account_summary_cache_miss",
            #     extra={
            #         "event": "account_summary_cache_miss",
            #         "cached_keys": list(self._account_cache.keys()),
            #         "has_equity": total_equity is not None,
            #         "has_available": available is not None,
            #         "has_upnl": total_upnl is not None,
            #     },
            # )
            try:
                resp = await self._call_private_rest("get_account_v3", self._client.get_account_v3)
                payload = self._unwrap_payload(resp)
                payload_dict = payload if isinstance(payload, dict) else {}
                account_candidates: list[dict[str, Any]] = []
                account_section = payload_dict.get("account")
                if isinstance(account_section, dict):
                    contract_account = account_section.get("contractAccount")
                    if isinstance(contract_account, dict):
                        account_candidates.append(contract_account)
                    account_candidates.append(account_section)
                contract_account = payload_dict.get("contractAccount")
                if isinstance(contract_account, dict):
                    account_candidates.append(contract_account)
                contract_accounts = payload_dict.get("contractAccounts") or payload_dict.get("accounts")
                if isinstance(contract_accounts, list) and contract_accounts:
                    first = contract_accounts[0]
                    if isinstance(first, dict):
                        account_candidates.append(first)
                account = next((cand for cand in account_candidates if isinstance(cand, dict)), {})
                total_equity = (
                    account.get("totalEquity")
                    or payload_dict.get("totalEquityValue")
                    or payload_dict.get("totalEquity")
                    or total_equity
                )
                available = (
                    account.get("availableBalance")
                    or payload_dict.get("availableBalance")
                    or payload_dict.get("available_margin")
                    or available
                )
                withdrawable = (
                    account.get("withdrawable")
                    or account.get("withdrawableAmount")
                    or account.get("availableWithdrawable")
                    or payload_dict.get("withdrawable")
                    or payload_dict.get("withdrawableAmount")
                    or payload_dict.get("availableWithdrawable")
                )
                total_upnl = (
                    account.get("totalUnrealizedPnl")
                    or account.get("totalUnrealizedPnlUsd")
                    or payload_dict.get("totalUnrealizedPnl")
                    or payload_dict.get("totalUnrealizedPnlUsd")
                    or payload_dict.get("totalUpnl")
                    or total_upnl
                )
                with self._lock:
                    if total_equity is not None:
                        self._account_cache["totalEquityValue"] = total_equity
                    if available is not None:
                        self._account_cache["availableBalance"] = available
                    if withdrawable is not None:
                        self._account_cache["withdrawableAmount"] = withdrawable
                    if total_upnl is not None:
                        self._account_cache["totalUnrealizedPnl"] = total_upnl
                # logger.info(
                #     "account_summary_refetched",
                #     extra={
                #         "event": "account_summary_refetched",
                #         "payload_keys": list(payload_dict.keys()),
                #         "account_keys": list(account.keys()),
                #         "total_equity": total_equity,
                #         "available": available,
                #         "total_upnl": total_upnl,
                #     },
                # )
            except Exception:
                pass
        # logger.info(
        #     "account_summary_snapshot",
        #     extra={
        #         "event": "account_summary_snapshot",
        #         "total_equity": total_equity,
        #         "available": available,
        #         "total_upnl": total_upnl,
        #     },
        # )
        summary = self._current_account_summary()
        if summary:
            return summary
        return {"total_equity": 0.0, "total_upnl": 0.0, "available_margin": 0.0, "withdrawable_amount": 0.0}

    async def load_configs(self) -> None:
        """Fetch and cache symbol configs."""
        try:
            # Use private client per ApeX requirement to ensure configV3 is populated for signatures.
            result = await asyncio.to_thread(self._client.configs_v3)
            payload = result.get("result") or result.get("data") or {}

            symbols: list[Dict[str, Any]] = []
            if "symbols" in payload:
                symbols = payload.get("symbols", []) or []
            else:
                contract_cfg = payload.get("contractConfig", {}) or {}
                symbols = contract_cfg.get("perpetualContract", []) or []

            mapped: Dict[str, Dict[str, Any]] = {}
            for item in symbols:
                try:
                    mapped[item["symbol"]] = {
                        "symbol": item.get("symbol"),
                        "tickSize": float(item.get("tickSize", 0.0)),
                        "stepSize": float(item.get("stepSize", 0.0)),
                        "minOrderSize": float(item.get("minOrderSize", 0.0)),
                        "maxOrderSize": float(
                            item.get("maxOrderSize") or item.get("maxPositionSize") or 0.0
                        ),
                        "maxLeverage": float(
                            item.get("displayMaxLeverage") or item.get("maxLeverage") or 0.0
                        ),
                        "baseAsset": item.get("baseTokenId") or item.get("baseAsset"),
                        "quoteAsset": item.get("settleAssetId") or item.get("quoteAsset"),
                        "status": item.get("status") or ("ENABLED" if item.get("enableTrade") else "DISABLED"),
                        "raw": item,
                    }
                except Exception:
                    continue

            self._configs_cache = mapped
        except Exception as exc:  # pragma: no cover
            logger.warning("load_configs_failed", extra={"event": "load_configs_failed", "error": str(exc)})
            # Preserve full config payload for SDK methods that expect configV3
            try:
                setattr(self._client, "configV3", payload)
            except Exception:
                pass
            self._configs_loaded_at = time.time()
            # logger.info(
            #     "configs_cached",
            #     extra={
            #         "event": "configs_cached",
            #         "count": len(self._configs_cache),
            #         "network": self._network,
            #         "testnet": self._testnet,
            #     },
            # )
        except Exception as exc:
            logger.exception("failed to load configs", extra={"error": str(exc)})
            raise

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._configs_cache.get(symbol)

    async def get_mark_price(self, symbol: str) -> float:
        """Return latest mark/last price for symbol, preferring WS cache."""
        norm_symbol = self._normalize_symbol_value(symbol)
        with self._lock:
            cached = self._ws_prices.get(norm_symbol)
        if cached is not None:
            return cached
        ticker = await asyncio.to_thread(self._public_client.ticker_v3, symbol=symbol)
        result = ticker.get("result") or ticker.get("data") or ticker
        entries = result if isinstance(result, list) else [result]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            price = (
                entry.get("markPrice")
                or entry.get("lastPrice")
                or entry.get("price")
                or entry.get("indexPrice")
            )
            if price:
                return float(price)
        raise ValueError(f"No ticker price for {symbol}")

    async def fetch_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[Dict[str, Any]]:
        """Venue-agnostic candle fetch used by ATR endpoints."""
        return await asyncio.to_thread(self.apex_client.fetch_klines, symbol, timeframe, limit)

    def _extract_reference_price(self, entry: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
        mid_candidates = [
            entry.get("midPrice"),
            entry.get("mid"),
            entry.get("mid_price"),
        ]
        for candidate in mid_candidates:
            try:
                if candidate is not None:
                    return float(candidate), "mid"
            except Exception:
                continue

        try:
            bid = float(entry.get("bidPrice") or entry.get("bid") or entry.get("bestBid"))
            ask = float(entry.get("askPrice") or entry.get("ask") or entry.get("bestAsk"))
            if bid > 0 and ask > 0:
                return (bid + ask) / 2.0, "mid"
        except Exception:
            pass

        mark_candidates = [
            entry.get("markPrice"),
            entry.get("oraclePrice"),
            entry.get("indexPrice"),
        ]
        for candidate in mark_candidates:
            try:
                if candidate is not None:
                    return float(candidate), "mark"
            except Exception:
                continue

        last_candidates = [
            entry.get("lastPrice"),
            entry.get("price"),
            entry.get("last"),
        ]
        for candidate in last_candidates:
            try:
                if candidate is not None:
                    return float(candidate), "last"
            except Exception:
                continue
        return None, None

    async def get_reference_price(self, symbol: str) -> Tuple[float, str]:
        """
        WS-first reference price:
        1) fresh WS ticker for symbol
        2) REST ticker_v3 (mid/mark/last)
        3) legacy fallback last price
        """
        norm_symbol = self._normalize_symbol_value(symbol)
        now = time.time()

        # Prefer live WS symbol price indefinitely, only forcing REST when stale.
        ws_price: Optional[float] = None
        ws_ts: Optional[float] = None
        with self._lock:
            cached_ws = self._ws_prices.get(norm_symbol)
            if cached_ws is not None:
                ws_price = float(cached_ws)
                ws_ts = float(self._ws_price_ts.get(norm_symbol) or 0.0)
        if ws_price is not None:
            if ws_ts and self._ws_price_stale_seconds > 0 and (now - ws_ts) > self._ws_price_stale_seconds:
                # Stale stream value: attempt REST refresh below.
                pass
            else:
                self._price_cache[norm_symbol] = {"price": ws_price, "ts": now, "source": "ws_ticker"}
                return ws_price, "ws_ticker"

        # Short-lived non-WS cache fallback keeps UI responsive during transient REST blips.
        cache_entry = self._price_cache.get(norm_symbol)
        if cache_entry:
            cache_source = str(cache_entry.get("source") or "cache")
            if cache_source != "ws_ticker" and (now - float(cache_entry.get("ts") or 0.0)) < 10:
                return float(cache_entry["price"]), cache_source

        try:
            ticker = await asyncio.to_thread(self._public_client.ticker_v3, symbol=symbol)
            result = ticker.get("result") or ticker.get("data") or ticker
            entries = result if isinstance(result, list) else [result]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                price, source = self._extract_reference_price(entry)
                if price is None:
                    continue
                self._price_cache[norm_symbol] = {
                    "price": float(price),
                    "ts": now,
                    "source": source or "ticker",
                }
                return float(price), (source or "ticker")
        except Exception:
            # If REST fails and we still have a WS value, return it as stale fallback.
            if ws_price is not None:
                return ws_price, "ws_ticker_stale"

        # Final fallback keeps legacy behavior for Apex.
        fallback = await self.get_symbol_last_price(symbol)
        self._price_cache[norm_symbol] = {"price": float(fallback), "ts": now, "source": "fallback_last"}
        return float(fallback), "fallback_last"

    async def ensure_configs_loaded(self) -> None:
        """Load configs if not already cached."""
        needs_refresh = not self._configs_cache
        if self._configs_loaded_at:
            age = time.time() - self._configs_loaded_at
            if age > 300:
                needs_refresh = True
        if needs_refresh:
            await self.load_configs()
        if not self._configs_cache:
            raise RuntimeError("Exchange symbol configs unavailable; aborting request")

    async def _ensure_account_cached(self) -> None:
        """Ensure account info is cached so we can derive fee rates/limits without extra calls."""
        if self._account_cache:
            return
        try:
            acct = await self._call_private_rest("get_account_v3", self._client.get_account_v3)
            if isinstance(acct, dict):
                payload = acct.get("result") or acct
                self._account_cache.update(payload if isinstance(payload, dict) else {})
        except Exception as exc:
            logger.warning("failed to cache account info", extra={"error": str(exc)})

    def _get_taker_fee_rate(self) -> Optional[str]:
        """Use takerFeeRate from cached account info to cap fee charges on orders."""
        account = None
        if isinstance(self._account_cache, dict):
            account = self._account_cache.get("account") or self._account_cache.get("contractAccount")
        rate = None
        if isinstance(account, dict):
            for key in ("takerFeeRate", "takerFee", "takerRate"):
                val = account.get(key)
                if val is not None:
                    rate = val
                    break
        if rate is None:
            return None
        try:
            dec = Decimal(str(rate)).quantize(Decimal("0.000000"), rounding=ROUND_DOWN)
            return format(dec, "f")
        except Exception:
            return str(rate)

    async def get_account_equity(self) -> float:
        try:
            # Preferred per docs: account-balance endpoint for totalEquity/availableBalance.
            account_balance_fn = getattr(self._client, "get_account_balance_v3", None)
            if callable(account_balance_fn):
                try:
                    acct = await self._call_private_rest("get_account_balance_v3", account_balance_fn)
                    if acct and isinstance(acct, dict):
                        payload = acct.get("result") or acct.get("data") or acct
                        account = payload.get("account") if isinstance(payload, dict) else None
                        account_equity = None
                        available_balance = None
                        withdrawable_amount = None
                        realized_pnl = None
                        total_upnl = None
                        if isinstance(payload, dict):
                            account_equity = payload.get("totalEquityValue")
                            available_balance = payload.get("availableBalance")
                            withdrawable_amount = (
                                payload.get("withdrawable")
                                or payload.get("withdrawableAmount")
                                or payload.get("availableWithdrawable")
                            )
                            realized_pnl = payload.get("realizedPnl")
                            total_upnl = (
                                payload.get("totalUnrealizedPnl")
                                or payload.get("totalUpnl")
                                or payload.get("unrealizedPnl")
                            )
                            # logger.info(
                            #     "account_balance_payload",
                            #     extra={
                            #         "event": "account_balance_payload",
                            #         "payload_keys": list(payload.keys()),
                            #         "account_keys": list(account.keys()) if isinstance(account, dict) else [],
                            #         "raw_total_upnl": payload.get("totalUnrealizedPnl")
                            #         or payload.get("totalUpnl")
                            #         or payload.get("unrealizedPnl"),
                            #     },
                            # )
                        if isinstance(account, dict):
                            account_equity = account_equity or account.get("totalEquityValue")
                            available_balance = available_balance or account.get("availableBalance")
                            withdrawable_amount = (
                                withdrawable_amount
                                or account.get("withdrawable")
                                or account.get("withdrawableAmount")
                                or account.get("availableWithdrawable")
                            )
                            realized_pnl = realized_pnl or account.get("realizedPnl")
                            total_upnl = (
                                total_upnl
                                or account.get("totalUnrealizedPnl")
                                or account.get("totalUpnl")
                                or account.get("unrealizedPnl")
                            )
                            # preserve account fields for downstream logging
                            self._account_cache.update({"account": account})
                        if account_equity is None and isinstance(payload, dict):
                            account_equity = payload.get("totalEquity") or payload.get("total_equity")
                        if account_equity is None and isinstance(account, dict):
                            account_equity = account.get("totalEquity") or account.get("total_equity")
                        if available_balance is not None and account_equity is None:
                            account_equity = available_balance
                        if account_equity is not None:
                            existing_upnl = self._account_cache.get("totalUnrealizedPnl")
                            ws_override = False
                            if total_upnl is None:
                                total_upnl = existing_upnl
                            elif self._ws_pnl_is_fresh(now=time.time()) and existing_upnl is not None:
                                total_upnl = existing_upnl
                                ws_override = True
                            self._account_cache.update(
                                {
                                    "totalEquityValue": account_equity,
                                    "availableBalance": available_balance,
                                    "withdrawableAmount": (
                                        withdrawable_amount if withdrawable_amount is not None else available_balance
                                    ),
                                    "totalUnrealizedPnl": total_upnl,
                                }
                            )
                            if total_upnl is not None:
                                self._last_upnl_source = "ws" if ws_override else "rest_account_balance"
                                self._last_upnl_updated_ts = time.time()
                            self._publish_account_summary_event()
                            return float(account_equity)
                        wallets = (account or {}).get("contractWallets") or payload.get("contractWallets") or []
                        if isinstance(wallets, list) and wallets:
                            equity_usdt = 0.0
                            for wallet in wallets:
                                bal = float(wallet.get("balance", 0) or 0)
                                if bal <= 0:
                                    continue  # ignore negative/zero balances when estimating equity
                                token = wallet.get("token") or "USDT"
                                price = await self._get_usdt_price(token)
                                equity_usdt += bal * price
                            existing_upnl = self._account_cache.get("totalUnrealizedPnl")
                            ws_override = False
                            if total_upnl is None:
                                total_upnl = existing_upnl
                            elif self._ws_pnl_is_fresh(now=time.time()) and existing_upnl is not None:
                                total_upnl = existing_upnl
                                ws_override = True
                            self._account_cache.update(
                                {
                                    "totalEquityValue": equity_usdt,
                                    "availableBalance": available_balance,
                                    "withdrawableAmount": (
                                        withdrawable_amount if withdrawable_amount is not None else available_balance
                                    ),
                                    "totalUnrealizedPnl": total_upnl,
                                }
                            )
                            if total_upnl is not None:
                                self._last_upnl_source = "ws" if ws_override else "rest_account_balance"
                                self._last_upnl_updated_ts = time.time()
                            self._publish_account_summary_event()
                            return equity_usdt
                        raise ValueError("totalEquityValue not present in account balance response")
                except Exception as exc:
                    logger.warning("get_account_balance_v3 failed, falling back", extra={"error": str(exc)})
            # Fallback: legacy account endpoint
            legacy = await self._call_private_rest("get_account_v3", self._client.get_account_v3)
            if not legacy or not isinstance(legacy, dict):
                raise ValueError("Empty account response")
            legacy_payload = legacy.get("result") or legacy
            if isinstance(legacy_payload, dict):
                self._account_cache.update(legacy_payload)
            legacy_account = legacy_payload.get("account", {}) if isinstance(legacy_payload, dict) else {}
            if legacy_account.get("totalEquity") is not None:
                legacy_upnl = legacy_account.get("totalUnrealizedPnl")
                if legacy_upnl is not None:
                    existing_upnl = self._account_cache.get("totalUnrealizedPnl")
                    ws_override = False
                    if self._ws_pnl_is_fresh(now=time.time()) and existing_upnl is not None:
                        legacy_upnl = existing_upnl
                        ws_override = True
                    self._account_cache["totalUnrealizedPnl"] = legacy_upnl
                    if legacy_upnl is not None:
                        self._last_upnl_source = "ws" if ws_override else "rest_account_legacy"
                        self._last_upnl_updated_ts = time.time()
                self._publish_account_summary_event()
                return float(legacy_account["totalEquity"])
            wallets = legacy_payload.get("contractWallets") or []
            if isinstance(wallets, list) and wallets:
                equity_usdt = 0.0
                for wallet in wallets:
                    bal = float(wallet.get("balance", 0) or 0)
                    if bal <= 0:
                        continue
                    token = wallet.get("token") or "USDT"
                    price = await self._get_usdt_price(token)
                    equity_usdt += bal * price
                return equity_usdt
            raise ValueError("No equity field in account responses")
        except Exception as exc:
            logger.exception("failed to fetch account equity", extra={"error": str(exc)})
            raise

    def _record_window_event(self, bucket: dict[str, deque[float]], key: str, ts: Optional[float] = None) -> int:
        now = ts if ts is not None else time.time()
        window = self._reconcile_alert_window_seconds
        q = bucket[key]
        q.append(now)
        if window > 0:
            while q and (now - q[0]) > window:
                q.popleft()
        return len(q)

    def _maybe_alert_rate(self, *, key: str, event: str, reason: str, count: int, threshold: int) -> None:
        if count < threshold:
            return
        now = time.time()
        last = self._last_alert_by_key.get(key, 0.0)
        if (now - last) < self._alert_min_interval_seconds:
            return
        self._last_alert_by_key[key] = now
        logger.warning(
            event,
            extra={
                "event": event,
                "venue": "apex",
                "reason": reason,
                "count": count,
                "window_seconds": self._reconcile_alert_window_seconds,
                "threshold": threshold,
            },
        )

    def _record_fallback_usage(self, reason: str) -> None:
        count = self._record_window_event(self._fallback_reason_events, reason)
        self._maybe_alert_rate(
            key=f"apex_fallback:{reason}",
            event="apex_fallback_rest_used_frequently",
            reason=reason,
            count=count,
            threshold=3,
        )

    def _record_reconcile_reason_event(self, reason: str) -> None:
        count = self._record_window_event(self._reconcile_reason_events, reason)
        self._maybe_alert_rate(
            key=f"apex_reconcile:{reason}",
            event="apex_reconcile_frequent",
            reason=reason,
            count=count,
            threshold=max(1, self._reconcile_alert_max_per_window),
        )

    def _stream_has_open_state(self) -> bool:
        return bool(self._ws_orders or self._ws_positions or self._ws_orders_raw)

    def record_tpsl_flap_suspected(self) -> None:
        self._tpsl_flap_suspected_count += 1

    def record_tpsl_hint_unconfirmed(self) -> None:
        self._reconcile_reason_counts["hint_unconfirmed"] = self._reconcile_reason_counts.get("hint_unconfirmed", 0) + 1

    def get_stream_health_snapshot(self) -> dict[str, Any]:
        now = time.time()
        last_public_age = (now - self._last_public_ws_event_ts) if self._last_public_ws_event_ts else None
        last_private_age = (now - self._last_private_ws_event_ts) if self._last_private_ws_event_ts else None
        last_reconcile_age = (now - self._last_reconcile_ts) if self._last_reconcile_ts else None
        tpsl_symbols = len(
            {
                self._normalize_symbol_value(o.get("symbol") or o.get("market"))
                for o in (self._ws_orders_tpsl or [])
                if isinstance(o, dict)
            }
        )
        payload = {
            "ws_alive": bool(self.apex_enable_ws and self._ws_running),
            "last_public_ws_event_age_seconds": last_public_age,
            "last_private_ws_event_age_seconds": last_private_age,
            "reconcile_count": int(self._reconcile_count),
            "last_reconcile_age_seconds": last_reconcile_age,
            "last_reconcile_reason": self._last_reconcile_reason,
            "last_reconcile_error": self._last_reconcile_error,
            "pending_submitted_orders": 0,
            "oldest_pending_order_age_seconds": None,
            "reconcile_reason_counts": dict(self._reconcile_reason_counts),
            "fallback_rest_orders_used_count": int(self._fallback_rest_orders_used_count),
            "fallback_rest_positions_used_count": int(self._fallback_rest_positions_used_count),
            "empty_snapshot_protected_count": int(self._empty_snapshot_protected_count),
            "tpsl_symbols_tracked": tpsl_symbols,
            "tpsl_flap_suspected_count": int(self._tpsl_flap_suspected_count),
            "upnl_source": self._last_upnl_source,
            "upnl_age_seconds": (now - self._last_upnl_updated_ts) if self._last_upnl_updated_ts else None,
        }
        if not self.apex_enable_ws:
            payload["poll_orders_interval_seconds"] = self._orders_poll_interval_seconds
            payload["poll_positions_interval_seconds"] = self._positions_poll_interval_seconds
            payload["poll_account_interval_seconds"] = self._account_poll_interval_seconds
        return payload

    def _collect_reconcile_reasons(self) -> list[str]:
        reasons: list[str] = []
        now = time.time()
        if self._reconcile_audit_interval > 0 and (now - self._last_reconcile_ts) >= self._reconcile_audit_interval:
            reasons.append("periodic_audit")
        if self._reconcile_stale_stream_seconds > 0 and self._stream_has_open_state():
            reference = self._last_private_ws_event_ts or self._stream_started_at
            if reference > 0 and (now - reference) >= self._reconcile_stale_stream_seconds:
                reasons.append("ws_stale")
        if self._suspicious_orders_empty_pending:
            reasons.append("orders_empty_suspicious")
        if self._suspicious_positions_empty_pending:
            reasons.append("positions_empty_suspicious")
        return reasons

    async def _audit_reconcile(self, *, reason: str, force: bool = False) -> bool:
        if not self.apex_enable_ws:
            return False
        if self._reconcile_lock.locked():
            return False
        now = time.time()
        if not force and self._reconcile_min_gap_seconds > 0 and (now - self._last_reconcile_ts) < self._reconcile_min_gap_seconds:
            return False
        async with self._reconcile_lock:
            started = time.time()
            try:
                await self.get_open_orders(force_rest=True, publish=True)
                await self.get_open_positions(force_rest=True, publish=True)
                finished = time.time()
                self._last_reconcile_ts = finished
                self._last_reconcile_reason = reason
                self._last_reconcile_error = None
                self._reconcile_count += 1
                self._reconcile_reason_counts[reason] = self._reconcile_reason_counts.get(reason, 0) + 1
                self._record_reconcile_reason_event(reason)
                self._suspicious_orders_empty_pending = False
                self._suspicious_positions_empty_pending = False
                logger.info(
                    "apex_reconcile_completed",
                    extra={
                        "event": "apex_reconcile_completed",
                        "venue": "apex",
                        "reason": reason,
                        "duration_ms": round((finished - started) * 1000, 2),
                        "orders_count": len(self._ws_orders),
                        "positions_count": len(self._ws_positions),
                    },
                )
                return True
            except Exception as exc:
                self._last_reconcile_error = str(exc)
                logger.warning(
                    "apex_reconcile_failed",
                    extra={"event": "apex_reconcile_failed", "venue": "apex", "reason": reason, "error": str(exc)},
                )
                return False

    async def get_open_positions(self, *, force_rest: bool = False, publish: bool = False) -> list[Dict[str, Any]]:
        with self._lock:
            # When publish=True callers expect an authoritative refresh for UI/state fanout,
            # so do not short-circuit on cached positions.
            if self._ws_positions and not force_rest and not publish:
                return list(self._ws_positions.values())
        self._fallback_rest_positions_used_count += 1
        self._record_fallback_usage("positions")
        try:
            resp = await self._call_private_rest("get_account_v3", self._client.get_account_v3)
            payload = self._unwrap_payload(resp)
            if isinstance(payload, list):
                payload = {"positions": payload}
            positions, has_key = self._extract_positions(payload if isinstance(payload, dict) else {})
            mapped = {self._normalize_symbol(p): p for p in positions if isinstance(p, dict)} if positions else {}
            keep_cached = False
            now = time.time()
            with self._lock:
                if mapped:
                    self._ws_positions = mapped
                    self._positions_empty_since = None
                    self._suspicious_positions_empty_pending = False
                elif has_key:
                    if self._ws_positions and self._positions_empty_stale_seconds > 0:
                        if self._positions_empty_since is None:
                            self._positions_empty_since = now
                            keep_cached = True
                            self._suspicious_positions_empty_pending = True
                            self._empty_snapshot_protected_count += 1
                        elif (now - self._positions_empty_since) < self._positions_empty_stale_seconds:
                            keep_cached = True
                            self._suspicious_positions_empty_pending = True
                            self._empty_snapshot_protected_count += 1
                        else:
                            self._positions_empty_since = None
                            self._suspicious_positions_empty_pending = False
                    if not keep_cached:
                        self._ws_positions = {}
                        self._recalculate_total_upnl_locked()
                elif not force_rest and self._ws_positions:
                    return list(self._ws_positions.values())
                else:
                    self._ws_positions = {}
                    self._positions_empty_since = None
            if publish:
                self._recompute_positions_pnl()
            if publish:
                self._publish_event({"type": "positions", "payload": list(self._ws_positions.values())})
                if has_key and not mapped:
                    self._publish_account_summary_event()
            return list(self._ws_positions.values())
        except Exception as exc:
            # Connection hiccups happen; keep cache and avoid noisy stack traces.
            logger.warning("failed to fetch positions", extra={"error": str(exc)})
            with self._lock:
                return list(self._ws_positions.values())

    async def get_open_orders(self, *, force_rest: bool = False, publish: bool = False) -> list[Dict[str, Any]]:
        with self._lock:
            if self._ws_orders and not force_rest:
                return list(self._ws_orders.values())
        self._fallback_rest_orders_used_count += 1
        self._record_fallback_usage("orders")
        try:
            resp = await self._call_private_rest("open_orders_v3", self._client.open_orders_v3)
            payload = self._unwrap_payload(resp)
            orders: Any = []
            if isinstance(payload, dict):
                orders = payload.get("list") or payload.get("orders") or payload.get("data") or []
            elif isinstance(payload, list):
                orders = payload
            if isinstance(orders, dict):
                orders = orders.get("list") or orders.get("orders") or orders.get("data") or []
            orders_list = orders if isinstance(orders, list) else []
            if orders_list is None:
                orders_list = []
            try:
                first_order = orders_list[0] if orders_list else {}
                # logger.info(
                #     "open_orders_snapshot",
                #     extra={
                #         "event": "open_orders_snapshot",
                #         "raw_count": len(orders_list),
                #         "first_status": first_order.get("status") if isinstance(first_order, dict) else None,
                #         "first_type": (
                #             first_order.get("type")
                #             or first_order.get("orderType")
                #             or first_order.get("order_type")
                #             if isinstance(first_order, dict)
                #             else None
                #         ),
                #         "contains_tpsl_flag": any(bool(o.get("isPositionTpsl")) for o in orders_list if isinstance(o, dict)),
                #         "symbols_sample": list({str(o.get("symbol") or o.get("market")) for o in orders_list if isinstance(o, dict)})[:5],
                #     },
                # )
            except Exception:
                pass
            mapped = self._filter_and_map_orders(orders)
            empty_snapshot = isinstance(orders_list, list) and len(orders_list) == 0
            keep_cached = False
            now = time.time()
            with self._lock:
                if mapped:
                    self._ws_orders = mapped
                    self._orders_empty_since = None
                    self._suspicious_orders_empty_pending = False
                elif empty_snapshot and self._ws_orders and self._orders_empty_stale_seconds > 0:
                    if self._orders_empty_since is None:
                        self._orders_empty_since = now
                        keep_cached = True
                        self._suspicious_orders_empty_pending = True
                        self._empty_snapshot_protected_count += 1
                    elif (now - self._orders_empty_since) < self._orders_empty_stale_seconds:
                        keep_cached = True
                        self._suspicious_orders_empty_pending = True
                        self._empty_snapshot_protected_count += 1
                    else:
                        self._orders_empty_since = None
                        self._suspicious_orders_empty_pending = False
                    if not keep_cached:
                        self._ws_orders = {}
                elif not force_rest and self._ws_orders:
                    return list(self._ws_orders.values())
                else:
                    self._ws_orders = {}
                    self._orders_empty_since = None
            if publish:
                self._publish_cached_orders()
                self._last_order_event_ts = time.time()
            return list(self._ws_orders.values())
        except Exception as exc:
            logger.exception("failed to fetch open orders", extra={"error": str(exc)})
            with self._lock:
                return list(self._ws_orders.values())

    def get_account_orders_snapshot(self) -> list[Dict[str, Any]]:
        """Return the most recent account-level orders payload (raw ws_zk_accounts_v3 orders only)."""
        with self._lock:
            if self._ws_orders_raw:
                return list(self._ws_orders_raw)
            if self._ws_orders_tpsl:
                return list(self._ws_orders_tpsl)
            return []

    async def refresh_account_orders_from_rest(self) -> list[Dict[str, Any]]:
        """
        Fetch account snapshot via REST (get_account_v3) to refresh TP/SL orders when WS hasn't delivered yet.
        Returns the parsed orders list (or empty).
        """
        self._record_fallback_usage("account_orders")
        try:
            resp = await self._call_private_rest("get_account_v3", self._client.get_account_v3)
            payload = self._unwrap_payload(resp)
            orders: Any = []
            if isinstance(payload, dict):
                orders = payload.get("orders") or payload.get("orderList") or payload.get("list") or payload.get("data")
            elif isinstance(payload, list):
                orders = payload
            if isinstance(orders, dict):
                orders = orders.get("list") or orders.get("orders") or orders.get("data")
            orders = orders if isinstance(orders, list) else []
            if orders:
                with self._lock:
                    self._ws_orders_raw = orders
                    self._ws_orders_tpsl = [
                        o
                        for o in orders
                        if isinstance(o, dict)
                        and self._is_tpsl_order_payload(o)
                        and str(o.get("status") or "").lower() not in {"canceled", "cancelled", "filled", "triggered"}
                    ]
                # logger.info(
                #     "account_snapshot_refreshed",
                #     extra={
                #         "event": "account_snapshot_refreshed",
                #         "orders_count": len(orders),
                #         "position_tpsl": len(self._ws_orders_tpsl),
                #     },
                # )
            return orders
        except Exception as exc:
            logger.warning(
                "account_snapshot_refresh_failed",
                extra={"event": "account_snapshot_refresh_failed", "error": str(exc)},
            )
            return []

    async def _reconcile_orders_loop(self) -> None:
        """Reason-driven reconcile loop (verification, not primary state source)."""
        while self._ws_running and self.apex_enable_ws:
            try:
                await asyncio.sleep(5)
                for reason in self._collect_reconcile_reasons():
                    await self._audit_reconcile(reason=reason)
                    # enforce one reconcile attempt per cycle to avoid bursts
                    break
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def _delayed_refresh(self) -> None:
        """Short delay then refresh open orders to reconcile after partial WS updates."""
        try:
            await asyncio.sleep(1)
            await self.get_open_orders(force_rest=True, publish=True)
            await self.get_open_positions(force_rest=True, publish=True)
        except Exception:
            pass

    async def _refresh_orders_now(self) -> None:
        await self.get_open_orders(force_rest=True, publish=True)

    async def _refresh_positions_now(self) -> None:
        await self.get_open_positions(force_rest=True, publish=True)

    def _recompute_positions_pnl(self) -> None:
        """Recompute PnL for cached positions using latest known prices to reduce flicker."""
        if not self._ws_prices or not self._ws_positions:
            return
        summary_changed = False
        with self._lock:
            for sym in list(self._ws_positions.keys()):
                price = self._ws_prices.get(sym)
                if price is not None and self._update_positions_pnl(sym, price):
                    summary_changed = True
            if summary_changed:
                self._recalculate_total_upnl_locked()
        if summary_changed:
            self._publish_account_summary_event()

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep WS connections alive."""
        while self._ws_running and self.apex_enable_ws:
            try:
                await asyncio.sleep(20)
                if self._ws_public:
                    await asyncio.to_thread(self._ws_public.runTimer)
                if self._ws_private:
                    await asyncio.to_thread(self._ws_private.runTimer)
            except Exception:
                continue

    async def _resubscribe_loop(self) -> None:
        """Resubscribe private stream when idle and trigger reconnect reconcile."""
        while self._ws_running and self.apex_enable_ws:
            try:
                await asyncio.sleep(30)
                idle = time.time() - self._last_order_event_ts
                if idle > 60 and self._ws_private:
                    try:
                        self._ws_private.account_info_stream_v3(self._handle_account_stream)
                        self._last_private_ws_event_ts = time.time()
                        await self._audit_reconcile(reason="ws_reconnect", force=False)
                        # logger.info("ws_resubscribe", extra={"event": "ws_resubscribe", "topic": "ws_zk_accounts_v3"})
                    except Exception as exc:  # pragma: no cover
                        logger.warning("ws_resubscribe_failed", extra={"error": str(exc)})
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # SDK signature differs by installed ApeX client version; strip only unsupported fields.
            api_payload = self._sanitize_create_order_payload(payload)
            resp = await asyncio.to_thread(self._client.create_order_v3, **api_payload)
            order_id = (
                resp.get("result", {}).get("orderId")
                or resp.get("data", {}).get("orderId")
                or resp.get("orderId")
                or resp.get("orderID")
            )
            # After submit, force a short delayed REST refresh so UI order tables update
            # even when private WS order updates are delayed or missing.
            if self._loop and (self._order_refresh_task is None or self._order_refresh_task.done()):
                self._order_refresh_task = self._loop.create_task(self._delayed_refresh())
            client_id = payload.get("clientId") or payload.get("client_id")
            return {"exchange_order_id": order_id, "client_id": client_id, "raw": resp}
        except Exception as exc:
            redacted = self._redact_order_payload(payload)
            logger.exception("failed to place order", extra={"error": str(exc), "payload_redacted": redacted})
            raise

    async def place_close_order(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        close_type: str,
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Submit a reduce-only close order (market or limit)."""
        if size <= 0:
            raise ValueError("Close size must be greater than 0")
        close_type_norm = (close_type or "").lower()
        if close_type_norm not in {"market", "limit"}:
            raise ValueError("close_type must be 'market' or 'limit'")
        side_norm = (side or "").upper()
        order_side = "SELL"
        if "SHORT" in side_norm or side_norm == "SELL":
            order_side = "BUY"
        elif "LONG" in side_norm or side_norm == "BUY":
            order_side = "SELL"
        else:
            order_side = "SELL" if side_norm != "BUY" else "BUY"

        price = limit_price
        if close_type_norm == "limit":
            if price is None:
                raise ValueError("Limit close requires limit_price")
        else:
            if price is None:
                base = symbol.split("-")[0] if "-" in symbol else symbol
                try:
                    price = await self._get_usdt_price(base)
                except Exception:
                    price = await asyncio.to_thread(self._get_worst_price, symbol)
            if price is None:
                raise ValueError("Unable to determine market price for close order")

        payload, warning = await self.build_order_payload(
            symbol=symbol,
            side=order_side,
            size=size,
            entry_price=price,
            reduce_only=True,
        )
        payload["type"] = "MARKET" if close_type_norm == "market" else "LIMIT"
        if close_type_norm == "market":
            payload["timeInForce"] = "IMMEDIATE_OR_CANCEL"
        if warning:
            logger.warning("close_order_payload_warning", extra={"event": "close_order_payload_warning", "warning": warning})
        return await self.place_order(payload)

    async def get_symbol_last_price(self, symbol: str) -> float:
        norm_symbol = (symbol or "").upper()
        now = time.time()
        cache_entry = self._ticker_cache.get(norm_symbol)
        if cache_entry and now - cache_entry.get("ts", 0) < 10:
            return cache_entry["price"]
        base = norm_symbol.split("-")[0] if "-" in norm_symbol else norm_symbol
        price = await self._get_usdt_price(base)
        self._ticker_cache[norm_symbol] = {"price": price, "ts": now}
        return price

    async def get_depth_snapshot(self, symbol: str, *, levels: int = 25) -> Dict[str, Any]:
        if not symbol:
            raise ValueError("symbol is required for depth snapshot")
        safe_levels = max(1, int(levels))
        try:
            return await asyncio.to_thread(self._public_client.depth_v3, symbol=symbol, limit=safe_levels)
        except TypeError:
            return await asyncio.to_thread(self._public_client.depth_v3, symbol=symbol)

    async def cancel_order(self, order_id: str, client_id: Optional[str] = None) -> Dict[str, Any]:
        errors: list[str] = []
        # ensure account/config set on client for signature
        try:
            await self._call_private_rest("get_account_v3", self._client.get_account_v3)
        except Exception:
            pass
        client_target = client_id or (order_id if not str(order_id).isdigit() else None)
        if client_target:
            try:
                normalized_client_id = str(client_target)
                resp = await asyncio.to_thread(
                    self._retry_delete_on_conflict, self._client.delete_order_by_client_order_id_v3, id=normalized_client_id
                )
                code, status = self._extract_code_status(resp)
                if code in (None, "0") and status in (None, "", "success", "canceled", "cancelled"):
                    if isinstance(resp, dict) and resp.get("data") == normalized_client_id:
                        status = "canceled"
                canceled = (
                    code in (0, "0", None)
                    and (str(status).lower() in {"canceled", "cancelled", "success"} or status is True)
                )
                if canceled:
                    with self._lock:
                        self._ws_orders = {
                            k: v
                            for k, v in self._ws_orders.items()
                            if (v.get("clientOrderId") or v.get("clientId")) != normalized_client_id
                        }
                    return {"canceled": True, "order_id": order_id, "client_id": client_target, "raw": resp}
                errors.append(f"delete_order_by_client_order_id_v3 code={code} status={status} resp={resp}")
            except Exception as exc:
                msg = f"delete_order_by_client_order_id_v3 error={exc}"
                errors.append(msg)
                logger.exception(
                    "failed to cancel order by client id",
                    extra={"error": str(exc), "order_id": order_id, "client_id": client_target},
                )
        if str(order_id).isdigit():
            try:
                oid = int(order_id)
                resp = await asyncio.to_thread(self._retry_delete_on_conflict, self._client.delete_order_v3, id=oid)
                code, status = self._extract_code_status(resp)
                success = (
                    code in (0, "0", None)
                    and (str(status).lower() in {"canceled", "cancelled", "success"} or status is True)
                )
                if success:
                    with self._lock:
                        self._ws_orders.pop(str(order_id), None)
                    return {"canceled": True, "order_id": order_id, "raw": resp}
                errors.append(f"delete_order_v3 code={code} status={status} resp={resp}")
            except Exception as exc:
                errors.append(f"delete_order_v3 error={exc}")
                logger.warning("delete_order_v3 failed", extra={"error": str(exc), "order_id": order_id})
        return {"canceled": False, "order_id": order_id, "raw": {"errors": errors}}

    async def cancel_all(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        try:
            params = {"symbol": symbol} if symbol else {}
            resp = await asyncio.to_thread(self._client.delete_open_orders_v3, **params)
            return {"canceled_all": True, "symbol": symbol, "raw": resp}
        except Exception as exc:
            logger.exception("failed to cancel all", extra={"error": str(exc), "symbol": symbol})
            raise

    async def cancel_tpsl_orders(self, *, symbol: Optional[str], cancel_tp: bool = False, cancel_sl: bool = False) -> Dict[str, Any]:
        """
        Cancel existing TP/SL position orders for a symbol using cached ws_orders_raw snapshots.
        Only TP/SL orders (isPositionTpsl and STOP_*/TAKE_PROFIT_ types) are targeted.
        """
        if not cancel_tp and not cancel_sl:
            return {"canceled": []}
        symbol_key = self._normalize_symbol_value(symbol or "")
        targets: list[Dict[str, Any]] = []

        def _collect_targets(order_list: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
            collected: list[Dict[str, Any]] = []
            for o in order_list or []:
                if not isinstance(o, dict):
                    continue
                sym = self._normalize_symbol_value(o.get("symbol") or o.get("market"))
                if symbol_key and sym != symbol_key:
                    continue
                status_raw = str(o.get("status") or o.get("orderStatus") or "").lower()
                if status_raw in {"canceled", "cancelled", "filled", "triggered"} or "cancel" in status_raw:
                    continue
                if not o.get("isPositionTpsl"):
                    continue
                otype = (o.get("type") or o.get("orderType") or o.get("order_type") or "").upper()
                if otype.startswith("TAKE_PROFIT") and cancel_tp:
                    collected.append(o)
                if otype.startswith("STOP") and cancel_sl:
                    collected.append(o)
            return collected

        # Always refresh a fresh snapshot before selecting targets to avoid stale cache issues.
        if symbol_key:
            await self.refresh_account_orders_from_rest()
        with self._lock:
            orders = list(self._ws_orders_raw or [])
            if not orders and self._ws_orders_tpsl:
                orders = list(self._ws_orders_tpsl)
        targets = _collect_targets(orders)

        # Explicitly drop non-requested types to avoid accidental opposite-side cancels.
        if cancel_tp and not cancel_sl:
            targets = [t for t in targets if str(t.get("type") or "").upper().startswith("TAKE_PROFIT")]
        if cancel_sl and not cancel_tp:
            targets = [t for t in targets if str(t.get("type") or "").upper().startswith("STOP")]

        # If no targets of requested type, avoid retrying and risking opposite-side cancels.
        if not targets:
            if symbol_key:
                # One-shot refresh to capture newly submitted TP/SL orders that have not yet hit WS cache.
                await self.refresh_account_orders_from_rest()
                with self._lock:
                    orders = list(self._ws_orders_raw or [])
                    if not orders and self._ws_orders_tpsl:
                        orders = list(self._ws_orders_tpsl)
                targets = _collect_targets(orders)
                if cancel_tp and not cancel_sl:
                    targets = [t for t in targets if str(t.get("type") or "").upper().startswith("TAKE_PROFIT")]
                if cancel_sl and not cancel_tp:
                    targets = [t for t in targets if str(t.get("type") or "").upper().startswith("STOP")]
            if not targets:
                return {"canceled": [], "errors": []}
        # Only cancel one TP and one SL per symbol (latest by updatedAt/createdAt)
        def _pick_latest(order_list: list[Dict[str, Any]], prefix: str) -> list[Dict[str, Any]]:
            filtered = []
            for o in order_list:
                otype = (o.get("type") or o.get("orderType") or o.get("order_type") or "").upper()
                if prefix == "TP" and otype.startswith("TAKE_PROFIT"):
                    filtered.append(o)
                if prefix == "SL" and otype.startswith("STOP"):
                    filtered.append(o)
            if not filtered:
                return []
            filtered.sort(
                key=lambda o: o.get("updatedAt")
                or o.get("createdAt")
                or o.get("updateTime")
                or o.get("createTime")
                or 0,
                reverse=True,
            )
            return [filtered[0]]

        limited_targets: list[Dict[str, Any]] = []
        limited_targets.extend(_pick_latest(targets, "TP") if cancel_tp else [])
        limited_targets.extend(_pick_latest(targets, "SL") if cancel_sl else [])
        targets = limited_targets
        attempted_count = len(targets)

        canceled_ids: list[str] = []
        errors: list[str] = []

        if not targets:
            # logger.info(
            #     "CANCEL_TPSL_EMPTY",
            #     extra={
            #         "event": "cancel_tpsl_empty",
            #         "symbol": symbol_key,
            #         "cancel_tp": cancel_tp,
            #         "cancel_sl": cancel_sl,
            #         "cache_orders": len(orders),
            #     },
            # )
            return {"canceled": [], "errors": ["no targets"], "attempted": attempted_count}

        def _cancel_success(resp: Dict[str, Any]) -> bool:
            code, status = self._extract_code_status(resp)
            success_flags = {
                str(flag).lower()
                for flag in (status, resp.get("success"), resp.get("retMsg"))
                if flag is not None
            }
            if code in (0, "0", None, 20016, "20016") and (
                "" in success_flags or "success" in success_flags or "canceled" in success_flags or "cancelled" in success_flags or "ok" in success_flags
            ):
                return True
            data = resp.get("data")
            if data is True:
                return True
            return False

        async def _attempt_cancel(batch: list[Dict[str, Any]]) -> None:
            for target in batch:
                otype = (target.get("type") or target.get("orderType") or target.get("order_type") or "").upper()
                # Defensive guard: even if a mismatched type slips in, skip it to avoid canceling the wrong side.
                if cancel_tp and not cancel_sl and not otype.startswith("TAKE_PROFIT"):
                    continue
                if cancel_sl and not cancel_tp and not otype.startswith("STOP"):
                    continue
                oid = target.get("orderId") or target.get("order_id") or target.get("id")
                cid = target.get("clientOrderId") or target.get("clientId")

                payloads: list[Tuple[str, Any, Dict[str, Any]]] = []
                if oid is not None:
                    payloads.append(("orderId", self._client.delete_order_v3, {"orderId": str(oid)}))
                    payloads.append(("id", self._client.delete_order_v3, {"id": str(oid)}))
                if cid is not None:
                    payloads.append(("clientOrderId", self._client.delete_order_by_client_order_id_v3, {"clientOrderId": str(cid)}))
                    payloads.append(("id_by_client", self._client.delete_order_by_client_order_id_v3, {"id": str(cid)}))

                attempted = False
                success = False
                for label, func, kwargs in payloads:
                    attempted = True
                    try:
                        resp = await asyncio.to_thread(self._retry_delete_on_conflict, func, **kwargs)
                    except Exception as exc:  # pragma: no cover
                        errors.append(f"cancel error id={oid or cid} via={label} err={exc}")
                        continue
                    if resp is not None and _cancel_success(resp):
                        canceled_ids.append(str(oid or cid))
                        success = True
                        break
                    code, status = self._extract_code_status(resp or {})
                    errors.append(f"cancel failed id={oid or cid} via={label} code={code} status={status}")

                if not attempted:
                    errors.append(f"cancel error id={oid or cid} err=no cancel payload attempted")

        # logger.info(
        #     "### CANCEL_TPSL_ATTEMPT ###",
        #     extra={
        #         "event": "cancel_tpsl_attempt",
        #         "symbol": symbol_key,
        #         "cancel_tp": cancel_tp,
        #         "cancel_sl": cancel_sl,
        #         "target_count": len(targets),
        #         "targets_compact": [
        #             {
        #                 "id": t.get("orderId") or t.get("order_id") or t.get("id"),
        #                 "clientId": t.get("clientOrderId") or t.get("clientId"),
        #                 "type": t.get("type"),
        #                 "status": t.get("status"),
        #                 "symbol": t.get("symbol") or t.get("market"),
        #                 "trigger": t.get("triggerPrice") or t.get("price"),
        #             }
        #             for t in targets
        #         ],
        #         "summary": f"CANCEL_TPSL_ATTEMPT symbol={symbol_key} cancel_tp={cancel_tp} cancel_sl={cancel_sl} targets={len(targets)} first_id={targets[0].get('orderId') or targets[0].get('order_id') or targets[0].get('id') if targets else None} first_type={targets[0].get('type') if targets else None} first_status={targets[0].get('status') if targets else None}",
        #     },
        # )

        await _attempt_cancel(targets)
        # If nothing canceled, retry once using the latest cached WS orders (no REST fallback) to avoid stale IDs.
        if not canceled_ids and symbol_key:
            with self._lock:
                refreshed = [
                    o
                    for o in (self._ws_orders_raw or [])
                    if isinstance(o, dict)
                    and self._normalize_symbol_value(o.get("symbol") or o.get("market")) == symbol_key
                    and o.get("isPositionTpsl")
                    and str(o.get("status") or "").lower() not in {"canceled", "cancelled", "filled", "triggered"}
                ]
            if cancel_tp and not cancel_sl:
                refreshed = [t for t in refreshed if str(t.get("type") or "").upper().startswith("TAKE_PROFIT")]
            if cancel_sl and not cancel_tp:
                refreshed = [t for t in refreshed if str(t.get("type") or "").upper().startswith("STOP")]
            limited_refreshed: list[Dict[str, Any]] = []
            limited_refreshed.extend(_pick_latest(refreshed, "TP") if cancel_tp else [])
            limited_refreshed.extend(_pick_latest(refreshed, "SL") if cancel_sl else [])
            refreshed = limited_refreshed
            # logger.info(
            #     "### CANCEL_TPSL_RETRY ###",
            #     extra={
            #         "event": "cancel_tpsl_retry",
            #         "symbol": symbol_key,
            #         "cancel_tp": cancel_tp,
            #         "cancel_sl": cancel_sl,
            #         "target_count": len(refreshed),
            #         "first_target_type": refreshed[0].get("type") if refreshed else None,
            #         "first_target_status": refreshed[0].get("status") if refreshed else None,
            #         "first_target_id": (refreshed[0].get("orderId") or refreshed[0].get("order_id") or refreshed[0].get("id")) if refreshed else None,
            #         "first_target_client": refreshed[0].get("clientOrderId") or refreshed[0].get("clientId") if refreshed else None,
            #         "targets_compact": [
            #             {
            #                 "id": t.get("orderId") or t.get("order_id") or t.get("id"),
            #                 "clientId": t.get("clientOrderId") or t.get("clientId"),
            #                 "type": t.get("type"),
            #                 "status": t.get("status"),
            #                 "symbol": t.get("symbol") or t.get("market"),
            #                 "trigger": t.get("triggerPrice") or t.get("price"),
            #             }
            #             for t in refreshed
            #         ],
            #         "summary": f"CANCEL_TPSL_RETRY symbol={symbol_key} cancel_tp={cancel_tp} cancel_sl={cancel_sl} targets={len(refreshed)} first_id={refreshed[0].get('orderId') or refreshed[0].get('order_id') or refreshed[0].get('id') if refreshed else None} first_type={refreshed[0].get('type') if refreshed else None} first_status={refreshed[0].get('status') if refreshed else None}",
            #     },
            # )
            await _attempt_cancel(refreshed)
        if not canceled_ids and errors:
            logger.warning(
                "cancel_tpsl_failed",
                extra={
                    "event": "cancel_tpsl_failed",
                    "symbol": symbol_key,
                    "cancel_tp": cancel_tp,
                    "cancel_sl": cancel_sl,
                    "errors": errors,
                },
            )
        return {"canceled": canceled_ids, "errors": errors, "attempted": attempted_count}

    async def update_targets(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        cancel_existing: bool = False,
        cancel_tp: bool = False,
        cancel_sl: bool = False,
    ) -> Dict[str, Any]:
        """
        Submit TP/SL orders for an open position. Uses TAKE_PROFIT_MARKET and STOP_MARKET reduce-only orders.
        """
        results: Dict[str, Any] = {"submitted": []}
        if cancel_existing or cancel_tp or cancel_sl:
            results["canceled"] = await self.cancel_tpsl_orders(
                symbol=symbol, cancel_tp=(cancel_existing or cancel_tp), cancel_sl=(cancel_existing or cancel_sl)
            )
        order_side = "SELL" if str(side).upper() in {"LONG", "BUY"} else "BUY"
        info = self.get_symbol_info(symbol) or {}
        tick = float(info.get("tickSize") or 0)
        step = float(info.get("stepSize") or 0)
        size_fmt = self._format_with_step(size, step) if size is not None else size
        async def _submit(order_type: str, trigger_price: float) -> Optional[Dict[str, Any]]:
            payload = {
                "symbol": symbol,
                "side": order_side,
                "type": order_type,
                "size": size_fmt,
                "triggerPrice": self._format_with_step(trigger_price, tick) if trigger_price is not None else None,
                "price": self._format_with_step(trigger_price, tick) if trigger_price is not None else None,
                "reduceOnly": True,
                "isPositionTpsl": True,
                "timeInForce": "GOOD_TIL_CANCEL",
            }
            if self._supports_create_order_field("triggerPriceType"):
                payload["triggerPriceType"] = "MARKET"
            try:
                api_payload = self._sanitize_create_order_payload(payload)
                resp = await asyncio.to_thread(self._client.create_order_v3, **api_payload)
                return {"payload": payload, "raw": resp}
            except Exception as exc:  # pragma: no cover
                logger.warning("update_targets_submit_failed", extra={"event": "update_targets_submit_failed", "error": str(exc)})
                return {"payload": payload, "error": str(exc)}

        if take_profit is not None:
            tp_res = await _submit("TAKE_PROFIT_MARKET", take_profit)
            if tp_res:
                results["submitted"].append(tp_res)
        if stop_loss is not None:
            sl_res = await _submit("STOP_MARKET", stop_loss)
            if sl_res:
                results["submitted"].append(sl_res)
        return results
    async def build_order_payload(
        self,
        *,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        reduce_only: bool = False,
        tp: Optional[float] = None,
        stop: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Build an ApeX create_order_v3 payload; returns (payload, warning).
        Note: SDK signature accepts clientId/timeInForce, not limitFee/expiration/clientOrderId.
        """
        client_order_id = f"{symbol}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "price": entry_price,
            "size": size,
            "reduceOnly": reduce_only,
            "clientId": client_order_id,
            "timeInForce": "GOOD_TIL_CANCEL",
        }
        # Format price/size according to symbol precision when available
        info = self.get_symbol_info(symbol) or {}
        tick = float(info.get("tickSize") or 0)
        step = float(info.get("stepSize") or 0)
        payload["price"] = self._format_with_step(entry_price, tick)
        payload["size"] = self._format_with_step(size, step)

        await self._ensure_account_cached()
        taker_fee_rate = self._get_taker_fee_rate()
        if taker_fee_rate is not None:
            payload["takerFeeRate"] = taker_fee_rate

        if tp:
            payload["tpPrice"] = self._format_with_step(tp, tick)
            payload["tpTriggerPrice"] = self._format_with_step(tp, tick)
            if self._supports_create_order_field("tpTriggerPriceType"):
                payload["tpTriggerPriceType"] = "MARKET"
            payload["isOpenTpslOrder"] = True
            payload["isSetOpenTp"] = True
            payload["tpSide"] = "SELL" if side.upper() == "BUY" else "BUY"
            payload["tpSize"] = self._format_with_step(size, step)
        if stop:
            payload["slPrice"] = self._format_with_step(stop, tick)
            payload["slTriggerPrice"] = self._format_with_step(stop, tick)
            if self._supports_create_order_field("slTriggerPriceType"):
                payload["slTriggerPriceType"] = "MARKET"
            payload["isOpenTpslOrder"] = True
            payload["isSetOpenSl"] = True
            payload["slSide"] = "SELL" if side.upper() == "BUY" else "BUY"
            payload["slSize"] = self._format_with_step(size, step)
        if (tp or stop) and self._supports_create_order_field("triggerPriceType"):
            payload["triggerPriceType"] = "MARKET"
        return payload, None

    def _redact_order_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields before logging."""
        if not isinstance(payload, dict):
            return {}
        redacted = {}
        for key, val in payload.items():
            if key.lower() in {"signature", "passphrase", "secret"}:
                redacted[key] = "***"
            elif key.lower() in {"clientorderid", "clientid"}:
                redacted[key] = "***client***"
            else:
                redacted[key] = val
        return redacted
    @staticmethod
    def _is_tpsl_order_payload(order: Dict[str, Any]) -> bool:
        """Detect TP/SL reduce-only orders even when isPositionTpsl flag is missing."""
        if not isinstance(order, dict):
            return False
        order_type = (order.get("type") or order.get("orderType") or order.get("order_type") or "").upper()
        if not (order_type.startswith("STOP") or order_type.startswith("TAKE_PROFIT")):
            return False
        if bool(order.get("isPositionTpsl")):
            return True
        reduce_only = order.get("reduceOnly")
        if reduce_only is None:
            reduce_only = order.get("reduce_only")
        return bool(reduce_only)
