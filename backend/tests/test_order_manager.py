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
        self.ensure_configs_loaded_called = False

    async def get_account_equity(self) -> float:
        return self._equity

    def get_symbol_info(self, symbol: str):
        return self.symbols.get(symbol)

    async def build_order_payload(self, **kwargs):
        return kwargs, None

    async def place_order(self, payload):
        self.placed.append(payload)
        return {"exchange_order_id": "order-123"}

    async def get_open_positions(self, force_rest: bool = False, publish: bool = False):
        return self._positions

    async def get_open_orders(self, force_rest: bool = False, publish: bool = False):
        return self._orders

    def get_account_orders_snapshot(self):
        return list(self._orders)

    async def refresh_account_orders_from_rest(self):
        return list(self._orders)

    async def ensure_configs_loaded(self):
        self.ensure_configs_loaded_called = True

    async def cancel_tpsl_orders(self, *, symbol=None, cancel_tp: bool = True, cancel_sl: bool = True):
        return {"symbol": symbol, "cancel_tp": cancel_tp, "cancel_sl": cancel_sl}

    async def update_targets(self, **kwargs):
        return {"results": [{"payload": kwargs}]}

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
        {"id": "abc", "symbol": "BTC-USDT", "side": "LONG", "size": 1.0, "status": "OPEN", "entry_price": None, "reduce_only": False}
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
        {
            "id": "BTC-USDT",
            "symbol": "BTC-USDT",
            "side": "LONG",
            "size": 1.0,
            "entry_price": 100.0,
            "take_profit": None,
            "stop_loss": None,
            "pnl": 5.0,
        }
    ]


def test_normalize_position_prefers_runtime_pnl():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    pos = {
        "symbol": "ETH-USDT",
        "positionSide": "LONG",
        "size": "1",
        "entryPrice": "2000",
        "unrealizedPnl": "3.5",  # stale payload
        "pnl": "15.25",  # runtime mark-to-market from WS ticker
    }
    normalized = manager._normalize_position(pos)
    assert normalized["pnl"] == pytest.approx(15.25)


def test_extract_tpsl_prefers_latest_untriggered():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    orders = [
        {
            "symbol": "BTC-USDT",
            "type": "TAKE_PROFIT_MARKET",
            "isPositionTpsl": True,
            "triggerPrice": "120",
            "status": "UNTRIGGERED",
            "createdTime": 1000,
        },
        {
            "symbol": "BTC-USDT",
            "type": "TAKE_PROFIT_MARKET",
            "isPositionTpsl": True,
            "triggerPrice": "125",
            "status": "UNTRIGGERED",
            "createdTime": 2000,
        },
        {
            "symbol": "BTC-USDT",
            "type": "STOP_MARKET",
            "isPositionTpsl": True,
            "triggerPrice": "90",
            "status": "UNTRIGGERED",
            "updatedTime": 1500,
        },
    ]
    tpsl_map = manager._extract_tpsl_from_orders(orders)
    assert tpsl_map == {"BTC-USDT": {"take_profit": 125.0, "stop_loss": 90.0}}


def test_extract_tpsl_ignores_non_position_tpsl_orders():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    orders = [
        {"symbol": "BTC-USDT", "type": "LIMIT", "isPositionTpsl": False, "triggerPrice": "90000", "status": "UNTRIGGERED"},
        {"symbol": "BTC-USDT", "type": "STOP_MARKET", "isPositionTpsl": False, "triggerPrice": "80000", "status": "UNTRIGGERED"},
        {"symbol": "BTC-USDT", "type": "TAKE_PROFIT_MARKET", "isPositionTpsl": True, "triggerPrice": "100000", "status": "UNTRIGGERED"},
    ]
    tpsl_map = manager._extract_tpsl_from_orders(orders)
    assert tpsl_map == {"BTC-USDT": {"take_profit": 100000.0}}


def test_enrich_positions_uses_symbol_map_even_with_different_ids():
    gateway = FakeGateway(
        positions=[
            {"positionId": "pos-123", "symbol": "ETH-USDT", "positionSide": "SHORT", "size": "2", "entryPrice": "1800"},
        ]
    )
    manager = OrderManager(gateway)
    enriched = asyncio.run(
        manager._enrich_positions(
            gateway._positions,
            tpsl_map={
                "ETH-USDT": {
                    "take_profit": 1500.0,
                    "stop_loss": 1850.0,
                }
            },
        )
    )
    assert enriched == [
        {
            "id": "pos-123",
            "symbol": "ETH-USDT",
            "side": "SHORT",
            "size": 2.0,
            "entry_price": 1800.0,
            "take_profit": 1500.0,
            "stop_loss": 1850.0,
            "pnl": None,
        }
    ]


def test_modify_targets_seeds_map_and_hints_for_immediate_display(monkeypatch):
    gateway = FakeGateway(
        positions=[
            {"positionId": "pos-1", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
        ],
        orders=[],
    )
    manager = OrderManager(gateway)

    async def fake_update_targets(**kwargs):
        return {"results": [{"payload": kwargs}]}

    monkeypatch.setattr(gateway, "update_targets", fake_update_targets)

    # Call modify_targets to set TP/SL and ensure map/hints updated even without order snapshots
    asyncio.run(manager.modify_targets(position_id="pos-1", take_profit=120.0, stop_loss=90.0))
    enriched = asyncio.run(manager.list_positions())
    assert enriched[0]["take_profit"] == 120.0
    assert enriched[0]["stop_loss"] == 90.0


def test_reconcile_tpsl_preserves_map_on_empty_snapshot():
    gateway = FakeGateway(
        positions=[
            {"positionId": "pos-1", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
        ]
    )
    manager = OrderManager(gateway)
    # Seed map from a TP+SL snapshot
    manager._reconcile_tpsl(
        [
            {
                "symbol": "BTC-USDT",
                "type": "TAKE_PROFIT_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "120",
                "status": "UNTRIGGERED",
            },
            {
                "symbol": "BTC-USDT",
                "type": "STOP_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "90",
                "status": "UNTRIGGERED",
            },
        ]
    )
    # Empty snapshot should leave map intact
    manager._reconcile_tpsl([])
    enriched = asyncio.run(manager.list_positions())
    assert enriched[0]["take_profit"] == 120.0
    assert enriched[0]["stop_loss"] == 90.0


def test_reconcile_tpsl_merges_without_dropping_existing_symbols():
    gateway = FakeGateway(
        positions=[
            {"positionId": "pos-btc", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
            {"positionId": "pos-doge", "symbol": "DOGE-USDT", "positionSide": "LONG", "size": "10", "entryPrice": "0.1"},
        ]
    )
    manager = OrderManager(gateway)
    manager._reconcile_tpsl(
        [
            {
                "symbol": "BTC-USDT",
                "type": "TAKE_PROFIT_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "150",
                "status": "UNTRIGGERED",
            },
            {
                "symbol": "BTC-USDT",
                "type": "STOP_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "90",
                "status": "UNTRIGGERED",
            },
        ]
    )
    # Second snapshot only has DOGE TP; BTC protections should remain.
    manager._reconcile_tpsl(
        [
            {
                "symbol": "DOGE-USDT",
                "type": "TAKE_PROFIT_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "0.25",
                "status": "UNTRIGGERED",
            }
        ]
    )
    enriched = asyncio.run(manager.list_positions())
    btc = next(p for p in enriched if p["symbol"] == "BTC-USDT")
    doge = next(p for p in enriched if p["symbol"] == "DOGE-USDT")
    assert btc["take_profit"] == 150.0
    assert btc["stop_loss"] == 90.0
    assert doge["take_profit"] == 0.25
    assert doge["stop_loss"] is None


def test_reconcile_tpsl_single_cancel_clears_only_that_target():
    gateway = FakeGateway(
        positions=[
            {"positionId": "pos-1", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
        ]
    )
    manager = OrderManager(gateway)
    manager._tpsl_targets_by_symbol["BTC-USDT"] = {"take_profit": 120.0, "stop_loss": 90.0}
    manager.position_targets["BTC-USDT"] = {"take_profit": 120.0, "stop_loss": 90.0}
    # Single canceled TP should drop TP but keep SL intact.
    manager._reconcile_tpsl(
        [
            {
                "symbol": "BTC-USDT",
                "type": "TAKE_PROFIT_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "120",
                "status": "CANCELED",
            }
        ]
    )
    enriched = asyncio.run(manager.list_positions())
    assert enriched[0]["take_profit"] is None
    assert enriched[0]["stop_loss"] == 90.0
    assert manager.position_targets["BTC-USDT"]["stop_loss"] == 90.0
    assert "take_profit" not in manager.position_targets["BTC-USDT"]
