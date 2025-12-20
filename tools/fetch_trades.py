"""
Simple CLI utility that fetches the most recent ApeX trades for a symbol.
Falls back to raw REST calls if the SDK wrapper returns an empty payload.

Usage (from repo root):
    python tools/fetch_trades.py BTC-USDT --limit 25

Use --json to dump the normalized payload instead of a formatted table.
Environment variables are loaded via backend.core.config.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import Settings, get_settings
from backend.exchange.apex_client import ApexClient, Trade

DEFAULT_PUBLIC_ENDPOINTS = (
    "https://omni.apex.exchange",
    "https://testnet.omni.apex.exchange",
)


def _format_timestamp(ts: int) -> str:
    seconds = ts / 1000 if ts > 10**10 else ts
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


def _normalize_symbol_input(symbol: str) -> str:
    raw = (symbol or "").strip().upper()
    if not raw:
        return raw
    if "-" in raw:
        return raw
    for quote in ("USDT", "USDC", "USDC.E", "USD"):
        if raw.endswith(quote) and len(raw) > len(quote):
            return f"{raw[:-len(quote)]}-{quote}"
    return raw


def _symbol_variants(symbol: str) -> List[str]:
    normalized = (symbol or "").replace(" ", "").upper()
    if not normalized:
        return []

    variants: List[str] = []

    def _add(value: Optional[str]) -> None:
        if not value:
            return
        candidate = value.strip().upper()
        if candidate and candidate not in variants:
            variants.append(candidate)

    _add(normalized)
    if "-" in normalized:
        _add(normalized.replace("-", ""))
    else:
        for quote in ("USDT", "USDC", "USDC.E", "USD"):
            if normalized.endswith(quote) and len(normalized) > len(quote):
                base = normalized[:-len(quote)]
                dashed = f"{base}-{quote}"
                _add(dashed)
                _add(dashed.replace("-", ""))
                break
    _add(normalized.replace("-", ""))
    return variants


def _iter_public_endpoints(settings: Settings) -> List[str]:
    seen: List[str] = []
    candidates: Iterable[Optional[str]] = (
        getattr(settings, "apex_http_endpoint", None),
        *DEFAULT_PUBLIC_ENDPOINTS,
    )
    for candidate in candidates:
        if not candidate:
            continue
        cleaned = candidate.rstrip("/")
        if cleaned.lower().endswith("/api"):
            cleaned = cleaned[:-4]
        if cleaned not in seen:
            seen.append(cleaned)
    return seen


def _api_base(base: str) -> str:
    cleaned = base.rstrip("/")
    if cleaned.lower().endswith("/api"):
        return cleaned
    return f"{cleaned}/api"


def _unwrap_trade_payload(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("result", "data", "payload"):
            if key in payload:
                rows = _unwrap_trade_payload(payload[key])
                if rows:
                    return rows
        for key in ("list", "rows", "trades", "dataList", "data_list"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
            if isinstance(rows, dict):
                nested = _unwrap_trade_payload(rows)
                if nested:
                    return nested
        flattened: List[Any] = []
        for value in payload.values():
            if isinstance(value, (list, dict)):
                nested = _unwrap_trade_payload(value)
                if nested:
                    if isinstance(nested, list):
                        flattened.extend(nested)
        if flattened:
            return flattened
    return []


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _parse_timestamp(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return None
    if timestamp > 10**15:
        timestamp //= 1_000_000  # ns -> ms
    elif timestamp > 10**13:
        timestamp //= 1_000  # µs -> ms
    return timestamp


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "t", "1", "maker", "yes"}:
            return True
        if lowered in {"false", "f", "0", "taker", "no"}:
            return False
    return None


def _normalize_trade_lax(row: Any) -> Optional[Trade]:
    price: Optional[float] = None
    size: Optional[float] = None
    timestamp: Optional[int] = None
    side: Optional[str] = None
    is_maker: Optional[bool] = None

    if isinstance(row, dict):
        price = _parse_float(
            row.get("price")
            or row.get("p")
            or row.get("lastPrice")
            or row.get("tradePrice")
            or row.get("dealPrice")
            or row.get("avgPrice")
            or row.get("xp")
        )
        size = _parse_float(
            row.get("size")
            or row.get("qty")
            or row.get("quantity")
            or row.get("lastQty")
            or row.get("tradeQty")
            or row.get("volume")
            or row.get("vol")
            or row.get("q")
            or row.get("amount")
            or row.get("v")
        )
        timestamp = _parse_timestamp(
            row.get("timestamp")
            or row.get("time")
            or row.get("ts")
            or row.get("tradeTime")
            or row.get("execTime")
            or row.get("createdAt")
            or row.get("tradeTimeNs")
            or row.get("timeNano")
            or row.get("updatedAt")
            or row.get("T")
        )
        raw_side = row.get("side") or row.get("tradeSide") or row.get("direction") or row.get("S")
        if isinstance(raw_side, str):
            side = raw_side.upper()
        elif isinstance(raw_side, (int, float)):
            side = "BUY" if raw_side >= 0 else "SELL"
        maker_flag = (
            row.get("isMaker")
            or row.get("maker")
            or row.get("is_maker")
            or row.get("M")
            or row.get("liquidity")
            or row.get("isBuyerMaker")
        )
        is_maker = _coerce_bool(maker_flag)
        if side is None and isinstance(row.get("isBuyerMaker"), bool):
            side = "SELL" if row["isBuyerMaker"] else "BUY"
    elif isinstance(row, Sequence) and len(row) >= 3:
        timestamp = _parse_timestamp(row[0])
        price = _parse_float(row[1])
        size = _parse_float(row[2])
        if len(row) >= 4:
            side = str(row[3]).upper()
        if len(row) >= 5:
            is_maker = _coerce_bool(row[4])

    if price is None:
        return None
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    if size is None:
        size = 0.0
    normalized_side = side or "UNKNOWN"
    return Trade(
        price=float(price),
        size=float(size),
        side=normalized_side,
        timestamp=int(timestamp),
        is_maker=is_maker,
    )


def _fetch_trades_via_http(symbol: str, limit: int, settings: Settings) -> List[Trade]:
    endpoints = _iter_public_endpoints(settings)
    for base in endpoints:
        url = f"{_api_base(base)}/v3/trades"
        for candidate in _symbol_variants(symbol):
            params = {"symbol": candidate, "limit": limit}
            try:
                response = requests.get(url, params=params, timeout=5)
            except Exception:
                continue
            if response.status_code != 200:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            rows = _unwrap_trade_payload(payload)
            if not rows:
                continue
            trades = [_normalize_trade_lax(row) for row in rows]
            normalized = [trade for trade in trades if trade]
            if normalized:
                normalized.sort(key=lambda entry: entry["timestamp"], reverse=True)
                return normalized[:limit]
    return []


def _print_table(symbol: str, trades: List[Trade]) -> None:
    print(f"Fetched {len(trades)} trades for {symbol.upper()}.")
    if not trades:
        return
    header = f"{'#':>3}  {'Time (UTC)':<23}  {'Side':<5}  {'Price':>14}  {'Size':>14}  {'Maker':<5}"
    print(header)
    print("-" * len(header))
    for idx, trade in enumerate(trades, start=1):
        timestamp = _format_timestamp(trade["timestamp"])
        side = trade["side"]
        maker = "Y" if trade.get("is_maker") else "N" if trade.get("is_maker") is not None else "-"
        print(
            f"{idx:>3}  {timestamp:<23}  {side:<5}  "
            f"{trade['price']:>14.6f}  {trade['size']:>14.6f}  {maker:<5}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch recent ApeX trades for a symbol.")
    parser.add_argument(
        "symbol",
        help="Symbol (BTC-USDT preferred, BTCUSDT accepted).",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=50,
        help="Number of trades to pull (max 200). Defaults to 50.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the normalized trades as JSON instead of a table.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = ApexClient(settings)
    normalized_symbol = _normalize_symbol_input(args.symbol)
    trades = client.fetch_recent_trades(symbol=normalized_symbol, limit=args.limit)
    fallback_used = False
    if not trades:
        trades = _fetch_trades_via_http(normalized_symbol, args.limit, settings)
        fallback_used = bool(trades)

    if not trades:
        print("No trades were returned from ApeX. Check the symbol or network.", file=sys.stderr)
        return

    if args.json:
        print(json.dumps(trades, indent=2))
    else:
        if fallback_used:
            print("(Fallback REST lookup used due to empty SDK response.)")
        _print_table(normalized_symbol, trades)


if __name__ == "__main__":
    main()
