# Decision Record: ApeX WS-Disabled Degraded Mode

**ID**: 0003-ws-disabled-degraded-mode  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

When ApeX WebSockets are disabled (`APEX_ENABLE_WS=false`) or unusable, the app must remain operational and predictable. “Degraded gracefully” must be defined so operators know what to expect.

## Decision

Define an explicit WS-disabled mode:

- `/ws/stream` remains the UI transport, but backend feeds it via periodic REST polling.
- Default poll cadence:
  - orders: **5s**
  - positions: **5s**
  - account: **15s**
- `/api/stream/health` must surface:
  - `ws_alive=false`
  - poll cadence fields (recommended)
- Entering WS-disabled mode must emit a structured warning log (rate-limited).
- TP/SL display must still follow the TP/SL state machine decision (retain last-known-good; never blank silently).

## Options Considered

### Option A — Disable streaming entirely when WS disabled
- Pros: simplest.
- Cons: breaks UI expectations; increases manual refresh reliance.

### Option B — REST polling feeds `/ws/stream` (chosen)
- Pros: keeps UI consistent; deterministic convergence.
- Cons: higher REST load; slower updates.

## Consequences

- REST load must be monitored; poll intervals may require tuning.
- Health snapshot becomes the operator’s primary indicator that they’re in degraded mode.

## Validation Plan

- Manual: run with `APEX_ENABLE_WS=false`; confirm UI updates without manual refresh at the stated cadences.
- Health: verify snapshot shows `ws_alive=false` and cadence fields.
- Ensure SLO-A2 degraded mode bound (≤ 10 seconds) is met.

