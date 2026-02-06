import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.exchange.exchange_gateway import ExchangeGateway  # noqa: E402
from backend.exchange.hyperliquid_gateway import HyperliquidGateway  # noqa: E402


class FakeSettings:
    apex_network = "testnet"
    apex_zk_seed = "seed"
    apex_zk_l2key = "l2key"
    apex_api_key = "key"
    apex_api_secret = "secret"
    apex_passphrase = "passphrase"
    apex_http_endpoint = None


class FakeClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []
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
    gateway = ExchangeGateway(FakeSettings(), client=FakeClient())
    positions = asyncio.run(gateway.get_open_positions())
    assert positions[0]["symbol"] == "BTC-USDT"
    assert positions[0]["side"] == "LONG"


def test_get_open_orders_returns_orders():
    gateway = ExchangeGateway(FakeSettings(), client=FakeClient())
    orders = asyncio.run(gateway.get_open_orders())
    assert orders[0]["orderId"] == "abc-123"
    assert orders[0]["symbol"] == "BTC-USDT"
    assert orders[0]["status"] == "OPEN"


def test_cancel_order_uses_client_and_returns_payload():
    client = FakeClient()
    gateway = ExchangeGateway(FakeSettings(), client=client)
    result = asyncio.run(gateway.cancel_order("abc-123"))
    assert result["canceled"] is True
    assert result["order_id"] == "abc-123"
    assert client.deleted == ["abc-123"]


def test_account_summary_handles_data_payload():
    gateway = ExchangeGateway(FakeSettings(), client=FakeDataClient())
    summary = asyncio.run(gateway.get_account_summary())
    assert summary["total_equity"] == 1500
    assert summary["available_margin"] == 1200
    assert summary["total_upnl"] == 25


def test_open_positions_handles_data_payload():
    gateway = ExchangeGateway(FakeSettings(), client=FakeDataClient())
    positions = asyncio.run(gateway.get_open_positions(force_rest=True))
    assert positions and positions[0]["symbol"] == "BTC-USDT"


def test_open_orders_handles_data_payload():
    gateway = ExchangeGateway(FakeSettings(), client=FakeDataClient())
    orders = asyncio.run(gateway.get_open_orders(force_rest=True))
    assert orders and orders[0]["orderId"] == "abc-123"


def test_update_positions_stream_updates_account_cache():
    gateway = ExchangeGateway(FakeSettings(), client=FakeClient())
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
    gateway = ExchangeGateway(FakeSettings(), client=FakeClient())
    gateway._public_client = FakeTickerClient()
    price, source = asyncio.run(gateway.get_reference_price("BTC-USDT"))
    assert price == 100.0
    assert source == "mid"

    gateway._public_client = None
    cached_price, cached_source = asyncio.run(gateway.get_reference_price("BTC-USDT"))
    assert cached_price == 100.0
    assert cached_source in {"mid", "cache"}


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
    asyncio.run(gateway.load_configs())
    symbols = asyncio.run(gateway.list_symbols())
    assert any(row["symbol"] == "BTC-USDC" for row in symbols)
    btc_info = gateway.get_symbol_info("BTC-USDT")
    assert btc_info and btc_info["symbol"] == "BTC-USDC"
    assert btc_info["stepSize"] == 0.001

    price, source = asyncio.run(gateway.get_reference_price("BTC-USDT"))
    assert price == 43000.1
    assert source == "mid"

    depth = asyncio.run(gateway.get_depth_snapshot("BTC-USDT", levels=5))
    assert depth["bids"][0]["size"] == 2.0
    assert depth["asks"][0]["size"] == 1.5

    candles = asyncio.run(gateway.fetch_klines("BTC-USDT", "15m", 20))
    assert candles[0]["open_time"] == 1000
    assert candles[1]["close"] == 12.0


def test_hyperliquid_private_account_orders_positions():
    gateway = FakeHyperliquidGateway()
    summary = asyncio.run(gateway.get_account_summary())
    assert summary["total_equity"] == 1200.5
    assert summary["available_margin"] == 800.1

    positions = asyncio.run(gateway.get_open_positions())
    assert len(positions) == 2
    assert positions[0]["symbol"] == "BTC-USDC"
    assert positions[1]["positionSide"] == "SHORT"

    orders = asyncio.run(gateway.get_open_orders())
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
                self.cancels = []

            def order(self, *args, **kwargs):
                self.orders.append((args, kwargs))
                return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 12345}}]}}}

            def cancel(self, *args, **kwargs):
                self.cancels.append((args, kwargs))
                return {"status": "ok", "response": {"data": {"statuses": [{"success": True}]}}}

            def market_close(self, *args, **kwargs):
                return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 98765}}]}}}
        super().__init__()
        self._exchange = _FakeExchange()


def test_hyperliquid_place_order_and_cancel():
    gateway = FakeHyperliquidTradeGateway()
    asyncio.run(gateway.load_configs())
    payload, warning = asyncio.run(
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
    placed = asyncio.run(gateway.place_order(payload))
    assert placed["exchange_order_id"] == "12345"

    canceled = asyncio.run(gateway.cancel_order("1"))
    assert canceled["canceled"] is True

    closed = asyncio.run(gateway.place_close_order(symbol="BTC-USDT", side="LONG", size=0.01, close_type="market"))
    assert closed["exchange_order_id"] == "98765"


def test_hyperliquid_update_targets_places_tp_and_sl_reduce_only():
    gateway = FakeHyperliquidTradeGateway()
    asyncio.run(gateway.load_configs())
    updated = asyncio.run(
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


def test_hyperliquid_cancel_tpsl_orders_filters_symbol_and_kind():
    gateway = FakeHyperliquidTradeGateway()
    asyncio.run(gateway.load_configs())
    result = asyncio.run(gateway.cancel_tpsl_orders(symbol="ETH-USDC", cancel_tp=True))
    assert result["canceled"] == ["2"]
    result = asyncio.run(gateway.cancel_tpsl_orders(symbol="ETH-USDC", cancel_sl=True))
    assert result["canceled"] == []
