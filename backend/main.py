import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_orders import router as orders_router
from backend.api.routes_market import configure_order_manager as configure_market_manager, router as market_router
from backend.api.routes_positions import router as positions_router
from backend.api.routes_risk import configure_gateway as configure_risk_gateway, router as risk_router
from backend.api.routes_trade import configure_order_manager, router as trade_router
from backend.api.routes_stream import router as stream_router
from backend.api.routes_venue import configure_venue_controller, router as venue_router
from backend.api.errors import error_response
from backend.core.config import get_settings
from backend.core.logging import init_logging
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.exchange.hyperliquid_gateway import HyperliquidGateway
from backend.exchange.venue_controller import VenueController
from backend.trading.order_manager import OrderManager


def create_app() -> FastAPI:
    settings = get_settings()
    init_logging(settings.log_level)

    apex_gateway = ExchangeGateway(settings)
    hyperliquid_gateway = HyperliquidGateway(
        base_url=settings.hyperliquid_http_endpoint,
        user_address=settings.hl_user_address,
        agent_private_key=settings.hl_agent_private_key,
    )
    apex_order_manager = OrderManager(
        apex_gateway,
        per_trade_risk_cap_pct=settings.per_trade_risk_cap_pct,
        daily_loss_cap_pct=settings.daily_loss_cap_pct,
        open_risk_cap_pct=settings.open_risk_cap_pct,
        slippage_factor=settings.slippage_factor,
        fee_buffer_pct=settings.fee_buffer_pct,
    )
    hyperliquid_order_manager = OrderManager(
        hyperliquid_gateway,
        per_trade_risk_cap_pct=settings.per_trade_risk_cap_pct,
        daily_loss_cap_pct=settings.daily_loss_cap_pct,
        open_risk_cap_pct=settings.open_risk_cap_pct,
        slippage_factor=settings.slippage_factor,
        fee_buffer_pct=settings.fee_buffer_pct,
    )

    def apply_active(order_manager: OrderManager, gateway) -> None:
        configure_order_manager(order_manager)
        configure_market_manager(order_manager)
        configure_risk_gateway(gateway)

    venue_controller = VenueController(
        active_venue=settings.active_venue,
        gateways={"apex": apex_gateway, "hyperliquid": hyperliquid_gateway},
        managers={"apex": apex_order_manager, "hyperliquid": hyperliquid_order_manager},
        on_active_changed=apply_active,
        ws_enabled_by_venue={"apex": settings.apex_enable_ws, "hyperliquid": settings.hyperliquid_enable_ws},
    )
    venue_controller.bind_active_components()
    configure_venue_controller(venue_controller)

    app = FastAPI(
        title="ApeX Risk & Trade Sizing Tool",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def guard_switching_requests(request: Request, call_next):
        path = request.url.path or ""
        if venue_controller.switch_in_progress:
            is_mutating = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            protected = (
                path.startswith("/api/trade")
                or path.startswith("/api/orders")
                or path.startswith("/api/positions")
            )
            if is_mutating and protected:
                return error_response(
                    status_code=503,
                    code="venue_switch_in_progress",
                    detail="Venue switch in progress. Retry after switching completes.",
                )
        return await call_next(request)

    @app.on_event("startup")
    async def startup_event() -> None:
        try:
            loop = asyncio.get_running_loop()
            await venue_controller.startup(loop)
        except Exception:
            # Continue startup even if refresh fails; errors are logged
            pass

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(trade_router)
    app.include_router(orders_router)
    app.include_router(positions_router)
    app.include_router(market_router)
    app.include_router(stream_router)
    app.include_router(risk_router)
    app.include_router(venue_router)
    return app


app = create_app()
