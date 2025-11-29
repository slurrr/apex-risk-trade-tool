from typing import Any, Dict, Optional, Tuple

from backend.exchange.exchange_gateway import ExchangeGateway
from backend.risk import risk_engine


class OrderManager:
    """Coordinates sizing, risk caps, and order placement."""

    def __init__(self, gateway: ExchangeGateway) -> None:
        self.gateway = gateway
        self.open_orders: list[Dict[str, Any]] = []
        self.positions: list[Dict[str, Any]] = []

    async def preview_trade(
        self,
        *,
        symbol: str,
        entry_price: float,
        stop_price: float,
        risk_pct: float,
        side: Optional[str] = None,
        tp: Optional[float] = None,
    ) -> Tuple[risk_engine.PositionSizingResult, list[str]]:
        """Run sizing without placing an order."""
        raise risk_engine.PositionSizingError("Preview not yet implemented")

    async def execute_trade(
        self,
        *,
        symbol: str,
        entry_price: float,
        stop_price: float,
        risk_pct: float,
        side: Optional[str] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Re-run sizing and place order when safe."""
        raise risk_engine.PositionSizingError("Execute not yet implemented")

    async def refresh_state(self) -> None:
        """Refresh in-memory orders and positions from gateway."""
        self.positions = await self.gateway.get_open_positions()
        self.open_orders = await self.gateway.get_open_orders()
