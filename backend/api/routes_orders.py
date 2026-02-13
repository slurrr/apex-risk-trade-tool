from fastapi import APIRouter, Depends

from backend.api.errors import error_response
from backend.api.routes_trade import get_order_manager
from backend.core.logging import get_logger
from backend.core.ui_mock import get_ui_mock_section, is_ui_mock_enabled
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import ErrorResponse, OrderResponse

router = APIRouter(prefix="/api", tags=["orders"])
logger = get_logger(__name__)


@router.get("/orders", response_model=list[OrderResponse], responses={500: {"model": ErrorResponse}})
async def list_orders(manager: OrderManager = Depends(get_order_manager)) -> list[dict]:
    """Return open orders from the gateway."""
    try:
        if is_ui_mock_enabled():
            venue = (getattr(manager.gateway, "venue", "apex") or "apex").lower()
            orders = get_ui_mock_section(venue, "orders", [])
            return orders if isinstance(orders, list) else []
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
        if is_ui_mock_enabled():
            return {"canceled": True, "order_id": order_id, "raw": {"status": "mock_canceled"}}
        return await manager.cancel_order(order_id)
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception(
            "cancel_order_failed", extra={"event": "cancel_order_failed", "order_id": order_id, "error": str(exc)}
        )
        return error_response(status_code=500, code="unexpected_error", detail="Cancel request failed")


@router.get("/orders/debug", responses={500: {"model": ErrorResponse}})
async def orders_debug(
    intent: str = "unknown",
    limit: int = 200,
    include_raw: bool = False,
    manager: OrderManager = Depends(get_order_manager),
) -> dict:
    """Debug endpoint for canonical order classification state."""
    try:
        if is_ui_mock_enabled():
            return {"orders": [], "meta": {"mode": "mock"}}
        return manager.get_orders_debug(intent=intent, limit=limit, include_raw=include_raw)
    except Exception as exc:
        logger.exception("orders_debug_failed", extra={"event": "orders_debug_failed", "error": str(exc)})
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch orders debug payload")
