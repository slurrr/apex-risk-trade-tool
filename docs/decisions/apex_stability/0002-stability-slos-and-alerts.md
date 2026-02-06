# Decision Record: ApeX Stability SLOs + Alert Thresholds

**ID**: 0002-stability-slos-and-alerts  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The stability spec defines outcomes (no TP/SL disappearance, minimal reconcile) but requires measurable targets so the team can validate improvements and detect regressions.

## Decision

Adopt the following numeric SLOs (initial defaults; tunable later):

### TP/SL display SLOs
- **SLO-A1 (No blank window)**: If a position has last-known-good TP and/or SL, the UI must not display that target as blank/`None` unless an authoritative removal condition is met. (Blank window = **0 seconds**.)
- **SLO-A2 (Post-update convergence)**: After a successful modify-targets action, new TP/SL values must appear in positions UI within:
  - **≤ 2 seconds** when WS is enabled and healthy
  - **≤ 10 seconds** in WS-disabled mode

### Reconcile SLOs
- **SLO-R1 (Normal frequency)**: Under WS-healthy conditions, reconcile should run **≤ 1 per 15 minutes** (excluding reconnect recovery).
- **SLO-R2 (Anti-storm)**: During WS reconnect storms/bursts, reconcile must not exceed **3 per 5 minutes**, and must always honor `APEX_RECONCILE_MIN_GAP_SECONDS`.

### Fallback SLOs
- **SLO-F1 (Fallback warning threshold)**: If any REST fallback path is invoked more than **3 times per 5 minutes** per reason, emit a structured warning log and increment a health “degraded” counter.

## Options Considered

### Option A — No numeric SLOs (qualitative acceptance only)
- Pros: no tuning needed.
- Cons: hard to validate; regressions slip through; no alert thresholds.

### Option B — Hard numeric SLOs with decision-record ownership (chosen)
- Pros: measurable; testable; supports alerting; forces alignment.
- Cons: may need tuning after real-world observation.

## Consequences

- Health endpoints must expose counters necessary to measure these SLOs.
- Test plans must include checks for “no blank window” and bounded reconcile/fallback frequency.

## Validation Plan

- Add test harness sequences that would previously cause flapping; confirm SLO-A1 holds.
- Operational smoke test with WS enabled: confirm reconcile frequency stays within SLO-R1.
- Simulated WS disconnect/reconnect: confirm SLO-R2 and min-gap enforcement.

