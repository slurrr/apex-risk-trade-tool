from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["positions"])


@router.get("/positions")
async def list_positions() -> list:
    """Placeholder positions endpoint."""
    return []
