# Decision Record: Idempotency & Retry Policy (Multi-Venue)

**ID**: 0005-idempotency-and-retry-policy  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The app has a “Preview” and “Execute” mode. Users can double-click “Place Order”, networks can drop, and APIs can time out. We must avoid duplicate orders and ensure predictable behavior across both venues.

Each venue has different notions of client order ids, dedupe windows, and error reporting. We need a unified app-level policy.

## Decision

- The backend will generate an application-level `client_order_id` for every execute attempt.
- The `client_order_id` will be passed to the venue if supported; otherwise it will be stored for local correlation.
- The backend will maintain an in-memory dedupe cache keyed by `(active_venue, client_order_id)` with a TTL (proposed: 10 minutes) to prevent duplicate submissions within a short window.
- Retry policy:
  - Do not automatically retry “unknown outcome” order submissions unless the venue provides a safe idempotency guarantee keyed on `client_order_id`.
  - For clearly transient network errors on **read** operations (symbols, prices, orders, positions), allow bounded retries with backoff (venue-specific).
  - For **write** operations (place/cancel/targets), prefer one-shot submission plus a follow-up “state reconcile” read rather than automatic retries.
- Error classification:
  - “validation / invalid payload” → do not retry; return 400.
  - “auth/signature/nonce” → do not retry automatically; return 401/503; log actionable hint.
  - “network timeout” on write → treat as unknown; trigger reconcile; return 502/503 with guidance.

## Options Considered

### Option A — Let UI handle idempotency (disable double-click etc.)
- Pros: reduces backend complexity.
- Cons: insufficient; network errors still cause duplicates; not trustworthy.

### Option B — Rely solely on venue idempotency
- Pros: clean if venue supports it.
- Cons: not uniform across venues; hard to reason about; risky if misconfigured.

### Option C — App-level idempotency + conservative retry (chosen)
- Pros: consistent cross-venue behavior; safer under uncertainty.
- Cons: in-memory TTL means dedupe resets on restart; acceptable for this MVP.

## Consequences

- Execute responses should return `client_order_id` for debugging (optional) but consider masking if it becomes sensitive.
- Reconciliation reads become important after timeouts to confirm whether an order exists.
- Future enhancement: persist dedupe keys to disk/redis if multi-instance deployment is needed.

## Validation Plan

- Unit test:
  - two execute calls with same `client_order_id` results in one submission attempt.
- Manual:
  - simulate slow network; click execute twice; verify only one order appears on venue.
- Integration:
  - instrument “unknown outcome” error path and ensure reconcile runs and UI sees eventual state.

