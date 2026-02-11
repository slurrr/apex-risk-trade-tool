from fastapi import APIRouter, Depends

from backend.api.errors import error_response
from backend.api.routes_trade import get_order_manager
from backend.core.logging import get_logger
from backend.core.ui_mock import get_ui_mock_section, is_ui_mock_enabled
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
async def list_positions(
    resync: bool = False, manager: OrderManager = Depends(get_order_manager)
) -> list[dict]:
    """Return open positions from the gateway."""
    try:
        if is_ui_mock_enabled():
            venue = (getattr(manager.gateway, "venue", "apex") or "apex").lower()
            positions = get_ui_mock_section(venue, "positions", [])
            return positions if isinstance(positions, list) else []
        if resync:
            ok = await manager.resync_tpsl_from_account()
            if not ok:
                logger.warning(
                    "positions_resync_failed",
                    extra={"event": "positions_resync_failed"},
                )
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
        if is_ui_mock_enabled():
            return {
                "position_id": position_id,
                "requested_percent": request.close_percent,
                "close_size": None,
                "exchange": {"status": "mock_closed"},
            }
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
        if is_ui_mock_enabled():
            return {
                "position_id": position_id,
                "take_profit": request.take_profit,
                "stop_loss": request.stop_loss,
                "clear_tp": bool(request.clear_tp),
                "clear_sl": bool(request.clear_sl),
                "status": "mock_updated",
            }
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
