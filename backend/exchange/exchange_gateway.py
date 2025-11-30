import asyncio
import time
import uuid
from typing import Any, Dict, Optional, Tuple, List

import requests

from backend.core.config import Settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ExchangeGateway:
    """Wrapper around ApeX Omni SDK with cached configs and basic helpers."""

    def __init__(self, settings: Settings, client: Optional[Any] = None) -> None:
        self.settings = settings
        self._configs_cache: Dict[str, Any] = {}
        self._client: Any = client if client is not None else self._init_client(settings)
        self._public_client: Any = self._init_public_client(settings)

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

    def _init_public_client(self, settings: Settings) -> Any:
        from apexomni.http_public import HttpPublic

        endpoint = settings.apex_http_endpoint or "https://omni.apex.exchange"
        client = HttpPublic(endpoint)
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

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

    async def load_configs(self) -> None:
        """Fetch and cache symbol configs."""
        try:
            result = await asyncio.to_thread(self._public_client.configs_v3)
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
            logger.info("configs cached", extra={"count": len(self._configs_cache)})
        except Exception as exc:
            logger.exception("failed to load configs", extra={"error": str(exc)})
            raise

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._configs_cache.get(symbol)

    async def ensure_configs_loaded(self) -> None:
        """Load configs if not already cached."""
        if not self._configs_cache:
            await self.load_configs()

    async def get_account_equity(self) -> float:
        try:
            acct = await asyncio.to_thread(self._client.get_account_v3)
            if not acct or not isinstance(acct, dict):
                raise ValueError("Empty account response")
            payload = acct.get("result") or acct
            account_equity = payload.get("account", {}).get("totalEquity")
            if account_equity is not None:
                return float(account_equity)
            # Fallback: sum contract wallet balances when totalEquity is missing.
            wallets = payload.get("contractWallets") or []
            if isinstance(wallets, list) and wallets:
                equity_usdt = 0.0
                for wallet in wallets:
                    bal = float(wallet.get("balance", 0) or 0)
                    token = wallet.get("token") or "USDT"
                    price = await self._get_usdt_price(token)
                    equity_usdt += bal * price
                return equity_usdt
            raise ValueError("No equity field in account response")
        except Exception as exc:
            logger.exception("failed to fetch account equity", extra={"error": str(exc)})
            raise

    async def get_open_positions(self) -> list[Dict[str, Any]]:
        try:
            resp = await asyncio.to_thread(self._client.get_account_v3)
            return resp.get("result", {}).get("positions", []) or []
        except Exception as exc:
            logger.exception("failed to fetch positions", extra={"error": str(exc)})
            return []

    async def get_open_orders(self) -> list[Dict[str, Any]]:
        try:
            resp = await asyncio.to_thread(self._client.open_orders_v3)
            return resp.get("result", {}).get("list", []) or []
        except Exception as exc:
            logger.exception("failed to fetch open orders", extra={"error": str(exc)})
            return []

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = await asyncio.to_thread(self._client.create_order_v3, **payload)
            return {
                "exchange_order_id": resp.get("result", {}).get("orderId"),
                "raw": resp,
            }
        except Exception as exc:
            logger.exception("failed to place order", extra={"error": str(exc), "payload": payload})
            raise

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        try:
            resp = await asyncio.to_thread(self._client.delete_order_v3, orderId=order_id)
            return {"canceled": True, "order_id": order_id, "raw": resp}
        except Exception as exc:
            logger.exception("failed to cancel order", extra={"error": str(exc), "order_id": order_id})
            raise

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
            "clientOrderId": f"{symbol}-{int(time.time())}-{uuid.uuid4().hex[:8]}",
        }
        if tp:
            payload["tpTriggerBy"] = "LAST_PRICE"
            payload["takeProfit"] = tp
        if stop:
            payload["stopLoss"] = stop
            payload["slTriggerBy"] = "LAST_PRICE"
        return payload, None
