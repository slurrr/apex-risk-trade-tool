import asyncio
import sys
from pathlib import Path

from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.routes_orders import cancel_order, list_orders  # noqa: E402
from backend.api.routes_positions import list_positions, update_targets  # noqa: E402
from backend.trading.schemas import TargetsUpdateRequest  # noqa: E402


class FakeManager:
    def __init__(self) -> None:
        self.orders = [{"id": "abc", "symbol": "BTC-USDT", "side": "BUY", "size": 1.0, "status": "OPEN", "entry_price": None, "reduce_only": False}]
        self.positions = [
            {
                "id": "pos-1",
                "symbol": "BTC-USDT",
                "side": "LONG",
                "size": 1.0,
                "entry_price": 100.0,
                "pnl": 5.0,
                "take_profit": None,
                "stop_loss": None,
            }
        ]
        self.canceled = []
        self.updated = []

    async def list_orders(self):
        return self.orders

    async def list_positions(self):
        return self.positions

    async def cancel_order(self, order_id: str):
        if order_id == "fail":
            raise ValueError("Unable to cancel")
        self.canceled.append(order_id)
        return {"canceled": True, "order_id": order_id}

    async def modify_targets(self, position_id: str, take_profit=None, stop_loss=None, clear_tp=False, clear_sl=False):
        self.updated.append(
            {"position_id": position_id, "take_profit": take_profit, "stop_loss": stop_loss, "clear_tp": clear_tp, "clear_sl": clear_sl}
        )
        for pos in self.positions:
            if str(pos.get("id")) == str(position_id):
                if clear_tp:
                    pos["take_profit"] = None
                if clear_sl:
                    pos["stop_loss"] = None
                if take_profit is not None:
                    pos["take_profit"] = take_profit
                if stop_loss is not None:
                    pos["stop_loss"] = stop_loss
        return {"position_id": position_id, "take_profit": take_profit, "stop_loss": stop_loss, "clear_tp": clear_tp, "clear_sl": clear_sl}


def test_list_orders_returns_manager_data():
    manager = FakeManager()
    resp = asyncio.run(list_orders(manager))
    assert resp == [
        {"id": "abc", "symbol": "BTC-USDT", "side": "BUY", "size": 1.0, "status": "OPEN", "entry_price": None, "reduce_only": False}
    ]


def test_list_positions_returns_manager_data():
    manager = FakeManager()
    resp = asyncio.run(list_positions(False, manager))
    assert resp == [
        {
            "id": "pos-1",
            "symbol": "BTC-USDT",
            "side": "LONG",
            "size": 1.0,
            "entry_price": 100.0,
            "take_profit": None,
            "stop_loss": None,
            "pnl": 5.0,
        }
    ]


def test_cancel_order_calls_manager_and_returns_response():
    manager = FakeManager()
    resp = asyncio.run(cancel_order("abc", manager))
    assert resp == {"canceled": True, "order_id": "abc"}
    assert manager.canceled == ["abc"]


def test_cancel_order_error_returns_400():
    manager = FakeManager()
    resp = asyncio.run(cancel_order("fail", manager))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert b"Unable to cancel" in resp.body


def test_update_targets_round_trip_positions_api():
    manager = FakeManager()
    req = TargetsUpdateRequest(take_profit=120.5, stop_loss=90.1)
    resp = asyncio.run(update_targets("pos-1", req, manager))
    assert resp["take_profit"] == 120.5
    assert resp["stop_loss"] == 90.1
    positions = asyncio.run(list_positions(False, manager))
    assert positions[0]["take_profit"] == 120.5
    assert positions[0]["stop_loss"] == 90.1


def test_clear_tp_only_keeps_sl():
    manager = FakeManager()
    manager.positions[0]["take_profit"] = 125.0
    manager.positions[0]["stop_loss"] = 95.0
    req = TargetsUpdateRequest(clear_tp=True)
    asyncio.run(update_targets("pos-1", req, manager))
    positions = asyncio.run(list_positions(False, manager))
    assert positions[0]["take_profit"] is None
    assert positions[0]["stop_loss"] == 95.0
    assert manager.updated[-1]["clear_tp"] is True
    assert manager.updated[-1]["clear_sl"] is False


def test_clear_sl_only_keeps_tp():
    manager = FakeManager()
    manager.positions[0]["take_profit"] = 125.0
    manager.positions[0]["stop_loss"] = 95.0
    req = TargetsUpdateRequest(clear_sl=True)
    asyncio.run(update_targets("pos-1", req, manager))
    positions = asyncio.run(list_positions(False, manager))
    assert positions[0]["take_profit"] == 125.0
    assert positions[0]["stop_loss"] is None
    assert manager.updated[-1]["clear_tp"] is False
    assert manager.updated[-1]["clear_sl"] is True
