# Decision Record: Migration Plan + Feature Flag

**ID**: 0004-migration-feature-flag  
**Date**: 2026-02-06  
**Status**: Accepted  
**Owners**: Backend team  

## Context

This refactor changes a core pipeline (orders → UI + TP/SL). We need safe rollout and rollback.

## Decision

Introduce a feature flag `ORDER_CLASSIFICATION_MODE` that supports:
- shadow mode (canonicalize + classify, but do not change outputs)
- active mode (route `/api/orders` and WS `orders` through classifier)
- fallback mode (revert to legacy behavior if critical regressions are found)

Allowed values:
- `legacy` (default)
- `shadow`
- `v2`

Runtime safety behavior:
- Even when configured `ORDER_CLASSIFICATION_MODE=v2`, the system may automatically switch the **effective** mode to `shadow` temporarily if unknown escalation thresholds persist (see decision `0003-publication-rules`).
- Operators must be able to observe configured vs effective mode via health fields.

Deprecation plan:
- Once verified on both venues, remove legacy classification paths.
- A temporary v2 publication safety guard may remain enabled during tuning; removal is **TBD** until soak gates pass.

## Options Considered

### Option A — Hard cutover
- Pros: fastest.
- Cons: risky; hard to debug; no rollback.

### Option B — Flagged migration (chosen)
- Pros: safer; enables side-by-side comparison; supports incremental rollout.
- Cons: short-term complexity while both paths exist.

## Consequences

- Must define “verified” gate: SLOs around helper leakage, TP/SL convergence, unknown rates.

## Validation Plan

- Shadow mode: log old vs new classification diffs.
- Active mode: run targeted regression scripts and manual checks before removing legacy path.

Ship-block gates (initial):
- `helper_leakage_count == 0` over 8 hours (per venue)
- `unknown_orders_rate_5m < 0.5%` steady state; ship-block at `>= 2%`
- TP/SL convergence p95 ≤ 2s (WS healthy), ≤ 10s (degraded)
- Temporary guard removal gate (TBD):
  - `order_classification_mode_effective = v2` stable through soak
  - `classification_guard_block_count` remains flat at `0` for the agreed soak interval
