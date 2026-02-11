import asyncio
import sys
import time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.exchange.exchange_gateway import ExchangeGateway  # noqa: E402
from backend.exchange.hyperliquid_gateway import HyperliquidGateway  # noqa: E402


@pytest.fixture(autouse=True)
def _inline_to_thread(monkeypatch):
    async def _run_inline(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _run_inline)


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def make_apex_gateway(client=None) -> ExchangeGateway:
    gateway = ExchangeGateway(FakeSettings(), client=client)
    gateway._lock = _NoLock()
    return gateway


class FakeSettings:
    apex_network = "testnet"
    apex_zk_seed = "seed"
    apex_zk_l2key = "l2key"
    apex_api_key = "key"
    apex_api_secret = "secret"
    apex_passphrase = "passphrase"
    apex_http_endpoint = None
    apex_enable_ws = False
    apex_poll_orders_interval_seconds = 5.0
    apex_poll_positions_interval_seconds = 5.0
    apex_poll_account_interval_seconds = 15.0


class FakeClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.created_orders: list[dict] = []
        self.positions = [{"symbol": "BTC-USDT", "size": "1", "side": "LONG"}]
        self.orders = [{"orderId": "abc-123", "symbol": "BTC-USDT", "status": "OPEN"}]
        self.account = {
            "totalEquityValue": 1500,
            "totalEquity": 1500,
            "availableBalance": 1200,
            "totalUnrealizedPnl": 25,
            "takerFeeRate": "0.0006",
        }

    def configs_v3(self):
        return {"result": {"symbols": [{"symbol": "BTC-USDT"}]}}

    def get_account_balance_v3(self):
        return {"result": {"account": self.account}}

    def get_account_v3(self):
        return {"result": {"account": self.account, "positions": self.positions}}

    def open_orders_v3(self):
        return {"result": {"list": self.orders}}

    def delete_order_by_client_order_id_v3(self, id: str = None, **kwargs):
        order_identifier = kwargs.get("id") or id
        self.deleted.append(order_identifier)
        return {"result": {"status": "canceled", "orderId": order_identifier}}

    def delete_order_v3(self, orderId: str = None, **kwargs):
        order_identifier = kwargs.get("id") or orderId
        self.deleted.append(order_identifier)
        return {"result": {"status": "canceled", "orderId": order_identifier}}

    def create_order_v3(self, **kwargs):
        self.created_orders.append(dict(kwargs))
        return {"result": {"orderId": "new-oid-1"}}


class FakeStrictClient(FakeClient):
    """Simulate SDK versions with strict create_order_v3 kwargs."""

    def create_order_v3(
        self,
        *,
        symbol: str,
        side: str,
        type: str,
        size: str,
        price: str,
        reduceOnly: bool = False,
        clientId: str | None = None,
        timeInForce: str | None = None,
        takerFeeRate: str | None = None,
        triggerPriceType: str | None = None,
        tpPrice: str | None = None,
        tpTriggerPrice: str | None = None,
        slPrice: str | None = None,
        slTriggerPrice: str | None = None,
        isOpenTpslOrder: bool | None = None,
        isSetOpenTp: bool | None = None,
        isSetOpenSl: bool | None = None,
        tpSide: str | None = None,
        slSide: str | None = None,
        tpSize: str | None = None,
        slSize: str | None = None,
        isPositionTpsl: bool | None = None,
        triggerPrice: str | None = None,
    ):
        payload = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "size": size,
            "price": price,
            "reduceOnly": reduceOnly,
            "clientId": clientId,
            "timeInForce": timeInForce,
            "takerFeeRate": takerFeeRate,
            "triggerPriceType": triggerPriceType,
            "tpPrice": tpPrice,
            "tpTriggerPrice": tpTriggerPrice,
            "slPrice": slPrice,
            "slTriggerPrice": slTriggerPrice,
            "isOpenTpslOrder": isOpenTpslOrder,
            "isSetOpenTp": isSetOpenTp,
            "isSetOpenSl": isSetOpenSl,
            "tpSide": tpSide,
            "slSide": slSide,
            "tpSize": tpSize,
            "slSize": slSize,
            "isPositionTpsl": isPositionTpsl,
            "triggerPrice": triggerPrice,
        }
        self.created_orders.append(payload)
        return {"result": {"orderId": "new-oid-1"}}


class FakeDataClient(FakeClient):
    """Return Apex responses with 'data' envelopes instead of 'result'."""

    def configs_v3(self):
        return {"data": {"symbols": [{"symbol": "BTC-USDT"}]}}

    def get_account_balance_v3(self):
        return {"data": {"account": self.account}}

    def get_account_v3(self):
        return {"data": {"account": self.account, "positions": self.positions, "orders": self.orders}}

    def open_orders_v3(self):
        return {"data": {"orders": self.orders}}


def test_get_open_positions_returns_positions():
    gateway = make_apex_gateway(FakeClient())
    positions = run(gateway.get_open_positions())
    assert positions[0]["symbol"] == "BTC-USDT"
    assert positions[0]["side"] == "LONG"


def test_get_open_positions_publish_bypasses_cached_positions():
    client = FakeClient()
    gateway = make_apex_gateway(client)
    # Seed cache with one open position.
    run(gateway.get_open_positions(force_rest=True, publish=False))
    assert gateway._ws_positions

    # Exchange now has no positions.
    client.positions = []
    gateway._positions_empty_stale_seconds = 0.0

    refreshed = run(gateway.get_open_positions(force_rest=False, publish=True))
    assert refreshed == []
    assert gateway._ws_positions == {}


def test_get_open_orders_returns_orders():
    gateway = make_apex_gateway(FakeClient())
    orders = run(gateway.get_open_orders())
    assert orders[0]["orderId"] == "abc-123"
    assert orders[0]["symbol"] == "BTC-USDT"
    assert orders[0]["status"] == "OPEN"


def test_get_open_orders_filters_tpsl_without_explicit_position_flag():
    client = FakeClient()
    client.orders = [
        {
            "orderId": "entry-1",
            "symbol": "ASTER-USDT",
            "status": "OPEN",
            "type": "LIMIT",
            "reduceOnly": False,
        },
        {
            "orderId": "sl-1",
            "symbol": "ASTER-USDT",
            "status": "OPEN",
            "type": "STOP_MARKET",
            "reduceOnly": True,
            # intentionally no isPositionTpsl flag to mimic WS/REST edge cases
        },
    ]
    gateway = make_apex_gateway(client)
    orders = run(gateway.get_open_orders(force_rest=True, publish=False))
    assert len(orders) == 1
    assert orders[0]["orderId"] == "entry-1"


def test_cancel_order_uses_client_and_returns_payload():
    client = FakeClient()
    gateway = make_apex_gateway(client)
    result = run(gateway.cancel_order("abc-123"))
    assert result["canceled"] is True
    assert result["order_id"] == "abc-123"
    assert client.deleted == ["abc-123"]


def test_account_summary_handles_data_payload():
    gateway = make_apex_gateway(FakeDataClient())
    summary = run(gateway.get_account_summary())
    assert summary["total_equity"] == 1500
    assert summary["available_margin"] == 1200
    assert summary["withdrawable_amount"] == 1200
    assert summary["total_upnl"] == 25


def test_open_positions_handles_data_payload():
    gateway = make_apex_gateway(FakeDataClient())
    positions = run(gateway.get_open_positions(force_rest=True))
    assert positions and positions[0]["symbol"] == "BTC-USDT"


def test_open_orders_handles_data_payload():
    gateway = make_apex_gateway(FakeDataClient())
    orders = run(gateway.get_open_orders(force_rest=True))
    assert orders and orders[0]["orderId"] == "abc-123"


def test_apex_place_order_schedules_delayed_refresh():
    client = FakeClient()
    gateway = make_apex_gateway(client)

    async def _scenario():
        gateway._loop = asyncio.get_running_loop()
        called = asyncio.Event()

        async def _fake_delayed_refresh():
            called.set()

        gateway._delayed_refresh = _fake_delayed_refresh
        placed = await gateway.place_order(
            {
                "symbol": "BTC-USDT",
                "side": "BUY",
                "type": "LIMIT",
                "size": "0.01",
                "price": "40000",
                "clientId": "cid-1",
                "slTriggerPriceType": "MARKET",
            }
        )
        assert placed["exchange_order_id"] == "new-oid-1"
        assert placed["client_id"] == "cid-1"
        assert client.created_orders[-1].get("slTriggerPriceType") == "MARKET"
        await asyncio.wait_for(called.wait(), timeout=0.5)

    asyncio.run(_scenario())


def test_apex_place_order_strips_unsupported_trigger_type_for_strict_sdk():
    client = FakeStrictClient()
    gateway = make_apex_gateway(client)
    placed = run(
        gateway.place_order(
            {
                "symbol": "BTC-USDT",
                "side": "BUY",
                "type": "LIMIT",
                "size": "0.01",
                "price": "40000",
                "clientId": "cid-2",
                "slTriggerPriceType": "MARKET",
            }
        )
    )
    assert placed["exchange_order_id"] == "new-oid-1"
    assert "slTriggerPriceType" not in client.created_orders[-1]


def test_apex_build_order_payload_sets_mark_trigger_type_for_attached_tpsl_when_supported():
    gateway = make_apex_gateway(FakeClient())
    run(gateway.load_configs())
    payload, warning = run(
        gateway.build_order_payload(
            symbol="BTC-USDT",
            side="BUY",
            size=0.1,
            entry_price=40000.0,
            reduce_only=False,
            tp=42000.0,
            stop=39000.0,
        )
    )
    assert warning is None
    assert payload["tpTriggerPriceType"] == "MARKET"
    assert payload["slTriggerPriceType"] == "MARKET"


def test_apex_update_targets_sets_mark_trigger_type_when_supported():
    gateway = make_apex_gateway(FakeClient())
    submitted = run(
        gateway.update_targets(
            symbol="BTC-USDT",
            side="LONG",
            size=0.1,
            take_profit=42000.0,
            stop_loss=39000.0,
        )
    )
    assert len(submitted["submitted"]) == 2
    for row in submitted["submitted"]:
        payload = row["payload"]
        assert payload["triggerPriceType"] == "MARKET"


def test_apex_build_order_payload_omits_trigger_type_when_sdk_does_not_support():
    gateway = make_apex_gateway(FakeStrictClient())
    run(gateway.load_configs())
    payload, warning = run(
        gateway.build_order_payload(
            symbol="BTC-USDT",
            side="BUY",
            size=0.1,
            entry_price=40000.0,
            reduce_only=False,
            tp=42000.0,
            stop=39000.0,
        )
    )
    assert warning is None
    assert "tpTriggerPriceType" not in payload
    assert "slTriggerPriceType" not in payload
    assert payload["triggerPriceType"] == "MARKET"


def test_update_positions_stream_updates_account_cache():
    gateway = make_apex_gateway(FakeClient())
    with gateway._lock:
        gateway._ws_positions = {
            "BTC-USDT": {"symbol": "BTC-USDT", "size": "1", "entryPrice": "100", "side": "LONG"},
        }
        changed = gateway._update_positions_pnl("BTC-USDT", 110)
        assert changed is True
        total = gateway._recalculate_total_upnl_locked()
    assert total == 10.0
    assert gateway._account_cache["totalUnrealizedPnl"] == 10.0


class FakeTickerClient:
    def ticker_v3(self, symbol: str):
        return {
            "result": {
                "bidPrice": "99",
                "askPrice": "101",
                "markPrice": "100.2",
                "lastPrice": "100.8",
            }
        }


def test_get_reference_price_prefers_mid_then_caches():
    gateway = make_apex_gateway(FakeClient())
    gateway._public_client = FakeTickerClient()
    price, source = run(gateway.get_reference_price("BTC-USDT"))
    assert price == 100.0
    assert source == "mid"

    gateway._public_client = None
    cached_price, cached_source = run(gateway.get_reference_price("BTC-USDT"))
    assert cached_price == 100.0
    assert cached_source in {"mid", "cache"}


def test_get_reference_price_prefers_fresh_ws_price():
    gateway = make_apex_gateway(FakeClient())
    gateway._ws_prices["BTC-USDT"] = 101.25
    gateway._ws_price_ts["BTC-USDT"] = time.time()
    gateway._ws_price_stale_seconds = 30.0

    class _FailTicker:
        def ticker_v3(self, symbol: str):
            raise AssertionError("REST ticker should not be called when WS price is fresh")

    gateway._public_client = _FailTicker()
    price, source = run(gateway.get_reference_price("BTC-USDT"))
    assert price == 101.25
    assert source == "ws_ticker"


def test_get_reference_price_uses_rest_when_ws_price_is_stale():
    gateway = make_apex_gateway(FakeClient())
    gateway._ws_prices["BTC-USDT"] = 101.25
    gateway._ws_price_ts["BTC-USDT"] = time.time() - 120
    gateway._ws_price_stale_seconds = 30.0
    gateway._public_client = FakeTickerClient()
    price, source = run(gateway.get_reference_price("BTC-USDT"))
    assert price == 100.0
    assert source == "mid"


def test_get_reference_price_falls_back_to_stale_ws_if_rest_fails():
    gateway = make_apex_gateway(FakeClient())
    gateway._ws_prices["BTC-USDT"] = 101.25
    gateway._ws_price_ts["BTC-USDT"] = time.time() - 120
    gateway._ws_price_stale_seconds = 30.0

    class _BrokenTicker:
        def ticker_v3(self, symbol: str):
            raise RuntimeError("ticker down")

    gateway._public_client = _BrokenTicker()
    price, source = run(gateway.get_reference_price("BTC-USDT"))
    assert price == 101.25
    assert source == "ws_ticker_stale"


def test_apex_stream_health_snapshot_has_parity_fields():
    gateway = make_apex_gateway(FakeClient())
    snapshot = gateway.get_stream_health_snapshot()
    assert snapshot["ws_alive"] is False
    assert "reconcile_count" in snapshot
    assert "last_reconcile_reason" in snapshot
    assert "reconcile_reason_counts" in snapshot
    assert snapshot["pending_submitted_orders"] == 0
    assert snapshot["fallback_rest_orders_used_count"] >= 0
    assert snapshot["fallback_rest_positions_used_count"] >= 0
    assert "upnl_source" in snapshot
    assert "upnl_age_seconds" in snapshot
    assert snapshot["poll_orders_interval_seconds"] == 5.0
    assert snapshot["poll_positions_interval_seconds"] == 5.0
    assert snapshot["poll_account_interval_seconds"] == 15.0


def test_apex_stream_health_fallback_counters_increment_on_rest_reads():
    gateway = make_apex_gateway(FakeClient())
    run(gateway.get_open_orders(force_rest=True))
    run(gateway.get_open_positions(force_rest=True))
    snapshot = gateway.get_stream_health_snapshot()
    assert snapshot["fallback_rest_orders_used_count"] >= 1
    assert snapshot["fallback_rest_positions_used_count"] >= 1


def test_apex_get_account_equity_prefers_rest_upnl_when_ws_pnl_stale():
    gateway = make_apex_gateway(FakeClient())
    gateway.apex_enable_ws = True
    gateway._account_cache["totalUnrealizedPnl"] = 999.0
    gateway._last_public_ws_event_ts = time.time() - 300
    gateway._last_pnl_recomputed_ts = time.time() - 300

    run(gateway.get_account_equity())
    assert gateway._account_cache["totalUnrealizedPnl"] == 25
    assert gateway.get_stream_health_snapshot()["upnl_source"] in {"rest_account_balance", "rest_account_legacy"}


def test_apex_get_account_equity_prefers_ws_upnl_when_ws_pnl_fresh():
    gateway = make_apex_gateway(FakeClient())
    gateway.apex_enable_ws = True
    gateway._account_cache["totalUnrealizedPnl"] = 999.0
    gateway._last_public_ws_event_ts = time.time()
    gateway._last_pnl_recomputed_ts = time.time()

    run(gateway.get_account_equity())
    assert gateway._account_cache["totalUnrealizedPnl"] == 999.0
    assert gateway.get_stream_health_snapshot()["upnl_source"] == "ws"


class FakeHyperliquidGateway(HyperliquidGateway):
    def __init__(self) -> None:
        class _FakeInfo:
            def meta(self):
                return {
                    "universe": [
                        {"name": "BTC", "szDecimals": 3, "maxLeverage": 50},
                        {"name": "ETH", "szDecimals": 2, "maxLeverage": 25},
                    ]
                }

            def all_mids(self):
                return {"BTC": "43000.1", "ETH": "2300.12"}

            def l2_snapshot(self, name: str):
                return {
                    "levels": [
                        [{"px": "42999.5", "sz": "2.0"}],
                        [{"px": "43000.5", "sz": "1.5"}],
                    ]
                }

            def candles_snapshot(self, name: str, interval: str, start_ms: int, end_ms: int):
                return [
                    {"t": 1000, "o": "10", "h": "12", "l": "9", "c": "11", "v": "100"},
                    {"t": 2000, "o": "11", "h": "13", "l": "10", "c": "12", "v": "120"},
                ]

            def user_state(self, address: str):
                return {
                    "marginSummary": {"accountValue": "1200.5", "totalNtlPos": "15.2"},
                    "withdrawable": "800.1",
                    "assetPositions": [
                        {"position": {"coin": "BTC", "szi": "0.02", "entryPx": "42000", "unrealizedPnl": "10.5"}},
                        {"position": {"coin": "ETH", "szi": "-1.5", "entryPx": "2300", "unrealizedPnl": "-3.1"}},
                    ],
                }

            def open_orders(self, address: str):
                return [
                    {"oid": 1, "cloid": "cid-1", "coin": "BTC", "side": "B", "sz": "0.01", "limitPx": "41000", "reduceOnly": False},
                    {"oid": 2, "cloid": "cid-2", "coin": "ETH", "side": "A", "sz": "0.5", "limitPx": "2400", "reduceOnly": True},
                ]

            def frontend_open_orders(self, address: str):
                return [
                    {
                        "oid": 1,
                        "cloid": "cid-1",
                        "coin": "BTC",
                        "side": "B",
                        "sz": "0.01",
                        "limitPx": "41000",
                        "reduceOnly": False,
                        "orderType": "Limit",
                        "status": "open",
                    },
                    {
                        "oid": 2,
                        "cloid": "cid-2",
                        "coin": "ETH",
                        "side": "A",
                        "sz": "0.5",
                        "limitPx": "2400",
                        "reduceOnly": True,
                        "isPositionTpsl": True,
                        "triggerPx": "2350",
                        "orderType": "Take Profit Market",
                        "status": "open",
                    },
                ]
        super().__init__(base_url="https://example.invalid", user_address="0xabc", info_client=_FakeInfo())


def test_hyperliquid_symbols_reference_depth_and_klines():
    gateway = FakeHyperliquidGateway()
    run(gateway.load_configs())
    symbols = run(gateway.list_symbols())
    assert any(row["symbol"] == "BTC-USDC" for row in symbols)
    btc_info = gateway.get_symbol_info("BTC-USDT")
    assert btc_info and btc_info["symbol"] == "BTC-USDC"
    assert btc_info["stepSize"] == 0.001

    price, source = run(gateway.get_reference_price("BTC-USDT"))
    assert price == 43000.1
    assert source == "mid"

    depth = run(gateway.get_depth_snapshot("BTC-USDT", levels=5))
    assert depth["bids"][0]["size"] == 2.0
    assert depth["asks"][0]["size"] == 1.5

    candles = run(gateway.fetch_klines("BTC-USDT", "15m", 20))
    assert candles[0]["open_time"] == 1000
    assert candles[1]["close"] == 12.0


def test_hyperliquid_private_account_orders_positions():
    gateway = FakeHyperliquidGateway()
    summary = run(gateway.get_account_summary())
    assert summary["total_equity"] == 1200.5
    assert summary["available_margin"] == 1200.5
    assert summary["sizing_available_margin"] == 800.1
    assert summary["withdrawable_amount"] == 800.1
    assert summary["total_upnl"] == pytest.approx(7.4)

    positions = run(gateway.get_open_positions())
    assert len(positions) == 2
    assert positions[0]["symbol"] == "BTC-USDC"
    assert positions[1]["positionSide"] == "SHORT"

    orders = run(gateway.get_open_orders())
    assert len(orders) == 2
    assert orders[0]["side"] == "BUY"
    assert orders[1]["side"] == "SELL"
    assert orders[1]["reduceOnly"] is True
    assert orders[1]["type"] == "TAKE_PROFIT_MARKET"
    assert orders[1]["triggerPrice"] == "2350"


class FakeHyperliquidTradeGateway(FakeHyperliquidGateway):
    def __init__(self) -> None:
        class _FakeExchange:
            def __init__(self):
                self.orders = []
                self.bulk_order_calls = []
                self.cancels = []

            def order(self, *args, **kwargs):
                self.orders.append((args, kwargs))
                return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 12345}}]}}}

            def bulk_orders(self, order_requests, builder=None, grouping="na"):
                self.bulk_order_calls.append((order_requests, builder, grouping))
                return {
                    "status": "ok",
                    "response": {
                        "data": {
                            "statuses": [
                                {"resting": {"oid": 12345}},
                                {"resting": {"oid": 12346}},
                                {"resting": {"oid": 12347}},
                            ]
                        }
                    },
                }

            def cancel(self, *args, **kwargs):
                self.cancels.append((args, kwargs))
                return {"status": "ok", "response": {"data": {"statuses": [{"success": True}]}}}

            def market_close(self, *args, **kwargs):
                return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 98765}}]}}}
        super().__init__()
        self._exchange = _FakeExchange()


def test_hyperliquid_place_order_and_cancel():
    gateway = FakeHyperliquidTradeGateway()
    run(gateway.load_configs())
    payload, warning = run(
        gateway.build_order_payload(
            symbol="BTC-USDT",
            side="BUY",
            size=0.01,
            entry_price=40000.0,
            reduce_only=False,
            tp=None,
            stop=None,
        )
    )
    assert warning is None
    placed = run(gateway.place_order(payload))
    assert placed["exchange_order_id"] == "12345"

    canceled = run(gateway.cancel_order("1"))
    assert canceled["canceled"] is True

    closed = run(gateway.place_close_order(symbol="BTC-USDT", side="LONG", size=0.01, close_type="market"))
    assert closed["exchange_order_id"] == "98765"


def test_hyperliquid_update_targets_places_tp_and_sl_reduce_only():
    gateway = FakeHyperliquidTradeGateway()
    run(gateway.load_configs())
    updated = run(
        gateway.update_targets(
            symbol="BTC-USDT",
            side="LONG",
            size=0.02,
            take_profit=45000.0,
            stop_loss=39000.0,
        )
    )
    assert len(updated["placed"]) == 2
    tp = next(x for x in updated["placed"] if x["kind"] == "tp")
    sl = next(x for x in updated["placed"] if x["kind"] == "sl")
    assert tp["order_id"] == "12345"
    assert sl["order_id"] == "12345"


def test_hyperliquid_place_order_with_attached_tpsl_uses_bulk_grouping():
    gateway = FakeHyperliquidTradeGateway()
    run(gateway.load_configs())
    payload, warning = run(
        gateway.build_order_payload(
            symbol="BTC-USDT",
            side="BUY",
            size=0.01,
            entry_price=40000.0,
            reduce_only=False,
            tp=42000.0,
            stop=39000.0,
        )
    )
    assert warning is None
    assert payload.get("grouping") == "normalTpsl"
    assert len(payload.get("order_requests") or []) == 3

    placed = run(gateway.place_order(payload))
    assert placed["exchange_order_id"] == "12345"
    assert len(gateway._exchange.bulk_order_calls) == 1
    order_requests, _, grouping = gateway._exchange.bulk_order_calls[0]
    assert grouping == "normalTpsl"
    sl_leg = next(
        req
        for req in order_requests
        if isinstance(req, dict) and (req.get("order_type") or {}).get("trigger", {}).get("tpsl") == "sl"
    )
    assert sl_leg["order_type"]["trigger"]["isMarket"] is True


def test_hyperliquid_cancel_tpsl_orders_filters_symbol_and_kind():
    gateway = FakeHyperliquidTradeGateway()
    run(gateway.load_configs())
    result = run(gateway.cancel_tpsl_orders(symbol="ETH-USDC", cancel_tp=True))
    assert result["canceled"] == ["2"]
    result = run(gateway.cancel_tpsl_orders(symbol="ETH-USDC", cancel_sl=True))
    assert result["canceled"] == []


def test_hyperliquid_reconcile_reasons_periodic_and_stale_for_pending_orders():
    gateway = FakeHyperliquidGateway()
    now = 1_000.0
    gateway._reconcile_audit_interval = 300.0
    gateway._reconcile_stale_stream_seconds = 90.0
    gateway._last_reconcile_ts = now - 400.0
    gateway._stream_started_at = now - 200.0
    gateway._last_private_ws_event_ts = now - 120.0
    gateway._pending_submitted_orders = {"1": {"ts": now - 30.0, "coin": "BTC"}}
    reasons = gateway._collect_reconcile_reasons(now=now)
    assert "periodic_audit" in reasons
    assert "ws_stale" in reasons


def test_hyperliquid_reconcile_stale_ignores_positions_only_state():
    gateway = FakeHyperliquidGateway()
    now = 1_500.0
    gateway._reconcile_stale_stream_seconds = 90.0
    gateway._stream_started_at = now - 200.0
    gateway._last_private_ws_event_ts = now - 180.0
    gateway._ws_positions = {"BTC": {"symbol": "BTC-USDC", "size": "0.01"}}
    reasons = gateway._collect_reconcile_reasons(now=now)
    assert "ws_stale" not in reasons


def test_hyperliquid_reconcile_stale_requires_private_event_reference():
    gateway = FakeHyperliquidGateway()
    now = 1_700.0
    gateway._reconcile_stale_stream_seconds = 90.0
    gateway._stream_started_at = now - 500.0
    gateway._last_private_ws_event_ts = 0.0
    gateway._pending_submitted_orders = {"1": {"ts": now - 30.0, "coin": "BTC"}}
    reasons = gateway._collect_reconcile_reasons(now=now)
    assert "ws_stale" not in reasons


def test_hyperliquid_reconcile_stale_ignores_resting_open_orders_without_pending_submit():
    gateway = FakeHyperliquidGateway()
    now = 1_750.0
    gateway._reconcile_stale_stream_seconds = 90.0
    gateway._last_private_ws_event_ts = now - 300.0
    gateway._ws_orders = {"1": {"orderId": "1"}}
    gateway._pending_submitted_orders = {}
    reasons = gateway._collect_reconcile_reasons(now=now)
    assert "ws_stale" not in reasons


def test_hyperliquid_empty_orders_snapshot_clears_cached_open_state():
    gateway = FakeHyperliquidGateway()
    gateway._ws_orders = {"1": {"orderId": "1", "symbol": "BTC-USDC"}}
    gateway._ws_orders_raw = [{"orderId": "1", "symbol": "BTC-USDC"}]

    async def _empty_orders():
        return []

    gateway._fetch_frontend_open_orders = _empty_orders
    orders = run(gateway.get_open_orders(force_rest=True, publish=False))
    assert orders == []
    assert gateway._ws_orders == {}
    assert gateway._ws_orders_raw == []

    now = 2_000.0
    gateway._reconcile_stale_stream_seconds = 90.0
    gateway._stream_started_at = now - 1_000.0
    gateway._last_private_ws_event_ts = now - 900.0
    reasons = gateway._collect_reconcile_reasons(now=now)
    assert "ws_stale" not in reasons


def test_hyperliquid_open_orders_filter_terminal_status_rows():
    gateway = FakeHyperliquidGateway()
    gateway._info.frontend_open_orders = lambda address: [
        {"oid": 1, "coin": "BTC", "side": "B", "sz": "0.01", "limitPx": "41000", "status": "OPEN", "orderType": "Limit"},
        {"oid": 2, "coin": "BTC", "side": "B", "sz": "0.01", "limitPx": "41000", "status": "CANCELED", "orderType": "Limit"},
        {"oid": 3, "coin": "BTC", "side": "B", "sz": "0.01", "limitPx": "41000", "status": "FILLED", "orderType": "Limit"},
    ]
    orders = run(gateway.get_open_orders(force_rest=True, publish=False))
    assert len(orders) == 1
    assert orders[0]["orderId"] == "1"


def test_hyperliquid_normalize_order_row_detects_dict_trigger_tpsl():
    gateway = FakeHyperliquidGateway()
    row = {
        "order": {
            "oid": 101,
            "coin": "BTC",
            "side": "A",
            "sz": "0.01",
            "limitPx": "41000",
            "reduceOnly": True,
            "orderType": {"trigger": {"isMarket": True, "triggerPx": "40900", "tpsl": "sl"}},
        },
        "status": "OPEN",
    }
    parsed = gateway._normalize_order_row(row)
    assert parsed is not None
    assert parsed["type"] == "STOP_MARKET"
    assert parsed["triggerPrice"] == "40900"
    assert parsed["isPositionTpsl"] is True


def test_hyperliquid_order_timeout_reason_and_clear_on_ws_update():
    gateway = FakeHyperliquidGateway()
    now = 2_000.0
    gateway._reconcile_order_timeout_seconds = 20.0
    gateway._pending_submitted_orders = {"12345": {"ts": now - 40.0, "coin": "BTC"}}
    reasons = gateway._collect_reconcile_reasons(now=now)
    assert "order_lifecycle_timeout" in reasons

    gateway._on_ws_order_updates(
        {
            "channel": "orderUpdates",
            "data": [
                {
                    "order": {
                        "oid": 12345,
                        "coin": "BTC",
                        "side": "B",
                        "sz": "0.01",
                        "limitPx": "41000",
                        "reduceOnly": False,
                        "orderType": "Limit",
                    },
                    "status": "open",
                }
            ],
        }
    )
    assert "12345" not in gateway._pending_submitted_orders


def test_hyperliquid_terminal_order_update_schedules_account_refresh():
    gateway = FakeHyperliquidGateway()
    gateway._ws_orders = {"12345": {"orderId": "12345", "symbol": "BTC-USDC"}}
    gateway._ws_orders_raw = list(gateway._ws_orders.values())
    scheduled = {"count": 0}

    async def _fake_refresh():
        return None

    gateway._refresh_account_summary_now = _fake_refresh
    gateway._schedule_coro = lambda factory: scheduled.__setitem__("count", scheduled["count"] + 1)

    gateway._on_ws_order_updates(
        {
            "channel": "orderUpdates",
            "data": [
                {
                    "order": {
                        "oid": 12345,
                        "coin": "BTC",
                        "side": "B",
                        "sz": "0.01",
                        "limitPx": "41000",
                        "reduceOnly": False,
                        "orderType": "Limit",
                    },
                    "status": "canceled",
                }
            ],
        }
    )

    assert "12345" not in gateway._ws_orders
    assert scheduled["count"] == 1


def test_hyperliquid_reconcile_min_gap_prevents_storm_and_tracks_reasons():
    gateway = FakeHyperliquidGateway()
    gateway._reconcile_min_gap_seconds = 60.0
    gateway._reconcile_audit_interval = 0.0
    gateway._reconcile_order_timeout_seconds = 5.0
    gateway._reconcile_stale_stream_seconds = 5.0
    gateway._stream_started_at = 100.0
    gateway._last_private_ws_event_ts = 100.0
    gateway._pending_submitted_orders = {"12345": {"ts": 120.0, "coin": "BTC"}}

    async def _fake_orders(force_rest=False, publish=False):
        return []

    async def _fake_positions(force_rest=False, publish=False):
        return []

    gateway.get_open_orders = _fake_orders
    gateway.get_open_positions = _fake_positions

    gateway._last_reconcile_ts = 0.0
    assert run(gateway._audit_reconcile(reason="ws_stale")) is True
    # immediate follow-up should be blocked by min-gap
    assert run(gateway._audit_reconcile(reason="order_lifecycle_timeout")) is False
    assert gateway._reconcile_count == 1
    assert gateway._reconcile_reason_counts.get("ws_stale") == 1
    assert gateway._reconcile_reason_counts.get("order_lifecycle_timeout") is None

    gateway._last_reconcile_ts -= 61.0
    assert run(gateway._audit_reconcile(reason="order_lifecycle_timeout")) is True
    assert gateway._reconcile_count == 2
    assert gateway._reconcile_reason_counts.get("order_lifecycle_timeout") == 1


def test_hyperliquid_account_summary_exposes_stream_health():
    gateway = FakeHyperliquidGateway()
    summary = run(gateway.get_account_summary())
    assert "stream_health" in summary
    assert "reconcile_count" in summary["stream_health"]


def test_hyperliquid_account_summary_retries_transient_disconnect():
    gateway = FakeHyperliquidGateway()
    gateway._rest_retry_backoff = 0.0
    gateway._rest_retry_backoff_max = 0.0
    gateway._rest_retry_jitter = 0.0
    original = gateway._info.user_state
    state = {"calls": 0}

    def _flaky_user_state(address: str):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("Connection aborted: Remote end closed connection without response")
        return original(address)

    gateway._info.user_state = _flaky_user_state
    summary = run(gateway.get_account_summary())
    assert summary["total_equity"] > 0
    assert state["calls"] >= 2


def test_hyperliquid_account_summary_uses_cache_on_repeated_disconnect():
    gateway = FakeHyperliquidGateway()
    cached = run(gateway.get_account_summary())
    gateway._rest_retry_backoff = 0.0
    gateway._rest_retry_backoff_max = 0.0
    gateway._rest_retry_jitter = 0.0
    gateway._info.user_state = lambda address: (_ for _ in ()).throw(
        RuntimeError("Connection aborted: Remote end closed connection without response")
    )
    summary = run(gateway.get_account_summary())
    assert summary["total_equity"] == cached["total_equity"]
    assert summary["available_margin"] == cached["available_margin"]
    assert gateway.get_stream_health_snapshot()["last_account_summary_error"] is not None
