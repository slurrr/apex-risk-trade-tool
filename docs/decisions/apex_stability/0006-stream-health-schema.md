# Decision Record: ApeX Stream Health Schema Parity

**ID**: 0006-stream-health-schema  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The UI includes a dev diagnostics panel that polls `GET /api/stream/health`. Hyperliquid provides a rich snapshot including reconcile counters and reason counts. ApeX must provide equivalent observability so operators can detect degraded mode and diagnose TP/SL issues without guesswork.

## Decision

ApeX gateway must implement `get_stream_health_snapshot()` returning a schema compatible with Hyperliquid’s snapshot (superset allowed), including:

- `ws_alive` (bool)
- `last_private_ws_event_age_seconds` (number|null)
- `reconcile_count` (int)
- `last_reconcile_age_seconds` (number|null)
- `last_reconcile_reason` (string|null)
- `last_reconcile_error` (string|null)
- `reconcile_reason_counts` (object: string → int)
- `pending_submitted_orders` (int; 0 if not tracked)

Recommended ApeX-specific additions:
- `fallback_rest_orders_used_count`
- `fallback_rest_positions_used_count`
- `empty_snapshot_protected_count`
- `tpsl_symbols_tracked`
- `tpsl_flap_suspected_count`
- WS-disabled poll cadence fields when `APEX_ENABLE_WS=false`

## Options Considered

### Option A — Minimal health endpoint (venue only)
- Pros: minimal work.
- Cons: not actionable; no parity; hard to debug ops issues.

### Option B — Parity schema with counters (chosen)
- Pros: actionable; supports alerting; aligned with HL patterns.
- Cons: requires maintaining counters and careful redaction.

## Consequences

- Logs and counters must not leak secrets or sensitive identifiers.
- The diagnostics panel becomes a reliable first-line tool for ops.

## Validation Plan

- Manual: with ApeX active, enable dev panel and confirm fields populate and update.
- WS-disabled: confirm `ws_alive=false` and poll cadence fields appear.
- Reconcile trigger: confirm counters increment and `last_reconcile_reason` changes.

