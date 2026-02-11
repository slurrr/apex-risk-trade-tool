import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.exchange.apex_client import ApexClient  # noqa: E402


class FakeSettings:
    apex_network = "testnet"
    apex_zk_seed = "seed"
    apex_zk_l2key = "l2"
    apex_api_key = "key"
    apex_api_secret = "secret"
    apex_passphrase = "pass"
    apex_http_endpoint = None
    apex_rest_timeout_seconds = 10


class FakePublicClientStartSensitive:
    def __init__(self) -> None:
        self.klines_requests = []

    def klines_v3(self, **kwargs):
        self.klines_requests.append(dict(kwargs))
        if "start" in kwargs:
            return {"result": {"list": []}}
        return {
            "result": {
                "list": [
                    {"startTime": 1700000000000, "open": "1", "high": "2", "low": "1", "close": "1.5", "volume": "10"},
                    {"startTime": 1700000060000, "open": "1.5", "high": "2", "low": "1.4", "close": "1.8", "volume": "8"},
                ]
            }
        }


class FakePublicClientVariantShape:
    def klines_v3(self, **kwargs):
        return {
            "data": {
                "rows": [
                    {
                        "openTime": 1700000000000,
                        "Open": "1",
                        "High": "2",
                        "Low": "1",
                        "Close": "1.5",
                        "Volume": "10",
                    }
                ]
            }
        }


class FakePublicClientDeepNested:
    def klines_v3(self, **kwargs):
        return {
            "result": {
                "bars": {
                    "items": [
                        {
                            "start": 1700000000000,
                            "openPrice": "1",
                            "highPrice": "2",
                            "lowPrice": "0.9",
                            "closePrice": "1.4",
                            "baseVolume": "12",
                        }
                    ]
                }
            }
        }


def test_fetch_klines_retries_without_start_when_empty() -> None:
    client = ApexClient(FakeSettings(), private_client=object(), public_client=FakePublicClientStartSensitive())
    candles = client.fetch_klines("BTC-USDT", "15m", limit=50)
    assert len(candles) == 2
    assert "start" in client.public_client.klines_requests[0]
    assert "start" not in client.public_client.klines_requests[1]


def test_fetch_klines_3m_fallback_retries_without_start_when_empty() -> None:
    client = ApexClient(FakeSettings(), private_client=object(), public_client=FakePublicClientStartSensitive())
    candles = client.fetch_klines("BTC-USDT", "3m", limit=50)
    assert len(candles) >= 1
    # 3m direct path retries with no start and should return data.
    assert "start" in client.public_client.klines_requests[0]
    assert "start" not in client.public_client.klines_requests[1]


def test_fetch_klines_normalizes_variant_candle_keys() -> None:
    client = ApexClient(FakeSettings(), private_client=object(), public_client=FakePublicClientVariantShape())
    candles = client.fetch_klines("BTC-USDT", "15m", limit=10)
    assert len(candles) == 1
    assert candles[0]["open_time"] == 1700000000000
    assert candles[0]["open"] == 1.0
    assert candles[0]["close"] == 1.5


def test_fetch_klines_extracts_deep_nested_rows() -> None:
    client = ApexClient(FakeSettings(), private_client=object(), public_client=FakePublicClientDeepNested())
    candles = client.fetch_klines("ZEC-USDT", "3m", limit=10)
    assert len(candles) == 1
    assert candles[0]["open_time"] == 1700000000000
    assert candles[0]["high"] == 2.0
