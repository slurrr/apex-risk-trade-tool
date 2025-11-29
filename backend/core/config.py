from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables from .env if present
load_dotenv(ENV_PATH)


class Settings(BaseSettings):
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

    class Config:
        env_file = ENV_PATH
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()  # type: ignore[call-arg]


def get_log_level(default: Optional[str] = None) -> str:
    """Convenience accessor for log level with optional override."""
    settings = get_settings()
    return settings.log_level or (default or "INFO")
