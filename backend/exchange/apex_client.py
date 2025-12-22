import time
from typing import Any, Optional, TypedDict, List, Sequence, Union, Tuple

from backend.core.logging import get_logger

from backend.core.config import Settings

logger = get_logger(__name__)


class Candle(TypedDict, total=False):
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]


class Trade(TypedDict, total=False):
    price: float
    size: float
    side: str
    timestamp: int
    is_maker: Optional[bool]


class ApexClient:
    """Thin wrapper around ApeX Omni SDK clients (HTTP + WebSocket)."""

    def __init__(self, settings: Settings, private_client: Optional[Any] = None, public_client: Optional[Any] = None) -> None:
        self.settings = settings
        self.private_client = private_client or self._init_private_client(settings)
        self.public_client = public_client or self._init_public_client(settings)

    def _init_private_client(self, settings: Settings) -> Any:
        from apexomni.constants import (
            APEX_OMNI_HTTP_MAIN,
            APEX_OMNI_HTTP_TEST,
            NETWORKID_MAIN,
            NETWORKID_OMNI_TEST_BNB,
            NETWORKID_OMNI_TEST_BASE,
        )
        from apexomni.http_private_sign import HttpPrivateSign

        network = getattr(settings, "apex_network", "testnet").lower()
        testnet_networks = {"base", "base-sepolia", "testnet-base", "testnet"}
        if network in {"base", "base-sepolia", "testnet-base"}:
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BASE
        elif network == "testnet":
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BNB
        else:
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_MAIN
            network_id = NETWORKID_MAIN

        client = HttpPrivateSign(
            endpoint,
            network_id=network_id,
            zk_seeds=settings.apex_zk_seed,
            zk_l2Key=settings.apex_zk_l2key,
            api_key_credentials={
                "key": settings.apex_api_key,
                "secret": settings.apex_api_secret,
                "passphrase": settings.apex_passphrase,
            },
        )
        # Avoid inheriting system proxy settings that can block testnet calls.
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

    def _init_public_client(self, settings: Settings) -> Any:
        from apexomni.http_public import HttpPublic

        endpoint = getattr(settings, "apex_http_endpoint", None) or "https://omni.apex.exchange"
        client = HttpPublic(endpoint)
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

    def ws_base_endpoint(self) -> str:
        from apexomni.constants import APEX_OMNI_WS_MAIN, APEX_OMNI_WS_TEST

        network = getattr(self.settings, "apex_network", "testnet").lower()
        if network in {"base", "base-sepolia", "testnet-base", "testnet"}:
            return APEX_OMNI_WS_TEST
        return APEX_OMNI_WS_MAIN

    def create_public_ws(self) -> Any:
        from apexomni.websocket_api import WebSocket

        return WebSocket(endpoint=self.ws_base_endpoint())

    def create_private_ws(self) -> Any:
        from apexomni.websocket_api import WebSocket

        creds = {
            "key": self.settings.apex_api_key,
            "secret": self.settings.apex_api_secret,
            "passphrase": self.settings.apex_passphrase,
        }
        return WebSocket(endpoint=self.ws_base_endpoint(), api_key_credentials=creds)

    def fetch_klines(self, symbol: str, timeframe: str, limit: int = 200) -> List[Candle]:
        """
        Fetch recent OHLC candles for a symbol/timeframe combo using the public REST API.
        """
        if not symbol:
            raise ValueError("symbol is required for klines lookup")
        if not timeframe:
            raise ValueError("timeframe is required for klines lookup")
        limit = max(1, min(limit, 1000))

        interval_label, interval_seconds = self._normalize_interval(timeframe)
        query: dict[str, Any] = {"symbol": symbol, "interval": interval_label, "limit": limit}
        if interval_seconds:
            lookback = min(limit, 200) + 2
            query["start"] = max(0, int(time.time()) - (lookback * interval_seconds))

        response: Any = self.public_client.klines_v3(**query)
        candles = self._normalize_candles(response)
        if candles:
            return candles

        if interval_label == "3" and interval_seconds == 180:
            fallback = self._fetch_3m_from_1m(symbol, limit)
            if fallback:
                logger.info(
                    "apex_client.fetch_klines.fallback_3m_from_1m",
                    extra={"symbol": symbol, "timeframe": timeframe, "limit": limit, "fallback_count": len(fallback)},
                )
                return fallback

        logger.warning(
            "apex_client.fetch_klines.empty",
            extra={"symbol": symbol, "timeframe": timeframe, "limit": limit},
        )
        return candles

    def _normalize_candles(self, response: Any) -> List[Candle]:
        rows = self._unwrap_candle_rows(response)
        candles: List[Candle] = []
        for row in rows:
            normalized = self._normalize_candle(row)
            if normalized:
                candles.append(normalized)
        return candles

    def _fetch_3m_from_1m(self, symbol: str, limit: int) -> List[Candle]:
        limit_1m = max(3, min(limit * 3, 1000))
        lookback = min(limit_1m, 200) + 2
        query = {
            "symbol": symbol,
            "interval": "1",
            "limit": limit_1m,
            "start": max(0, int(time.time()) - (lookback * 60)),
        }
        response: Any = self.public_client.klines_v3(**query)
        candles_1m = self._normalize_candles(response)
        if not candles_1m:
            return []
        candles_1m.sort(key=lambda c: c.get("open_time", 0))
        return self._aggregate_candles(candles_1m, bucket_seconds=180)

    def _aggregate_candles(self, candles: Sequence[Candle], bucket_seconds: int) -> List[Candle]:
        if not candles:
            return []
        bucket_ms = bucket_seconds * 1000
        grouped: dict[int, List[Candle]] = {}
        for candle in candles:
            open_time = candle.get("open_time")
            if open_time is None:
                continue
            bucket = int(open_time // bucket_ms) * bucket_ms
            grouped.setdefault(bucket, []).append(candle)

        aggregated: List[Candle] = []
        for bucket in sorted(grouped.keys()):
            bucket_candles = grouped[bucket]
            if not bucket_candles:
                continue
            bucket_candles.sort(key=lambda c: c.get("open_time", 0))
            open_price = bucket_candles[0]["open"]
            close_price = bucket_candles[-1]["close"]
            high_price = max(c["high"] for c in bucket_candles)
            low_price = min(c["low"] for c in bucket_candles)
            volumes = [c.get("volume") for c in bucket_candles if c.get("volume") is not None]
            volume = sum(volumes) if volumes else None
            aggregated.append(
                Candle(
                    open_time=int(bucket),
                    open=float(open_price),
                    high=float(high_price),
                    low=float(low_price),
                    close=float(close_price),
                    volume=float(volume) if volume is not None else None,
                )
            )
        return aggregated

    def fetch_recent_trades(self, symbol: str, limit: int = 50) -> List[Trade]:
        """
        Fetch recent public trades for the provided symbol.
        """
        if not symbol:
            raise ValueError("symbol is required for trades lookup")
        limit = max(1, min(limit, 200))

        response: Any = self.public_client.trades_v3(symbol=symbol, limit=limit)
        rows = self._unwrap_trade_rows(response)
        trades: List[Trade] = []
        for row in rows:
            normalized = self._normalize_trade(row)
            if normalized:
                trades.append(normalized)
        trades.sort(key=lambda entry: entry["timestamp"], reverse=True)
        if len(trades) > limit:
            trades = trades[:limit]
        if not trades:
            logger.warning(
                "apex_client.fetch_recent_trades.empty",
                extra={"symbol": symbol, "limit": limit},
            )
        return trades

    def _unwrap_candle_rows(self, payload: Any) -> List[Any]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("result", "data"):
                if key in payload:
                    return self._unwrap_candle_rows(payload[key])
            for key in ("list", "rows", "klines"):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return rows
            map_values = payload.values()
            flattened: List[Any] = []
            for value in map_values:
                if isinstance(value, list):
                    flattened.extend(value)
            if flattened:
                return flattened
            candle_keys = {"open", "high", "low", "close"}
            if candle_keys.issubset({k.lower() for k in payload.keys()}):
                return [payload]
        return []

    def _normalize_candle(self, row: Union[Sequence[Any], dict]) -> Optional[Candle]:
        open_time: Optional[int] = None
        open_price: Optional[float] = None
        high: Optional[float] = None
        low: Optional[float] = None
        close: Optional[float] = None
        volume: Optional[float] = None

        if isinstance(row, dict):
            def _get_num(key: str) -> Optional[float]:
                value = row.get(key)
                if value is None:
                    return None
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None

            open_time_candidates = (
                row.get("startTime")
                or row.get("openTime")
                or row.get("time")
                or row.get("timestamp")
                or row.get("start")
                or row.get("t")
            )
            if open_time_candidates is not None:
                try:
                    open_time = int(open_time_candidates)
                except (TypeError, ValueError):
                    open_time = None
            open_price = _get_num("open") or _get_num("o")
            high = _get_num("high") or _get_num("h")
            low = _get_num("low") or _get_num("l")
            close = _get_num("close") or _get_num("c")
            volume = _get_num("volume") or _get_num("v")
        elif isinstance(row, Sequence) and len(row) >= 6:
            try:
                open_time = int(row[0])
            except (TypeError, ValueError):
                open_time = None
            try:
                open_price = float(row[1])
                high = float(row[2])
                low = float(row[3])
                close = float(row[4])
            except (TypeError, ValueError):
                return None
            try:
                volume = float(row[5])
            except (TypeError, ValueError):
                volume = None

        if any(value is None for value in (open_time, open_price, high, low, close)):
            return None
        return Candle(
            open_time=int(open_time),  # type: ignore[arg-type]
            open=float(open_price),  # type: ignore[arg-type]
            high=float(high),  # type: ignore[arg-type]
            low=float(low),  # type: ignore[arg-type]
            close=float(close),  # type: ignore[arg-type]
            volume=float(volume) if volume is not None else None,
        )

    def _unwrap_trade_rows(self, payload: Any) -> List[Any]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("result", "data", "payload"):
                if key in payload:
                    return self._unwrap_trade_rows(payload[key])
            for key in ("list", "rows", "trades"):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return rows
            flattened: List[Any] = []
            for value in payload.values():
                if isinstance(value, list):
                    flattened.extend(value)
            if flattened:
                return flattened
        return []

    def _normalize_trade(self, row: Union[Sequence[Any], dict]) -> Optional[Trade]:
        price: Optional[float] = None
        size: Optional[float] = None
        timestamp: Optional[int] = None
        side: Optional[str] = None
        is_maker: Optional[bool] = None

        def _parse_float(value: Any) -> Optional[float]:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _parse_timestamp(value: Any) -> Optional[int]:
            if value is None:
                return None
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        if isinstance(row, dict):
            price = _parse_float(row.get("price") or row.get("p"))
            size = _parse_float(
                row.get("size")
                or row.get("qty")
                or row.get("quantity")
                or row.get("q")
                or row.get("volume")
                or row.get("v")
            )
            timestamp = _parse_timestamp(
                row.get("timestamp")
                or row.get("time")
                or row.get("ts")
                or row.get("tradeTime")
            )
            raw_side = row.get("side") or row.get("direction") or row.get("S")
            side = str(raw_side).upper() if raw_side is not None else None
            maker_flag = (
                row.get("isMaker")
                or row.get("maker")
                or row.get("M")
                or row.get("liquidity")
            )
            is_maker = self._coerce_bool(maker_flag)
        elif isinstance(row, Sequence) and len(row) >= 4:
            price = _parse_float(row[1])
            size = _parse_float(row[2])
            timestamp = _parse_timestamp(row[0] if isinstance(row[0], (int, float, str)) else row[3])
            if isinstance(row[3], str):
                side = row[3].upper()
            elif len(row) >= 5 and isinstance(row[4], str):
                side = row[4].upper()
            if len(row) >= 6:
                is_maker = self._coerce_bool(row[5])

        if any(value is None for value in (price, size, timestamp)):
            return None
        normalized_side = side or "UNKNOWN"
        return Trade(
            price=float(price),  # type: ignore[arg-type]
            size=float(size),  # type: ignore[arg-type]
            side=normalized_side,
            timestamp=int(timestamp),  # type: ignore[arg-type]
            is_maker=is_maker,
        )

    def _coerce_bool(self, value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "t", "1", "maker"}:
                return True
            if lowered in {"false", "f", "0", "taker"}:
                return False
        return None

    def _normalize_interval(self, timeframe: str) -> Tuple[str, Optional[int]]:
        raw = (timeframe or "").strip().lower()
        if not raw:
            raise ValueError("timeframe cannot be empty")
        if raw.endswith("m"):
            magnitude = raw[:-1]
            if not magnitude.isdigit():
                raise ValueError(f"Unsupported timeframe '{timeframe}'")
            minutes = int(magnitude)
            return str(minutes), minutes * 60
        if raw.endswith("h"):
            magnitude = raw[:-1]
            if not magnitude.isdigit():
                raise ValueError(f"Unsupported timeframe '{timeframe}'")
            hours = int(magnitude)
            minutes = hours * 60
            return str(minutes), minutes * 60
        if raw.endswith("d"):
            magnitude = raw[:-1]
            if not magnitude.isdigit():
                raise ValueError(f"Unsupported timeframe '{timeframe}'")
            days = int(magnitude)
            minutes = days * 24 * 60
            return str(minutes), minutes * 60
        if raw.isdigit():
            minutes = int(raw)
            return str(minutes), minutes * 60
        raise ValueError(f"Unsupported timeframe '{timeframe}'")
