# Decision Record: ApeX TP/SL Authority + State Machine

**ID**: 0001-tpsl-authority-state-machine  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

We observed TP/SL “flapping” and occasional disappearance in ApeX UI state when upstream data sources are partial, delayed, or contradictory.

The app currently has multiple sources that influence displayed TP/SL:
- private WS `ws_zk_accounts_v3` account `orders` payload (`orders_raw`)
- REST snapshots (account/orders)
- optional REST order history (`/v3/history-orders`) which may surface TP/SL lifecycle fields after fill/trigger
- local “hints” (immediately after a successful `/api/positions/{id}/targets` call)

Without explicit precedence + tie-breakers + authoritative removal conditions, race conditions can still produce UI flapping.

## Decision

Implement and enforce an explicit TP/SL state machine per `symbol` (and target type TP vs SL).

### Source precedence (highest → lowest)
1) `local_hint` — immediately after a successful modify/clear request returns
2) `ws_orders_raw` — private WS account order payload; primary for active protection discovery
3) `rest_history` — `/v3/history-orders`; **supplemental verification only**, not primary discovery

### Freshness rules
- `local_hint` is provisional and must be confirmed by `ws_orders_raw` within **20 seconds** (default).
- If `ws_orders_raw` explicitly contradicts a fresh `local_hint`, **WS wins immediately** (do not wait for hint expiry).
  - Contradiction includes: a different TP/SL price, or confirmed absence of that target type in a full snapshot.

### Authoritative removal conditions (to clear TP/SL display)
TP or SL may be cleared (set to `None`) only if at least one holds:
- WS explicitly shows the relevant protective order is `canceled` / `filled` / `triggered`, OR
- A full WS snapshot confirms no active protective order of that type exists AND the last-known-good value is older than a **10 second** grace window, OR
- `/v3/history-orders` confirms lifecycle completion AND WS (if enabled) no longer shows an active protective order after a grace window.

### Tie-breaker rules
- If two sources provide conflicting non-empty values, select the higher-precedence source.
- If a tie-break is still required (same source family), prefer the newest exchange timestamp (`updatedAt`/`createdAt`) when present; otherwise use most recent `observed_at`.

## Options Considered

### Option A — “Last writer wins” (no precedence)
- Pros: simplest.
- Cons: flapping persists; contradictory updates overwrite stable state; poor UX.

### Option B — WS-only truth (ignore hints and history)
- Pros: simplest consistent truth.
- Cons: post-modify UX regresses (lag until WS confirms); WS gaps still cause blanking.

### Option C — Precedence + freshness + authoritative removal (chosen)
- Pros: robust under races; preserves usability; bounded behavior under partial snapshots.
- Cons: more logic; requires good health counters + tests.

## Consequences

- The system can no longer “blank” TP/SL purely due to missing data; it requires authoritative removal evidence.
- Additional observability is required:
  - `hint_unconfirmed` counters
  - “full snapshot” identification metrics
  - suspected flap counters

## Validation Plan

- Unit tests with recorded payload sequences:
  - partial snapshots that omit TP/SL orders
  - canceled-only pushes
  - contradictory hint vs WS updates
  - reconnect sequences
- Manual:
  - set TP/SL; observe immediate UI update (hint), then WS confirmation; no disappearance during WS jitter.

