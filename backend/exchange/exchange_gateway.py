import asyncio
import time
import uuid
import threading
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional, Tuple, List, Any as AnyType

import requests

from backend.core.config import Settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ExchangeGateway:
    """Wrapper around ApeX Omni SDK with cached configs and basic helpers."""

    def __init__(self, settings: Settings, client: Optional[Any] = None) -> None:
        self.settings = settings
        self._configs_cache: Dict[str, Any] = {}
        self._account_cache: Dict[str, Any] = {}
        self._ws_prices: Dict[str, float] = {}
        self._ws_orders: Dict[str, Dict[str, Any]] = {}
        self._ws_positions: Dict[str, Dict[str, Any]] = {}
        self._ws_running: bool = False
        self._ws_public: Optional[Any] = None
        self._ws_private: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._client: Any = client if client is not None else self._init_client(settings)
        self._public_client: Any = self._init_public_client(settings)
        self._prime_client()

    def _init_client(self, settings: Settings) -> Any:
        from apexomni.constants import (
            APEX_OMNI_HTTP_MAIN,
            APEX_OMNI_HTTP_TEST,
            NETWORKID_MAIN,
            NETWORKID_OMNI_TEST_BNB,
            NETWORKID_OMNI_TEST_BASE,
        )
        from apexomni.http_private_sign import HttpPrivateSign

        network = settings.apex_network.lower()
        if network in {"base", "base-sepolia", "testnet-base"}:
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BASE
        elif network == "testnet":
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BNB
        else:
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_MAIN
            network_id = NETWORKID_MAIN

        client = HttpPrivateSign(
            endpoint,
            network_id=network_id,
            zk_seeds=settings.apex_zk_seed,
            zk_l2Key=settings.apex_zk_l2key,
            api_key_credentials={
                "key": settings.apex_api_key,
                "secret": settings.apex_api_secret,
                "passphrase": settings.apex_passphrase,
            },
        )
        # Avoid inheriting system proxy settings that can block testnet calls.
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

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
            if isinstance(acct, dict):
                payload = acct.get("result") or acct
                self._account_cache.update(payload)
        except Exception as exc:
            logger.warning("prime_client get_account_v3 failed", extra={"error": str(exc)})

    def _init_public_client(self, settings: Settings) -> Any:
        from apexomni.http_public import HttpPublic

        endpoint = settings.apex_http_endpoint or "https://omni.apex.exchange"
        client = HttpPublic(endpoint)
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

    # --- WebSocket helpers ---
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _ws_base_endpoint(self) -> str:
        from apexomni.constants import APEX_OMNI_WS_MAIN, APEX_OMNI_WS_TEST
        network = self.settings.apex_network.lower()
        if network in {"base", "base-sepolia", "testnet-base", "testnet"}:
            return APEX_OMNI_WS_TEST
        return APEX_OMNI_WS_MAIN

    async def start_streams(self) -> None:
        if not self.settings.apex_enable_ws or self._ws_running:
            return
        self._ws_running = True
        await asyncio.to_thread(self._start_public_stream)
        await asyncio.to_thread(self._start_private_stream)

    def _start_public_stream(self) -> None:
        try:
            from apexomni.websocket_api import WebSocket
            self._ws_public = WebSocket(endpoint=self._ws_base_endpoint())
            self._ws_public.all_ticker_stream(self._handle_ticker)
            logger.info("public WS stream started")
        except Exception as exc:
            logger.warning("public WS stream failed", extra={"error": str(exc)})

    def _start_private_stream(self) -> None:
        try:
            from apexomni.websocket_api import WebSocket
            creds = {
                "key": self.settings.apex_api_key,
                "secret": self.settings.apex_api_secret,
                "passphrase": self.settings.apex_passphrase,
            }
            self._ws_private = WebSocket(endpoint=self._ws_base_endpoint(), api_key_credentials=creds)
            self._ws_private.account_info_stream_v3(self._handle_account_stream)
            logger.info("private WS stream started")
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

    def _format_with_step(self, value: float, step: Optional[float]) -> str:
        """Format numeric to a string respecting step precision."""
        if not step or step <= 0:
            return str(value)
        step_decimal = Decimal(str(step))
        quantized = Decimal(str(value)).quantize(step_decimal, rounding=ROUND_DOWN)
        return format(quantized, "f").rstrip("0").rstrip(".") if "." in format(quantized, "f") else str(quantized)

    async def _get_usdt_price(self, token: str) -> float:
        """Fetch mid price for TOKEN-USDT via depth, fallback to ticker, then hardcoded 1.0 for ETH."""
        if token.upper() == "USDT":
            return 1.0
        symbol = f"{token.upper()}-USDT"
        try:
            book = await asyncio.to_thread(self._public_client.depth_v3, symbol=symbol, limit=1)
            bids: List[List[str]] = book.get("result", {}).get("bids") or []
            asks: List[List[str]] = book.get("result", {}).get("asks") or []
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                return (best_bid + best_ask) / 2.0
        except Exception as exc:
            logger.warning("depth_v3 failed, trying ticker", extra={"symbol": symbol, "error": str(exc)})
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
        # Fallback: call ticker via HTTP on known endpoints without SDK
        endpoints = []
        if self.settings.apex_http_endpoint:
            endpoints.append(self.settings.apex_http_endpoint)
        endpoints.extend(
            [
                "https://qa.omni.apex.exchange",
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
            with self._lock:
                norm_symbol = self._normalize_symbol_value(symbol)
                self._ws_prices[norm_symbol] = price_f
                publish_positions = self._update_positions_pnl(norm_symbol, price_f)
            self._publish_event({"type": "ticker", "symbol": self._normalize_symbol_value(symbol), "price": price_f})
            if publish_positions:
                self._publish_event({"type": "positions", "payload": list(self._ws_positions.values())})

    def _handle_account_stream(self, message: Dict[str, Any]) -> None:
        payload = None
        if isinstance(message, dict):
            payload = message.get("contents") or message.get("data") or message
        if not isinstance(payload, dict):
            return
        accounts = payload.get("accounts") or payload.get("account") or payload.get("contractAccounts") or []
        positions, has_positions_key = self._extract_positions(payload)
        orders_raw = payload.get("orders") or payload.get("orderList") or []
        has_orders_key = any(k in payload for k in ("orders", "orderList"))

        publish_orders = False
        publish_positions = False

        with self._lock:
            if accounts:
                acct = accounts[0] if isinstance(accounts, list) and accounts else accounts
                if isinstance(acct, dict):
                    self._account_cache.update({"account": acct})
                    self._publish_event({"type": "account", "payload": acct})
            if has_positions_key and positions:
                normalized_pos = {self._normalize_symbol(p): p for p in positions if isinstance(p, dict)}
                new_positions = {k: v for k, v in normalized_pos.items() if k}
                if new_positions:
                    for sym, pos in new_positions.items():
                        prior = self._ws_positions.get(sym, {})
                        if pos.get("entryPrice") is None and prior.get("entryPrice") is not None:
                            pos["entryPrice"] = prior.get("entryPrice")
                        if pos.get("avgPrice") is None and prior.get("avgPrice") is not None:
                            pos["avgPrice"] = prior.get("avgPrice")
                        if pos.get("size") in (None, 0, "0", "0.0") and prior.get("size") not in (None, 0, "0", "0.0"):
                            pos["size"] = prior.get("size")
                        if not pos.get("side") and prior.get("side"):
                            pos["side"] = prior.get("side")
                    self._ws_positions = new_positions
                    publish_positions = True
            if has_orders_key and orders_raw:
                self._ws_orders = self._filter_and_map_orders(orders_raw)
                publish_orders = True

        if publish_positions:
            self._publish_event({"type": "positions", "payload": list(self._ws_positions.values())})
        if publish_orders:
            self._publish_event({"type": "orders", "payload": list(self._ws_orders.values())})

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

    def _filter_and_map_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        mapped: Dict[str, Dict[str, Any]] = {}
        for o in orders:
            if not isinstance(o, dict):
                continue
            status = str(o.get("status") or o.get("orderStatus") or "").lower()
            if status in {"canceled", "cancelled", "filled"}:
                continue
            key = str(o.get("orderId") or o.get("order_id") or o.get("clientOrderId") or o.get("_cache_id") or uuid.uuid4().hex)
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
                        "tickSize": float(item.get("tickSize", 0.0)),
                        "stepSize": float(item.get("stepSize", 0.0)),
                        "minOrderSize": float(item.get("minOrderSize", 0.0)),
                        "maxOrderSize": float(
                            item.get("maxOrderSize") or item.get("maxPositionSize") or 0.0
                        ),
                        "maxLeverage": float(
                            item.get("displayMaxLeverage") or item.get("maxLeverage") or 0.0
                        ),
                        "raw": item,
                    }
                except Exception:
                    continue

            self._configs_cache = mapped
            # Preserve full config payload for SDK methods that expect configV3
            try:
                setattr(self._client, "configV3", payload)
            except Exception:
                pass
            logger.info("configs cached", extra={"count": len(self._configs_cache)})
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

    async def ensure_configs_loaded(self) -> None:
        """Load configs if not already cached."""
        if not self._configs_cache:
            await self.load_configs()

    async def _ensure_account_cached(self) -> None:
        """Ensure account info is cached so we can derive fee rates/limits without extra calls."""
        if self._account_cache:
            return
        try:
            acct = await asyncio.to_thread(self._client.get_account_v3)
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
                    acct = await asyncio.to_thread(account_balance_fn)
                    if acct and isinstance(acct, dict):
                        payload = acct.get("result") or acct.get("data") or acct
                        if isinstance(payload, dict):
                            self._account_cache.update(payload)
                        account = payload.get("account") if isinstance(payload, dict) else None
                        account_equity = None
                        if isinstance(account, dict):
                            account_equity = account.get("totalEquity") or account.get("total_equity")
                        if account_equity is not None:
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
                            return equity_usdt
                except Exception as exc:
                    logger.warning("get_account_balance_v3 failed, falling back", extra={"error": str(exc)})
            # Fallback: legacy account endpoint
            legacy = await asyncio.to_thread(self._client.get_account_v3)
            if not legacy or not isinstance(legacy, dict):
                raise ValueError("Empty account response")
            legacy_payload = legacy.get("result") or legacy
            if isinstance(legacy_payload, dict):
                self._account_cache.update(legacy_payload)
            legacy_account = legacy_payload.get("account", {}) if isinstance(legacy_payload, dict) else {}
            if legacy_account.get("totalEquity") is not None:
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

    async def get_open_positions(self) -> list[Dict[str, Any]]:
        with self._lock:
            if self._ws_positions:
                return list(self._ws_positions.values())
        try:
            resp = await asyncio.to_thread(self._client.get_account_v3)
            payload = resp.get("result") or resp
            positions, has_key = self._extract_positions(payload)
            if positions:
                with self._lock:
                    self._ws_positions = {self._normalize_symbol(p): p for p in positions if isinstance(p, dict)}
                return positions
            with self._lock:
                if self._ws_positions:
                    return list(self._ws_positions.values())
            return positions
        except Exception as exc:
            logger.exception("failed to fetch positions", extra={"error": str(exc)})
            return []

    async def get_open_orders(self) -> list[Dict[str, Any]]:
        with self._lock:
            if self._ws_orders:
                return list(self._ws_orders.values())
        try:
            resp = await asyncio.to_thread(self._client.open_orders_v3)
            payload = resp.get("result") or resp
            orders = payload.get("list") or payload.get("orders") or payload.get("data") or []
            if orders:
                with self._lock:
                    self._ws_orders = self._filter_and_map_orders(orders)
                return orders
            with self._lock:
                if self._ws_orders:
                    return list(self._ws_orders.values())
            return orders
        except Exception as exc:
            logger.exception("failed to fetch open orders", extra={"error": str(exc)})
            return []

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = await asyncio.to_thread(self._client.create_order_v3, **payload)
            order_id = (
                resp.get("result", {}).get("orderId")
                or resp.get("data", {}).get("orderId")
                or resp.get("orderId")
                or resp.get("orderID")
            )
            return {"exchange_order_id": order_id, "raw": resp}
        except Exception as exc:
            logger.exception("failed to place order", extra={"error": str(exc), "payload": payload})
            raise

    async def cancel_order(self, order_id: str, client_id: Optional[str] = None) -> Dict[str, Any]:
        errors: list[str] = []
        # ensure account/config set on client for signature
        try:
            await asyncio.to_thread(self._client.get_account_v3)
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
        """
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "price": entry_price,
            "size": size,
            "reduceOnly": reduce_only,
            "clientId": f"{symbol}-{int(time.time())}-{uuid.uuid4().hex[:8]}",
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
            payload["isOpenTpslOrder"] = True
            payload["isSetOpenTp"] = True
            payload["tpSide"] = "SELL" if side.upper() == "BUY" else "BUY"
            payload["tpSize"] = self._format_with_step(size, step)
        if stop:
            payload["slPrice"] = self._format_with_step(stop, tick)
            payload["slTriggerPrice"] = self._format_with_step(stop, tick)
            payload["isOpenTpslOrder"] = True
            payload["isSetOpenSl"] = True
            payload["slSide"] = "SELL" if side.upper() == "BUY" else "BUY"
            payload["slSize"] = self._format_with_step(size, step)
        return payload, None
