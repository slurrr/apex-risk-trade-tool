# Decision Record: Publication Rules (Open Orders vs TP/SL vs Unknown)

**ID**: 0003-publication-rules  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

Even perfect classification can be undermined if we publish the wrong payload to the wrong UI stream. We need explicit rules for:
- what goes to Open Orders
- what feeds TP/SL on positions
- what happens to unknowns

## Decision

- `orders_raw` is the authoritative event for classification and TP/SL derivation.
- Open Orders stream and `/api/orders` return **only** `intent=discretionary`.
- TP/SL representation for positions uses **only** `intent=tpsl_helper` plus local hints until confirmed.
- Unknown orders are never shown as normal open orders; optionally exposed only via debug diagnostics.

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

