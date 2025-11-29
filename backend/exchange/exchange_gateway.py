import asyncio
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from backend.core.config import Settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ExchangeGateway:
    """Wrapper around ApeX Omni SDK with cached configs and basic helpers."""

    def __init__(self, settings: Settings, client: Optional[Any] = None) -> None:
        self.settings = settings
        self._configs_cache: Dict[str, Any] = {}
        self._client: Any = client if client is not None else self._init_client(settings)

    def _init_client(self, settings: Settings) -> Any:
        from apexomni.constants import APEX_OMNI_HTTP_MAIN, APEX_OMNI_HTTP_TEST, NETWORKID_OMNI_BNB, NETWORKID_OMNI_TEST_BNB
        from apexomni.http_private_v3 import HttpPrivateSign

        network = settings.apex_network.lower()
        if network == "testnet":
            endpoint = APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BNB
        else:
            endpoint = APEX_OMNI_HTTP_MAIN
            network_id = NETWORKID_OMNI_BNB

        return HttpPrivateSign(
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

    async def load_configs(self) -> None:
        """Fetch and cache symbol configs."""
        try:
            result = await asyncio.to_thread(self._client.configs_v3)
            self._configs_cache = {
                item["symbol"]: item for item in result.get("result", {}).get("symbols", [])
            }
            logger.info("configs cached", extra={"count": len(self._configs_cache)})
        except Exception as exc:
            logger.exception("failed to load configs", extra={"error": str(exc)})
            raise

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._configs_cache.get(symbol)

    async def get_account_equity(self) -> float:
        try:
            acct = await asyncio.to_thread(self._client.get_account_v3)
            return float(acct.get("result", {}).get("account", {}).get("totalEquity", 0.0))
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
