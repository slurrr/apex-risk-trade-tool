# Review Report: Recent Order Classification + HL Disambiguation Changes

**Date**: 2026-02-13  
**Primary commit reviewed**: `7b48089` (`feat(order-classification): update intent classifier policy and publication rules`)  
**Goal of this report**: Identify logic/parsing/precedence patterns likely to cause UI inconsistencies or crashes, based on the last committed change-set.

## Executive Summary

The biggest correctness risk is not “classification rules” themselves, but **precedence and lifecycle handling** during TP/SL modify flows:

1. **TP/SL cancel events can clobber fresh “move stop” hints** and temporarily blank the stop on positions, even though the app just submitted a replacement stop.
2. **Hyperliquid TP/SL rehydration on cancel-only payloads is not guaranteed** (ApeX-only forced refresh), so a stop can disappear until the next good payload arrives.
3. **Enriched (orderStatus) classification can be overwritten by later partial updates** because “more recent observed timestamp wins” in the classification cache.

If you are seeing “stop not updating on positions” or “stop disappears and never comes back without a refresh”, the first two items are the most likely causes.

## Findings

### 1. Critical: Cancel-only TP/SL events overwrite fresh move-stop intent

**Why it matters**

During a stop move, the exchange often cancels the old stop before the new stop is fully reflected in the stream. The app sets a local hint to keep the UI responsive, but the cancel-only path can clear that hint immediately, creating a blank-stop window or permanent blank if the replacement stop is late/ambiguous.

**Where**

- `backend/trading/order_manager.py:1686` (single canceled TP/SL payload handling)
- `backend/trading/order_manager.py:1738` (batch cancel-only handling)

**What looks wrong**

In both cancel-only paths, the code calls:
- `self._set_local_tpsl_hint(... clear_sl=True ...)` for STOP cancels (`backend/trading/order_manager.py:1711` and `backend/trading/order_manager.py:1769`)

That operation can overwrite a fresh, correct hint set by `modify_targets(...)` for a replacement stop, because it does not check whether a newer hint exists that expects a replacement value.

**Expected safer behavior**

If a fresh hint exists for the same symbol and kind (e.g., `stop_loss`), a cancel-only event for the previous stop should not set `stop_loss=None` unless there is strong evidence “no replacement is expected”.

### 2. High: HL cancel-only TP/SL payloads can request refresh, but HL path never forces it

**Why it matters**

`_reconcile_tpsl(...)` returns `True` for cancel-only payloads to indicate “rehydration required” (by design). The stream handler only uses that flag to force a refresh on ApeX, not Hyperliquid.

If Hyperliquid emits a stop cancel event before it emits the replacement stop event, the TP/SL map can be cleared and remain cleared until:
- the next WS `orders_raw` payload contains an active stop order, or
- something else triggers a REST snapshot path (for example a positions REST call hitting `_maybe_hl_tpsl_hint_fallback_snapshot`)

**Where**

- `_reconcile_tpsl` cancel-only contract: `backend/trading/order_manager.py:1660`
- refresh hook applied only for Apex: `backend/api/routes_stream.py:129`
- refresh only triggered when `refresh_needed and is_apex_gateway`: `backend/api/routes_stream.py:245` (not shown in this snippet, but controlled by `is_apex_gateway` checks)

**What looks wrong**

The “rehydrate” signal is ignored for Hyperliquid streaming updates. That creates a gap where HL positions can show blank TP/SL even though the move is in progress and the app has local intent.

### 3. High: orderStatus enrichment can be overwritten by later partial updates

**Why it matters**

The HL disambiguation strategy enriches ambiguous rows using `orderStatus(oid)` and ingests that enriched record into the classification cache.

However, the cache merge logic allows **newer timestamps** (including `observed_at_ms`) to override prior records. That means a later WS update with partial/missing markers can regress a previously enriched record back to unknown/ambiguous classification.

**Where**

- Cache merge: `backend/trading/order_manager.py:349` (`_select_more_recent_record`)
- Time-preference: `backend/trading/order_manager.py:384` (`if in_t > cur_t: return incoming`)

**What looks wrong**

Enrichment is only forced to win in one direction: when an enriched record arrives after a non-enriched record (`backend/trading/order_manager.py:376`).

There is no symmetrical guard that says: “if current is enriched and incoming is not enriched, keep current unless incoming provides stronger evidence”.

This can cause “flapping”:
- enrichment resolves intent correctly
- later partial WS row arrives with a newer `observed_at_ms`
- cache regresses to unknown/incorrect intent

### 4. Medium: Ingesting `orders` events into the classifier can pollute unknown windows

**Why it matters**

`routes_stream` calls `ingest_orders_raw(...)` not only on `orders_raw` events, but also on `orders` events:
- `backend/api/routes_stream.py:260`

Some `orders` payloads (venue-dependent) are explicitly “no TP/SL data here”. Ingesting them can:
- overwrite cache records with weaker shapes (depending on timestamps)
- add `unknown` events to the rolling windows and trigger recovery/auto-shadow

**Where**

- `backend/api/routes_stream.py:260`
- classification windows and unknown escalation: `backend/trading/order_manager.py:398`

### 5. Medium: “last_orders_raw_ts” is only updated for `source="ws"`

**Why it matters**

`_last_orders_raw_ts` drives some “stale orders_raw” logic. It is only updated when ingest `source == "ws"`:
- `backend/trading/order_manager.py:475`

But the system ingests from multiple sources (`orders`, `rest`, `enrichment`). Depending on how venues publish events, this can make health reporting and recovery triggers inconsistent.

### 6. Low: Large raw payload logging in unknown path

**Why it matters**

On first-seen unknowns, the logger includes `raw` payload:
- `backend/trading/order_manager.py:453`

This is good for debugging but can be heavy and potentially leak sensitive order details into logs (depending on venue payload). Consider redaction/size limits.

## “Most Likely Cause” for the Current Symptom: Stop Moves Not Showing on Positions

If the UI stop value disappears or fails to update after a stop move, the most likely interaction is:

1. `modify_targets(...)` sets a fresh stop hint and seeds `_tpsl_targets_by_symbol`.
2. Exchange cancels the previous stop first; WS sends a cancel-only TP/SL payload.
3. `_reconcile_tpsl(...)` processes the cancel-only payload and calls `_set_local_tpsl_hint(clear_sl=True)` (`backend/trading/order_manager.py:1711`), clobbering the fresh stop hint.
4. Hyperliquid does not force a refresh on `needs_refresh=True` (`backend/api/routes_stream.py:129`), so the map remains cleared until a later good payload arrives.

## Suggested Verification Steps (No Code Changes)

1. After moving SL, immediately check `GET /api/orders/debug?intent=unknown&limit=200&include_raw=1` for:
   - ambiguous reduce-only rows
   - whether enrichment is happening (`enriched_order_status` evidence in canonical records)
2. Watch `GET /api/stream/health` for:
   - `hl_disamb_enrich_*` counters increasing
   - unknown counters and whether auto-shadow is engaged
3. Capture the exact `orders_raw` WS events around “move stop”:
   - confirm whether a cancel-only event is emitted before replacement is visible

