from typing import Any, Dict, Optional, Tuple

from backend.core.logging import get_logger
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.risk import risk_engine

logger = get_logger(__name__)


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
        equity = await self.gateway.get_account_equity()
        symbol_info = self.gateway.get_symbol_info(symbol)
        if not symbol_info:
            raise risk_engine.PositionSizingError(f"Unknown symbol: {symbol}")

        result = risk_engine.calculate_position_size(
            equity=equity,
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_price=stop_price,
            symbol_config=symbol_info,
        )
        logger.info(
            "preview_trade",
            extra={
                "symbol": symbol,
                "entry": entry_price,
                "stop": stop_price,
                "risk_pct": risk_pct,
                "size": result.size,
                "side": result.side,
                "warnings": result.warnings,
            },
        )
        # warnings may be extended later with caps/other checks
        return result, result.warnings

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
