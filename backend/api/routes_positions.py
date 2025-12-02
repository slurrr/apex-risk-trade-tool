from fastapi import APIRouter, Depends

from backend.api.errors import error_response
from backend.api.routes_trade import get_order_manager
from backend.core.logging import get_logger
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import ErrorResponse

router = APIRouter(prefix="/api", tags=["positions"])
logger = get_logger(__name__)


@router.get("/positions", responses={500: {"model": ErrorResponse}})
async def list_positions(manager: OrderManager = Depends(get_order_manager)) -> list:
    """Return open positions from the gateway."""
    try:
        return await manager.list_positions()
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception("list_positions_failed", extra={"event": "list_positions_failed", "error": str(exc)})
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch positions")
