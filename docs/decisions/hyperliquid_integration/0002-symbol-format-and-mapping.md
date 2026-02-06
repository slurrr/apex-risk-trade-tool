# Decision Record: Symbol Format & Hyperliquid Mapping

**ID**: 0002-symbol-format-and-mapping  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The existing app uses symbols in `BASE-QUOTE` form (e.g., `BTC-USDC`) in:
- UI validation (regex)
- API schemas
- risk engine (`tickSize`, `stepSize`, etc.)
- gateway caches keyed by symbol string

Hyperliquid perps are commonly referenced by “coin” (e.g., `BTC`) and collateral is typically in a stable asset. We need a consistent internal symbol format that keeps the UI stable while mapping cleanly to Hyperliquid instruments.

## Decision

- Canonical **UI/API symbol format remains** `BASE-QUOTE` (already supported by schemas and UI patterns).
- Hyperliquid will expose its symbols via `GET /api/symbols` as `COIN-USDC` (example: `BTC-USDC`) to match Hyperliquid’s common display convention and avoid implying USDT settlement.
- Hyperliquid mapping rule:
  - `coin = symbol.split("-")[0]` (the `BASE` part)
  - `quote = symbol.split("-")[1]` is accepted for display, but **not used** to select the HL instrument (HL instrument selection uses `coin`).
- Input normalization:
  - For Hyperliquid, accept user-entered symbols with any quote token that matches the existing regex (e.g., `BTC-USDT`, `BTC-USD`, `BTC-USDC`) and normalize to `coin = BASE`.
  - For ApeX, preserve existing `BASE-QUOTE` meaning.
- The UI should prefer dropdown selection from `/api/symbols` rather than free-typing to reduce mapping ambiguity.

## Options Considered

### Option A — Keep `BTC-USDT` everywhere (and map to coin)
- Pros: minimal perceived change to users familiar with current app.
- Cons: misleading semantics (HL isn’t “USDT” in the same way); likely to cause confusion in ops.

### Option B — Switch to coin-only (`BTC`) everywhere
- Pros: aligns with HL naming.
- Cons: breaks existing schemas/regex; larger UI/API change; impacts ApeX too.

### Option C — Keep `BASE-QUOTE` in UI; expose HL as `COIN-USDC` and map by base (chosen)
- Pros: stable UI/API contract; clearer display semantics; simple HL mapping.
- Cons: quote token becomes partially informational on HL; must be documented.

## Consequences

- HL order placement and market data fetches must consistently use `coin` derived from `BASE`.
- Documentation must state that HL ignores the quote token for instrument selection.
- If HL ever introduces multiple markets per coin, mapping may need revisiting.

## Validation Plan

- Unit tests:
  - mapping from `BTC-USD`, `BTC-USDT`, `BTC-USDC` all resolves to HL coin `BTC`
  - `/api/symbols` for HL returns `COIN-USDC` codes matching UI regex
- Manual:
  - switch venue to HL; confirm dropdown shows `*-USDC` symbols and trading works.
- Observability:
  - log `symbol_in`, `symbol_normalized`, `venue_coin` for HL requests (redacted as needed).
