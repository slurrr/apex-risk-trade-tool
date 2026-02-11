import re
import time
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


def _timeframe_to_ms(timeframe: str) -> int:
    value = (timeframe or "").strip().lower()
    match = re.fullmatch(r"(\d+)([mh])", value)
    if not match:
        raise ValueError(f"Unsupported ATR timeframe '{timeframe}'.")
    qty = int(match.group(1))
    unit = match.group(2)
    base = 60_000 if unit == "m" else 3_600_000
    return qty * base


def _drop_incomplete_tail(candles: List[Any], timeframe: str) -> List[Any]:
    if not candles:
        return candles
    try:
        interval_ms = _timeframe_to_ms(timeframe)
    except ValueError:
        return candles
    last = candles[-1] if isinstance(candles[-1], dict) else None
    if not isinstance(last, dict):
        return candles
    open_ts = last.get("open_time") or last.get("openTime")
    try:
        open_ms = int(open_ts)
    except (TypeError, ValueError):
        return candles
    now_ms = int(time.time() * 1000)
    if open_ms + interval_ms > now_ms:
        return candles[:-1]
    return candles


def _atr_fetch_limit(gateway: ExchangeGateway, period: int, timeframe: str) -> int:
    base = max(period * 20, 200)
    venue = str(getattr(gateway, "venue", "") or "").strip().lower()
    # Apex REST kline endpoint is less tolerant to large windows, especially 3m->1m fallback.
    if venue == "apex":
        tf = (timeframe or "").strip().lower()
        if tf == "3m":
            return max(period * 3, period + 5)
        return min(120, base)
    return min(500, base)


def _configured_timeframes(settings) -> list[str]:
    configured = list(getattr(settings, "atr_sl_timeframes", lambda: [])() or [])
    return configured or ["3m", "15m", "1h", "4h"]


@router.get(
    "/atr-config",
    responses={500: {"model": ErrorResponse}},
)
async def atr_config():
    settings = get_settings()
    options = _configured_timeframes(settings)
    default_tf = settings.atr_timeframe if settings.atr_timeframe in options else options[0]
    return {
        "timeframes": options[:4],
        "default_timeframe": default_tf,
        "risk_presets": settings.risk_pct_presets()[:4],
        "period": settings.atr_period,
        "multiplier": settings.atr_multiplier,
    }


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
    configured_timeframes = _configured_timeframes(settings)
    allowed_timeframes = set(configured_timeframes)
    default_timeframe = config.timeframe if config.timeframe in allowed_timeframes else configured_timeframes[0]
    effective_timeframe = request.timeframe or default_timeframe
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

    # Use a deep warmup window so Wilder smoothing aligns more closely with chart ATR values.
    # Cap per venue where needed for endpoint stability.
    limit = _atr_fetch_limit(gateway, config.period, config.timeframe)
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

    candles = _drop_incomplete_tail(_sort_candles(candles), config.timeframe)
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
