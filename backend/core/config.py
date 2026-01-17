from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables from .env if present
load_dotenv(ENV_PATH)


class Settings(BaseSettings):
    """Central application settings loaded via Pydantic (includes ATR config)."""

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        case_sensitive=False,
        extra="ignore",
    )
    app_env: str = Field("development", env="APP_ENV")
    app_host: str = Field("127.0.0.1", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    per_trade_risk_cap_pct: Optional[float] = Field(None, env="PER_TRADE_RISK_CAP_PCT")
    daily_loss_cap_pct: Optional[float] = Field(None, env="DAILY_LOSS_CAP_PCT")
    open_risk_cap_pct: Optional[float] = Field(None, env="OPEN_RISK_CAP_PCT")

    apex_api_key: str = Field(..., env="APEX_API_KEY")
    apex_api_secret: str = Field(..., env="APEX_API_SECRET")
    apex_passphrase: str = Field(..., env="APEX_PASSPHRASE")
    apex_zk_seed: str = Field(..., env="APEX_ZK_SEED")
    apex_zk_l2key: str = Field(..., env="APEX_ZK_L2KEY")
    apex_network: str = Field("testnet", env="APEX_NETWORK")
    apex_http_endpoint: Optional[str] = Field(None, env="APEX_HTTP_ENDPOINT")
    apex_enable_ws: bool = Field(False, env="APEX_ENABLE_WS")
    apex_rest_timeout_seconds: int = Field(10, env="APEX_REST_TIMEOUT_SECONDS")
    apex_rest_retries: int = Field(2, env="APEX_REST_RETRIES")
    apex_rest_retry_backoff_seconds: float = Field(0.5, env="APEX_REST_RETRY_BACKOFF_SECONDS")
    apex_rest_retry_backoff_max_seconds: float = Field(4.0, env="APEX_REST_RETRY_BACKOFF_MAX_SECONDS")
    apex_rest_retry_jitter_seconds: float = Field(0.2, env="APEX_REST_RETRY_JITTER_SECONDS")
    apex_positions_empty_stale_seconds: float = Field(12.0, env="APEX_POSITIONS_EMPTY_STALE_SECONDS")
    apex_orders_empty_stale_seconds: float = Field(12.0, env="APEX_ORDERS_EMPTY_STALE_SECONDS")
    slippage_factor: float = Field(0.0, env="SLIPPAGE_FACTOR")
    fee_buffer_pct: float = Field(0.0, env="FEE_BUFFER_PCT")
    atr_timeframe: str = Field(
        "5m",
        env=("ATR_TIMEFRAME", "TIMEFRAME"),
        description="ATR candle timeframe (e.g., '5m', '15m', '1h').",
    )
    atr_period: int = Field(
        14,
        env=("ATR_PERIOD", "PERIOD"),
        description="ATR lookback window in candles.",
    )
    atr_multiplier: float = Field(
        1.5,
        env=("ATR_MULTIPLIER", "MULTIPLIER"),
        description="ATR multiplier applied when deriving stop offsets.",
    )

    @field_validator("apex_network")
    @classmethod
    def validate_network(cls, value: str) -> str:
        normalized = (value or "testnet").strip().lower()
        allowed = {"testnet", "base", "base-sepolia", "testnet-base", "mainnet"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported APEX_NETWORK '{value}'. Use one of {sorted(allowed)}")
        return normalized

    @field_validator("atr_period")
    @classmethod
    def validate_atr_period(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ATR_PERIOD must be greater than zero")
        return value

    @field_validator("atr_multiplier")
    @classmethod
    def validate_atr_multiplier(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ATR_MULTIPLIER must be greater than zero")
        return value

    @field_validator("atr_timeframe")
    @classmethod
    def validate_atr_timeframe(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("TIMEFRAME must be a non-empty candle interval (e.g., 5m)")
        return normalized

    @field_validator(
        "apex_rest_timeout_seconds",
        "apex_rest_retries",
        "apex_rest_retry_backoff_seconds",
        "apex_rest_retry_backoff_max_seconds",
        "apex_rest_retry_jitter_seconds",
        "apex_positions_empty_stale_seconds",
        "apex_orders_empty_stale_seconds",
    )
    @classmethod
    def validate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Apex REST settings must be non-negative")
        return value


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()  # type: ignore[call-arg]


def get_log_level(default: Optional[str] = None) -> str:
    """Convenience accessor for log level with optional override."""
    settings = get_settings()
    return settings.log_level or (default or "INFO")
