# Decision Record: Auto Entry Prefill + ATR Stop Autofill (Hyperliquid Parity)

**ID**: 0008-auto-entry-and-atr-autofill  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The key productivity feature of this tool is auto-population:

- When a user selects a symbol, the UI calls `GET /api/price/{symbol}` and **prefills Entry** with a best-available price.
- Once symbol, side, and entry price are set, the UI calls `POST /risk/atr-stop` and **prefills Stop** using ATR (timeframe selectable: `3m`, `15m`, `1h`, `4h`).
- The UI preserves manual stop overrides (if the user types a Stop, ATR autofill pauses until Stop is cleared).

These features must carry over to Hyperliquid. They depend on:
- an interactive “best available price” for entry prefill
- candle history availability and correct timeframe mapping for ATR
- clear fallback semantics when data is unavailable (no dangerous guesses)

## Decision

### Auto Entry Prefill (`/api/price/{symbol}`)

- Hyperliquid will implement `GET /api/price/{symbol}` returning `{ "symbol": "<BASE-QUOTE>", "price": <number> }` with the same response shape as today.
- For Hyperliquid, the meaning of `price` is **best-available reference price** intended for UI convenience, not guaranteed fill price.
- Preferred price source order (Hyperliquid):
  1) **mid price** (if available via a lightweight endpoint / cached WS mids)
  2) **mark/oracle price** (if mid is unavailable)
  3) **last trade price** (if the above are unavailable)
  4) error / null (do not guess)
- If the backend cannot produce a valid price quickly, it returns a structured error; UI should leave Entry blank (current UI already tolerates null by silently failing to prefill).

Rationale:
- Mid is generally stable, fast, and neutral when side is unknown at symbol selection time.
- Last trade can be stale/spiky; use only as fallback.

### ATR Stop Autofill (`/risk/atr-stop`)

- Hyperliquid must support candle history sufficient to compute ATR for the UI timeframes:
  - `3m`, `15m`, `1h`, `4h`
- If Hyperliquid cannot provide candles for a given timeframe, the backend must return a structured 503 error consistent with the current endpoint behavior (UI will prompt user to enter stop manually).
- ATR remains a **suggestion** only; the user can override Stop and the override is preserved.

### Caching & Streaming (supporting behavior)

- The gateway may cache reference prices for short TTL (e.g., 10s) to make entry prefill and UI interactions snappy.
- When WS price streams are enabled, the backend should update the same cache used by `/api/price/{symbol}` (so the UI prefill reflects live prices).

## Options Considered

### Option A — Use best bid/ask based on side
- Pros: closer to actionable entry for limit orders.
- Cons: side is often unset at symbol select; adds coupling to orderbook; can mislead; more edge cases.

### Option B — Use mid/mark as reference price (chosen)
- Pros: neutral; available from simple “mids” feeds; good for prefill ergonomics.
- Cons: not directly executable; must be explained as a reference price.

### Option C — Disable autofill on Hyperliquid
- Pros: avoids data dependencies.
- Cons: violates parity; removes the primary tool value; not acceptable.

## Consequences

- Phase 0 must confirm:
  - which HL endpoints/WS topics provide mid/mark/last quickly and reliably
  - candle endpoint(s) and timeframe encoding
- Documentation should clarify that Entry autofill uses a reference price and may differ from achievable fills.
- If HL candle/timeframe support is limited, the UI timeframe list may need to be constrained per venue (must be a deliberate follow-up decision if needed).

## Validation Plan

- Manual:
  - With venue=Hyperliquid, selecting a symbol prefills Entry within ~1s under normal conditions.
  - Changing side/entry triggers ATR stop suggestion; Stop field updates unless manually overridden.
  - Clearing Stop re-enables ATR suggestions.
- Integration script:
  - fetch `/api/price/{symbol}` repeatedly; confirm stable values and acceptable latency.
  - call `/risk/atr-stop` for each timeframe; confirm candle counts and no off-by-one ordering issues.
- Failure mode:
  - simulate price endpoint failure; ensure UI does not set Entry incorrectly.
  - simulate candle fetch failure; ensure backend returns structured 503 and UI prompts for manual stop.

