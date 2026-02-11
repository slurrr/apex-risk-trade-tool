import asyncio
import sys
from pathlib import Path

from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.routes_risk import atr_stop, configure_gateway as configure_risk_gateway  # noqa: E402
from backend.api.routes_trade import trade  # noqa: E402
from backend.api.routes_venue import configure_venue_controller, get_venue, set_venue  # noqa: E402
from backend.risk.risk_engine import PositionSizingResult  # noqa: E402
from backend.trading.schemas import AtrStopRequest, TradeRequest, VenueSwitchRequest  # noqa: E402
import backend.api.routes_risk as routes_risk  # noqa: E402


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


def test_trade_preview_success():
    manager = FakeManager()
    payload = TradeRequest(
        symbol="BTC-USDT",
        entry_price=100,
        stop_price=90,
        risk_pct=1,
        preview=True,
        execute=False,
    )
    resp = asyncio.run(trade(payload, manager))
    assert resp.side == "BUY"
    assert resp.size == 1.2
    assert manager.preview_called is True


def test_trade_execute_success():
    manager = FakeManager()
    payload = TradeRequest(
        symbol="BTC-USDT",
        entry_price=100,
        stop_price=90,
        risk_pct=1,
        preview=False,
        execute=True,
    )
    resp = asyncio.run(trade(payload, manager))
    assert resp["executed"] is True
    assert resp["exchange_order_id"] == "order-xyz"
    assert manager.execute_called is True


def test_trade_preview_validation_error():
    manager = FakeManager()
    payload = TradeRequest(
        symbol="BTC-USDT",
        entry_price=100,
        stop_price=100,
        risk_pct=1,
        preview=True,
        execute=False,
    )

    async def raise_error(**kwargs):
        raise ValueError("Stop price equals entry price.")

    manager.preview_trade = raise_error  # type: ignore
    resp = asyncio.run(trade(payload, manager))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 400
    assert b"Stop price equals entry price" in resp.body


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


class FakeApexRiskGateway(FakeRiskGateway):
    venue = "apex"


def test_atr_stop_uses_gateway_fetch_klines(monkeypatch):
    gateway = FakeRiskGateway()
    configure_risk_gateway(gateway)
    monkeypatch.setattr("backend.api.routes_risk.get_settings", lambda: FakeAtrSettings())

    resp = asyncio.run(
        atr_stop(
            AtrStopRequest(symbol="BTC-USDT", side="long", entry_price=100.0),
            gateway,
        )
    )
    assert resp.stop_loss_price > 0
    assert gateway.calls
    assert gateway.calls[0][0] == "BTC-USDT"
    assert gateway.calls[0][1] == "15m"
    assert gateway.calls[0][2] >= 200


def test_atr_stop_caps_limit_for_apex_default_timeframe(monkeypatch):
    gateway = FakeApexRiskGateway()
    configure_risk_gateway(gateway)
    monkeypatch.setattr("backend.api.routes_risk.get_settings", lambda: FakeAtrSettings())

    resp = asyncio.run(
        atr_stop(
            AtrStopRequest(symbol="BTC-USDT", side="long", entry_price=100.0),
            gateway,
        )
    )
    assert resp.stop_loss_price > 0
    assert gateway.calls
    assert gateway.calls[0][2] == 120


def test_atr_stop_uses_minimal_limit_for_apex_3m(monkeypatch):
    gateway = FakeApexRiskGateway()
    configure_risk_gateway(gateway)
    monkeypatch.setattr("backend.api.routes_risk.get_settings", lambda: FakeAtrSettings())

    resp = asyncio.run(
        atr_stop(
            AtrStopRequest(symbol="BTC-USDT", side="long", entry_price=100.0, timeframe="3m"),
            gateway,
        )
    )
    assert resp.stop_loss_price > 0
    assert gateway.calls
    assert gateway.calls[0][2] == 9


def test_drop_incomplete_tail_excludes_open_candle(monkeypatch):
    monkeypatch.setattr("backend.api.routes_risk.time.time", lambda: 1000.0)
    candles = [
        {"open_time": 998_000},
        {"open_time": 999_000},
    ]
    trimmed = routes_risk._drop_incomplete_tail(candles, "1m")
    assert len(trimmed) == 1


def test_drop_incomplete_tail_keeps_closed_candle(monkeypatch):
    monkeypatch.setattr("backend.api.routes_risk.time.time", lambda: 1000.0)
    candles = [
        {"open_time": 876_000},
        {"open_time": 938_000},
    ]
    trimmed = routes_risk._drop_incomplete_tail(candles, "1m")
    assert len(trimmed) == 2


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
    configure_venue_controller(FakeVenueController())
    resp = asyncio.run(get_venue())
    assert resp.active_venue == "apex"


def test_set_venue_state():
    ctrl = FakeVenueController()
    configure_venue_controller(ctrl)
    resp = asyncio.run(set_venue(VenueSwitchRequest(active_venue="hyperliquid")))
    assert resp.active_venue == "hyperliquid"
    assert ctrl.active_venue == "hyperliquid"
