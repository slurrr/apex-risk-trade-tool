# Decision Record: Snapshot-Authoritative State, WS-Accelerated Updates

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

We have REST endpoints that are more shape-stable and complete for the data we need:
- Hyperliquid: `/info` `frontendOpenOrders` + `clearinghouseState` (`user_state`) are richer than raw deltas for classification and TP/SL derivation.
- ApeX: REST snapshots can corroborate and backfill around missed WS deltas (with WS still valuable for immediacy).

## Decision

Flip authority: the system becomes **snapshot-authoritative** and **WS-accelerated**.

Definitions:
- **Authoritative snapshot**: a REST snapshot payload (venue-specific) that the backend uses to *commit* UI-facing state (Open Orders, Positions TP/SL representation, and internal caches).
- **WS signal**: a WS event used to speed up the UI by triggering refreshes or, when safe, providing a provisional update.

Rules:
1. UI-facing state MUST be committed from the authoritative snapshot pipeline.
2. WS MUST NOT be the sole authority for classification or TP/SL derivation.
3. WS MAY be used for immediate UI updates only when the event is “complete enough” (strict schema predicate) and MUST still be followed by an authoritative snapshot confirmation shortly thereafter.
4. When WS events are partial/ambiguous, they act only as **invalidate/refresh signals**; they do not mutate committed state.

## How This Preserves Existing Logic

This ADR is a precedence flip, not a rewrite:
- Keep the canonical order model + shared intent classifier + unknown policy.
- Keep local hints for post-submit/post-modify immediate UX.
- Keep reason-based reconcile/anti-storm mechanisms.

The key change is: what source is allowed to *commit* state vs merely *suggest* changes.

## Precedence (Required)

For any derived UI value (order intent, TP/SL targets, position enrichment), apply:

1. **Authoritative snapshot (REST)**
2. **WS complete event (provisional overlay)**
3. **Local hint (short TTL overlay)**
4. **Last-known-good derived state**

Tie-breaker: if two candidates at the same precedence disagree, prefer newer `updated_at_ms` (or venue-specific timestamp), else prefer newer ingestion `observed_at_ms`.

Notes:
- WS “complete event” is venue- and domain-specific. If the completeness predicate fails, WS is not allowed above local hint / last-known-good.
- Local hints never permanently override snapshot; they exist to prevent UI lag while waiting for the next snapshot confirmation.

## Operational Model (WS for Speed, Snapshot for Truth)

### WS-triggered snapshot refresh

WS events (order updates, fills, user events) enqueue a refresh:
- debounce/coalesce per symbol (or global if symbol cannot be inferred)
- enforce hard call budgets and min-gaps

### Optional provisional UI update

If a WS event passes completeness checks, we may:
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

