from fastapi import FastAPI

from backend.api.routes_orders import router as orders_router
from backend.api.routes_positions import router as positions_router
from backend.api.routes_trade import configure_order_manager, router as trade_router
from backend.core.config import get_settings
from backend.core.logging import init_logging
from backend.exchange.exchange_gateway import ExchangeGateway
from backend.trading.order_manager import OrderManager


def create_app() -> FastAPI:
    settings = get_settings()
    init_logging(settings.log_level)

    gateway = ExchangeGateway(settings)
    order_manager = OrderManager(gateway)
    configure_order_manager(order_manager)

    app = FastAPI(
        title="ApeX Risk & Trade Sizing Tool",
        version="0.1.0",
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(trade_router)
    app.include_router(orders_router)
    app.include_router(positions_router)
    return app


app = create_app()
