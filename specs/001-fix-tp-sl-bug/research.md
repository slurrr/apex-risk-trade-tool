# Phase 0 Research

## Source of truth for TP/SL
Decision: Use the ApeX account WebSocket stream (`ws_zk_accounts_v3`) as the primary source of truth for untriggered TP/SL orders, with REST fallbacks only when the stream is unavailable.  
Rationale: The account stream exposes isPositionTpsl orders, STOP_* and TAKE_PROFIT_* types that never appear in standard REST lists for untriggered orders, and it is already being cached for the UI; treating it as primary avoids races and missing protections.  
Alternatives considered: Rely solely on REST `get_open_orders` responses (cannot see untriggered TP/SL), or poll additional REST endpoints on every refresh (higher latency and risk of inconsistency relative to the streaming account view).

## Mapping TP/SL orders to positions
Decision: Build a symbol-keyed map of TP and SL targets from untriggered isPositionTpsl orders, assuming at most one open position per symbol, and merge this map into normalized positions before computing PnL and returning `/api/positions`.  
Rationale: The one-position-per-symbol invariant makes symbol-level mapping sufficient, avoids brittle client-order-id joins, and aligns with how the UI presents positions; merging server-side keeps the API contract simple for the frontend.  
Alternatives considered: Track TP/SL purely in the UI layer (would desync from exchange state), or introduce a separate TP/SL table keyed by internal IDs (adds storage and complexity without clear benefit under the one-position-per-symbol constraint).

## Handling multiple TP/SL orders per type
Decision: For each symbol, keep at most one active TP and one active SL in the TP/SL map by selecting the most recent untriggered order per type from the account stream and cancelling older untriggered isPositionTpsl orders of the same type when a new TP or SL is submitted.  
Rationale: This preserves a clear “single source of truth” per protection type for both UI and risk reasoning, and ensures the exchange only has the latest intended TP or SL while avoiding ambiguity about which order will fire.  
Alternatives considered: Allow multiple concurrent TP or SL orders and surface them all (confusing in the UI and riskier to reason about), or silently ignore older orders without cancelling (leaves unexpected protections live on the exchange).

## Semantics of modifying vs clearing TP/SL
Decision: Treat “modify” as either setting a new TP/SL or explicitly clearing one or both protections, using a request shape where omitted fields leave existing targets unchanged and explicit clear flags or actions remove the corresponding protection.  
Rationale: This matches trader expectations: updating only TP must not affect SL, and vice versa; clearing must be deliberate and visible rather than inferred from empty inputs, reducing accidental loss of protection.  
Alternatives considered: Require both TP and SL on every update (blocks partial adjustments), or interpret empty fields as “clear” (too easy to accidentally drop protections during routine edits).

## UI behaviour for missing or stale TP/SL data
Decision: Preserve the last known good TP/SL values in the Positions UI when a transient snapshot or reconnect lacks TP/SL orders, and only show “TP: None, SL: None” when the system has high confidence that no active protections exist for that position.  
Rationale: This avoids misleading traders during short-lived data gaps and keeps the UI aligned with the last confirmed protective state until the stream or fallback reconciliation proves otherwise.  
Alternatives considered: Reset TP/SL display to “None” any time a snapshot omits orders (caused the current regression), or block the positions view entirely on missing TP/SL (harms usability more than it helps safety).

