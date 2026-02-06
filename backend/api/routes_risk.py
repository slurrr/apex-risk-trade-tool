from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException

from backend.api.errors import error_response
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.risk.atr import AtrConfig, calculate_atr, compute_configured_stop, config_from_settings
from backend.trading.schemas import AtrStopRequest, AtrStopResponse, ErrorResponse

router = APIRouter(prefix="/risk", tags=["risk"])

logger = get_logger(__name__)
_gateway: ExchangeGateway | None = None


def configure_gateway(gateway: ExchangeGateway) -> None:
    global _gateway
    _gateway = gateway


def get_gateway() -> ExchangeGateway:
    if _gateway is None:
        raise HTTPException(status_code=500, detail="Risk gateway not configured")
    return _gateway


def _sort_candles(candles: List[Any]) -> List[Any]:
    try:
        return sorted(candles, key=lambda c: (c or {}).get("open_time") or (c or {}).get("openTime") or 0)
    except Exception:
        return candles


@router.post(
    "/atr-stop",
    response_model=AtrStopResponse,
    responses={
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def atr_stop(
    request: AtrStopRequest, gateway: ExchangeGateway = Depends(get_gateway)
):
    settings = get_settings()
    config: AtrConfig = config_from_settings(settings)
    effective_timeframe = request.timeframe or config.timeframe
    allowed_timeframes = {"3m", "15m", "1h", "4h", config.timeframe}
    if effective_timeframe not in allowed_timeframes:
        return error_response(
            status_code=400,
            code="validation_error",
            detail=f"Unsupported ATR timeframe '{effective_timeframe}'.",
            context={"allowed": sorted(allowed_timeframes)},
        )
    config = AtrConfig(
        timeframe=effective_timeframe,
        period=config.period,
        multiplier=config.multiplier,
    )

    limit = max(config.period * 3, config.period + 5)
    try:
        candles = await gateway.fetch_klines(
            request.symbol,
            config.timeframe,
            limit,
        )
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        logger.warning(
            "atr_klines_fetch_failed",
            extra={"event": "atr_klines_fetch_failed", "symbol": request.symbol, "error": str(exc)},
        )
        return error_response(
            status_code=503,
            code="atr_data_unavailable",
            detail="Unable to fetch ATR data. Please retry shortly.",
            context={
                "symbol": request.symbol,
                "timeframe": config.timeframe,
                "reason": "fetch_failed",
            },
        )

    candles = _sort_candles(candles)
    available_candles = len(candles)
    if available_candles == 0:
        return error_response(
            status_code=503,
            code="atr_history_unavailable",
            detail="Market data unavailable for ATR calculation. Enter a stop price manually.",
            context={
                "symbol": request.symbol,
                "timeframe": config.timeframe,
                "required_candles": config.period,
                "available_candles": available_candles,
            },
        )
    if available_candles < config.period:
        return error_response(
            status_code=503,
            code="atr_insufficient_history",
            detail=f"ATR requires {config.period} candles but only {available_candles} are available.",
            context={
                "symbol": request.symbol,
                "timeframe": config.timeframe,
                "required_candles": config.period,
                "available_candles": available_candles,
            },
        )

    atr_value = calculate_atr(request.symbol, config.timeframe, candles, config.period)
    if atr_value is None:
        return error_response(
            status_code=503,
            code="atr_unavailable",
            detail="ATR calculation unavailable for the selected symbol/timeframe.",
            context={
                "symbol": request.symbol,
                "timeframe": config.timeframe,
                "period": config.period,
                "available_candles": available_candles,
            },
        )

    result = compute_configured_stop(
        request.symbol,
        request.side,
        request.entry_price,
        atr_value,
        config,
    )
    if result is None:
        return error_response(
            status_code=400,
            code="stop_unavailable",
            detail="Unable to derive a stop price for the provided entry price.",
        )

    # logger.info(
    #     "atr_stop_computed",
    #     extra={
    #         "event": "atr_stop_computed",
    #         "symbol": request.symbol,
    #         "side": request.side,
    #         "entry": request.entry_price,
    #         "atr": atr_value,
    #         "timeframe": config.timeframe,
    #         "period": config.period,
    #     },
    # )

    return AtrStopResponse(
        stop_loss_price=result.stop_price,
        atr_value=result.atr_value,
        multiplier=result.config.multiplier,
        timeframe=result.config.timeframe,
        period=result.config.period,
    )
