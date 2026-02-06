from fastapi import APIRouter, HTTPException

from backend.api.errors import error_response
from backend.exchange.venue_controller import VenueController
from backend.trading.schemas import ErrorResponse, VenueStateResponse, VenueSwitchRequest

router = APIRouter(prefix="/api", tags=["venue"])

_controller: VenueController | None = None


def configure_venue_controller(controller: VenueController) -> None:
    global _controller
    _controller = controller


def get_venue_controller() -> VenueController:
    if _controller is None:
        raise HTTPException(status_code=500, detail="Venue controller not configured")
    return _controller


@router.get("/venue", response_model=VenueStateResponse, responses={500: {"model": ErrorResponse}})
async def get_venue() -> VenueStateResponse:
    controller = get_venue_controller()
    return VenueStateResponse(active_venue=controller.active_venue)


@router.post("/venue", response_model=VenueStateResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def set_venue(request: VenueSwitchRequest):
    controller = get_venue_controller()
    try:
        active = await controller.switch_venue(request.active_venue)
        return VenueStateResponse(active_venue=active)
    except ValueError as exc:
        return error_response(status_code=400, code="validation_error", detail=str(exc))
    except Exception as exc:
        return error_response(
            status_code=500,
            code="venue_switch_failed",
            detail="Unable to switch venue.",
            context={"requested_venue": request.active_venue, "reason": str(exc)},
        )
