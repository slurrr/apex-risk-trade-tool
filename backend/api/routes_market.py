from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.errors import error_response
from backend.core.logging import get_logger
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import DepthSummaryResponse, ErrorResponse

router = APIRouter(prefix="/api/market", tags=["market"])

_manager: OrderManager | None = None
logger = get_logger(__name__)


def configure_order_manager(manager: OrderManager) -> None:
    global _manager
    _manager = manager


def get_order_manager() -> OrderManager:
    if _manager is None:
        raise HTTPException(status_code=500, detail="Order manager not configured")
    return _manager


@router.get(
    "/depth-summary/{symbol}",
    response_model=DepthSummaryResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def depth_summary(
    symbol: str,
    tolerance_bps: int = Query(10),
    levels: int = Query(25),
    manager: OrderManager = Depends(get_order_manager),
):
    symbol_clean = (symbol or "").strip().upper()
    if not symbol_clean:
        return error_response(status_code=400, code="validation_error", detail="Symbol is required")
    if tolerance_bps not in {5, 10, 25}:
        return error_response(
            status_code=400,
            code="validation_error",
            detail="tolerance_bps must be one of 5, 10, 25",
        )
    safe_levels = max(5, min(int(levels), 200))
    try:
        summary = await manager.get_depth_summary(
            symbol=symbol_clean,
            tolerance_bps=tolerance_bps,
            levels=safe_levels,
        )
        levels_used = min(safe_levels, max(summary.get("bids_count", 0), summary.get("asks_count", 0)))
        return DepthSummaryResponse(
            symbol=symbol_clean,
            tolerance_bps=tolerance_bps,
            levels_used=levels_used,
            bid=summary.get("bid"),
            ask=summary.get("ask"),
            spread_bps=summary.get("spread_bps"),
            max_buy_notional=summary.get("max_buy_notional"),
            max_sell_notional=summary.get("max_sell_notional"),
            as_of=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError as exc:
        return error_response(status_code=400, code="liquidity_unavailable", detail=str(exc))
    except Exception as exc:
        logger.exception(
            "depth_summary_failed",
            extra={"event": "depth_summary_failed", "symbol": symbol_clean, "error": str(exc)},
        )
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch depth summary")
