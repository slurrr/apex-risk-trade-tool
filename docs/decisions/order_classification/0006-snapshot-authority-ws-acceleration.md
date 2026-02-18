# Decision Record: Snapshot-Authoritative State (REST or WS Snapshot), Delta-Accelerated Updates

**ID**: 0006-snapshot-authority-ws-acceleration  
**Date**: 2026-02-13  
**Status**: Proposed  
**Owners**: Backend team  

## Context

This app’s primary operator requirements are:
- speed (realtime-ish UI updates)
- accuracy (prerequisite; wrong UI state is unacceptable)
- stability (no manual refresh, no flapping)

In practice, WebSocket event feeds across venues can be:
- partial (missing fields required for classification/TP-SL derivation)
- out-of-order
- empty/quiet for long periods
- inconsistent during short lifecycle windows (especially around helper legs)

Treating WS as the single ground-truth authority pushes complexity into the app (hints, heuristics, and piecemeal object construction) and creates “fix one issue, break another” dynamics.

Crucially, “authoritative” cannot mean “REST-only” globally:
- ApeX exposes active TP/SL helpers most reliably via private WS (and may not expose all active TP/SL details via REST while orders are open).
- Hyperliquid exposes rich order intent markers via REST snapshots (`frontendOpenOrders`), and WS can be partial/inconsistent around helper legs.

Therefore the global invariant must be **snapshot-authoritative** (where a snapshot may come from REST or a WS snapshot payload), with deltas used only to accelerate refresh and optionally provide provisional UX.

## Decision

Flip authority semantics: the system becomes **snapshot-authoritative** and **delta-accelerated**.

Definitions:
- **Authoritative snapshot**: a venue-specific snapshot payload (REST snapshot or WS snapshot) that the backend uses to *commit* UI-facing state (Open Orders, Positions TP/SL representation, and internal caches).
- **Delta signal**: a WS event (or other event stream) used to speed up the UI by triggering refreshes or, when safe, providing a provisional update.

Rules:
1. UI-facing state MUST be committed from the authoritative snapshot pipeline.
2. No delta-only feed (including WS deltas) may be the sole authority for classification or TP/SL derivation.
3. Deltas MAY be used for immediate UI updates only when the event is “complete enough” (strict schema predicate) and MUST still be followed by an authoritative snapshot confirmation shortly thereafter.
4. When delta events are partial/ambiguous, they act only as **invalidate/refresh signals**; they do not mutate committed state.

## How This Preserves Existing Logic

This ADR is a precedence flip, not a rewrite:
- Keep the canonical order model + shared intent classifier + unknown policy.
- Keep local hints for post-submit/post-modify immediate UX.
- Keep reason-based reconcile/anti-storm mechanisms.

The key change is: what source is allowed to *commit* state vs merely *suggest* changes.

## Precedence (Required)

For any derived UI value (order intent, TP/SL targets, position enrichment), apply:

1. **Authoritative snapshot (REST or WS snapshot)**
2. **Delta complete event (provisional overlay)**
3. **Local hint (short TTL overlay)**
4. **Last-known-good derived state**

Tie-breaker: if two candidates at the same precedence disagree, prefer newer `updated_at_ms` (or venue-specific timestamp), else prefer newer ingestion `observed_at_ms`.

Notes:
- “Snapshot” is venue- and domain-specific. Some domains may only have a WS snapshot that is complete enough (example: ApeX TP/SL helpers).
- Delta “complete event” is venue- and domain-specific. If the completeness predicate fails, deltas are not allowed above local hint / last-known-good.
- Local hints never permanently override snapshot; they exist to prevent UI lag while waiting for the next snapshot confirmation.

## Operational Model (Deltas for Speed, Snapshot for Truth)

### Delta-triggered snapshot refresh

Delta events (order updates, fills, user events) enqueue a refresh:
- debounce/coalesce per symbol (or global if symbol cannot be inferred)
- enforce hard call budgets and min-gaps

### Optional provisional UI update

If a delta event passes completeness checks, we may:
- update the UI immediately (overlay)
- schedule a snapshot refresh soon after to confirm and commit

If the snapshot contradicts the provisional overlay:
- snapshot wins immediately
- record a structured warning counter (for tuning completeness predicates)

## Budgets (Defaults; Tunable)

These defaults are intended to prevent REST storms while maintaining responsiveness:

- Snapshot refresh (authoritative):
  - global max: **1 refresh / 10 sec**
  - per-symbol max: **1 refresh / 20 sec**
  - min-gap per venue (any refresh reason): **5 sec**
  - coalesce window: **250 ms**

- Enrichment (only for ambiguous rows, keyed by stable id):
  - global max: **2 calls/sec** sustained (burst **5/sec** for 2 sec)
  - per-symbol max: **1 call/sec**
  - max in-flight: **5**

## Venue-Specific Snapshot Sources (Required Mapping)

This ADR requires a per-venue, per-domain mapping of what “authoritative snapshot” means.

Initial mapping (expected):
- Hyperliquid:
  - Orders/intent/TP-SL helpers: REST snapshot `frontendOpenOrders` (authoritative)
  - Positions: REST snapshot clearinghouse state (`clearinghouseState` / `user_state`) (authoritative)
  - Deltas: WS `orderUpdates` and `userEvents` accelerate refresh and may provide provisional overlay when complete
- ApeX:
  - TP/SL helpers: private WS snapshot payloads that include `isPositionTpsl` and trigger semantics (authoritative)
  - Discretionary open orders: REST `open-orders` snapshot can be authoritative for the Open Orders table (venue-dependent)
  - REST history (`history-orders`): corroboration/backfill only (never sole authority for active TP/SL)

## Consequences

Pros:
- Reduces reliance on partial WS shapes for correctness.
- Makes correctness/debugging deterministic: “state is last successful snapshot + defined overlays”.
- Improves multi-venue maintainability by standardizing authority semantics.

Cons:
- Adds some REST load (mitigated by budgets + coalescing).
- Some UI updates may shift from “instant delta” to “fast refresh”, depending on venue and rate limits.
- Requires explicit “completeness predicates” and clear commit/overlay separation.

## Validation Plan

Success looks like:
- No manual refresh required for normal operation.
- TP/SL state does not flap due to partial WS events.
- Under churn, REST budgets are respected and the UI remains coherent (last-known-good + overlays).

Instrumentation required:
- snapshot refresh reason counts + last refresh age
- WS event age + completeness failure counters
- overlay vs snapshot contradiction counters
- REST call-rate counters over 5m windows (ship-block if ceilings exceeded)

## Follow-ups (Expected Spec Updates)

This ADR implies updates to specs that currently state “WS orders_raw is authoritative”:
- `order-classification-refactor-spec.md` should be amended to reflect snapshot-authoritative commit semantics.
- `hyperliquid-order-disambiguation-spec.md` already adopts snapshot fallback; align its precedence table with this ADR.
