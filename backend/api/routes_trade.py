from fastapi import APIRouter, Depends, HTTPException

from backend.api.errors import error_response
from backend.core.logging import get_logger
from backend.risk.risk_engine import PositionSizingError
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import ErrorResponse, TradePreviewResponse, TradeRequest

router = APIRouter(prefix="/api", tags=["trade"])

_manager: OrderManager | None = None
logger = get_logger(__name__)


def configure_order_manager(manager: OrderManager) -> None:
    global _manager
    _manager = manager


def get_order_manager() -> OrderManager:
    if _manager is None:
        raise HTTPException(status_code=500, detail="Order manager not configured")
    return _manager


@router.post(
    "/trade",
    response_model=None,
    responses={
        200: {"description": "Preview or execute trade"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def trade(request: TradeRequest, manager: OrderManager = Depends(get_order_manager)):
    """Preview trade sizing or execute when requested."""
    try:
        if request.execute:
            exec_result = await manager.execute_trade(
                symbol=request.symbol,
                entry_price=request.entry_price,
                stop_price=request.stop_price,
                risk_pct=request.risk_pct,
                side=request.side,
                tp=request.tp,
            )
            sizing = exec_result["sizing"]
            warnings = exec_result.get("warnings", [])
            return {
                "side": sizing.side,
                "size": sizing.size,
                "notional": sizing.notional,
                "estimated_loss": sizing.estimated_loss,
                "warnings": warnings,
                "entry_price": sizing.entry_price,
                "stop_price": sizing.stop_price,
                "executed": True,
                "exchange_order_id": exec_result["exchange_order_id"],
            }

        # Preview flow
        result, warnings = await manager.preview_trade(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            risk_pct=request.risk_pct,
            side=request.side,
            tp=request.tp,
        )
        return TradePreviewResponse(
            side=result.side,
            size=result.size,
            notional=result.notional,
            estimated_loss=result.estimated_loss,
            warnings=warnings,
            entry_price=result.entry_price,
            stop_price=result.stop_price,
        )
    except PositionSizingError as exc:
        logger.warning(
            "trade_validation_failed",
            extra={
                "event": "trade_validation_failed",
                "symbol": request.symbol,
                "execute": request.execute,
                "error": str(exc),
            },
        )
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except ValueError as exc:
        logger.warning(
            "trade_value_error",
            extra={
                "event": "trade_validation_failed",
                "symbol": request.symbol,
                "execute": request.execute,
                "error": str(exc),
            },
        )
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "trade_request_failed",
            extra={"event": "trade_request_failed", "symbol": request.symbol, "execute": request.execute},
        )
        return error_response(status_code=500, code="unexpected_error", detail="Unexpected error. Check server logs.")
