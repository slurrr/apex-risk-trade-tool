import time

from fastapi import APIRouter, Depends, HTTPException

from backend.api.errors import error_response
from backend.core.logging import get_logger
from backend.core.ui_mock import get_ui_mock_section, is_ui_mock_enabled
from backend.risk.risk_engine import PositionSizingError
from backend.trading.order_manager import OrderManager
from backend.trading.schemas import (
    AccountSummary,
    ErrorResponse,
    SymbolResponse,
    TradePreviewResponse,
    TradeRequest,
)

router = APIRouter(prefix="/api", tags=["trade"])

_manager: OrderManager | None = None
logger = get_logger(__name__)
trade_audit_logger = get_logger("audit.trade")


def _audit_trade(event: str, **extra) -> None:
    trade_audit_logger.info(event, extra={"event": event, **extra})


def _active_venue(manager: OrderManager) -> str:
    return (getattr(manager.gateway, "venue", "apex") or "apex").lower()


def configure_order_manager(manager: OrderManager) -> None:
    global _manager
    _manager = manager


def get_order_manager() -> OrderManager:
    if _manager is None:
        raise HTTPException(status_code=500, detail="Order manager not configured")
    return _manager


@router.get("/symbols", response_model=list[SymbolResponse], responses={500: {"model": ErrorResponse}})
async def list_symbols(manager: OrderManager = Depends(get_order_manager)):
    """Return catalog of tradeable symbols for dropdowns."""
    try:
        if is_ui_mock_enabled():
            venue = _active_venue(manager)
            return get_ui_mock_section(venue, "symbols", [])
        return await manager.list_symbols()
    except Exception as exc:
        logger.exception("list_symbols_failed", extra={"event": "list_symbols_failed", "error": str(exc)})
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch symbols")


@router.get("/account/summary", response_model=AccountSummary, responses={500: {"model": ErrorResponse}})
async def account_summary(manager: OrderManager = Depends(get_order_manager)):
    """Return account summary for UI header."""
    try:
        if is_ui_mock_enabled():
            venue = _active_venue(manager)
            summary = get_ui_mock_section(venue, "account_summary", {})
            if isinstance(summary, dict):
                payload = dict(summary)
                payload.setdefault("venue", venue)
                return payload
            return {"total_equity": 0.0, "total_upnl": 0.0, "available_margin": 0.0, "venue": venue}
        return await manager.get_account_summary()
    except Exception as exc:
        logger.exception("account_summary_failed", extra={"event": "account_summary_failed", "error": str(exc)})
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch account summary")


@router.get("/price/{symbol}", responses={500: {"model": ErrorResponse}})
async def symbol_price(symbol: str, manager: OrderManager = Depends(get_order_manager)):
    """Return latest price for symbol (best-effort)."""
    try:
        if is_ui_mock_enabled():
            venue = _active_venue(manager)
            prices = get_ui_mock_section(venue, "prices", {})
            if isinstance(prices, dict):
                raw = prices.get(symbol.upper())
                try:
                    return {"symbol": symbol.upper(), "price": float(raw)}
                except Exception:
                    pass
            return {"symbol": symbol.upper(), "price": 0.0}
        return await manager.get_symbol_price(symbol)
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.exception(
            "symbol_price_failed",
            extra={
                "event": "symbol_price_failed",
                "symbol": symbol,
                "error": str(exc),
            },
        )
        return error_response(status_code=500, code="unexpected_error", detail="Unable to fetch symbol price")


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
    trace_id = request.trace_id or f"srv-{int(time.time() * 1000)}"
    try:
        _audit_trade(
            "trade_request_received",
            trace_id=trace_id,
            execute=bool(request.execute),
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            requested_side=request.side,
            risk_pct=request.risk_pct,
            tp=request.tp,
            venue=_active_venue(manager),
        )
        if is_ui_mock_enabled():
            side = (request.side or "").upper().strip()
            if side not in {"BUY", "SELL"}:
                side = "BUY" if request.stop_price < request.entry_price else "SELL"
            per_unit = abs(float(request.entry_price) - float(request.stop_price))
            size = max(1.0, round(float(request.risk_pct or 1.0) * 120.0, 3))
            notional = float(size * float(request.entry_price))
            estimated_loss = float(size * per_unit)
            payload = {
                "side": side,
                "size": size,
                "notional": notional,
                "estimated_loss": estimated_loss,
                "warnings": [],
                "entry_price": float(request.entry_price),
                "stop_price": float(request.stop_price),
                "trace_id": trace_id,
            }
            if request.execute:
                payload["executed"] = True
                payload["exchange_order_id"] = f"MOCK-{int(time.time() * 1000)}"
            return payload
        if request.execute:
            exec_result = await manager.execute_trade(
                symbol=request.symbol,
                entry_price=request.entry_price,
                stop_price=request.stop_price,
                risk_pct=request.risk_pct,
                side=request.side,
                tp=request.tp,
                trace_id=trace_id,
            )
            sizing = exec_result["sizing"]
            warnings = exec_result.get("warnings", [])
            _audit_trade(
                "trade_submit_result",
                trace_id=trace_id,
                symbol=request.symbol,
                requested_side=request.side,
                resolved_side=sizing.side,
                size=sizing.size,
                notional=sizing.notional,
                estimated_loss=sizing.estimated_loss,
                exchange_order_id=exec_result.get("exchange_order_id"),
                warning_count=len(warnings),
                venue=_active_venue(manager),
            )
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
                "trace_id": trace_id,
            }

        # Preview flow
        result, warnings = await manager.preview_trade(
            symbol=request.symbol,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            risk_pct=request.risk_pct,
            side=request.side,
            tp=request.tp,
            trace_id=trace_id,
        )
        _audit_trade(
            "trade_preview_result",
            trace_id=trace_id,
            symbol=request.symbol,
            requested_side=request.side,
            resolved_side=result.side,
            size=result.size,
            notional=result.notional,
            estimated_loss=result.estimated_loss,
            warning_count=len(warnings),
            venue=_active_venue(manager),
        )
        return TradePreviewResponse(
            side=result.side,
            size=result.size,
            notional=result.notional,
            estimated_loss=result.estimated_loss,
            warnings=warnings,
            entry_price=result.entry_price,
            stop_price=result.stop_price,
            trace_id=trace_id,
        )
    except PositionSizingError as exc:
        _audit_trade(
            "trade_submit_failed",
            trace_id=trace_id,
            symbol=request.symbol,
            execute=bool(request.execute),
            error=str(exc),
            error_type="PositionSizingError",
            venue=_active_venue(manager),
        )
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
        _audit_trade(
            "trade_submit_failed",
            trace_id=trace_id,
            symbol=request.symbol,
            execute=bool(request.execute),
            error=str(exc),
            error_type="ValueError",
            venue=_active_venue(manager),
        )
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
        _audit_trade(
            "trade_submit_failed",
            trace_id=trace_id,
            symbol=request.symbol,
            execute=bool(request.execute),
            error=str(exc),
            error_type=type(exc).__name__,
            venue=_active_venue(manager),
        )
        logger.exception(
            "trade_request_failed",
            extra={"event": "trade_request_failed", "symbol": request.symbol, "execute": request.execute},
        )
        return error_response(status_code=500, code="unexpected_error", detail="Unexpected error. Check server logs.")
