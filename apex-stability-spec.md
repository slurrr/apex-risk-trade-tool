# ApeX Stability Spec (TP/SL Correctness + Observability Parity)

**Repo**: `apex-risk-trade-tool`  
**Date**: 2026-02-06  
**Status**: Draft for planning / team alignment (no implementation in this doc)  

## 1) Summary

Hyperliquid integration introduced stronger patterns for stream health, reconciliation discipline, and TP/SL stability. ApeX remains functional but has lingering issues around TP/SL correctness and operational observability.

Goal: patch ApeX forward so it behaves “as good as Hyperliquid” in the areas that matter for trading ops:

- **TP/SL correctness**: TP/SL never disappears from UI state unexpectedly.
- **No manual refresh required**: normal operation should stay correct via streaming + light verification.
- **Reconcile is verification**: reconciliation should be infrequent and reason-driven, not the primary mechanism.
- **Observability parity**: ApeX exposes the same stream health / reason counters / alert signals as Hyperliquid.

This spec is outcome-based and phased to allow incremental improvements with clear acceptance criteria.

## 1.1 Documentation & Decision Records (Process Requirement)

This repo uses:
- `docs/api/` for scratchpads/reference
- `docs/decisions/` for **formal decision records**

**Policy**: Any non-trivial change that affects TP/SL behavior, reconcile triggers, or stream-health/alert semantics MUST have a decision record in `docs/decisions/` before (or alongside) the first PR implementing it.

## 2) Scope

### In Scope
- ApeX TP/SL display correctness for:
  - initial load
  - WS disconnect/reconnect
  - partial snapshots / canceled-only payloads
  - post-modify-targets
- ApeX observability parity with Hyperliquid:
  - `GET /api/stream/health` fields and reason counters
  - structured logs for reconcile + fallback use with thresholds and alerts
- Reconciliation redesign for ApeX:
  - reason-based triggers
  - anti-storm minimum gap
  - “verification not primary” discipline
- Clear separation between:
  - **open entry orders** (discretionary orders shown in Open Orders table)
  - **TP/SL representation** (protective orders / targets used to populate positions)
- Explicit scoping of ApeX REST fallback logic as fallback, with thresholds and alerting signals.

### Out of Scope
- Changes to risk sizing formula (`backend/risk/risk_engine.py`)
- UI redesign beyond what is required to preserve correctness / remove manual-refresh dependency
- New venue features not already present in Hyperliquid parity set

## 3) Current Baseline (Relevant Parts)

### Key modules
- ApeX gateway: `backend/exchange/exchange_gateway.py` (venue=`apex`)
- Stream fanout + health endpoint: `backend/api/routes_stream.py`
  - Health endpoint exists: `GET /api/stream/health` (currently most useful for Hyperliquid)
- Order/position normalization + TP/SL map: `backend/trading/order_manager.py`
  - Maintains `_tpsl_targets_by_symbol` and reconciles it from `orders_raw` payloads.

### Observed gap (high-level)
- Hyperliquid has explicit reconcile counters, reason accounting, min-gap anti-storming, and alert windows.
- ApeX has REST fallbacks and WS caches, but lacks:
  - first-class stream health snapshot parity fields
  - reason-based reconcile triggers and anti-storm gates
  - clearly delineated “open orders” vs “TP/SL” data flows in all WS/event paths

## 4) Desired Outcomes (Acceptance-Focused)

### Outcome A — TP/SL never disappears unexpectedly
**Definition**: For any open position, once a TP or SL is displayed, it must not flip to `None` unless the exchange state truly removed it (triggered/filled/canceled/cleared).

Acceptable transitions:
- `None → value` when protection is added or discovered
- `value → None` only when an authoritative signal indicates removal

Explicitly unacceptable:
- `value → None → value` flapping due to missing/partial snapshots
- “TP/SL disappears until refresh” behavior

### Outcome B — No manual refresh in normal operation
**Definition**: With ApeX WS enabled, the UI should remain correct without user-initiated refresh actions for:
- positions table
- TP/SL shown on positions
- open orders table
- account header

Manual refresh remains as a “break glass” tool, not a required workflow step.

### Outcome C — Reconcile is infrequent verification
**Definition**: Reconcile is a bounded, reason-driven verification mechanism, not a continuous polling loop.

Targets (tunable, but explicit):
- A reconcile SHOULD NOT run more often than once per `APEX_RECONCILE_MIN_GAP_SECONDS`.
- A reconcile SHOULD NOT be the primary way TP/SL stays visible (streaming + stable local representation are primary).

### 4.1 Proposed SLOs (Measurable Targets)

These SLOs are intentionally numeric and can be tuned in decision records, but must not remain qualitative.

**TP/SL display SLOs**
- **SLO-A1 (No blank window)**: For any open position with a last-known-good TP and/or SL, the UI MUST NOT show that target as blank/`None` at any time unless an authoritative removal condition is met (i.e., “blank window” = 0 seconds; retention wins over flapping).
- **SLO-A2 (Post-update convergence)**: After a successful “modify targets” action, the updated TP/SL values MUST appear in the positions UI within:
  - **≤ 2 seconds** when ApeX WS is enabled and healthy
  - **≤ 10 seconds** in WS-disabled (degraded) mode

**Reconcile SLOs**
- **SLO-R1 (Normal frequency)**: Under normal WS-healthy conditions, reconcile SHOULD run no more than **1 time per 15 minutes** (excluding explicit reconnect recovery).
- **SLO-R2 (Anti-storm)**: During WS reconnect storms or bursty updates, reconcile MUST still enforce `APEX_RECONCILE_MIN_GAP_SECONDS` and must not exceed **3 reconciles per 5 minutes**.

**Fallback SLOs**
- **SLO-F1 (Fallback threshold warning)**: If any ApeX REST fallback path is invoked more than **3 times per 5 minutes** (per reason), the system MUST emit a structured warning log and increment a health counter indicating degraded mode.

## 5) Requirements

### 5.1 Stream Health Endpoint Parity (`/api/stream/health`)

`GET /api/stream/health` already exists and returns `{"venue": ..., ...}` using `gateway.get_stream_health_snapshot()` when available.

Requirement: ApeX gateway MUST implement `get_stream_health_snapshot()` with a payload schema compatible with Hyperliquid’s snapshot (superset allowed).

Minimum fields (parity set already displayed by UI and/or useful for diagnostics):
- `ws_alive` (bool)
- `last_private_ws_event_age_seconds` (number|null)
- `reconcile_count` (int)
- `last_reconcile_age_seconds` (number|null)
- `last_reconcile_reason` (string|null)
- `last_reconcile_error` (string|null)
- `reconcile_reason_counts` (object: string → int)
- `pending_submitted_orders` (int; may be 0 for ApeX if not tracked)

ApeX-specific additions (recommended):
- `fallback_rest_orders_used_count`
- `fallback_rest_positions_used_count`
- `empty_snapshot_protected_count` (times empty snapshots were ignored due to staleness thresholds)
- `tpsl_symbols_tracked` (int)
- `tpsl_flap_suspected_count` (int)

### 5.2 Reason-Based Reconcile Triggers + Anti-Storm Min Gap

Port Hyperliquid’s reconciliation posture to ApeX:

- Reconcile triggers MUST be reason-based, increment counters, and update `last_reconcile_reason`.
- Reconcile MUST respect `APEX_RECONCILE_MIN_GAP_SECONDS` (anti-storm).
- Reconcile MUST be disabled or degraded gracefully when WS is disabled (defined below).

Candidate reasons (exact set to be decided, but must be finite and named):
- `periodic_audit` (infrequent)
- `ws_stale` (no private WS events for threshold duration while open state exists)
- `ws_reconnect` (after reconnect/resubscribe)
- `tpsl_inconsistent` (positions exist but TP/SL map appears incomplete vs recent known good)
- `orders_empty_suspicious` / `positions_empty_suspicious` (empty snapshots that contradict recent state)
- `user_requested` (explicit resync endpoint if retained)

Reconcile data sources (ApeX):
- **Primary**: private WS `ws_zk_accounts_v3` `orders` payload for active TP/SL discovery.
- **Fallback verification**: `GET /v3/history-orders` as a bounded, reason-driven verification source for TP/SL lifecycle (e.g., post-fill/post-trigger confirmation) when WS payloads appear inconsistent. Documented in `docs/api/Apex/apex_api_cheatsheet.md`.

#### WS-Disabled Mode (Defined)

When ApeX venue WebSockets are disabled (`APEX_ENABLE_WS=false`), the system MUST enter an explicit degraded mode that is still operational:

- The app’s own `/ws/stream` remains the UI transport, but it is fed by **periodic REST polling**.
- Poll cadence (initial defaults; tunable):
  - orders: every **5 seconds**
  - positions: every **5 seconds**
  - account summary: every **15 seconds**
- Health behavior:
  - `ws_alive=false`
  - health snapshot MUST include the poll cadence (recommended additional fields: `poll_orders_interval_seconds`, `poll_positions_interval_seconds`, `poll_account_interval_seconds`)
- Alerting behavior:
  - entering WS-disabled mode MUST emit a structured warning log (once per process start, rate-limited)
  - fallback/reconcile warning thresholds (SLO-F1) still apply

Guarantees in WS-disabled mode:
- Order/position views converge to REST truth within the poll cadence.
- TP/SL visibility follows the TP/SL state machine rules (retention + authoritative removal); if active TP/SL cannot be discovered without WS, the UI must continue to show last-known-good targets and mark reconciliation as degraded in health counters (no silent blanking).

### 5.3 Split: Open Entry Orders vs TP/SL Representation

We must keep two independent conceptual streams:

1) **Open entry orders feed** (shown in “Open Orders” UI)
   - excludes TP/SL helper orders
   - stable IDs and statuses

2) **TP/SL representation**
   - derived from authoritative account-level data about protective orders
   - represented in positions table as `take_profit` / `stop_loss`
   - preserves “last known good” targets under partial/empty snapshots until authoritative removal

Requirement: ApeX WS/event handlers and the `/ws/stream` fanout must not accidentally use the TP/SL-only payload as the open-orders UI feed.

#### TP/SL State Machine (Required)

To prevent flapping under race conditions, TP/SL state MUST follow an explicit precedence + freshness rule set per `symbol`:

**State tracked (conceptual)**
- `tp_value`, `sl_value`
- `tp_source`, `sl_source` ∈ `{local_hint, ws_orders_raw, rest_history, unknown}`
- `tp_observed_at`, `sl_observed_at` (timestamps)
- `tp_removed_at`, `sl_removed_at` (timestamps, optional)

**Source precedence (highest → lowest)**
1) `local_hint` (immediately after `/api/positions/{id}/targets` returns success)
2) `ws_orders_raw` (private WS account orders payload; primary truth for active protections)
3) `rest_history` (`/v3/history-orders`; verification/supporting evidence only)

**Freshness / expiry**
- `local_hint` is provisional and must expire if not confirmed by `ws_orders_raw` within a bounded window (default: **20 seconds**). After expiry, the displayed value must revert to `ws_orders_raw` (or remain last-known-good if WS is degraded), and health should record a “hint_unconfirmed” reason counter.
- If `ws_orders_raw` provides a newer, explicit contradiction to a `local_hint` (e.g., different TP/SL value or clear absence of the hinted target type in a full snapshot), WS wins immediately; do not wait for hint expiry.

**Authoritative removal conditions**
TP or SL may be cleared (set to `None`) ONLY if at least one of the following holds:
- WS explicitly indicates the relevant TP/SL protective order is **canceled/filled/triggered**, OR
- A “full snapshot” (as defined in the decision record) confirms there is no active TP/SL of that type for the symbol AND the last-known-good value is older than a configured grace window (default: **10 seconds**), OR
- `/v3/history-orders` provides confirming evidence of TP/SL lifecycle completion (filled/triggered/canceled) AND WS (if enabled) no longer shows an active protective order after a grace window.

**Tie-breaker rules**
- When two sources provide conflicting non-empty values for the same target type, choose the higher-precedence source **unless** the lower-precedence value is newer by an “unreasonable” margin (to be defined in the decision record). Default tie-breaker: most recent `updatedAt/createdAt` when available, otherwise most recent `observed_at`.

### 5.4 Apex REST Fallback Policy (Explicitly “Fallback”)

ApeX has venue-specific fallbacks (REST reads, “empty snapshot stale” protection windows, retry/backoff).

Requirements:
- Fallback behavior MUST be explicitly scoped as fallback:
  - triggered only when needed (reason-based)
  - bounded by thresholds (stale window, min gap)
  - visible in logs + `/api/stream/health` counters
- The system MUST emit structured warning logs when fallback becomes frequent, using alert windows similar to Hyperliquid:
  - max-per-window thresholds
  - include reason and count

Reference:
- ApeX API cheat sheet (including `GET /v3/history-orders` note): `docs/api/Apex/apex_api_cheatsheet.md`

## 6) Observability Requirements (Parity + Actionability)

### Logs
All reconcile and fallback events must produce structured logs with at least:
- `venue="apex"`
- `event` name (e.g., `apex_reconcile_completed`, `apex_fallback_rest_used`)
- `reason`
- `duration_ms`
- `orders_count`, `positions_count`
- relevant staleness ages and counters

### Health Snapshot
Health snapshot must be usable for:
- alerting (even if external alerting is not wired yet)
- debugging “TP/SL disappeared” incidents post-facto

## 7) Phased Plan (Decisions First → Incremental Implementation)

### Phase 0 — Decision Records + Measurement Plan
Deliverables:
- Decision records in `docs/decisions/`:
  - `docs/decisions/apex_stability/0006-stream-health-schema.md`: exact `get_stream_health_snapshot()` schema for ApeX + invariants
  - `docs/decisions/apex_stability/0005-reconcile-triggers-and-data-sources.md`: reconcile reasons, thresholds, and min-gap behavior
  - `docs/decisions/apex_stability/0001-tpsl-authority-state-machine.md`: authoritative TP/SL selection rules + “last known good” retention policy
  - `docs/decisions/apex_stability/0004-open-orders-vs-tpsl-helpers.md`: rule for what appears in Open Orders vs what counts as TP/SL helper orders
  - `docs/decisions/apex_stability/0002-stability-slos-and-alerts.md`: measurable SLOs and warning thresholds
  - `docs/decisions/apex_stability/0003-ws-disabled-degraded-mode.md`: WS-disabled operational mode definition
- Measurement plan:
  - what counters/logs define “no manual refresh required”
  - what indicates TP/SL flapping (and how we detect it)

Acceptance:
- Team alignment on outcomes + “what we will measure”.

### Phase 1 — Stream Health Parity for ApeX
Deliverables:
- ApeX implements `get_stream_health_snapshot()` with parity fields and counters.
- `/api/stream/health` provides meaningful ApeX diagnostics (not just venue name).

Acceptance:
- Health snapshot fields populate on ApeX with WS enabled and WS disabled.

### Phase 2 — Reconcile Discipline (Reason Triggers + Anti-Storm)
Deliverables:
- Remove/disable any tight reconcile loops that act as the primary mechanism.
- Implement reason-based reconcile triggers and `APEX_RECONCILE_MIN_GAP_SECONDS`.
- Add reason counters and alert-window warnings.

Acceptance:
- Under normal WS-healthy conditions, reconcile runs at or below **SLO-R1** (≤ 1 per 15 minutes) and never violates **SLO-R2**.
- Under WS disconnect/reconnect, reconcile runs predictably, respects min-gap, and does not exceed **3 per 5 minutes**.

### Phase 3 — TP/SL Correctness Hardening
Deliverables:
- Enforce “last known good TP/SL retention” under partial/empty snapshots.
- Ensure TP/SL removal only on authoritative removal signals.
- Ensure Open Orders feed never regresses due to TP/SL-only payloads.

Acceptance:
- TP/SL “blanking” regressions are eliminated:
  - **SLO-A1** holds in targeted tests and disconnect/reconnect simulations.
  - `tpsl_flap_suspected_count` does not increment under normal conditions.
- “Modify targets” convergence meets **SLO-A2**.
- UI shows correct TP/SL without manual refresh when WS is enabled and healthy.

### Phase 4 — Fallback Tightening + Alerts
Deliverables:
- Scope Apex-specific REST fallbacks as true fallback with explicit thresholds.
- Implement alert-window logs when fallbacks become frequent.

Acceptance:
- Frequent fallback is visible (counters + logs) and actionable, and **SLO-F1** warning thresholds produce alerts as designed.

## 8) Testing Plan (Outcome-Oriented)

### Targeted automated tests
- “TP/SL never disappears” regression tests using recorded payload sequences:
  - partial snapshots
  - canceled-only updates
  - empty snapshots inside stale window
  - reconnect sequences
- “Open orders vs TP/SL split” tests:
  - ensure TP/SL helpers never show in open orders UI feed

### Manual verification
- Enable WS for ApeX; open a position; set TP/SL; observe:
  - TP/SL stays visible for extended period
  - no manual refresh needed during normal operation
  - health endpoint shows ws alive and low reconcile count

## 9) Configuration (Proposed Additions)

To mirror Hyperliquid’s reconcile tunables, introduce ApeX equivalents (names to be finalized in decision records):
- `APEX_RECONCILE_AUDIT_INTERVAL_SECONDS`
- `APEX_RECONCILE_STALE_STREAM_SECONDS`
- `APEX_RECONCILE_MIN_GAP_SECONDS`
- `APEX_RECONCILE_ALERT_WINDOW_SECONDS`
- `APEX_RECONCILE_ALERT_MAX_PER_WINDOW`

Existing ApeX fallback tunables remain but must be treated as fallback and surfaced in health:
- `APEX_POSITIONS_EMPTY_STALE_SECONDS`
- `APEX_ORDERS_EMPTY_STALE_SECONDS`

## 10) Open Questions

1) What exact ApeX WS payload patterns caused TP/SL “disappears” incidents (partial snapshots vs canceled-only vs ordering)?
2) What staleness thresholds are acceptable for ApeX given current API reliability (and what is the operator tolerance for delayed convergence)?

Resolved direction (not an open question):
- TP/SL helper orders MUST NOT appear in the “Open Orders” table; they are represented only via TP/SL targets on positions.
