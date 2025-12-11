from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from backend.core.config import Settings
from backend.core.logging import get_logger


logger = get_logger(__name__)


CandlePayload = Mapping[str, Any]


@dataclass(frozen=True)
class AtrConfig:
    timeframe: str
    period: int
    multiplier: float


@dataclass(frozen=True)
class AtrStopResult:
    symbol: str
    side: str
    entry_price: float
    atr_value: float
    config: AtrConfig
    stop_price: float


def config_from_settings(settings: Settings) -> AtrConfig:
    """Map repo settings -> ATR-focused config struct."""
    return AtrConfig(
        timeframe=settings.atr_timeframe,
        period=settings.atr_period,
        multiplier=settings.atr_multiplier,
    )


def calculate_atr(symbol: str, timeframe: str, candles: Sequence[CandlePayload], period: int) -> Optional[float]:
    """
    Calculate Wilder's ATR for the supplied symbol/timeframe using ordered candles.

    Candles should be ordered from oldest -> newest and must expose high/low/close keys.
    """
    if period <= 0:
        raise ValueError("ATR period must be positive")
    if len(candles) < period:
        logger.warning(
            "atr_insufficient_candles",
            extra={"symbol": symbol, "timeframe": timeframe, "available": len(candles), "period": period},
        )
        return None

    true_ranges: list[float] = []
    prev_close: Optional[float] = None

    for candle in candles:
        high = _extract_price(candle, "high", "High", "h")
        low = _extract_price(candle, "low", "Low", "l")
        close = _extract_price(candle, "close", "Close", "c")

        if None in (high, low, close):
            continue

        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))

        if tr < 0:
            continue
        true_ranges.append(tr)
        prev_close = close

    if len(true_ranges) < period:
        logger.warning(
            "atr_tr_gap",
            extra={"symbol": symbol, "timeframe": timeframe, "valid_tr": len(true_ranges), "period": period},
        )
        return None

    # Wilder's smoothing: SMA for first period, then recursive smoothing for the rest.
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = ((atr * (period - 1)) + tr) / period
    return atr


def compute_configured_stop(
    symbol: str,
    side: str,
    entry_price: float,
    atr_value: float,
    config: AtrConfig,
) -> Optional[AtrStopResult]:
    """Combine ATR output and configured multiplier to derive a default stop."""
    stop_price = default_stop_price(entry_price, side, atr_value, config.multiplier)
    if stop_price is None:
        return None
    return AtrStopResult(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        atr_value=atr_value,
        config=config,
        stop_price=stop_price,
    )


def default_stop_price(entry_price: float, side: str, atr_value: float, multiplier: float) -> Optional[float]:
    """Return ATR-based offset below (long) or above (short) the entry price."""
    if not all(map(_is_positive_number, (entry_price, atr_value, multiplier))):
        return None

    offset = atr_value * multiplier
    direction = (side or "").strip().lower()

    if direction == "long":
        return max(entry_price - offset, 0.0)
    if direction == "short":
        return entry_price + offset
    raise ValueError("side must be 'long' or 'short'")


def _extract_price(candle: CandlePayload, *keys: str) -> Optional[float]:
    for key in keys:
        if key in candle:
            value = candle[key]
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _is_positive_number(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0
