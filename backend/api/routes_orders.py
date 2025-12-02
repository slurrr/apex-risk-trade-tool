from fastapi import APIRouter, Depends

from backend.api.errors import error_response
from backend.api.routes_trade import get_order_manager
from backend.core.logging import get_logger
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import ErrorResponse

router = APIRouter(prefix="/api", tags=["orders"])
logger = get_logger(__name__)


@router.get("/orders", responses={500: {"model": ErrorResponse}})
async def list_orders(manager: OrderManager = Depends(get_order_manager)) -> list:
    """Return open orders from the gateway."""
    try:
        return await manager.list_orders()
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception("list_orders_failed", extra={"event": "list_orders_failed", "error": str(exc)})
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch orders")


@router.post("/orders/{order_id}/cancel", responses={500: {"model": ErrorResponse}})
async def cancel_order(order_id: str, manager: OrderManager = Depends(get_order_manager)) -> dict:
    """Cancel an order and return status."""
    try:
        return await manager.cancel_order(order_id)
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception(
            "cancel_order_failed", extra={"event": "cancel_order_failed", "order_id": order_id, "error": str(exc)}
        )
        return error_response(status_code=500, code="unexpected_error", detail="Cancel request failed")
