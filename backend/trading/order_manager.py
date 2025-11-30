from typing import Any, Dict, Optional, Tuple

from backend.core.logging import get_logger
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.risk import risk_engine

logger = get_logger(__name__)


class OrderManager:
    """Coordinates sizing, risk caps, and order placement."""

    def __init__(
        self,
        gateway: ExchangeGateway,
        *,
        per_trade_risk_cap_pct: Optional[float] = None,
        daily_loss_cap_pct: Optional[float] = None,
        open_risk_cap_pct: Optional[float] = None,
    ) -> None:
        self.gateway = gateway
        self.per_trade_risk_cap_pct = per_trade_risk_cap_pct
        self.daily_loss_cap_pct = daily_loss_cap_pct
        self.open_risk_cap_pct = open_risk_cap_pct
        self.daily_realized_loss: float = 0.0
        self.open_risk_estimates: Dict[str, float] = {}
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
        await self.gateway.ensure_configs_loaded()
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
        await self.gateway.ensure_configs_loaded()
        equity = await self.gateway.get_account_equity()
        symbol_info = self.gateway.get_symbol_info(symbol)
        if not symbol_info:
            raise risk_engine.PositionSizingError(f"Unknown symbol: {symbol}")

        # Risk caps
        if self.per_trade_risk_cap_pct is not None and risk_pct > self.per_trade_risk_cap_pct:
            raise risk_engine.PositionSizingError(
                f"Risk % {risk_pct} exceeds per-trade cap {self.per_trade_risk_cap_pct}"
            )

        sizing = risk_engine.calculate_position_size(
            equity=equity,
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_price=stop_price,
            symbol_config=symbol_info,
        )

        if self.daily_loss_cap_pct is not None:
            daily_limit = equity * (self.daily_loss_cap_pct / 100.0)
            if self.daily_realized_loss >= daily_limit:
                raise risk_engine.PositionSizingError("Daily loss cap exceeded.")
            if (self.daily_realized_loss + sizing.estimated_loss) > daily_limit:
                raise risk_engine.PositionSizingError("Order would exceed daily loss cap.")

        if self.open_risk_cap_pct is not None:
            open_risk_limit = equity * (self.open_risk_cap_pct / 100.0)
            if sum(self.open_risk_estimates.values()) + sizing.estimated_loss > open_risk_limit:
                raise risk_engine.PositionSizingError("Order would exceed open-risk cap.")

        payload, payload_warning = await self.gateway.build_order_payload(
            symbol=symbol,
            side=sizing.side,
            size=sizing.size,
            entry_price=sizing.entry_price,
            reduce_only=False,
            tp=tp,
            stop=stop_price,
        )
        warnings = list(sizing.warnings)
        if payload_warning:
            warnings.append(payload_warning)

        logger.info(
            "execute_trade",
            extra={
                "symbol": symbol,
                "entry": entry_price,
                "stop": stop_price,
                "risk_pct": risk_pct,
                "size": sizing.size,
                "side": sizing.side,
                "warnings": warnings,
            },
        )

        order_resp = await self.gateway.place_order(payload)
        exchange_order_id = order_resp.get("exchange_order_id")
        if not exchange_order_id:
            raise risk_engine.PositionSizingError("Order placement failed: no order id returned")

        self.open_risk_estimates[exchange_order_id] = sizing.estimated_loss

        return {
            "executed": True,
            "exchange_order_id": exchange_order_id,
            "warnings": warnings,
            "sizing": sizing,
        }

    async def refresh_state(self) -> None:
        """Refresh in-memory orders and positions from gateway."""
        self.positions = [self._normalize_position(pos) for pos in await self.gateway.get_open_positions()]
        raw_orders = await self.gateway.get_open_orders()
        self.open_orders = [self._normalize_order(order) for order in raw_orders]
        # drop risk estimates for orders no longer present
        open_ids = {order["id"] for order in self.open_orders if order.get("id")}
        self.open_risk_estimates = {
            order_id: risk for order_id, risk in self.open_risk_estimates.items() if order_id in open_ids
        }
        logger.info(
            "state_refreshed",
            extra={"positions_count": len(self.positions), "open_orders_count": len(self.open_orders)},
        )

    async def list_orders(self) -> list[Dict[str, Any]]:
        """Return open orders from gateway and update cache."""
        raw_orders = await self.gateway.get_open_orders()
        self.open_orders = [self._normalize_order(order) for order in raw_orders]
        return self.open_orders

    async def list_positions(self) -> list[Dict[str, Any]]:
        """Return open positions from gateway and update cache."""
        self.positions = [self._normalize_position(pos) for pos in await self.gateway.get_open_positions()]
        return self.positions

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order and refresh cached state."""
        result = await self.gateway.cancel_order(order_id)
        self.open_orders = [
            order
            for order in self.open_orders
            if str(order.get("id")) != order_id
        ]
        await self.refresh_state()
        self.open_risk_estimates.pop(order_id, None)
        logger.info("cancel_order", extra={"order_id": order_id})
        return result

    def _normalize_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Return a consistent shape for UI/API consumption."""
        return {
            "id": str(order.get("orderId") or order.get("order_id") or order.get("clientOrderId") or ""),
            "symbol": order.get("symbol") or order.get("market"),
            "side": order.get("side") or order.get("positionSide") or order.get("direction"),
            "size": order.get("size") or order.get("qty") or order.get("quantity"),
            "status": order.get("status") or order.get("state") or order.get("orderStatus"),
            "price": order.get("price") or order.get("avgPrice") or order.get("orderPrice"),
        }

    def _normalize_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """Return a consistent shape for UI/API consumption."""
        return {
            "symbol": position.get("symbol") or position.get("market"),
            "side": position.get("side") or position.get("positionSide") or position.get("direction"),
            "size": position.get("size") or position.get("qty") or position.get("quantity"),
            "entry_price": position.get("entryPrice") or position.get("avgPrice") or position.get("entry_price"),
            "pnl": position.get("unrealizedPnl") or position.get("unrealizedPnlUsd") or position.get("pnl"),
        }
