from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


def error_response(
    *,
    status_code: int,
    code: str,
    detail: str,
    context: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Return a consistent error payload for API responses."""
    payload: Dict[str, Any] = {"error": code, "detail": detail}
    if context:
        payload["context"] = context
    return JSONResponse(status_code=status_code, content=payload)
