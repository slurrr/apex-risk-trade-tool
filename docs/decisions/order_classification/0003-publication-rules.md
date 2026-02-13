# Decision Record: Publication Rules (Open Orders vs TP/SL vs Unknown)

**ID**: 0003-publication-rules  
**Date**: 2026-02-06  
**Status**: Accepted  
**Owners**: Backend team  

## Context

Even perfect classification can be undermined if we publish the wrong payload to the wrong UI stream. We need explicit rules for:
- what goes to Open Orders
- what feeds TP/SL on positions
- what happens to unknowns

## Decision

- `orders_raw` is the authoritative event for classification and TP/SL derivation.
- Open Orders stream and `/api/orders` return **only** `intent=discretionary`.
- TP/SL representation for positions uses **only** `intent=tpsl_helper` plus local hints until confirmed.
- Unknown orders are never shown as normal open orders under normal conditions, but they MUST NOT be silently hidden without an operator escape hatch.

### Mandatory unknown escalation policy

- Track unknown counters in health (count, rate, persistence age).
- If unknown thresholds are exceeded, trigger bounded recovery actions (WS resubscribe, then one bounded REST snapshot if needed).
- If `ORDER_CLASSIFICATION_MODE=v2` and unknown escalation persists after recovery, automatically switch the **effective** classification mode to `shadow`:
  - auto-switch duration: 10 minutes
  - cooldown: 30 minutes before another auto-switch can trigger
  - continue computing v2 classification/counters for debugging, but publish legacy outputs while in auto-shadow
- Provide a debug endpoint contract:
  - `GET /api/orders/debug?intent=unknown&limit=200` returns unknown canonical orders + meta counters.

## Options Considered

### Option A — Publish everything and let UI filter
- Pros: simplest backend.
- Cons: leaks helpers; inconsistent UX; duplicates logic.

### Option B — Backend publishes canonical, intent-filtered streams (chosen)
- Pros: stable UI; single source-of-truth; less frontend complexity.
- Cons: requires canonical stream plumbing.

## Consequences

- A small debug pathway may be needed to investigate unknowns without polluting main UI.

## Validation Plan

- Automated regression: helper orders never appear in Open Orders table under replayed WS sequences.
