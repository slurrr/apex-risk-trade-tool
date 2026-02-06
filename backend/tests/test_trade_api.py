import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.routes_trade import configure_order_manager, router  # noqa: E402
from backend.api.routes_risk import configure_gateway as configure_risk_gateway, router as risk_router  # noqa: E402
from backend.api.routes_venue import configure_venue_controller, router as venue_router  # noqa: E402
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


class FakeAtrSettings:
    atr_timeframe = "15m"
    atr_period = 3
    atr_multiplier = 1.5


class FakeRiskGateway:
    def __init__(self) -> None:
        self.calls = []

    async def fetch_klines(self, symbol: str, timeframe: str, limit: int):
        self.calls.append((symbol, timeframe, limit))
        return [
            {"open_time": 1, "open": 100, "high": 103, "low": 99, "close": 102},
            {"open_time": 2, "open": 102, "high": 104, "low": 100, "close": 103},
            {"open_time": 3, "open": 103, "high": 105, "low": 101, "close": 104},
            {"open_time": 4, "open": 104, "high": 106, "low": 102, "close": 105},
        ]


def test_atr_stop_uses_gateway_fetch_klines(monkeypatch):
    app = FastAPI()
    gateway = FakeRiskGateway()
    configure_risk_gateway(gateway)
    app.include_router(risk_router)
    monkeypatch.setattr("backend.api.routes_risk.get_settings", lambda: FakeAtrSettings())

    client = TestClient(app)
    resp = client.post(
        "/risk/atr-stop",
        json={"symbol": "BTC-USDT", "side": "long", "entry_price": 100.0},
    )
    assert resp.status_code == 200
    assert gateway.calls
    assert gateway.calls[0][0] == "BTC-USDT"
    assert gateway.calls[0][1] == "15m"


class FakeVenueController:
    def __init__(self) -> None:
        self.active_venue = "apex"

    async def switch_venue(self, requested: str) -> str:
        target = (requested or "").strip().lower()
        if target not in {"apex", "hyperliquid"}:
            raise ValueError(f"Unsupported venue '{requested}'.")
        self.active_venue = target
        return self.active_venue


def test_get_venue_state():
    app = FastAPI()
    configure_venue_controller(FakeVenueController())
    app.include_router(venue_router)
    client = TestClient(app)
    resp = client.get("/api/venue")
    assert resp.status_code == 200
    assert resp.json() == {"active_venue": "apex"}


def test_set_venue_state():
    app = FastAPI()
    ctrl = FakeVenueController()
    configure_venue_controller(ctrl)
    app.include_router(venue_router)
    client = TestClient(app)
    resp = client.post("/api/venue", json={"active_venue": "hyperliquid"})
    assert resp.status_code == 200
    assert resp.json() == {"active_venue": "hyperliquid"}
    assert ctrl.active_venue == "hyperliquid"
