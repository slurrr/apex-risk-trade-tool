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
  - must not appear in Open Orders
  - must not overwrite last-known-good TP/SL
  - may be exposed in debug-only diagnostics

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
  - `client_order_id` (preferred)
  - `order_id` (fallback)
  - `(symbol, side, trigger_price)` (last resort, risky—must be time-bounded)

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
- Increment health counters and (optionally) expose debug stream/panel

## 7) Dataflow Refactor (Where the Classifier Runs)

Recommended flow:
1) Adapter emits `orders_raw` as a list of `CanonicalOrder` (not venue-native dicts).
2) Shared classifier runs once per `orders_raw` event:
   - updates internal classification cache
   - updates TP/SL targets model
3) Adapter (or OrderManager) publishes derived streams:
   - `orders` = discretionary-only canonical orders (for Open Orders UI)
   - `positions` = positions enriched with TP/SL targets (from classified helper orders + hints)

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
- Optional: `/v3/history-orders` integrated as supplemental verification input for removal confirmation only.

### Phase 4 — Remove old classification paths
Deliverables:
- Remove scattered venue-specific classification hacks.
- Keep compatibility shims only where necessary for UI schema.

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

## 11) Open Questions / Inputs Needed

1) For Hyperliquid: what stable identifiers are always present for helper legs (e.g., `cloid` patterns, parent linkage, grouping metadata)?
2) For ApeX: confirm `GET /v3/history-orders` response shape and whether it reliably carries TP/SL lifecycle fields needed for supplemental verification.
3) Do we want unknown orders visible anywhere:
   - health-only counters (default), or
   - optional debug UI panel / endpoint?

