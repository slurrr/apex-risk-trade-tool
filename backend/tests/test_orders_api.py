import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.routes_orders import router as orders_router  # noqa: E402
from backend.api.routes_positions import router as positions_router  # noqa: E402
from backend.api.routes_trade import configure_order_manager  # noqa: E402


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


def build_client(manager: FakeManager) -> TestClient:
    app = FastAPI()
    configure_order_manager(manager)
    app.include_router(orders_router)
    app.include_router(positions_router)
    return TestClient(app)


def test_list_orders_returns_manager_data():
    manager = FakeManager()
    client = build_client(manager)
    resp = client.get("/api/orders")
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "abc", "symbol": "BTC-USDT", "side": "BUY", "size": 1.0, "status": "OPEN", "entry_price": None, "created_at": None}
    ]


def test_list_positions_returns_manager_data():
    manager = FakeManager()
    client = build_client(manager)
    resp = client.get("/api/positions")
    assert resp.status_code == 200
    assert resp.json() == [
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
    client = build_client(manager)
    resp = client.post("/api/orders/abc/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"canceled": True, "order_id": "abc"}
    assert manager.canceled == ["abc"]


def test_cancel_order_error_returns_400():
    manager = FakeManager()
    client = build_client(manager)
    resp = client.post("/api/orders/fail/cancel")
    assert resp.status_code == 400
    assert "Unable to cancel" in resp.json()["detail"]


def test_update_targets_round_trip_positions_api():
    manager = FakeManager()
    client = build_client(manager)
    resp = client.post("/api/positions/pos-1/targets", json={"take_profit": 120.5, "stop_loss": 90.1})
    assert resp.status_code == 200
    assert manager.updated[-1] == {
        "position_id": "pos-1",
        "take_profit": 120.5,
        "stop_loss": 90.1,
        "clear_tp": False,
        "clear_sl": False,
    }
    positions = client.get("/api/positions")
    assert positions.status_code == 200
    body = positions.json()
    assert body[0]["take_profit"] == 120.5
    assert body[0]["stop_loss"] == 90.1
