# Decision Record: ApeX Reconcile Triggers + Data Sources

**ID**: 0005-reconcile-triggers-and-data-sources  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

Reconciliation exists to verify and recover from missed WS deltas or partial payloads, but must not become the primary mechanism for correctness. Hyperliquid introduced:
- reason-based triggers
- minimum gap anti-storming
- reason counters and alert windows

We want the same posture for ApeX, plus clarify the role of `/v3/history-orders`.

## Decision

### Triggers
Reconcile runs only when a named reason triggers it, and is subject to min-gap.

Initial reasons:
- `periodic_audit` (infrequent)
- `ws_stale` (no private WS events for threshold duration while open state exists)
- `ws_reconnect` (after reconnect/resubscribe)
- `tpsl_inconsistent` (positions exist but TP/SL map incomplete vs recent known good)
- `orders_empty_suspicious` / `positions_empty_suspicious`
- `user_requested` (optional)

### Anti-storm
- Enforce `APEX_RECONCILE_MIN_GAP_SECONDS` always.
- Track counters per reason and emit warnings when thresholds are exceeded (see SLO-F1).

### Data sources and authority
- **Primary**: private WS `ws_zk_accounts_v3` `orders` payload (`orders_raw`) for active TP/SL discovery.
- **Supplemental verification**: `GET /v3/history-orders` can be used to confirm lifecycle completion (post-fill/post-trigger) and to support authoritative removal decisions, but must not replace WS as primary for active target discovery.

## Options Considered

### Option A — Continuous reconcile loop (polling)
- Pros: “eventual truth” by brute force.
- Cons: noisy; becomes primary mechanism; increases load; still flaps.

### Option B — Reason-based reconcile + bounded verification (chosen)
- Pros: measurable; minimizes load; easier ops; aligns with HL patterns.
- Cons: requires careful reason selection and counters.

## Consequences

- Health snapshot must expose reconcile counters and reason counts.
- Alert thresholds become meaningful and can be tuned.

## Validation Plan

- WS healthy: reconcile stays within SLO-R1.
- WS stale/reconnect: reconcile triggers for the expected reason(s) and respects min-gap.
- TP/SL inconsistent sequence: reconcile triggers `tpsl_inconsistent` and recovers state without blanking UI.

