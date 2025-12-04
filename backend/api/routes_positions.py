from fastapi import APIRouter, Depends

from backend.api.errors import error_response
from backend.api.routes_trade import get_order_manager
from backend.core.logging import get_logger
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import (
    ClosePositionRequest,
    ErrorResponse,
    PositionResponse,
    TargetsUpdateRequest,
)

router = APIRouter(prefix="/api", tags=["positions"])
logger = get_logger(__name__)


@router.get("/positions", response_model=list[PositionResponse], responses={500: {"model": ErrorResponse}})
async def list_positions(manager: OrderManager = Depends(get_order_manager)) -> list[dict]:
    """Return open positions from the gateway."""
    try:
        return await manager.list_positions()
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception("list_positions_failed", extra={"event": "list_positions_failed", "error": str(exc)})
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch positions")


@router.post(
    "/positions/{position_id}/close",
    responses={500: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def close_position(
    position_id: str, request: ClosePositionRequest, manager: OrderManager = Depends(get_order_manager)
) -> dict:
    """Close part or all of a position."""
    try:
        return await manager.close_position(
            position_id=position_id,
            close_percent=request.close_percent,
            close_type=request.close_type,
            limit_price=request.limit_price,
        )
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception(
            "close_position_failed",
            extra={
                "event": "close_position_failed",
                "position_id": position_id,
                "error": str(exc),
            },
        )
        return error_response(status_code=500, code="unexpected_error", detail="Unable to close position")


@router.post(
    "/positions/{position_id}/targets",
    responses={500: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def update_targets(
    position_id: str, request: TargetsUpdateRequest, manager: OrderManager = Depends(get_order_manager)
) -> dict:
    """Modify TP/SL targets for a position."""
    try:
        return await manager.modify_targets(
            position_id=position_id,
            take_profit=request.take_profit,
            stop_loss=request.stop_loss,
            clear_tp=request.clear_tp or False,
            clear_sl=request.clear_sl or False,
        )
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception(
            "update_targets_failed",
            extra={
                "event": "update_targets_failed",
                "position_id": position_id,
                "error": str(exc),
            },
        )
        return error_response(status_code=500, code="unexpected_error", detail="Unable to update targets")
