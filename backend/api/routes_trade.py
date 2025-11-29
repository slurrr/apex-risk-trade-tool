from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["trade"])


@router.post("/trade")
async def trade() -> dict:
    """Placeholder trade endpoint; implementation arrives in US1/US2."""
    raise HTTPException(status_code=501, detail="Trade endpoint not implemented yet")
