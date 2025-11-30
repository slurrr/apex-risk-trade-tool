from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes_trade import get_order_manager
from backend.trading.order_manager import OrderManager

router = APIRouter(prefix="/api", tags=["positions"])


@router.get("/positions")
async def list_positions(manager: OrderManager = Depends(get_order_manager)) -> list:
    """Return open positions from the gateway."""
    try:
        return await manager.list_positions()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
