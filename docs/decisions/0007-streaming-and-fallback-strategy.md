# Decision Record: Streaming Strategy & REST Fallback (Hyperliquid)

**ID**: 0007-streaming-and-fallback-strategy  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The app’s UI uses `/ws/stream` for live updates (orders, positions, account). ApeX support already uses WS feeds with REST fallback.

Hyperliquid parity requires:
- live-enough updates for a single operator
- robust behavior under WS disconnects
- correct TP/SL reconciliation signals

We must decide what is “authoritative” (WS vs REST) and how to converge state.

## Decision

- Hyperliquid will support WS streaming in Phase 5, but correctness must not depend solely on WS.
- Source-of-truth policy:
  - WS is used to keep caches “hot” and drive UI updates quickly.
  - REST snapshots are used as the authoritative fallback for reconciliation, especially after disconnects or on-demand resync.
- Reconnect policy:
  - on WS disconnect, attempt reconnect with backoff
  - on reconnect, resubscribe and then trigger a REST snapshot refresh to reconcile state
- Event normalization:
  - HL events will be mapped into the same message types the UI expects: `account`, `orders`, `orders_raw` (or equivalent), `positions`.
- Minimum fallback guarantee:
  - if WS is disabled/unavailable, periodic REST refresh (or manual refresh endpoints) still provides correct orders/positions/account state.

## Options Considered

### Option A — WS-only, no REST reconcile (chosen)
- Pros: lower REST load; simple update flow.
- Cons: incorrect under disconnects; poor reliability; not acceptable for trading ops.

### Option B — REST polling only (no WS)
- Pros: simplest correctness story.
- Cons: worse UX; more load; slower target reconciliation; does not meet “full suite” parity goal.

### Option C — WS for latency + REST for authority (fallback)
- Pros: best balance; matches current ApeX approach; resilient.
- Cons: more moving parts; requires careful state merge logic.

## Consequences

- Need explicit resync hooks after reconnects and on suspicious gaps.
- Need to define the minimal HL WS topic set for:
  - account updates (or periodic account refresh)
  - order updates/fills
  - position updates
  - mid/mark price updates (for PnL/price displays)

## Validation Plan

- Manual:
  - start with WS enabled; verify UI updates live
  - simulate WS disconnect; verify UI continues to work with REST refresh and resync after reconnect
- Integration:
  - log WS reconnect events and ensure a REST reconciliation is triggered
- Regression:
  - switching venues stops old streams and prevents cross-venue event leakage

