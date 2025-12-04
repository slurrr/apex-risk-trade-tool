from typing import Optional

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


class AccountSummary(BaseModel):
    total_equity: float
    total_upnl: float
    available_margin: float
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
