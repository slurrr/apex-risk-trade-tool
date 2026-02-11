import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.risk.risk_engine import (  # noqa: E402
    PositionSizingError,
    PositionSizingResult,
    calculate_position_size,
)


def base_config():
    return {
        "tickSize": 0.5,
        "stepSize": 0.1,
        "minOrderSize": 0.5,
        "maxOrderSize": 100.0,
        "maxLeverage": 5,
    }


def test_long_sizing_basic():
    cfg = base_config()
    result = calculate_position_size(
        equity=5000,
        risk_pct=1,
        entry_price=100,
        stop_price=95,
        symbol_config=cfg,
    )
    assert isinstance(result, PositionSizingResult)
    assert result.side == "BUY"
    assert math.isclose(result.size, 10.0)  # (5000*1%)/(5) = 10
    assert math.isclose(result.estimated_loss, 50.0)


def test_short_sizing_basic():
    cfg = base_config()
    result = calculate_position_size(
        equity=5000,
        risk_pct=1,
        entry_price=95,
        stop_price=100,
        symbol_config=cfg,
    )
    assert result.side == "SELL"
    assert math.isclose(result.size, 10.0)
    assert math.isclose(result.estimated_loss, 50.0)


def test_stop_equals_entry_rejected():
    cfg = base_config()
    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=1000,
            risk_pct=1,
            entry_price=100,
            stop_price=100,
            symbol_config=cfg,
        )


def test_below_min_order_rejected():
    cfg = base_config()
    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=100,
            risk_pct=0.1,
            entry_price=100,
            stop_price=99,
            symbol_config=cfg,
        )


def test_leverage_cap_reduces_size():
    cfg = base_config()
    cfg["maxLeverage"] = 1
    result = calculate_position_size(
        equity=1000,
        risk_pct=20,
        entry_price=200,
        stop_price=190,
        symbol_config=cfg,
    )
    # Raw size would be 1000*20%/10=20, but leverage cap limits notional to 1000 -> size 5
    assert math.isclose(result.size, 5.0)
    assert "leverage constraints" in " ".join(result.warnings).lower()


def test_leverage_cap_uses_leverage_capital_when_provided():
    cfg = base_config()
    cfg["maxLeverage"] = 10
    result = calculate_position_size(
        equity=1000,
        leverage_capital=100,
        risk_pct=20,
        entry_price=100,
        stop_price=95,
        symbol_config=cfg,
    )
    # Risk-based raw size = 40, but leverage cap uses 100*10=1000 notional -> size 10.
    assert math.isclose(result.size, 10.0)
    assert math.isclose(result.notional, 1000.0)
    assert "leverage constraints" in " ".join(result.warnings).lower()


def test_slippage_reduces_size():
    cfg = base_config()
    result = calculate_position_size(
        equity=1000,
        risk_pct=1,
        entry_price=100,
        stop_price=99,
        symbol_config=cfg,
        slippage_factor=0.1,  # 10% worse stop
    )
    # Without slippage: size = 10. With slippage, effective loss=1.1 -> size < 10
    assert result.size < 10


def test_small_tick_precision_preserved():
    cfg = base_config()
    cfg["tickSize"] = 0.00001
    result = calculate_position_size(
        equity=1000,
        risk_pct=1,
        entry_price=0.00409,
        stop_price=0.00398,
        symbol_config=cfg,
    )
    assert math.isclose(result.entry_price, 0.00409, rel_tol=1e-9)
    assert math.isclose(result.stop_price, 0.00398, rel_tol=1e-9)
    assert result.entry_price != result.stop_price


def test_rounding_collision_raises_error():
    cfg = base_config()
    cfg["tickSize"] = 0.0001
    with pytest.raises(PositionSizingError):
        calculate_position_size(
            equity=1000,
            risk_pct=1,
            entry_price=1.00004,
            stop_price=1.000049,
            symbol_config=cfg,
        )
