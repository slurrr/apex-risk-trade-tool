from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders")
async def list_orders() -> list:
    """Placeholder orders endpoint."""
    return []


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict:
    """Placeholder cancel endpoint."""
    raise HTTPException(status_code=501, detail=f"Cancel not implemented for {order_id}")
