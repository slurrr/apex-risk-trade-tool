import asyncio
import time
from typing import Any, Callable

from backend.core.logging import get_logger
from backend.trading.order_manager import OrderManager

logger = get_logger(__name__)


class VenueController:
    """Owns active venue state and coordinates safe switching."""

    def __init__(
        self,
        *,
        active_venue: str,
        gateways: dict[str, Any],
        managers: dict[str, OrderManager],
        on_active_changed: Callable[[OrderManager, Any], None],
        ws_enabled_by_venue: dict[str, bool],
    ) -> None:
        self._active_venue = active_venue
        self._gateways = gateways
        self._managers = managers
        self._on_active_changed = on_active_changed
        self._ws_enabled_by_venue = ws_enabled_by_venue
        self._switch_lock = asyncio.Lock()
        self._switch_in_progress = False

    @property
    def active_venue(self) -> str:
        return self._active_venue

    @property
    def switch_in_progress(self) -> bool:
        return self._switch_in_progress

    @property
    def active_gateway(self) -> Any:
        return self._gateways[self._active_venue]

    @property
    def active_manager(self) -> OrderManager:
        return self._managers[self._active_venue]

    def bind_active_components(self) -> None:
        self._on_active_changed(self.active_manager, self.active_gateway)

    async def startup(self, loop: asyncio.AbstractEventLoop) -> None:
        gateway = self.active_gateway
        gateway.attach_loop(loop)
        await gateway.load_configs()
        gateway.start_account_refresh(15)
        await self.active_manager.refresh_state()
        if self._ws_enabled_by_venue.get(self._active_venue, False):
            await gateway.start_streams()
        self.bind_active_components()

    async def switch_venue(self, target_venue: str) -> str:
        target = (target_venue or "").strip().lower()
        if target not in self._gateways:
            raise ValueError(f"Unsupported venue '{target_venue}'.")

        async with self._switch_lock:
            if target == self._active_venue:
                return self._active_venue

            old = self._active_venue
            started = time.perf_counter()
            self._switch_in_progress = True
            old_gateway = self._gateways[old]
            new_gateway = self._gateways[target]
            new_manager = self._managers[target]
            try:
                await old_gateway.stop_streams()
                old_gateway.clear_runtime_state()

                await new_gateway.load_configs()
                await new_manager.refresh_state()
                if self._ws_enabled_by_venue.get(target, False):
                    await new_gateway.start_streams()

                self._active_venue = target
                self.bind_active_components()
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                logger.info(
                    "venue_switch_success",
                    extra={"event": "venue_switch_success", "from_venue": old, "to_venue": target, "duration_ms": elapsed_ms},
                )
                return self._active_venue
            except Exception as exc:
                self._active_venue = old
                self.bind_active_components()
                if self._ws_enabled_by_venue.get(old, False):
                    try:
                        await old_gateway.start_streams()
                    except Exception:
                        pass
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                logger.exception(
                    "venue_switch_failed",
                    extra={
                        "event": "venue_switch_failed",
                        "from_venue": old,
                        "to_venue": target,
                        "duration_ms": elapsed_ms,
                        "error": str(exc),
                    },
                )
                raise
            finally:
                self._switch_in_progress = False
