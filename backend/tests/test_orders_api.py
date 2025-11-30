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
        self.orders = [{"id": "abc", "symbol": "BTC-USDT", "side": "BUY", "size": "1", "status": "OPEN", "price": None}]
        self.positions = [{"symbol": "BTC-USDT", "side": "LONG", "size": "1", "entry_price": "100", "pnl": "5"}]
        self.canceled = []

    async def list_orders(self):
        return self.orders

    async def list_positions(self):
        return self.positions

    async def cancel_order(self, order_id: str):
        if order_id == "fail":
            raise ValueError("Unable to cancel")
        self.canceled.append(order_id)
        return {"canceled": True, "order_id": order_id}


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
    assert resp.json() == [{"id": "abc", "symbol": "BTC-USDT", "side": "BUY", "size": "1", "status": "OPEN", "price": None}]


def test_list_positions_returns_manager_data():
    manager = FakeManager()
    client = build_client(manager)
    resp = client.get("/api/positions")
    assert resp.status_code == 200
    assert resp.json() == [{"symbol": "BTC-USDT", "side": "LONG", "size": "1", "entry_price": "100", "pnl": "5"}]


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
