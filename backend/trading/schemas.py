from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator, validator


class TradeRequest(BaseModel):
    symbol: str
    entry_price: float = Field(..., gt=0)
    stop_price: float = Field(..., gt=0)
    risk_pct: float = Field(..., gt=0)
    side: Optional[str] = None
    tp: Optional[float] = Field(None, gt=0)
    preview: bool = True
    execute: bool = False

    @validator("side")
    def validate_side(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        side_upper = value.upper()
        if side_upper not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return side_upper


class TradePreviewResponse(BaseModel):
    side: str
    size: float
    notional: float
    estimated_loss: float
    warnings: list[str] = []
    entry_price: float
    stop_price: float


class TradeExecuteResponse(TradePreviewResponse):
    executed: bool = True
    exchange_order_id: str


class SymbolResponse(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    base_asset: Optional[str] = None
    quote_asset: Optional[str] = None
    status: Optional[str] = None
    tick_size: Optional[float] = Field(None, gt=0)
    step_size: Optional[float] = Field(None, gt=0)
    price_decimals: Optional[int] = Field(None, ge=0, le=12)
    size_decimals: Optional[int] = Field(None, ge=0, le=12)


class AccountSummary(BaseModel):
    total_equity: float
    total_upnl: float
    available_margin: float
    as_of: Optional[str] = None


class DepthSummaryResponse(BaseModel):
    symbol: str
    tolerance_bps: int
    levels_used: int
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_bps: Optional[float] = None
    max_buy_notional: Optional[float] = None
    max_sell_notional: Optional[float] = None
    as_of: Optional[str] = None


class OrderResponse(BaseModel):
    id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    size: Optional[float] = None
    entry_price: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


class PositionResponse(BaseModel):
    id: Optional[str] = None
    symbol: str
    side: str
    size: float
    entry_price: float
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    pnl: Optional[float] = None


class ClosePositionRequest(BaseModel):
    close_percent: float = Field(..., ge=0, le=100)
    close_type: str = Field(..., pattern="^(market|limit)$")
    limit_price: Optional[float] = Field(None, gt=0)

    @validator("close_type")
    def validate_close_type(cls, value: str) -> str:
        return value.lower()

    @validator("limit_price")
    def validate_limit_price(cls, value: Optional[float], values):
        close_type = values.get("close_type")
        if close_type == "limit" and value is None:
            raise ValueError("limit_price is required for limit close")
        return value


class TargetsUpdateRequest(BaseModel):
    take_profit: Optional[float] = Field(None, gt=0)
    stop_loss: Optional[float] = Field(None, gt=0)
    clear_tp: Optional[bool] = False
    clear_sl: Optional[bool] = False

    @model_validator(mode="after")
    def ensure_at_least_one(cls, values: "TargetsUpdateRequest"):
        if (
            values.take_profit is None
            and values.stop_loss is None
            and not values.clear_tp
            and not values.clear_sl
        ):
            raise ValueError("At least one of take_profit, stop_loss, clear_tp, or clear_sl must be provided")
        return values


class ErrorResponse(BaseModel):
    error: str
    detail: str
    context: Optional[dict] = None


class VenueStateResponse(BaseModel):
    active_venue: Literal["apex", "hyperliquid"]


class VenueSwitchRequest(BaseModel):
    active_venue: Literal["apex", "hyperliquid"]


class AtrStopRequest(BaseModel):
    symbol: str = Field(..., pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    side: Literal["long", "short"]
    entry_price: float = Field(..., gt=0)
    timeframe: Optional[str] = None

    @validator("symbol", pre=True)
    def normalize_symbol(cls, value: str) -> str:
        if not value:
            raise ValueError("symbol is required")
        return value.strip().upper()

    @validator("side", pre=True)
    def normalize_side(cls, value: str) -> str:
        if not value:
            raise ValueError("side is required")
        normalized = value.strip().lower()
        if normalized not in {"long", "short"}:
            if normalized in {"buy", "sell"}:
                normalized = "long" if normalized == "buy" else "short"
            else:
                raise ValueError("side must be 'long' or 'short'")
        return normalized

    @validator("timeframe", pre=True)
    def normalize_timeframe(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None


class AtrStopResponse(BaseModel):
    stop_loss_price: float = Field(..., gt=0)
    atr_value: float = Field(..., gt=0)
    multiplier: float = Field(..., gt=0)
    timeframe: str
    period: int
