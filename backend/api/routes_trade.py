from fastapi import APIRouter, Depends, HTTPException

from backend.trading.order_manager import OrderManager
from backend.trading.schemas import ErrorResponse, TradePreviewResponse, TradeRequest

router = APIRouter(prefix="/api", tags=["trade"])

_manager: OrderManager | None = None


def configure_order_manager(manager: OrderManager) -> None:
    global _manager
    _manager = manager


def get_order_manager() -> OrderManager:
    if _manager is None:
        raise HTTPException(status_code=500, detail="Order manager not configured")
    return _manager


@router.post(
    "/trade",
    response_model=TradePreviewResponse,
    responses={400: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
async def trade(request: TradeRequest, manager: OrderManager = Depends(get_order_manager)):
    """Preview trade sizing; execution is added in a later phase."""
    if request.execute:
        raise HTTPException(status_code=501, detail="Execute flow not implemented yet")

    try:
        result, warnings = await manager.preview_trade(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            risk_pct=request.risk_pct,
            side=request.side,
            tp=request.tp,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TradePreviewResponse(
        side=result.side,
        size=result.size,
        notional=result.notional,
        estimated_loss=result.estimated_loss,
        warnings=warnings,
        entry_price=result.entry_price,
        stop_price=result.stop_price,
    )
