from typing import Any, Dict, Optional

from backend.core.config import Settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ExchangeGateway:
    """A thin wrapper around the ApeX Omni SDK (wired in later)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._configs_cache: Dict[str, Any] = {}

    async def load_configs(self) -> None:
        """Fetch and cache symbol configs. Placeholder until SDK wiring."""
        logger.info("load_configs called - placeholder implementation")
        self._configs_cache = {}

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._configs_cache.get(symbol)

    async def get_account_equity(self) -> float:
        logger.info("get_account_equity called - placeholder implementation")
        return 0.0

    async def get_open_positions(self) -> list[Dict[str, Any]]:
        logger.info("get_open_positions called - placeholder implementation")
        return []

    async def get_open_orders(self) -> list[Dict[str, Any]]:
        logger.info("get_open_orders called - placeholder implementation")
        return []

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("place_order called - placeholder implementation", extra={"payload": payload})
        return {"exchange_order_id": "placeholder"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        logger.info("cancel_order called - placeholder implementation", extra={"order_id": order_id})
        return {"canceled": True, "order_id": order_id}

    async def cancel_all(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        logger.info("cancel_all called - placeholder implementation", extra={"symbol": symbol})
        return {"canceled_all": True, "symbol": symbol}
