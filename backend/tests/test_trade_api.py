import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.routes_trade import configure_order_manager, router  # noqa: E402
from backend.risk.risk_engine import PositionSizingResult  # noqa: E402


class FakeManager:
    def __init__(self) -> None:
        self.preview_called = False
        self.execute_called = False

    async def preview_trade(self, **kwargs):
        self.preview_called = True
        return PositionSizingResult(
            side="BUY",
            size=1.2,
            notional=120.0,
            estimated_loss=10.0,
            warnings=[],
            entry_price=100.0,
            stop_price=90.0,
        ), []

    async def execute_trade(self, **kwargs):
        self.execute_called = True
        sizing = PositionSizingResult(
            side="BUY",
            size=1.0,
            notional=100.0,
            estimated_loss=10.0,
            warnings=[],
            entry_price=100.0,
            stop_price=90.0,
        )
        return {
            "executed": True,
            "exchange_order_id": "order-xyz",
            "warnings": [],
            "sizing": sizing,
        }


def build_client(fake_manager: FakeManager) -> TestClient:
    app = FastAPI()
    configure_order_manager(fake_manager)
    app.include_router(router)
    return TestClient(app)


def test_trade_preview_success():
    manager = FakeManager()
    client = build_client(manager)
    payload = {
        "symbol": "BTC-USDT",
        "entry_price": 100,
        "stop_price": 90,
        "risk_pct": 1,
        "preview": True,
        "execute": False,
    }
    resp = client.post("/api/trade", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["side"] == "BUY"
    assert data["size"] == 1.2
    assert manager.preview_called is True


def test_trade_execute_success():
    manager = FakeManager()
    client = build_client(manager)
    payload = {
        "symbol": "BTC-USDT",
        "entry_price": 100,
        "stop_price": 90,
        "risk_pct": 1,
        "preview": False,
        "execute": True,
    }
    resp = client.post("/api/trade", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["executed"] is True
    assert data["exchange_order_id"] == "order-xyz"
    assert manager.execute_called is True


def test_trade_preview_validation_error():
    manager = FakeManager()
    client = build_client(manager)
    payload = {
        "symbol": "BTC-USDT",
        "entry_price": 100,
        "stop_price": 100,  # invalid: stop == entry
        "risk_pct": 1,
        "preview": True,
        "execute": False,
    }
    # Force preview to raise by swapping manager method
    async def raise_error(**kwargs):
        raise ValueError("Stop price equals entry price.")

    manager.preview_trade = raise_error  # type: ignore
    resp = client.post("/api/trade", json=payload)
    assert resp.status_code == 400
    assert "Stop price equals entry price" in resp.json()["detail"]
