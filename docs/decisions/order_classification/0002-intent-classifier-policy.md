# Decision Record: Shared Intent Classifier Policy

**ID**: 0002-intent-classifier-policy  
**Date**: 2026-02-06  
**Status**: Accepted  
**Owners**: Backend team  

## Context

Discretionary vs TP/SL helper orders must be separated reliably across venues even when WS rows are transiently missing fields. The system must avoid:
- helper orders leaking into Open Orders
- TP/SL state failing to update on positions
- flapping due to contradictory sources

## Decision

Implement a single shared classifier producing `OrderIntent`:
- `discretionary`
- `tpsl_helper`
- `unknown`

Policy:
- Run classification on `orders_raw` as the authoritative input.
- Use multiple signals (flags + order kind + trigger + reduce-only + timestamps).
- Maintain local hint store (TTL default 20s) to resolve ambiguity when WS rows are incomplete.
  - Prefer `order_id` when present (Hyperliquid `oid` is the primary stable identifier).
  - Use `client_order_id` when present, but do not assume it exists for HL helper legs across the full lifecycle.
  - Use a strict-TTL fallback fingerprint for brief missing-marker windows: `(venue, symbol, side, tpsl_kind_if_known, trigger_price≈, size≈)`.
- Unknowns are hidden from Open Orders by default and do not clear TP/SL.

## Options Considered

### Option A — Trust one field (e.g., `reduceOnly` or `isPositionTpsl`)
- Pros: simple.
- Cons: fails under transient missing markers; causes observed issues.

### Option B — Multi-signal classifier + hint-assisted resolution (chosen)
- Pros: robust; testable; clean UI; supports more venues.
- Cons: requires hint plumbing and counters.

## Consequences

- Requires observability counters for unknown/hint usage.
- Requires clear tie-break rules when conflicting signals occur.

## Validation Plan

- Unit tests with recorded sequences including missing markers windows.
- Ensure “unknown never shown as open order” invariant holds.
