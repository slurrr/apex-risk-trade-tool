from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional, Tuple


TERMINAL_STATUSES = {
    "filled",
    "triggered",
    "canceled",
    "cancelled",
    "rejected",
    "expired",
    "failed",
    "closed",
    "done",
    "perpmarginrejected",
}


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def canonical_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "UNKNOWN"
    if raw in {"open", "new", "working", "resting", "pending", "partially_filled", "partiallyfilled"}:
        return "OPEN"
    if raw in {"filled"}:
        return "FILLED"
    if raw in {"triggered"}:
        return "TRIGGERED"
    if raw in {"canceled", "cancelled"} or "cancel" in raw:
        return "CANCELED"
    if raw in {"rejected"} or "reject" in raw:
        return "REJECTED"
    if raw in {"expired"} or "expire" in raw:
        return "CANCELED"
    if raw in {"failed", "error"}:
        return "REJECTED"
    return "OPEN"


def canonical_order_kind(raw: Any) -> str:
    text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    if "TAKE" in text and "PROFIT" in text:
        return "TAKE_PROFIT_MARKET"
    if text.startswith("STOP") or text.startswith("TRIGGER"):
        return "STOP_MARKET"
    if text.startswith("MARKET"):
        return "MARKET"
    if text.startswith("LIMIT"):
        return "LIMIT"
    if not text:
        return "UNKNOWN"
    return text


def build_canonical_order(
    order: Dict[str, Any],
    *,
    venue: str,
    source: str = "ws",
    observed_at_ms: Optional[int] = None,
) -> Dict[str, Any]:
    observed = int(observed_at_ms if observed_at_ms is not None else time.time() * 1000)
    order_type_raw = order.get("orderType")
    order_type_obj = order_type_raw if isinstance(order_type_raw, dict) else {}
    order_kind = canonical_order_kind(
        order.get("type") or order.get("orderType") or order.get("order_type")
    )
    trigger_price = _coerce_float(
        order.get("triggerPrice")
        or order.get("triggerPx")
        or order_type_obj.get("triggerPrice")
    )
    reduce_only = order.get("reduceOnly")
    if reduce_only is None:
        reduce_only = order.get("reduce_only")
    side = str(
        order.get("side") or order.get("positionSide") or order.get("direction") or ""
    ).upper() or None
    created_at = _coerce_int(
        order.get("createdAt")
        or order.get("createTime")
        or order.get("statusTimestamp")
        or order.get("timestamp")
        or order.get("created_at_ms")
    )
    updated_at = _coerce_int(
        order.get("updatedAt")
        or order.get("updateTime")
        or order.get("statusTimestamp")
        or order.get("updated_at_ms")
        or order.get("timestamp")
    )
    tpsl_kind: Optional[str] = None
    if order_kind.startswith("TAKE_PROFIT"):
        tpsl_kind = "tp"
    elif order_kind.startswith("STOP"):
        tpsl_kind = "sl"
    client_id = order.get("clientOrderId") or order.get("clientId") or order.get("client_id")
    order_id = (
        order.get("orderId")
        or order.get("order_id")
        or order.get("id")
        or order.get("_cache_id")
    )
    symbol = (
        order.get("symbol")
        or order.get("market")
        or order.get("pair")
        or ""
    )
    canonical = {
        "venue": (venue or "unknown").lower(),
        "source": source,
        "symbol": symbol,
        "order_id": str(order_id) if order_id is not None else None,
        "client_order_id": str(client_id) if client_id is not None else None,
        "parent_order_id": None,
        "side": side,
        "status": canonical_status(order.get("status") or order.get("state") or order.get("orderStatus")),
        "created_at_ms": created_at,
        "updated_at_ms": updated_at,
        "order_kind": order_kind,
        "reduce_only": bool(reduce_only) if reduce_only is not None else None,
        "size": _coerce_float(order.get("size") or order.get("qty") or order.get("quantity")),
        "filled_size": _coerce_float(
            order.get("cumFilledSize") or order.get("executedQty") or order.get("filled_size")
        ),
        "limit_price": _coerce_float(
            order.get("price")
            or order.get("limitPrice")
            or order.get("orderPrice")
            or order.get("entry_price")
            or order.get("entryPrice")
        ),
        "avg_price": _coerce_float(order.get("avgPrice") or order.get("avgFillPrice")),
        "trigger_price": trigger_price,
        "is_tpsl_flag": bool(order.get("isPositionTpsl")) if order.get("isPositionTpsl") is not None else None,
        "tpsl_kind": tpsl_kind,
        "evidence": {
            "raw_status": order.get("status") or order.get("state") or order.get("orderStatus"),
            "has_trigger_price": trigger_price is not None,
            "has_reduce_only": reduce_only is not None,
            "enriched_order_status": bool(order.get("__enriched_order_status")),
        },
        "raw": order,
        "observed_at_ms": observed,
    }
    return canonical


def _fallback_fingerprint(canonical: Dict[str, Any]) -> str:
    parts = [
        canonical.get("venue") or "",
        canonical.get("symbol") or "",
        canonical.get("side") or "",
        canonical.get("tpsl_kind") or "",
        f"{_coerce_float(canonical.get('trigger_price')) or 0.0:.10f}",
        f"{abs(_coerce_float(canonical.get('size')) or 0.0):.10f}",
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"fp:{digest}"


def canonical_order_key(canonical: Dict[str, Any]) -> str:
    if canonical.get("order_id"):
        return f"oid:{canonical['order_id']}"
    if canonical.get("client_order_id"):
        return f"cid:{canonical['client_order_id']}"
    return _fallback_fingerprint(canonical)


def is_terminal_canonical(canonical: Dict[str, Any]) -> bool:
    status = str(canonical.get("status") or "").strip().upper()
    return status in {"FILLED", "CANCELED", "REJECTED", "TRIGGERED"}


def classify_intent(
    canonical: Dict[str, Any],
    *,
    helper_hint: bool = False,
) -> Tuple[str, str, list[str]]:
    reasons: list[str] = []
    venue = str(canonical.get("venue") or "").lower()
    status = str(canonical.get("status") or "").upper()
    order_kind = str(canonical.get("order_kind") or "").upper()
    reduce_only = canonical.get("reduce_only")
    is_tpsl_flag = canonical.get("is_tpsl_flag")
    has_trigger = canonical.get("trigger_price") is not None
    client_order_id = canonical.get("client_order_id")

    if status in {"FILLED", "CANCELED", "REJECTED", "TRIGGERED"}:
        reasons.append("terminal_status")
        return "unknown", "low", reasons

    if bool(is_tpsl_flag):
        reasons.append("is_tpsl_flag")
        return "tpsl_helper", "high", reasons
    if order_kind.startswith(("STOP", "TAKE_PROFIT")):
        reasons.append("trigger_order_kind")
        if bool(reduce_only) or has_trigger:
            return "tpsl_helper", "high", reasons
        return "unknown", "medium", reasons
    if bool(reduce_only) and has_trigger:
        reasons.append("reduce_only_plus_trigger")
        return "tpsl_helper", "high", reasons
    if (
        venue == "hyperliquid"
        and bool(reduce_only)
        and order_kind in {"LIMIT", "MARKET"}
        and not has_trigger
        and not client_order_id
    ):
        # Ambiguous by shape alone: this can be either helper or discretionary
        # reduce-only close; require enrichment or local intent hint.
        reasons.append("hl_reduce_only_without_trigger_markers")
        if bool((canonical.get("evidence") or {}).get("enriched_order_status")):
            reasons.append("enriched_discretionary")
            return "discretionary", "medium", reasons
        return "unknown", "medium", reasons
    if helper_hint:
        reasons.append("helper_hint")
        return "tpsl_helper", "medium", reasons

    if order_kind in {"LIMIT", "MARKET"} and not bool(reduce_only):
        reasons.append("plain_discretionary_shape")
        return "discretionary", "high", reasons
    if order_kind in {"LIMIT", "MARKET"} and reduce_only is False:
        reasons.append("non_reduce_discretionary")
        return "discretionary", "high", reasons

    reasons.append("insufficient_evidence")
    return "unknown", "low", reasons
