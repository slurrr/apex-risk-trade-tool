from functools import lru_cache
from pathlib import Path
import re
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
    active_venue: str = Field("apex", env="ACTIVE_VENUE")
    app_host: str = Field("127.0.0.1", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_to_file: bool = Field(True, env="LOG_TO_FILE")
    log_dir: str = Field("logs", env="LOG_DIR")
    log_console_level: str = Field("INFO", env="LOG_CONSOLE_LEVEL")
    log_incident_level: str = Field("WARNING", env="LOG_INCIDENT_LEVEL")
    log_audit_trade_enabled: bool = Field(True, env="LOG_AUDIT_TRADE_ENABLED")
    log_audit_stream_enabled: bool = Field(False, env="LOG_AUDIT_STREAM_ENABLED")
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
    hyperliquid_http_endpoint: str = Field("https://api.hyperliquid.xyz", env="HYPERLIQUID_HTTP_ENDPOINT")
    hyperliquid_min_notional_usdc: float = Field(10.0, env="HYPERLIQUID_MIN_NOTIONAL_USDC")
    hl_user_address: Optional[str] = Field(None, env="HL_USER_ADDRESS")
    hl_agent_private_key: Optional[str] = Field(None, env="HL_AGENT_PRIVATE_KEY")
    hyperliquid_enable_ws: bool = Field(True, env="HYPERLIQUID_ENABLE_WS")
    hyperliquid_reconcile_audit_interval_seconds: float = Field(
        900.0,
        env="HYPERLIQUID_RECONCILE_AUDIT_INTERVAL_SECONDS",
    )
    hyperliquid_reconcile_stale_stream_seconds: float = Field(
        90.0,
        env="HYPERLIQUID_RECONCILE_STALE_STREAM_SECONDS",
    )
    hyperliquid_reconcile_order_timeout_seconds: float = Field(
        20.0,
        env="HYPERLIQUID_RECONCILE_ORDER_TIMEOUT_SECONDS",
    )
    hyperliquid_reconcile_min_gap_seconds: float = Field(
        5.0,
        env="HYPERLIQUID_RECONCILE_MIN_GAP_SECONDS",
    )
    hyperliquid_reconcile_alert_window_seconds: float = Field(
        300.0,
        env="HYPERLIQUID_RECONCILE_ALERT_WINDOW_SECONDS",
    )
    hyperliquid_reconcile_alert_max_per_window: int = Field(
        3,
        env="HYPERLIQUID_RECONCILE_ALERT_MAX_PER_WINDOW",
    )
    hyperliquid_order_timeout_alert_max_per_window: int = Field(
        3,
        env="HYPERLIQUID_ORDER_TIMEOUT_ALERT_MAX_PER_WINDOW",
    )
    apex_enable_ws: bool = Field(False, env="APEX_ENABLE_WS")
    apex_rest_timeout_seconds: int = Field(10, env="APEX_REST_TIMEOUT_SECONDS")
    apex_rest_retries: int = Field(2, env="APEX_REST_RETRIES")
    apex_rest_retry_backoff_seconds: float = Field(0.5, env="APEX_REST_RETRY_BACKOFF_SECONDS")
    apex_rest_retry_backoff_max_seconds: float = Field(4.0, env="APEX_REST_RETRY_BACKOFF_MAX_SECONDS")
    apex_rest_retry_jitter_seconds: float = Field(0.2, env="APEX_REST_RETRY_JITTER_SECONDS")
    apex_positions_empty_stale_seconds: float = Field(12.0, env="APEX_POSITIONS_EMPTY_STALE_SECONDS")
    apex_orders_empty_stale_seconds: float = Field(12.0, env="APEX_ORDERS_EMPTY_STALE_SECONDS")
    apex_reconcile_audit_interval_seconds: float = Field(900.0, env="APEX_RECONCILE_AUDIT_INTERVAL_SECONDS")
    apex_reconcile_stale_stream_seconds: float = Field(90.0, env="APEX_RECONCILE_STALE_STREAM_SECONDS")
    apex_reconcile_min_gap_seconds: float = Field(5.0, env="APEX_RECONCILE_MIN_GAP_SECONDS")
    apex_reconcile_alert_window_seconds: float = Field(300.0, env="APEX_RECONCILE_ALERT_WINDOW_SECONDS")
    apex_reconcile_alert_max_per_window: int = Field(3, env="APEX_RECONCILE_ALERT_MAX_PER_WINDOW")
    apex_poll_orders_interval_seconds: float = Field(5.0, env="APEX_POLL_ORDERS_INTERVAL_SECONDS")
    apex_poll_positions_interval_seconds: float = Field(5.0, env="APEX_POLL_POSITIONS_INTERVAL_SECONDS")
    apex_poll_account_interval_seconds: float = Field(15.0, env="APEX_POLL_ACCOUNT_INTERVAL_SECONDS")
    apex_local_hint_ttl_seconds: float = Field(20.0, env="APEX_LOCAL_HINT_TTL_SECONDS")
    apex_ws_price_stale_seconds: float = Field(30.0, env="APEX_WS_PRICE_STALE_SECONDS")
    slippage_factor: float = Field(0.0, env="SLIPPAGE_FACTOR")
    fee_buffer_pct: float = Field(0.0, env="FEE_BUFFER_PCT")
    atr_timeframe: str = Field(
        "15m",
        env="ATR_TIMEFRAME",
        description="ATR candle timeframe (e.g., '5m', '15m', '1h').",
    )
    atr_sl_1: str = Field("3m", env="ATR_SL_1")
    atr_sl_2: str = Field("15m", env="ATR_SL_2")
    atr_sl_3: str = Field("1h", env="ATR_SL_3")
    atr_sl_4: str = Field("4h", env="ATR_SL_4")
    risk_pct_1: float = Field(1.0, env="RISK_PCT_1")
    risk_pct_2: float = Field(3.0, env="RISK_PCT_2")
    risk_pct_3: float = Field(6.0, env="RISK_PCT_3")
    risk_pct_4: float = Field(9.0, env="RISK_PCT_4")
    risk_pct_default: float = Field(3.0, env="RISK_PCT_DEFAULT")
    atr_period: int = Field(
        14,
        env="ATR_PERIOD",
        description="ATR lookback window in candles.",
    )
    atr_multiplier: float = Field(
        1.5,
        env="ATR_MULTIPLIER",
        description="ATR multiplier applied when deriving stop offsets.",
    )
    ui_mock_mode_enabled: bool = Field(False, env="UI_MOCK_MODE_ENABLED")
    ui_mock_data_path: str = Field("spec/ui-whale-mock.json", env="UI_MOCK_DATA_PATH")

    @field_validator("apex_network")
    @classmethod
    def validate_network(cls, value: str) -> str:
        normalized = (value or "testnet").strip().lower()
        allowed = {"testnet", "base", "base-sepolia", "testnet-base", "mainnet"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported APEX_NETWORK '{value}'. Use one of {sorted(allowed)}")
        return normalized

    @field_validator("active_venue")
    @classmethod
    def validate_active_venue(cls, value: str) -> str:
        normalized = (value or "apex").strip().lower()
        allowed = {"apex", "hyperliquid"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported ACTIVE_VENUE '{value}'. Use one of {sorted(allowed)}")
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

    @field_validator("risk_pct_default")
    @classmethod
    def validate_risk_pct_default(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RISK_PCT_DEFAULT must be greater than zero")
        return value

    @field_validator("atr_timeframe", "atr_sl_1", "atr_sl_2", "atr_sl_3", "atr_sl_4")
    @classmethod
    def validate_atr_timeframe(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("ATR_TIMEFRAME must be a non-empty candle interval (e.g., 5m)")
        compact = normalized.lower()
        if re.fullmatch(r"\d+", compact):
            compact = f"{compact}m"
        if not re.fullmatch(r"\d+[mh]", compact):
            raise ValueError(
                "ATR_TIMEFRAME must include a unit suffix in minutes or hours (examples: 3m, 15m, 1h, 4h)"
            )
        return compact

    def atr_sl_timeframes(self) -> list[str]:
        ordered = [self.atr_sl_1, self.atr_sl_2, self.atr_sl_3, self.atr_sl_4]
        out: list[str] = []
        for tf in ordered:
            if tf and tf not in out:
                out.append(tf)
        return out

    def risk_pct_presets(self) -> list[float]:
        ordered = [self.risk_pct_1, self.risk_pct_2, self.risk_pct_3, self.risk_pct_4]
        out: list[float] = []
        for value in ordered:
            try:
                parsed = float(value)
            except Exception:
                continue
            if parsed > 0:
                out.append(parsed)
        return out or [1.0, 3.0, 6.0, 9.0]

    @field_validator(
        "apex_rest_timeout_seconds",
        "apex_rest_retries",
        "apex_rest_retry_backoff_seconds",
        "apex_rest_retry_backoff_max_seconds",
        "apex_rest_retry_jitter_seconds",
        "apex_positions_empty_stale_seconds",
        "apex_orders_empty_stale_seconds",
        "apex_reconcile_audit_interval_seconds",
        "apex_reconcile_stale_stream_seconds",
        "apex_reconcile_min_gap_seconds",
        "apex_reconcile_alert_window_seconds",
        "apex_reconcile_alert_max_per_window",
        "apex_poll_orders_interval_seconds",
        "apex_poll_positions_interval_seconds",
        "apex_poll_account_interval_seconds",
        "apex_local_hint_ttl_seconds",
        "apex_ws_price_stale_seconds",
        "hyperliquid_reconcile_audit_interval_seconds",
        "hyperliquid_reconcile_stale_stream_seconds",
        "hyperliquid_reconcile_order_timeout_seconds",
        "hyperliquid_reconcile_min_gap_seconds",
        "hyperliquid_reconcile_alert_window_seconds",
        "hyperliquid_reconcile_alert_max_per_window",
        "hyperliquid_order_timeout_alert_max_per_window",
    )
    @classmethod
    def validate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Timing and retry settings must be non-negative")
        return value


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()  # type: ignore[call-arg]


def get_log_level(default: Optional[str] = None) -> str:
    """Convenience accessor for log level with optional override."""
    settings = get_settings()
    return settings.log_level or (default or "INFO")
