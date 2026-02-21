# Decision Record: Hyperliquid Endpoint Precedence for Order Intent

**ID**: 0005-hyperliquid-endpoint-precedence  
**Date**: 2026-02-13  
**Status**: Accepted  
**Owners**: Backend team  

## Context

Some Hyperliquid immediate update shapes can transiently omit trigger markers, making stop-loss helpers indistinguishable from discretionary reduce-only closes if we rely on sparse fields only. We need a deterministic and bounded way to classify SL helpers without leaking them into Open Orders.

## Decision

- Do not use Hyperliquid `openOrders` as the sole source of truth for intent classification (it is too sparse).
- Use `frontendOpenOrders` (a Hyperliquid `/info` response; not app-defined) as the primary open-state snapshot for classification and TP/SL derivation.
- For ambiguous reduce-only rows, enrich using `orderStatus(oid)` and reclassify from the enriched payload.
- Use `historicalOrders` only for terminal/backfill corroboration, not primary live classification.

## Consequences

- Adds a bounded enrichment call path in degraded/ambiguous cases.
- Reduces reliance on heuristics like "HL reduce-only without trigger markers implies helper".

## Validation Plan

- Replay or capture sequences where helper legs briefly lack trigger markers and confirm:
  - zero helper leakage into Open Orders
  - TP/SL convergence without manual refresh
