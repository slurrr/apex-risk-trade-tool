import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.config import BASE_DIR, get_settings

_lock = threading.Lock()
_cache_path: Optional[Path] = None
_cache_mtime: Optional[float] = None
_cache_payload: Dict[str, Any] = {}


def is_ui_mock_enabled() -> bool:
    settings = get_settings()
    return bool(getattr(settings, "ui_mock_mode_enabled", False))


def _resolve_path() -> Path:
    settings = get_settings()
    raw = str(getattr(settings, "ui_mock_data_path", "spec/ui-whale-mock.json") or "").strip()
    if not raw:
        raw = "spec/ui-whale-mock.json"
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (BASE_DIR / candidate).resolve()


def _load_payload() -> Dict[str, Any]:
    global _cache_path, _cache_mtime, _cache_payload
    path = _resolve_path()
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = None
    with _lock:
        if _cache_path == path and _cache_mtime == mtime:
            return _cache_payload
        payload: Dict[str, Any] = {}
        if mtime is not None:
            try:
                with path.open("r", encoding="utf-8") as f:
                    parsed = json.load(f)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        _cache_path = path
        _cache_mtime = mtime
        _cache_payload = payload
        return payload


def _normalize_venue(venue: Optional[str]) -> str:
    clean = (venue or "").strip().lower()
    if clean in {"apex", "hyperliquid"}:
        return clean
    return "apex"


def get_ui_mock_section(venue: str, section: str, default: Any) -> Any:
    payload = _load_payload()
    venue_key = _normalize_venue(venue)
    venue_payload = payload.get(venue_key)
    if not isinstance(venue_payload, dict):
        return default
    value = venue_payload.get(section)
    if value is None:
        return default
    return value

