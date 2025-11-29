import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.risk.risk_engine import PositionSizingError  # noqa: E402
from backend.trading.order_manager import OrderManager  # noqa: E402


class FakeGateway:
    def __init__(self, equity: float = 1000.0, orders=None, positions=None) -> None:
        self.symbols = {"BTC-USDT": {"tickSize": 0.5, "stepSize": 0.1, "minOrderSize": 0.5, "maxOrderSize": 100.0, "maxLeverage": 5}}
        self._equity = equity
        self.placed = []
        self._orders = orders or []
        self._positions = positions or []

    async def get_account_equity(self) -> float:
        return self._equity

    def get_symbol_info(self, symbol: str):
        return self.symbols.get(symbol)

    async def build_order_payload(self, **kwargs):
        return kwargs, None

    async def place_order(self, payload):
        self.placed.append(payload)
        return {"exchange_order_id": "order-123"}

    async def get_open_positions(self):
        return self._positions

    async def get_open_orders(self):
        return self._orders


def test_execute_trade_happy_path():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    result = asyncio.run(
        manager.execute_trade(
            symbol="BTC-USDT",
            entry_price=100,
            stop_price=95,
            risk_pct=1,
        )
    )
    assert result["executed"] is True
    assert result["exchange_order_id"] == "order-123"
    assert result["sizing"].size > 0


def test_execute_trade_unknown_symbol():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    with pytest.raises(PositionSizingError):
        asyncio.run(
            manager.execute_trade(
                symbol="UNKNOWN",
                entry_price=100,
                stop_price=95,
                risk_pct=1,
            )
        )


def test_execute_trade_rejects_per_trade_cap():
    gateway = FakeGateway()
    manager = OrderManager(gateway, per_trade_risk_cap_pct=0.5)
    with pytest.raises(PositionSizingError):
        asyncio.run(
            manager.execute_trade(
                symbol="BTC-USDT",
                entry_price=100,
                stop_price=95,
                risk_pct=1.0,
            )
        )


def test_execute_trade_rejects_open_risk_cap():
    gateway = FakeGateway(equity=10000)
    manager = OrderManager(gateway, open_risk_cap_pct=2.0)
    manager.open_risk_estimates = {"existing": 150.0}  # existing open risk
    # New estimated loss would be 50 (size 10 * per unit 5)
    with pytest.raises(PositionSizingError):
        asyncio.run(
            manager.execute_trade(
                symbol="BTC-USDT",
                entry_price=100,
                stop_price=95,
                risk_pct=1.0,
            )
        )


def test_list_orders_normalizes_fields():
    gateway = FakeGateway(
        orders=[
            {"orderId": "abc", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "status": "OPEN"},
        ]
    )
    manager = OrderManager(gateway)
    orders = asyncio.run(manager.list_orders())
    assert orders == [
        {"id": "abc", "symbol": "BTC-USDT", "side": "LONG", "size": "1", "status": "OPEN", "price": None}
    ]


def test_list_positions_normalizes_fields():
    gateway = FakeGateway(
        positions=[
            {"symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100", "unrealizedPnl": "5"},
        ]
    )
    manager = OrderManager(gateway)
    positions = asyncio.run(manager.list_positions())
    assert positions == [
        {"symbol": "BTC-USDT", "side": "LONG", "size": "1", "entry_price": "100", "pnl": "5"}
    ]
