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
    def __init__(self, equity: float = 1000.0) -> None:
        self.symbols = {"BTC-USDT": {"tickSize": 0.5, "stepSize": 0.1, "minOrderSize": 0.5, "maxOrderSize": 100.0, "maxLeverage": 5}}
        self._equity = equity
        self.placed = []

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
        return []

    async def get_open_orders(self):
        return []


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
    manager.open_risk_estimates = [150.0]  # existing open risk
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
