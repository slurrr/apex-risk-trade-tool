# Decision Record: Open Orders vs TP/SL Helpers (ApeX)

**ID**: 0004-open-orders-vs-tpsl-helpers  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

To improve clarity and avoid UX confusion, we must keep “open entry orders” separate from “protective TP/SL helper orders.” Mixing them leads to:
- open orders table noise
- incorrect cancel targeting
- TP/SL state flapping if the wrong payload is treated as the open orders feed

Hyperliquid integration established the convention that TP/SL helper orders do not appear in the Open Orders table.

## Decision

- TP/SL helper orders MUST NOT appear in the Open Orders UI table on ApeX.
- Open Orders feed must include only discretionary entry/close orders that the trader would consider “open orders.”
- TP/SL state is represented only via TP/SL targets on positions, derived from `orders_raw` and state machine logic.

Classification (conceptual):
- Treat an order as TP/SL helper if:
  - `isPositionTpsl=true`, OR
  - `reduceOnly=true` AND type starts with `STOP` or `TAKE_PROFIT` (defensive inference)

## Options Considered

### Option A — Show TP/SL helper orders in Open Orders
- Pros: “everything in one list.”
- Cons: confusing; increases operational error; breaks parity direction.

### Option B — Hide helper orders (chosen)
- Pros: clearer; aligns with positions-centric TP/SL UX; safer.
- Cons: requires good TP/SL representation and reconciliation.

## Consequences

- Cancel UI remains focused on discretionary orders; TP/SL changes happen only through the targets controls.

## Validation Plan

- Unit test: helper orders are excluded from orders feed.
- Manual: set TP/SL; confirm they are shown on positions and not on open orders.

