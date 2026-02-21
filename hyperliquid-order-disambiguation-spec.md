# Hyperliquid Order Disambiguation Spec (SL Close vs Reduce-Only Limit Close)

**Repo**: `apex-risk-trade-tool`  
**Date**: 2026-02-13  
**Status**: Draft for planning/team alignment (intended to drive a single correct patch)  

## 1) Problem

On Hyperliquid, some immediate order-update shapes can temporarily look identical for:
- stop-loss close (TP/SL helper leg), and
- discretionary reduce-only limit close

If the adapter/classifier only sees `reduceOnly=true` and a limit-like shape with no trigger markers, it cannot reliably classify intent. The result is helper leakage into Open Orders and/or missing TP/SL updates on Positions.

Additionally, even when helper orders are correctly excluded from Open Orders, the UI must reflect **updated** TP/SL targets (especially SL moves) on **Open Positions** in a realtime-ish way. This requires a WS-first derivation path with bounded fallbacks that do not spam REST.

## 2) Verified Endpoint Capabilities (Facts)

This spec is based on:
- the Hyperliquid Python SDK contracts in `.venv/lib/python3.10/site-packages/hyperliquid/info.py`, and
- a live probe against `POST https://api.hyperliquid.xyz/info` using `HL_USER_ADDRESS` from `.env`.

### 2.1 `openOrders` (insufficient for intent)

`type=openOrders` returns a sparse shape (SDK doc):
- `coin`, `limitPx`, `oid`, `side`, `sz`, `timestamp` (plus sometimes `origSz`, `reduceOnly`)

It does not carry reliable trigger markers (`isTrigger`, `triggerPx`, `orderType`, etc.). It MUST NOT be used as the sole source to distinguish SL helper vs reduce-only limit close.

### 2.2 `frontendOpenOrders` (preferred open-state snapshot)

`type=frontendOpenOrders` is a **Hyperliquid-provided** `/info` response (despite the name); we do not “build” it. The backend calls it via the HL SDK (`Info.frontend_open_orders`) and then normalizes fields into our internal shape.

`type=frontendOpenOrders` includes the intent-relevant fields we need (verified live):
- `oid`, `coin`, `reduceOnly`
- `isTrigger`, `isPositionTpsl`
- `orderType` (humanized string, e.g., "Stop Market")
- `triggerPx`, `triggerCondition`
- `tif`, `side`, `sz`, `origSz`, `limitPx`, `cloid`, `children`

This is the preferred open-state snapshot for classification and TP/SL derivation.

### 2.3 `orderStatus` (authoritative per-order disambiguation)

`type=orderStatus` queried by `oid` is the preferred enrichment path for ambiguous rows. It is keyed by the stable identifier `oid` and returns detailed order metadata suitable for classification even when stream/update payloads are partial.

### 2.4 `historicalOrders` (terminal/backfill only)

`type=historicalOrders` returns records with:
- top-level: `status`, `statusTimestamp`
- nested: `order` containing the same rich shape as `frontendOpenOrders` (verified live)

Use for backfill/corroboration of terminal lifecycle, not as the primary live classifier input.

## 3) Required Inputs for TP/SL Derivation (Hyperliquid)

### 3.1 Primary truth for open-state classification

Use `frontendOpenOrders` (or canonicalized `orders_raw` derived from it) as the primary input for open-state classification on Hyperliquid.

### 3.2 Primary truth for realtime-ish updates

Under normal operation, TP/SL (including SL moves) must be derived from **WS `orderUpdates`** events (which the adapter normalizes and publishes as `orders_raw`).

`frontendOpenOrders` is the preferred REST snapshot fallback when WS is stale or when a post-modify confirmation window times out.

### 3.3 Ambiguity definition

Treat an order row as *ambiguous* when it is reduce-only but lacks all trigger markers:
- `reduceOnly == true`
- `isTrigger` is missing/false AND `isPositionTpsl` is missing/false
- `triggerPx` missing/empty
- `orderType` appears non-trigger (e.g., "Limit" or "Market") or is missing

In this state, do not guess.

## 4) Adapter-Level Enrichment Policy (Single Correct Patch)

### 4.1 Rule: do not publish ambiguous as Open Orders

If Hyperliquid order rows are ambiguous:
- classify as `unknown` (or "pending enrichment")
- do not publish to Open Orders
- do not clear/overwrite TP/SL last-known-good state

**Clarification (publish rule after timeout)**:
- Ambiguous rows remain hidden from the main Open Orders UI even if enrichment times out.
- After enrichment timeout, ambiguous/unknown rows MUST be accessible via a debug-only surface (e.g., `GET /api/orders/debug?intent=unknown` from the order-classification refactor), but MUST NOT appear in normal Open Orders flows. This avoids silent losses without polluting the primary workflow.

### 4.2 Enrich ambiguous rows using `orderStatus(oid)`

When ambiguity is detected for a known `oid`:
1. Call `orderStatus` by `oid` (bounded, rate-limited).
2. Merge the returned fields into the canonical order record.
3. Re-run intent classification:
   - if trigger markers exist (`isTrigger`, `triggerPx`, trigger-like `orderType`, or `isPositionTpsl`), classify `tpsl_helper`
   - else classify discretionary reduce-only close

**No-`oid` behavior (required)**
- If an ambiguous row has no `oid` (cannot call `orderStatus`):
  - keep `intent=unknown`
  - keep hidden from Open Orders
  - do not clear TP/SL last-known-good
  - expire from the ambiguous/enrichment queue after a TTL (default: 20 seconds) unless a later WS or snapshot event provides an `oid` or adds trigger markers

### 4.3 Bounded behavior (anti-storm)

Requirements:
- Enrichment is attempted only for ambiguous rows and only when `oid` is present.
- Cache enrichment results per `oid` for a short TTL.
- Enforce a minimum gap between enrichment calls (global and/or per-symbol).
- If enrichment fails, keep the order `unknown` and rely on the next `frontendOpenOrders` snapshot or normal stream convergence.

**Hard rate budgets (defaults; tunable via config)**
- `orderStatus` enrichment:
  - global: max **2 calls/sec** sustained, burst **5 calls/sec** for up to 2 seconds
  - per-symbol: max **1 call/sec**
  - max in-flight: **5**
- `frontendOpenOrders` fallback snapshots (when WS confirmation times out):
  - global: max **1 call / 10 sec**
  - per-symbol: max **1 call / 20 sec**
- Coalescing and min-gap defaults:
  - coalesce window for repeated same-symbol refresh triggers: **250 ms**
  - min-gap between any fallback actions for the same symbol: **5 sec**

## 5) Deterministic Source Precedence (Intent + TP/SL)

To prevent flapping under partial payload windows, the system must apply a deterministic precedence order for derived TP/SL state and for order intent classification.

### 5.1 Precedence table (highest to lowest)

1. **WS enriched record**: a normalized WS `orderUpdates` row that contains explicit trigger markers.
2. **Recent `orderStatus(oid)` enrichment**: per-order metadata fetched for an ambiguous row.
3. **Latest `frontendOpenOrders` snapshot**: open-state snapshot, used primarily as fallback when WS is stale or during confirmation timeout.
4. **Last-known-good derived state**: previously derived TP/SL targets retained under partial/empty snapshots until authoritative removal evidence.

### 5.2 Tie-breaker (timestamp)

When two candidates disagree at the same precedence level:
- prefer the candidate with higher `updated_at_ms`
- derive `updated_at_ms` using, in order:
  - `statusTimestamp` (when present)
  - `timestamp` (when present)
  - ingestion `observed_at_ms` (fallback)

## 6) SL Move Updates (Open Positions Must Reflect New Stop)

### 6.1 Goal (operator-visible outcome)

When the operator updates SL (moves stop up/down), the Open Positions UI must reflect the new SL:
- quickly (WS healthy),
- correctly (no flapping back to old SL), and
- without requiring manual refresh.

### 6.2 Dataflow (WS-first, REST-bounded)

This is the recommended pipeline for a stop-loss move:

1. `POST /api/positions/{id}/targets` request succeeds.
2. Backend records a **local hint** (symbol + expected stop value + observed_at) and immediately publishes an updated positions payload using the hint as provisional display value.
3. Backend waits for **confirmation** via incoming WS `orderUpdates` (normalized into `orders_raw`) that contains an SL helper order for that symbol at the expected trigger price.
4. On confirmation, the backend:
   - promotes the hint into last-known-good derived state,
   - clears the hint (or marks it confirmed),
   - updates TP/SL map for the symbol and repushes positions.

### 6.3 Confirmation signals (what counts as “we saw the new SL”)

An SL move is considered confirmed when, for the relevant symbol:
- we observe an open helper order with any trigger marker (`isTrigger` or `triggerPx` or trigger-like `orderType`), AND
- the derived SL value matches the hinted stop within an epsilon window.

### 6.4 Failure modes and bounded fallback (no spam)

If confirmation does not arrive within a bounded window (default: 2 seconds WS healthy, 10 seconds degraded):

Fallback steps (in order, each bounded by min-gap and coalesced per symbol):
1. Trigger a single REST snapshot fetch of `frontendOpenOrders` (not `openOrders`) to rebuild the helper-order set for that symbol.
2. If the snapshot includes ambiguous reduce-only rows, enrich only those rows using `orderStatus(oid)` (bounded).
3. If still unconfirmed after the overall hint TTL, keep last-known-good TP/SL on positions and emit an operator-visible warning (health counter + log), rather than blanking or flapping.

**Anti-storm requirements**
- Coalesce multiple SL moves within a short window: only the latest hint per symbol matters.
- Enforce `min_gap_seconds` between REST snapshot fallbacks (global and per-symbol).
- Enrich via `orderStatus` only for ambiguous rows and only for oids observed recently (TTL).

### 6.5 Removal/replace semantics (avoid flapping)

When moving SL, the old SL order may be canceled and replaced by a new SL order. The system must not briefly regress to “no SL” or the old SL due to partial payload windows.

Rules:
- Prefer “last-known-good” retention on positions until authoritative evidence clears a target.
- Do not clear SL based solely on:
  - a missing row in a delta payload, or
  - a historical-only record.
- Clear SL only when:
  - the exchange confirms SL cancellation/trigger/fill and no replacement is active after a short grace window, OR
  - a full snapshot confirms absence beyond a grace window.

## 7) Acceptance (Outcome-Based)

- Stop-loss close orders never appear in Open Orders UI as discretionary orders.
- Discretionary reduce-only limit close orders do appear in Open Orders UI.
- During brief missing-marker windows, ambiguous rows are either:
  - classified correctly after enrichment, or
  - held as `unknown` without polluting Open Orders and without blanking TP/SL on Positions.
- After an SL move request succeeds, positions reflect the new SL within:
  - ≤ 2 seconds under WS-healthy conditions, or
  - ≤ 10 seconds under WS-degraded conditions.

### 7.1 Call hygiene SLOs (required)

These SLOs ensure “no spam” is measurable:
- No REST storm under churn:
  - `frontendOpenOrders` fallback calls: ≤ **30 calls / 5 minutes** global (sustained ceiling)
  - `orderStatus` enrichment calls: ≤ **150 calls / 5 minutes** global (sustained ceiling)
- Enrichment latency (when enrichment is invoked):
  - p95 time from ambiguity detection to resolved intent: ≤ **1.0 sec**
  - p99 ≤ **3.0 sec**

## 8) Implementation Checklist

- Confirm Hyperliquid adapter uses `frontendOpenOrders` as the default open-state snapshot for `orders_raw`.
- Add an enrichment path for ambiguous rows keyed by `oid` using `orderStatus`.
- Ensure the shared classifier treats "reduceOnly without trigger markers" as `unknown` (not auto-TP/SL) unless a hint or enrichment confirms helper intent.
- Add health counters for:
  - ambiguous/unknown count and rate
  - enrichment attempts/success/failure
- Implement WS-first SL move confirmation loop:
  - local hint immediate display
  - bounded confirmation window
  - bounded fallback snapshot + selective orderStatus enrichment
  - last-known-good retention (no blanking/flapping)

## 9) Local Probing Note (Environment)

The repo stores `HL_USER_ADDRESS` in `.env`, but shell processes do not automatically export `.env`.
If you need to probe locally:
- load `.env` explicitly (or have the app load settings), or
- use a small Python loader that reads `.env` without relying on `source .env` (line endings may be CRLF).
