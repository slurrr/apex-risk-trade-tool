import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.exchange.exchange_gateway import ExchangeGateway  # noqa: E402


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
