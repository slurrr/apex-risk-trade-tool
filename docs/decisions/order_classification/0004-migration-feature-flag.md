# Decision Record: Migration Plan + Feature Flag

**ID**: 0004-migration-feature-flag  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

This refactor changes a core pipeline (orders → UI + TP/SL). We need safe rollout and rollback.

## Decision

Introduce a feature flag (name TBD) that supports:
- shadow mode (canonicalize + classify, but do not change outputs)
- active mode (route `/api/orders` and WS `orders` through classifier)
- fallback mode (revert to legacy behavior if critical regressions are found)

Deprecation plan:
- Once verified on both venues, remove legacy classification paths.

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

