from fastapi import APIRouter, Depends, HTTPException

from backend.api.routes_trade import get_order_manager
from backend.trading.order_manager import OrderManager

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders")
async def list_orders(manager: OrderManager = Depends(get_order_manager)) -> list:
    """Return open orders from the gateway."""
    try:
        return await manager.list_orders()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, manager: OrderManager = Depends(get_order_manager)) -> dict:
    """Cancel an order and return status."""
    try:
        return await manager.cancel_order(order_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
