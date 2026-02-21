# Order Classification Refactor Spec (Canonical Internal Order + Intent Classifier)

**Repo**: `apex-risk-trade-tool`  
**Date**: 2026-02-06  
**Status**: Draft for planning / team alignment (no implementation in this doc)  

## 1) Summary

We have order classification issues where TP/SL helper orders (especially stop-loss legs) occasionally appear in the **Open Orders** UI, while simultaneously failing to update TP/SL on **Open Positions** as expected.

Root cause (observed in practice):
- Venue WS payloads (notably Hyperliquid) can transiently deliver helper legs with **partial / inconsistent markers** during short lifecycle windows (missing `reduceOnly`, missing trigger fields, missing explicit helper flags, partial status transitions).
- A “trust one field” classifier (e.g., only `isPositionTpsl` or only `reduceOnly`) cannot reliably distinguish **discretionary orders** vs **TP/SL helpers** in those windows.

Goal:
- Normalize all venues into **one canonical internal order shape**.
- Classify every canonical order into a single `OrderIntent`:
  - `discretionary` (open entry/close orders shown in Open Orders)
  - `tpsl_helper` (protective orders represented on Positions as TP/SL)
  - `unknown` (never shown as a normal order; debug-only)
- Make `orders_raw` stream the authoritative input for classification and TP/SL derivation.
- Use REST only as **rare recovery** when WS is stale/missing, not as primary functionality.

## 1.1 Documentation & Decision Records (Process Requirement)

Decision records for this workstream live in `docs/decisions/order_classification/`.

**Policy**: Any change to canonical order schema, classifier precedence, unknown-handling, or migration flags MUST have a decision record before (or in the same PR as) the first dependent implementation.

## 2) Scope

### In Scope
- Canonical internal order model used across:
  - `/api/orders` (REST)
  - `/ws/stream` orders events
  - TP/SL representation on `/api/positions` and WS positions events
- A shared classifier that runs on canonical orders:
  - deterministic, reasoned, testable
  - supports “local hints” to resolve transient WS ambiguities
- Adapter-level normalization changes for both venues:
  - ApeX adapter (`backend/exchange/exchange_gateway.py`)
  - Hyperliquid adapter (`backend/exchange/hyperliquid_gateway.py`)
- Migration plan with feature flag and safe fallback to current behavior during rollout.

### Out of Scope
- UI redesign (beyond optional debug visibility for unknown orders)
- Risk sizing changes
- Venue feature additions unrelated to order classification

## 3) Current Architecture (Where Classification Happens Today)

Today, classification is implicit and scattered:
- Gateways emit WS events: `orders`, `orders_raw`, `positions`, `account`.
- `backend/trading/order_manager.py`:
  - `_is_tpsl_order(...)` tries to detect TP/SL helpers from fields like `type`, `isPositionTpsl`, `reduceOnly`.
  - `_include_in_open_orders(...)` hides HL TP/SL orders from Open Orders based on `_is_tpsl_order`.
  - `_reconcile_tpsl(...)` builds `_tpsl_targets_by_symbol` from `orders_raw`, but it filters input using `_is_tpsl_order`.
- `backend/api/routes_stream.py`:
  - filters outgoing Open Orders payload via `_include_in_open_orders`, but can still leak helpers if they’re not detected in time.

Failure mode:
- If a helper leg is temporarily missing the fields `_is_tpsl_order` expects, it can be:
  - published as a normal open order
  - excluded from TP/SL reconciliation
  - causing “stop shows in Open Orders but not on Positions”

## 4) Target Architecture (Clean Separation of Concerns)

### 4.1 Venue Adapter Responsibilities (Normalization Only)

Each venue adapter must normalize raw WS/REST orders into a **canonical internal order model** (`CanonicalOrder`).

Adapters MUST NOT make UI-facing classification decisions. They only:
- normalize and preserve important fields consistently
- attach raw payload (redacted if necessary)
- attach adapter-level “evidence” fields that help classification (e.g., `trigger_price` present, reduce-only flag present, etc.)

### 4.2 Shared Classifier Responsibilities (Intent Only)

A single shared classifier decides `OrderIntent` for each canonical order, given:
- the canonical order itself
- current local hint state (recent submissions / expectations)
- venue capability flags (what signals exist, e.g., `isPositionTpsl` for ApeX)

Classifier outputs:
- `intent`: `discretionary` | `tpsl_helper` | `unknown`
- `confidence`: `high` | `medium` | `low` (optional but useful)
- `reasons`: list of strings (for logging/health/debug)

### 4.3 Publication Rules (UI Streams)

From `orders_raw`:
- Open Orders stream/payload = **only** `intent=discretionary`
- Positions TP/SL derivation = **only** `intent=tpsl_helper` (plus local hints while pending confirmation)
- Unknown orders:
  - MUST NOT appear in Open Orders during normal operation
  - MUST NOT overwrite last-known-good TP/SL
  - MUST have an operator escape hatch + escalation policy (see §6.5)

## 5) Canonical Internal Order Model

### 5.1 CanonicalOrder (minimum fields)

Canonical fields should support all current app behaviors:
- showing Open Orders table
- canceling discretionary orders
- deriving TP/SL targets for positions
- reconciling order lifecycle transitions
- observability and debugging of ambiguous rows

Proposed `CanonicalOrder` (conceptual):
- `venue`: `"apex" | "hyperliquid" | <future>`
- `symbol`: canonical UI symbol (e.g., `BTC-USDT`, `BTC-USDC`)
- `order_id`: string (venue order id)
- `client_order_id`: string|null (venue client id / cloid / clientId)
- `parent_order_id`: string|null (optional; for grouped submissions when supported)
- `side`: `"BUY" | "SELL" | null`
- `status`: canonical status enum (see §5.3)
- `created_at_ms`: int|null
- `updated_at_ms`: int|null
- `order_kind`: `"LIMIT" | "MARKET" | "TRIGGER" | "STOP_MARKET" | "TAKE_PROFIT_MARKET" | ...`
- `reduce_only`: bool|null
- `size`: float|null
- `filled_size`: float|null
- `limit_price`: float|null
- `avg_price`: float|null
- `trigger_price`: float|null
- `is_tpsl_flag`: bool|null (explicit venue flag if present, e.g., ApeX `isPositionTpsl`)
- `tpsl_kind`: `"tp" | "sl" | null` (derived from order_kind and/or trigger semantics; adapter evidence)
- `evidence`: dict of adapter-collected evidence flags (booleans/strings/ints only)
- `raw`: dict|null (redacted raw payload for diagnostics; never includes secrets)

### 5.2 Canonical status mapping

Define a canonical order status set used internally:
- `OPEN`
- `PENDING`
- `FILLED`
- `CANCELED`
- `REJECTED`
- `TRIGGERED` (optional; if venue provides)
- `UNKNOWN`

Each adapter must map venue-specific statuses into this set while preserving raw status in `evidence.raw_status`.

### 5.3 CanonicalOrderIntent

Classifier output per `CanonicalOrder`:
- `intent`: `discretionary` | `tpsl_helper` | `unknown`
- `reasons`: string list (e.g., `["isPositionTpsl", "reduceOnly+trigger", "hint:attached_sl"]`)
- `observed_at_ms`: ingestion time

## 6) Classification Rules (Deterministic + Hint-Assisted)

### 6.1 Principle: orders_raw is authoritative input

We classify based on the highest-fidelity feed available:
- Prefer WS `orders_raw` payloads for classification and TP/SL derivation.
- REST may be used to recover missing data only when WS is stale/missing.

### 6.2 Base signals (cross-venue)

Signals that indicate TP/SL helper intent:
- explicit TP/SL flags (`isPositionTpsl=true` in ApeX)
- order kind indicates protection (`STOP*`, `TAKE_PROFIT*`)
- presence of `trigger_price` (common for protective legs)
- `reduce_only=true` for protective legs (when accurate)
- grouped submission evidence (e.g., same `client_order_id` prefix / known “attached legs” signature)

Signals that indicate discretionary intent:
- plain `LIMIT`/`MARKET` without trigger and without reduce-only helper semantics
- not tagged by hints as an attached protection

### 6.3 Local hints (required for transient ambiguity windows)

To handle short windows where WS rows are missing markers:
- Maintain a local hint store keyed by:
  - `order_id` (preferred when present; e.g., Hyperliquid `oid`)
  - `client_order_id` (useful when present, but not reliably available on HL helper legs across the full lifecycle)
  - **stable fingerprint** (last resort; strictly time-bounded): `(venue, symbol, side, tpsl_kind_if_known, trigger_price≈, size≈)`

Hints are created when:
- placing a new trade with attached TP/SL legs
- modifying targets (create/clear TP/SL)
- canceling targets

Hints must have:
- TTL / expiry (e.g., 20s)
- expected intent (`tpsl_helper` vs `discretionary`)
- expected tpsl_kind (`tp`/`sl`) if applicable

Classifier must use hints only to resolve `unknown` ambiguity, not to override clear WS truth indefinitely.

### 6.4 Unknown handling (explicit)

If a row cannot be classified with high confidence:
- Mark `intent=unknown`
- Do not publish to Open Orders
- Do not clear TP/SL representation based on unknowns
- Increment health counters and expose a required debug/escape hatch path (see §6.5)

### 6.5 Unknown Escalation Policy (Mandatory)

Unknown orders are hidden from Open Orders by default, but they MUST NOT become “silent losses” of real user orders.

Define the following escalation policy:

**Health counters (required)**
- `order_classification_mode_configured` (`legacy|shadow|v2`)
- `order_classification_mode_effective` (`legacy|shadow|v2`) (may differ during automatic temporary fallback)
- `order_classification_auto_switch_until` (unix ms|null)
- `order_classification_auto_switch_cooldown_until` (unix ms|null)
- `order_classification_auto_switch_reason` (string|null)
- `unknown_orders_count`
- `unknown_orders_rate_5m` (unknown / total, last 5 minutes)
- `unknown_orders_last_seen_age_seconds`
- `unknown_orders_last_recovery_action` (string|null)

**Thresholds (initial defaults; tunable)**
- Trigger escalation if either:
  - `unknown_orders_count >= 3` within 60 seconds, OR
  - `unknown_orders_rate_5m >= 0.5%` with at least 200 observed orders, OR
  - any `unknown` order persists (still unknown) for `>= 20 seconds`

**Automatic recovery actions (in order)**
1) Force a bounded “freshness recovery” to obtain a newer `orders_raw` snapshot (WS resubscribe if available).
2) If `orders_raw` is stale or missing after the recovery attempt, run a single REST snapshot recovery (bounded, anti-stormed).
3) If unknowns persist after recovery, emit a structured warning log and expose them through the debug endpoint contract below.
4) If `ORDER_CLASSIFICATION_MODE=v2` and unknown escalation persists, automatically and temporarily switch **effective** behavior to `shadow`:
   - duration: **10 minutes**
   - cooldown: **30 minutes** before another auto-switch can trigger
   - continue computing v2 classification/counters for debugging, but publish legacy outputs while in auto-shadow
   - record `order_classification_auto_switch_*` fields and `unknown_orders_last_recovery_action="auto_switch_to_shadow"`

**Debug endpoint contract (required escape hatch)**
- `GET /api/orders/debug`
  - Query params:
    - `intent=unknown|tpsl_helper|discretionary` (default `unknown`)
    - `limit` (default 200)
  - Response includes:
    - `orders`: list of `CanonicalOrder` (redacted `raw`)
    - `meta`: counters and last recovery action

This endpoint is required even if it is gated behind “dev mode” or operator auth later; the contract must exist.

## 7) Dataflow Refactor (Where the Classifier Runs)

**Single owner requirement**:
- `OrderManager` owns the **classification + publication** pipeline for UI-facing streams.
- Venue adapters own only **normalization** into `CanonicalOrder` and publication of `orders_raw` (and other raw feeds).

Recommended flow:
1) Adapter emits `orders_raw` as a list of `CanonicalOrder` (not venue-native dicts).
2) `OrderManager` ingests `orders_raw` and runs the shared classifier once per event:
   - updates internal classification cache with monotonic apply rules (see §11.2)
   - updates TP/SL targets model
3) `OrderManager` publishes derived streams:
   - `orders` = discretionary-only canonical orders (for Open Orders UI)
   - `positions` enrichment uses TP/SL targets derived from classified helper orders + hints

Migration constraint:
- During rollout, keep existing behavior behind a flag until verified (see §9).

## 8) Acceptance Criteria (Measurable)

### Open Orders correctness
- No TP/SL helper orders appear in Open Orders during normal operation.
- Ambiguous orders never appear as normal Open Orders (they are hidden or debug-only).

### Positions TP/SL correctness
- Setting/clearing TP/SL updates positions display within:
  - ≤ 2 seconds under WS-healthy conditions
  - ≤ 10 seconds under WS-disabled/degraded mode
- TP/SL does not disappear due to partial/missing WS fields; last-known-good retention applies until authoritative removal evidence.

### Reconcile posture
- Reconciliation remains fallback-only, triggered by explicit reasons and anti-storm min-gap.

### Observability
Health counters exist for:
- unknown classification count and rate
- hint usage count and “hint unconfirmed” count
- reconcile reason counts and last reconcile reason

## 8.1 SLOs and Ship-Block Gates (Numeric)

These numeric gates are required to prevent regressions during rollout.

**Helper leakage SLO**
- `helper_leakage_count == 0` over a continuous **8-hour** run under normal operation (per venue).

**Unknown rate SLO**
- `unknown_orders_rate_5m < 0.5%` in steady state (excluding the first 60 seconds after startup / venue switch).
- Ship-block if `unknown_orders_rate_5m >= 2%` for any 5-minute window during testing.

**TP/SL convergence SLO**
- After a modify-targets request:
  - p95 time-to-correct-positions-display ≤ **2 seconds** (WS healthy)
  - p95 ≤ **10 seconds** (WS disabled / degraded)

**Reconcile posture SLO**
- Under WS healthy conditions, reconcile frequency ≤ **1 per 15 minutes** (verification only).

**Temporary rollout guard SLO (TBD removal gate)**
- While v2 is tuning, a temporary safety guard may suppress helper leakage even when classifier output is ambiguous.
- Track `classification_guard_block_count` and `classification_guard_block_reasons` in health.
- Guard removal remains **TBD** until:
  - `order_classification_mode_effective="v2"` remains stable through soak windows, and
  - `classification_guard_block_count` stays flat at **0** for the agreed soak interval.

## 9) Migration Plan (Safe Rollout)

### Phase 0 — Decisions + Contracts
Deliverables:
- Decision records in `docs/decisions/order_classification/`:
  - canonical order schema
  - classifier precedence + hint rules
  - unknown visibility policy
  - migration flag and deprecation plan

### Phase 1 — Add CanonicalOrder + Classifier (no behavior change)
Deliverables:
- Implement canonical model + classifier contract in shared module.
- Adapters emit canonical orders alongside existing payloads (shadow mode).
- Compare old vs new classification in logs/health counters.

### Phase 2 — Hyperliquid adapter + streams routed through classifier
Deliverables:
- HL adapter emits canonical `orders_raw`.
- WS `orders` and `/api/orders` use classifier derived discretionary set.
- Unknown orders hidden by default.

### Phase 3 — ApeX adapter + streams routed through classifier
Deliverables:
- ApeX adapter emits canonical `orders_raw` (including explicit isPositionTpsl evidence).
- Same routing rules for `orders`.
- Optional: `/v3/history-orders` integrated as **advisory-only** corroboration/backfill (never a sole removal trigger).

### Phase 4 — Remove old classification paths
Deliverables:
- Remove scattered venue-specific classification hacks.
- Keep compatibility shims only where necessary for UI schema.
- Temporary v2 safety guard removal is **TBD** pending soak evidence (see §8.1).

## 10) Testing Strategy

### Unit tests
- Canonical mapping tests per venue (raw → canonical)
- Classifier tests with recorded payload sequences covering:
  - helper legs missing markers briefly
  - partial snapshots
  - canceled-only updates
  - reorder/race between modify targets and WS confirmation

### Integration scripts
- Record WS `orders_raw` sequences for both venues and replay into classifier to validate stable output.

## 11) Event Ordering, Idempotency, and Dedupe Rules (Required)

WS and REST events can arrive out-of-order. The classification cache must be monotonic.

### 11.1 Dedupe key

Define a canonical key per order:
1) `order_id` (preferred)
2) `client_order_id` (fallback)
3) stable fingerprint hash of (`venue`, `symbol`, `side`, `tpsl_kind_if_known`, `trigger_price≈`, `size≈`) (last resort; time-bounded)

### 11.2 Monotonic apply rule (“latest wins”)

For a given canonical key:
- Prefer the record with the greatest `updated_at_ms`.
- If `updated_at_ms` missing on either side, fall back to `created_at_ms`.
- If both missing, fall back to ingestion time `observed_at_ms`.
- Tie-breaker: prefer `orders_raw` source over REST snapshot when timestamps tie.

Deletion/removal rule:
- Do not remove an order from the cache purely because it is missing from a partial/delta payload.
- Only remove when:
  - a full snapshot asserts absence, OR
  - an authoritative terminal status is observed.

## 12) Open Questions / Inputs Needed

1) Specify exact fingerprint “≈” rules:
   - trigger price rounding/epsilon
   - size rounding/epsilon
   - maximum TTL (default 20s) and whether to use per-venue defaults
2) For ApeX: confirm `GET /v3/history-orders` response shape and the subset of fields used for advisory corroboration/backfill.
3) Confirm if we want an optional UI dev panel for `/api/orders/debug` (endpoint remains mandatory either way).

## 13) Source-of-Truth Precedence When orders_raw Is Missing/Late/Partial (Required)

`orders_raw` is the authoritative input when it is available and fresh, but the system must define behavior when it is not.

### 13.1 Freshness windows

Define `orders_raw_fresh_seconds` (default: **5 seconds**) as the maximum acceptable age of the last `orders_raw` event when WS is expected to be healthy.

### 13.2 Precedence order (best → worst)

1) **WS `orders_raw` (fresh)**: classify and publish from `orders_raw`.
2) **WS `orders` only (no `orders_raw`)**: enter *degraded* classification mode:
   - do not clear TP/SL from positions based on missing helper evidence
   - publish discretionary orders only when classification confidence is high
   - trigger escalation/recovery if unknown thresholds are exceeded (see §6.5)
3) **REST snapshot recovery**: if WS `orders_raw` is stale beyond a cutoff, force one bounded REST refresh to reconstruct a synthetic `orders_raw` snapshot for classification.

### 13.3 Stale cutoff and forced recovery trigger

Define `orders_raw_stale_cutoff_seconds` (default: **30 seconds**).

If:
- WS is enabled and the last `orders_raw` age exceeds `orders_raw_stale_cutoff_seconds`, OR
- unknown escalation triggers recovery and WS cannot deliver a fresh `orders_raw`,

Then:
- run a forced recovery action (WS resubscribe, then one bounded REST snapshot if needed), anti-stormed by a minimum gap (default: **5 seconds**).
