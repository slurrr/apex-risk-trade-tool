import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_orders import router as orders_router
from backend.api.routes_positions import router as positions_router
from backend.api.routes_trade import configure_order_manager, router as trade_router
from backend.api.routes_stream import router as stream_router
from backend.core.config import get_settings
from backend.core.logging import init_logging
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.trading.order_manager import OrderManager


def create_app() -> FastAPI:
    settings = get_settings()
    init_logging(settings.log_level)

    gateway = ExchangeGateway(settings)
    order_manager = OrderManager(
        gateway,
        per_trade_risk_cap_pct=settings.per_trade_risk_cap_pct,
        daily_loss_cap_pct=settings.daily_loss_cap_pct,
        open_risk_cap_pct=settings.open_risk_cap_pct,
    )
    configure_order_manager(order_manager)

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

    @app.on_event("startup")
    async def startup_event() -> None:
        try:
            loop = asyncio.get_running_loop()
            gateway.attach_loop(loop)
            await gateway.load_configs()
            await order_manager.refresh_state()
            if settings.apex_enable_ws:
                await gateway.start_streams()
        except Exception:
            # Continue startup even if refresh fails; errors are logged
            pass

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(trade_router)
    app.include_router(orders_router)
    app.include_router(positions_router)
    app.include_router(stream_router)
    return app


app = create_app()
