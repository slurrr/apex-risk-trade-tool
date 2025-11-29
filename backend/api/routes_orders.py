from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders")
async def list_orders() -> list:
    """Placeholder orders endpoint."""
    return []


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict:
    """Placeholder cancel endpoint."""
    return {"canceled": False, "order_id": order_id}
