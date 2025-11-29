from typing import Optional

from pydantic import BaseModel, Field, validator


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


class ErrorResponse(BaseModel):
    detail: str
