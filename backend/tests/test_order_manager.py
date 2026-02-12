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
    def __init__(self, equity: float = 1000.0, orders=None, positions=None, venue: str = "apex") -> None:
        self.symbols = {"BTC-USDT": {"tickSize": 0.5, "stepSize": 0.1, "minOrderSize": 0.5, "maxOrderSize": 100.0, "maxLeverage": 5}}
        self._equity = equity
        self.placed = []
        self._orders = orders or []
        self._positions = positions or []
        self.venue = venue
        self.ensure_configs_loaded_called = False
        self.hint_unconfirmed_count = 0

    async def get_account_equity(self) -> float:
        return self._equity

    async def get_account_summary(self):
        return {"available_margin": self._equity, "total_equity": self._equity, "total_upnl": 0.0}

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

    async def place_close_order(self, *, symbol: str, side: str, size: float, close_type: str, limit_price=None):
        return {"exchange_order_id": "close-oid-1", "client_id": "close-cid-1", "raw": {"ok": True}}

    async def get_reference_price(self, symbol: str):
        return 101.25, "mid"

    def record_tpsl_hint_unconfirmed(self):
        self.hint_unconfirmed_count += 1

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


def test_close_position_market_returns_payload_and_refreshes():
    gateway = FakeGateway(
        positions=[
            {"positionId": "BTC-USDT", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
        ]
    )
    manager = OrderManager(gateway)
    result = asyncio.run(
        manager.close_position(
            position_id="BTC-USDT",
            close_percent=100.0,
            close_type="market",
            limit_price=None,
        )
    )
    assert isinstance(result, dict)
    assert result["position_id"] == "BTC-USDT"
    assert result["exchange"]["exchange_order_id"] == "close-oid-1"


def test_close_position_limit_returns_payload():
    gateway = FakeGateway(
        positions=[
            {"positionId": "BTC-USDT", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "2", "entryPrice": "100"},
        ]
    )
    manager = OrderManager(gateway)
    result = asyncio.run(
        manager.close_position(
            position_id="BTC-USDT",
            close_percent=50.0,
            close_type="limit",
            limit_price=101.0,
        )
    )
    assert isinstance(result, dict)
    assert result["position_id"] == "BTC-USDT"
    assert result["close_size"] == pytest.approx(1.0)


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


def test_get_symbol_price_uses_reference_price():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    payload = asyncio.run(manager.get_symbol_price("BTC-USDT"))
    assert payload == {"symbol": "BTC-USDT", "price": 101.25}


def test_preview_trade_rejects_hyperliquid_min_notional():
    gateway = FakeGateway(venue="hyperliquid")
    manager = OrderManager(gateway, hyperliquid_min_notional_usdc=10.0)
    with pytest.raises(PositionSizingError, match="below Hyperliquid minimum"):
        asyncio.run(
            manager.preview_trade(
                symbol="BTC-USDT",
                entry_price=5.0,
                stop_price=4.5,
                risk_pct=0.05,
            )
        )


def test_execute_trade_rejects_hyperliquid_min_notional():
    gateway = FakeGateway(venue="hyperliquid")
    manager = OrderManager(gateway, hyperliquid_min_notional_usdc=10.0)
    with pytest.raises(PositionSizingError, match="below Hyperliquid minimum"):
        asyncio.run(
            manager.execute_trade(
                symbol="BTC-USDT",
                entry_price=5.0,
                stop_price=4.5,
                risk_pct=0.05,
            )
        )
    assert gateway.placed == []


def test_execute_trade_hl_grouped_submit_warning_on_partial_leg_reject():
    class _Gateway(FakeGateway):
        def __init__(self):
            super().__init__(venue="hyperliquid")

        async def build_order_payload(self, **kwargs):
            payload = {
                "coin": "BTC",
                "is_buy": True,
                "price": kwargs["entry_price"],
                "size": kwargs["size"],
                "order_requests": [{}, {}, {}],
                "grouping": "normalTpsl",
            }
            return payload, None

        async def place_order(self, payload):
            self.placed.append(payload)
            return {
                "exchange_order_id": "order-123",
                "raw": {
                    "response": {
                        "data": {
                            "statuses": [
                                {"resting": {"oid": 1}},
                                "waitingForFill",
                                {"error": "bad trigger"},
                            ]
                        }
                    }
                },
            }

    gateway = _Gateway()
    manager = OrderManager(gateway)
    result = asyncio.run(
        manager.execute_trade(
            symbol="BTC-USDT",
            entry_price=100,
            stop_price=95,
            risk_pct=1,
            tp=110,
        )
    )
    assert result["executed"] is True
    assert any("did not fully accept all attached TP/SL legs" in w for w in result["warnings"])


def test_execute_trade_hl_grouped_submit_no_warning_when_all_legs_accepted():
    class _Gateway(FakeGateway):
        def __init__(self):
            super().__init__(venue="hyperliquid")

        async def build_order_payload(self, **kwargs):
            payload = {
                "coin": "BTC",
                "is_buy": True,
                "price": kwargs["entry_price"],
                "size": kwargs["size"],
                "order_requests": [{}, {}, {}],
                "grouping": "normalTpsl",
            }
            return payload, None

        async def place_order(self, payload):
            self.placed.append(payload)
            return {
                "exchange_order_id": "order-123",
                "raw": {
                    "response": {
                        "data": {
                            "statuses": [
                                {"resting": {"oid": 1}},
                                "waitingForFill",
                                "waitingForFill",
                            ]
                        }
                    }
                },
            }

    gateway = _Gateway()
    manager = OrderManager(gateway)
    result = asyncio.run(
        manager.execute_trade(
            symbol="BTC-USDT",
            entry_price=100,
            stop_price=95,
            risk_pct=1,
            tp=110,
        )
    )
    assert result["executed"] is True
    assert not any("attached TP/SL legs" in w for w in result["warnings"])


def test_execute_trade_hyperliquid_retries_with_reduced_size_on_margin_error():
    class _Gateway(FakeGateway):
        def __init__(self):
            super().__init__(venue="hyperliquid")
            self._summary_calls = 0

        async def get_account_summary(self):
            self._summary_calls += 1
            if self._summary_calls == 1:
                return {"available_margin": 1000.0, "total_equity": 1000.0, "total_upnl": 0.0}
            # Keep margin tight but still enough for a reduced size >= minOrderSize.
            return {"available_margin": 12.0, "total_equity": 1000.0, "total_upnl": 0.0}

        async def place_order(self, payload):
            self.placed.append(payload)
            if len(self.placed) == 1:
                return {
                    "exchange_order_id": None,
                    "raw": {
                        "status": "ok",
                        "response": {"type": "order", "data": {"statuses": [{"error": "Insufficient margin to place order. asset=209"}]}},
                    },
                }
            return {"exchange_order_id": "order-123"}

    gateway = _Gateway()
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
    assert len(gateway.placed) == 2
    assert float(gateway.placed[1]["size"]) < float(gateway.placed[0]["size"])
    assert any("margin tightened at submit time" in w for w in result["warnings"])


def test_execute_trade_hyperliquid_fails_when_summary_unavailable():
    class _Gateway(FakeGateway):
        def __init__(self):
            super().__init__(venue="hyperliquid")

        async def get_account_summary(self):
            raise RuntimeError("summary fetch failed")

    gateway = _Gateway()
    manager = OrderManager(gateway)
    with pytest.raises(PositionSizingError, match="Unable to fetch Hyperliquid account summary"):
        asyncio.run(
            manager.execute_trade(
                symbol="BTC-USDT",
                entry_price=100,
                stop_price=95,
                risk_pct=1,
            )
        )
    assert gateway.placed == []


def test_execute_trade_hyperliquid_fails_when_available_margin_missing():
    class _Gateway(FakeGateway):
        def __init__(self):
            super().__init__(venue="hyperliquid")

        async def get_account_summary(self):
            return {"total_equity": 1000.0, "total_upnl": 0.0}

    gateway = _Gateway()
    manager = OrderManager(gateway)
    with pytest.raises(PositionSizingError, match="available margin is unavailable"):
        asyncio.run(
            manager.execute_trade(
                symbol="BTC-USDT",
                entry_price=100,
                stop_price=95,
                risk_pct=1,
            )
        )
    assert gateway.placed == []


def test_list_orders_hyperliquid_hides_tpsl_orders():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "BTC-USDT",
                "side": "BUY",
                "size": "0.01",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
            },
            {
                "orderId": "sl-1",
                "symbol": "BTC-USDT",
                "side": "SELL",
                "size": "0.01",
                "status": "OPEN",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "isPositionTpsl": True,
            },
        ],
    )
    manager = OrderManager(gateway)
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_list_orders_apex_hides_tpsl_orders():
    gateway = FakeGateway(
        venue="apex",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "BTC-USDT",
                "side": "BUY",
                "size": "0.01",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
            },
            {
                "orderId": "sl-1",
                "symbol": "BTC-USDT",
                "side": "SELL",
                "size": "0.01",
                "status": "OPEN",
                "type": "STOP_MARKET",
                "reduceOnly": True,
                "isPositionTpsl": True,
            },
        ],
    )
    manager = OrderManager(gateway)
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_list_orders_hides_terminal_and_rejected_status_rows():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "open-1",
                "symbol": "ASTER-USDC",
                "side": "SELL",
                "size": "100",
                "status": "OPEN",
                "type": "LIMIT",
            },
            {
                "orderId": "rej-1",
                "symbol": "ASTER-USDC",
                "side": "SELL",
                "size": "100",
                "status": "perpMarginRejected",
                "type": "LIMIT",
            },
            {
                "orderId": "fill-1",
                "symbol": "ASTER-USDC",
                "side": "SELL",
                "size": "100",
                "status": "FILLED",
                "type": "LIMIT",
            },
        ],
    )
    manager = OrderManager(gateway)
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "open-1"


def test_list_orders_hyperliquid_hides_reduce_only_trigger_rows_without_tpsl_flag():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "ASTER-USDC",
                "side": "SELL",
                "size": "1200",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
            },
            {
                "orderId": "sl-transient-1",
                "symbol": "ASTER-USDC",
                "side": "BUY",
                "size": "1200",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": True,
                "isPositionTpsl": False,
                "triggerPrice": "0.78",
            },
        ],
    )
    manager = OrderManager(gateway)
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_list_orders_hyperliquid_hides_transient_helper_rows_via_recent_submit_hint():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "XPL-USDC",
                "side": "BUY",
                "size": "11678",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
                "price": "0.082",
            },
            {
                # Transient helper row missing explicit TP/SL markers.
                "orderId": "sl-transient-1",
                "symbol": "XPL-USDC",
                "side": "SELL",
                "size": "11678",
                "status": "OPEN",
                "type": "LIMIT",
                "price": "0.080543",
                "isPositionTpsl": False,
            },
        ],
    )
    manager = OrderManager(gateway)
    manager._record_hl_transient_helper_hints(
        {
            "order_requests": [
                {"coin": "XPL", "is_buy": True, "sz": 11678, "limit_px": 0.082, "reduce_only": False},
                {
                    "coin": "XPL",
                    "is_buy": False,
                    "sz": 11678,
                    "limit_px": 0.080543,
                    "reduce_only": True,
                    "order_type": {"trigger": {"isMarket": True, "triggerPx": 0.080543, "tpsl": "sl"}},
                },
            ]
        }
    )
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_update_targets_hyperliquid_hides_transient_helper_rows_via_single_leg_hint():
    gateway = FakeGateway(
        venue="hyperliquid",
        positions=[
            {
                "positionId": "XPL-USDC",
                "symbol": "XPL-USDC",
                "positionSide": "LONG",
                "size": "1000",
                "entryPrice": "0.083",
            }
        ],
        orders=[
            {
                "orderId": "sl-transient-1",
                "symbol": "XPL-USDC",
                "side": "SELL",
                "size": "1000",
                "status": "OPEN",
                "type": "LIMIT",
                "price": "0.0815",
                "isPositionTpsl": False,
            }
        ],
    )
    manager = OrderManager(gateway)
    asyncio.run(
        manager.modify_targets(
            position_id="XPL-USDC",
            take_profit=None,
            stop_loss=0.0815,
            clear_tp=False,
            clear_sl=False,
        )
    )
    orders = asyncio.run(manager.list_orders())
    assert orders == []


def test_list_orders_hyperliquid_hides_transient_helper_rows_without_trigger_flags_when_size_nearby():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "XPL-USDC",
                "side": "BUY",
                "size": "1000",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
                "price": "0.0830",
            },
            {
                # Helper row shape seen in the wild: no trigger markers and no reduce-only flag.
                "orderId": "sl-transient-1",
                "symbol": "XPL-USDC",
                "side": "SELL",
                "size": "999.8",
                "status": "OPEN",
                "type": "LIMIT",
                "price": "0.0815",
                "isPositionTpsl": False,
            },
        ],
    )
    manager = OrderManager(gateway)
    manager._record_hl_transient_helper_hints(
        {
            "order_requests": [
                {
                    "coin": "XPL",
                    "is_buy": False,
                    "sz": 1000,
                    "limit_px": 0.0815,
                    "reduce_only": True,
                    "order_type": {"trigger": {"isMarket": True, "triggerPx": 0.0815, "tpsl": "sl"}},
                }
            ]
        }
    )
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_list_orders_hyperliquid_hides_transient_helper_rows_without_markers_or_client_id():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "XPL-USDC",
                "side": "BUY",
                "size": "1000",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
                "price": "0.0830",
                "clientOrderId": "user-entry-1",
            },
            {
                # Helper row occasionally arrives with no trigger/reduce/client-id markers.
                "orderId": "sl-transient-1",
                "symbol": "XPL-USDC",
                "side": "SELL",
                "size": "777",
                "status": "OPEN",
                "type": "LIMIT",
                "price": "0.0815",
                "isPositionTpsl": False,
            },
        ],
    )
    manager = OrderManager(gateway)
    manager._record_hl_transient_helper_hints(
        {
            "order_requests": [
                {
                    "coin": "XPL",
                    "is_buy": False,
                    "sz": 1000,
                    "limit_px": 0.0815,
                    "reduce_only": True,
                    "order_type": {"trigger": {"isMarket": True, "triggerPx": 0.0815, "tpsl": "sl"}},
                }
            ]
        }
    )
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_list_orders_hyperliquid_hides_known_target_helper_without_markers():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "entry-1",
                "symbol": "XPL-USDC",
                "side": "BUY",
                "size": "100",
                "status": "OPEN",
                "type": "LIMIT",
                "reduceOnly": False,
                "price": "0.0830",
                "clientOrderId": "user-entry-1",
            },
            {
                "orderId": "sl-helper-1",
                "symbol": "XPL-USDC",
                "side": "SELL",
                "size": "1000",
                "status": "OPEN",
                "type": "LIMIT",
                "price": "0.0815",
                "isPositionTpsl": False,
            },
        ],
        positions=[
            {"positionId": "XPL-USDC", "symbol": "XPL-USDC", "positionSide": "LONG", "size": "1000", "entryPrice": "0.083"},
        ],
    )
    manager = OrderManager(gateway)
    manager.position_targets["XPL-USDC"] = {"stop_loss": 0.0815}
    manager._tpsl_targets_by_symbol["XPL-USDC"] = {"stop_loss": 0.0815}
    manager.positions = [{"symbol": "XPL-USDC", "side": "LONG", "size": 1000.0}]
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "entry-1"


def test_list_orders_hyperliquid_keeps_user_order_even_if_price_matches_target_when_client_id_present():
    gateway = FakeGateway(
        venue="hyperliquid",
        orders=[
            {
                "orderId": "manual-1",
                "symbol": "XPL-USDC",
                "side": "SELL",
                "size": "100",
                "status": "OPEN",
                "type": "LIMIT",
                "price": "0.0815",
                "clientOrderId": "manual-user-order",
            },
        ],
        positions=[
            {"positionId": "XPL-USDC", "symbol": "XPL-USDC", "positionSide": "LONG", "size": "1000", "entryPrice": "0.083"},
        ],
    )
    manager = OrderManager(gateway)
    manager.position_targets["XPL-USDC"] = {"stop_loss": 0.0815}
    manager._tpsl_targets_by_symbol["XPL-USDC"] = {"stop_loss": 0.0815}
    manager.positions = [{"symbol": "XPL-USDC", "side": "LONG", "size": 1000.0}]
    orders = asyncio.run(manager.list_orders())
    assert len(orders) == 1
    assert orders[0]["id"] == "manual-1"


def test_list_positions_apex_backfills_tpsl_without_manual_refresh():
    gateway = FakeGateway(
        venue="apex",
        positions=[
            {"positionId": "pos-1", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
        ],
        orders=[
            {
                "symbol": "BTC-USDT",
                "type": "STOP_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "90",
                "status": "UNTRIGGERED",
            }
        ],
    )
    manager = OrderManager(gateway)
    positions = asyncio.run(manager.list_positions())
    assert positions[0]["stop_loss"] == 90.0


def test_list_positions_hyperliquid_backfills_tpsl_without_manual_refresh():
    gateway = FakeGateway(
        venue="hyperliquid",
        positions=[
            {"positionId": "pos-1", "symbol": "BTC-USDT", "positionSide": "LONG", "size": "1", "entryPrice": "100"},
        ],
        orders=[
            {
                "symbol": "BTC-USDT",
                "type": "STOP_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "90",
                "status": "UNTRIGGERED",
                "reduceOnly": True,
            }
        ],
    )
    manager = OrderManager(gateway)
    positions = asyncio.run(manager.list_positions())
    assert positions[0]["stop_loss"] == 90.0


def test_preview_trade_hyperliquid_margin_guard_uses_leverage():
    class _Gateway(FakeGateway):
        async def get_account_summary(self):
            # Small free margin, but leverage should permit larger notional.
            return {"available_margin": 100.0, "total_equity": self._equity, "total_upnl": 0.0}

    gateway = _Gateway(equity=1000.0, venue="hyperliquid")
    gateway.symbols["BTC-USDT"]["maxLeverage"] = 20
    manager = OrderManager(gateway, hyperliquid_min_notional_usdc=10.0)

    result, _warnings = asyncio.run(
        manager.preview_trade(
            symbol="BTC-USDT",
            entry_price=100.0,
            stop_price=95.0,
            risk_pct=1.0,
        )
    )
    # notional ~= 200, required initial margin ~= 10 at 20x leverage
    assert result.notional > 100.0


def test_preview_trade_hyperliquid_margin_guard_caps_by_available_margin():
    class _Gateway(FakeGateway):
        async def get_account_summary(self):
            return {"available_margin": 50.0, "total_equity": self._equity, "total_upnl": 0.0}

    gateway = _Gateway(equity=1000.0, venue="hyperliquid")
    gateway.symbols["BTC-USDT"]["maxLeverage"] = 2
    manager = OrderManager(gateway, hyperliquid_min_notional_usdc=10.0)

    result, _warnings = asyncio.run(
        manager.preview_trade(
            symbol="BTC-USDT",
            entry_price=100.0,
            stop_price=95.0,
            risk_pct=1.0,
        )
    )
    # available_margin=50 and leverage=2 => max notional should cap at 100.
    assert result.notional <= 100.0 + 1e-9


def test_preview_trade_hyperliquid_leverage_cap_uses_available_margin():
    class _Gateway(FakeGateway):
        async def get_account_summary(self):
            # Equity is high, but free margin is much lower.
            return {"available_margin": 100.0, "total_equity": self._equity, "total_upnl": 0.0}

    gateway = _Gateway(equity=1000.0, venue="hyperliquid")
    gateway.symbols["BTC-USDT"]["maxLeverage"] = 10
    manager = OrderManager(gateway, hyperliquid_min_notional_usdc=10.0)

    result, _warnings = asyncio.run(
        manager.preview_trade(
            symbol="BTC-USDT",
            entry_price=100.0,
            stop_price=95.0,
            risk_pct=20.0,
        )
    )
    # available_margin=100 and leverage=10 => max notional should cap at 1000.
    assert result.notional <= 1000.0 + 1e-9


def test_preview_trade_hyperliquid_uses_sizing_available_margin_when_present():
    class _Gateway(FakeGateway):
        async def get_account_summary(self):
            return {
                "available_margin": 1000.0,
                "sizing_available_margin": 100.0,
                "total_equity": self._equity,
                "total_upnl": 0.0,
            }

    gateway = _Gateway(equity=1000.0, venue="hyperliquid")
    gateway.symbols["BTC-USDT"]["maxLeverage"] = 10
    manager = OrderManager(gateway, hyperliquid_min_notional_usdc=10.0)

    result, _warnings = asyncio.run(
        manager.preview_trade(
            symbol="BTC-USDT",
            entry_price=100.0,
            stop_price=95.0,
            risk_pct=20.0,
        )
    )
    # Must be capped by sizing_available_margin (100 * 10 = 1000), not available_margin 1000.
    assert result.notional <= 1000.0 + 1e-9


def test_tpsl_local_hint_takes_precedence_then_expires_to_ws_value():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    manager._tpsl_hint_ttl_seconds = 0.01
    manager._tpsl_targets_by_symbol["BTC-USDT"] = {"take_profit": 120.0}
    manager._set_local_tpsl_hint(symbol="BTC-USDT", take_profit=125.0)

    pos = manager._normalize_position(
        {
            "symbol": "BTC-USDT",
            "positionSide": "LONG",
            "size": "1",
            "entryPrice": "100",
        }
    )
    assert pos["take_profit"] == 125.0

    # Expire the hint and ensure we fall back to WS/cache value.
    manager._tpsl_local_hints["BTC-USDT"]["take_profit_observed_at"] = 0.0
    pos_after_expiry = manager._normalize_position(
        {
            "symbol": "BTC-USDT",
            "positionSide": "LONG",
            "size": "1",
            "entryPrice": "100",
        }
    )
    assert pos_after_expiry["take_profit"] == 120.0
    assert gateway.hint_unconfirmed_count >= 1


def test_tpsl_ws_reconcile_contradiction_overrides_fresh_local_hint_immediately():
    gateway = FakeGateway()
    manager = OrderManager(gateway)
    manager._tpsl_hint_ttl_seconds = 20.0
    manager._tpsl_targets_by_symbol["BTC-USDT"] = {"take_profit": 120.0}
    manager._set_local_tpsl_hint(symbol="BTC-USDT", take_profit=125.0)

    # Explicit TP reconcile payload contradicts the local hint.
    manager._reconcile_tpsl(
        [
            {
                "symbol": "BTC-USDT",
                "type": "TAKE_PROFIT_MARKET",
                "isPositionTpsl": True,
                "triggerPrice": "120",
                "status": "UNTRIGGERED",
            }
        ]
    )

    pos = manager._normalize_position(
        {
            "symbol": "BTC-USDT",
            "positionSide": "LONG",
            "size": "1",
            "entryPrice": "100",
        }
    )
    assert pos["take_profit"] == 120.0
    hint = manager._tpsl_local_hints.get("BTC-USDT", {})
    assert "take_profit" not in hint
