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
        rows = self._unwrap_candle_rows(response)
        candles: List[Candle] = []
        for row in rows:
            normalized = self._normalize_candle(row)
            if normalized:
                candles.append(normalized)
        if not candles:
            logger.warning(
                "apex_client.fetch_klines.empty",
                extra={"symbol": symbol, "timeframe": timeframe, "limit": limit},
            )
        return candles

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
