import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PositionSizingResult:
    side: str
    size: float
    notional: float
    estimated_loss: float
    warnings: List[str]
    entry_price: float
    stop_price: float


class PositionSizingError(Exception):
    """Raised when sizing cannot be computed safely."""


def _round_down(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


def _round_price(value: float, tick: float) -> float:
    if tick <= 0:
        return value
    return round(value / tick) * tick


def calculate_position_size(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    symbol_config: Dict[str, float],
    slippage_factor: float = 0.0,
    fee_buffer_pct: float = 0.0,
    leverage_capital: Optional[float] = None,
) -> PositionSizingResult:
    """
    Pure position sizing with exchange constraints and safety rails.
    - Applies slippage by inflating loss distance.
    - Applies fee buffer by reducing risk capital.
    - Rounds prices to tickSize and size down to stepSize.
    - Enforces min/max size and leverage caps.
    """
    if risk_pct <= 0:
        raise PositionSizingError("Risk% must be positive.")

    tick = float(symbol_config.get("tickSize", 0) or 0)
    step = float(symbol_config.get("stepSize", 0) or 0)
    min_size = float(symbol_config.get("minOrderSize", 0) or 0)
    max_size = float(symbol_config.get("maxOrderSize", float("inf")) or float("inf"))
    max_leverage = symbol_config.get("maxLeverage")
    max_leverage = float(max_leverage) if max_leverage not in (None, 0) else None

    entry_price_rounded = _round_price(entry_price, tick)
    stop_price_rounded = _round_price(stop_price, tick)

    delta = entry_price_rounded - stop_price_rounded
    if delta == 0:
        raise PositionSizingError("Stop price equals entry price.")

    side = "BUY" if delta > 0 else "SELL"
    per_unit_loss = abs(delta)

    # Inflate loss distance for slippage (conservative)
    effective_loss = per_unit_loss * (1 + slippage_factor)
    if effective_loss <= 0:
        raise PositionSizingError("Effective per-unit loss is non-positive.")

    risk_capital = equity * (risk_pct / 100.0)
    if fee_buffer_pct > 0:
        risk_capital *= max(0.0, 1 - (fee_buffer_pct / 100.0))

    if risk_capital <= 0:
        raise PositionSizingError("Risk capital is non-positive.")

    raw_size = risk_capital / effective_loss
    raw_size = min(raw_size, max_size)

    sized = _round_down(raw_size, step)
    if sized <= 0:
        raise PositionSizingError("Calculated size is zero after rounding.")

    if sized < min_size:
        raise PositionSizingError(
            f"Calculated size {sized} below minimum order size {min_size}"
        )

    notional = sized * entry_price_rounded
    warnings: List[str] = []

    if max_leverage is not None and max_leverage > 0:
        leverage_base_capital = (
            float(leverage_capital)
            if leverage_capital is not None and float(leverage_capital) > 0
            else float(equity)
        )
        max_notional = leverage_base_capital * max_leverage
        if notional > max_notional:
            allowed = max_notional / entry_price_rounded
            allowed = _round_down(allowed, step)
            if allowed < min_size:
                raise PositionSizingError(
                    "Size violates leverage cap and cannot meet minimum size."
                )
            warnings.append("Size reduced to fit leverage constraints.")
            sized = allowed
            notional = sized * entry_price_rounded

    estimated_loss = per_unit_loss * sized

    return PositionSizingResult(
        side=side,
        size=sized,
        notional=notional,
        estimated_loss=estimated_loss,
        warnings=warnings,
        entry_price=entry_price_rounded,
        stop_price=stop_price_rounded,
    )
