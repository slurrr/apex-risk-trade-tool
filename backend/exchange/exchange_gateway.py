import time
import uuid
from typing import Any, Dict, Optional, Tuple

from backend.core.config import Settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ExchangeGateway:
    """A thin wrapper around the ApeX Omni SDK (wired in later)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._configs_cache: Dict[str, Any] = {}

    async def load_configs(self) -> None:
        """Fetch and cache symbol configs. Placeholder data until SDK is wired."""
        logger.info("load_configs called - placeholder implementation")
        # Minimal placeholder config for BTC-USDT; extend as needed
        self._configs_cache = {
            "BTC-USDT": {
                "tickSize": 0.1,
                "stepSize": 0.001,
                "minOrderSize": 0.001,
                "maxOrderSize": 10_000,
                "maxLeverage": 20,
            }
        }

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._configs_cache.get(symbol)

    async def get_account_equity(self) -> float:
        logger.info("get_account_equity called - placeholder implementation")
        # Simulate non-zero equity
        return 10_000.0

    async def get_open_positions(self) -> list[Dict[str, Any]]:
        logger.info("get_open_positions called - placeholder implementation")
        return []

    async def get_open_orders(self) -> list[Dict[str, Any]]:
        logger.info("get_open_orders called - placeholder implementation")
        return []

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("place_order called - placeholder implementation", extra={"payload": payload})
        # Simulate an exchange order id
        return {"exchange_order_id": f"sim-{uuid.uuid4()}"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        logger.info("cancel_order called - placeholder implementation", extra={"order_id": order_id})
        return {"canceled": True, "order_id": order_id}

    async def cancel_all(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        logger.info("cancel_all called - placeholder implementation", extra={"symbol": symbol})
        return {"canceled_all": True, "symbol": symbol}

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
        Build a placeholder payload; real SDK call will be wired later.
        Returns (payload, warning).
        """
        payload = {
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": entry_price,
            "reduceOnly": reduce_only,
            "clientOrderId": f"{symbol}-{int(time.time())}-{uuid.uuid4().hex[:8]}",
        }
        if tp:
            payload["tp"] = tp
        if stop:
            payload["sl"] = stop
        return payload, None
