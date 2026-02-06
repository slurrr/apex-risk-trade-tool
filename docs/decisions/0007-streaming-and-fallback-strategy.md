# Decision Record: Streaming Strategy (WS-First) (Hyperliquid)

**ID**: 0007-streaming-and-fallback-strategy  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The app’s UI uses `/ws/stream` for live updates (orders, positions, account).

Hyperliquid parity requires:
- live-enough updates for a single operator
- robust behavior under WS disconnects
- correct TP/SL reconciliation signals

We must decide what is “authoritative” for Hyperliquid streaming during initial parity rollout.

## Decision

- Hyperliquid will use WS streaming as the primary and authoritative source for live monitor state in Phase 5.
- Source-of-truth policy:
  - WS topics feed caches and UI updates directly.
  - No automatic REST reconciliation fallback is required in the initial Hyperliquid rollout.
- Reconnect policy:
  - on WS disconnect, attempt reconnect with backoff
  - on reconnect, resubscribe to required topics and continue normal event processing
- Event normalization:
  - HL events will be mapped into the same message types the UI expects: `account`, `orders`, `orders_raw` (or equivalent), `positions`.
- Runtime assumption:
  - if WS is unavailable, monitoring quality degrades until WS is restored.

## Options Considered

### Option A — WS-only, no REST reconcile (chosen)
- Pros: lower REST load; simple update flow.
- Cons: temporary blind spots during outages until reconnect succeeds.

### Option B — REST polling only (no WS)
- Pros: simplest correctness story.
- Cons: worse UX; more load; slower target reconciliation; does not meet “full suite” parity goal.

### Option C — WS for latency + REST for authority (fallback)
- Pros: best balance; matches current ApeX approach; resilient.
- Cons: more moving parts; requires careful state merge logic.

## Consequences

- Need to define the minimal HL WS topic set for:
  - account updates (or periodic account refresh)
  - order updates/fills
  - position updates
  - mid/mark price updates (for PnL/price displays)

## Validation Plan

- Manual:
  - start with WS enabled; verify UI updates live
  - simulate WS disconnect; verify reconnect backoff/resubscribe and recovery when stream returns
- Integration:
  - log WS reconnect/resubscribe events and message flow recovery
- Regression:
  - switching venues stops old streams and prevents cross-venue event leakage
