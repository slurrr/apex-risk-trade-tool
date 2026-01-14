from __future__ import annotations

from typing import Any, Iterable, Optional


def compute_depth_summary(orderbook_payload: Any, *, tolerance_bps: int) -> dict[str, Any]:
    """
    Compute max notional capacity inside a bps band around top-of-book.
    Returns bid/ask/spread along with max_buy_notional/max_sell_notional.
    """
    data = _unwrap_orderbook(orderbook_payload)
    bids = _parse_levels(_extract_side(data, ("bids", "bid", "b", "buy", "buys")))
    asks = _parse_levels(_extract_side(data, ("asks", "ask", "a", "sell", "sells")))
    bids.sort(key=lambda lvl: lvl[0], reverse=True)
    asks.sort(key=lambda lvl: lvl[0])

    bid0 = bids[0][0] if bids else None
    ask0 = asks[0][0] if asks else None
    spread_bps = _compute_spread_bps(bid0, ask0)

    t = float(tolerance_bps) / 10000.0 if tolerance_bps is not None else 0.0
    max_buy = _sum_band_notional(asks, ask0, 1 + t, comparator="lte")
    max_sell = _sum_band_notional(bids, bid0, 1 - t, comparator="gte")

    return {
        "bid": bid0,
        "ask": ask0,
        "spread_bps": spread_bps,
        "max_buy_notional": max_buy,
        "max_sell_notional": max_sell,
        "bids_count": len(bids),
        "asks_count": len(asks),
    }


def _unwrap_orderbook(payload: Any) -> Any:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        for key in ("result", "data", "payload"):
            if key in payload:
                return _unwrap_orderbook(payload[key])
    return payload


def _extract_side(data: Any, keys: Iterable[str]) -> Any:
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return data.get(key)
    return []


def _parse_levels(raw_levels: Any) -> list[tuple[float, float]]:
    levels: list[tuple[float, float]] = []
    if raw_levels is None:
        return levels
    if isinstance(raw_levels, dict):
        raw_levels = raw_levels.get("levels") or raw_levels.get("data") or raw_levels.get("list") or []
    if not isinstance(raw_levels, (list, tuple)):
        return levels
    for level in raw_levels:
        price, size = _parse_level(level)
        if price is None or size is None:
            continue
        if price <= 0 or size <= 0:
            continue
        levels.append((price, size))
    return levels


def _parse_level(level: Any) -> tuple[Optional[float], Optional[float]]:
    if level is None:
        return None, None
    if isinstance(level, (list, tuple)) and len(level) >= 2:
        return _to_float(level[0]), _to_float(level[1])
    if isinstance(level, dict):
        price = _to_float(
            level.get("price")
            or level.get("p")
            or level.get("rate")
            or level.get("px")
        )
        size = _to_float(
            level.get("size")
            or level.get("qty")
            or level.get("quantity")
            or level.get("q")
        )
        return price, size
    return None, None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_spread_bps(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return ((ask - bid) / mid) * 10000.0


def _sum_band_notional(
    levels: list[tuple[float, float]],
    top_price: Optional[float],
    multiplier: float,
    *,
    comparator: str,
) -> Optional[float]:
    if top_price is None:
        return None
    limit = top_price * multiplier
    total = 0.0
    for price, size in levels:
        if comparator == "lte" and price <= limit:
            total += price * size
        elif comparator == "gte" and price >= limit:
            total += price * size
    return total
