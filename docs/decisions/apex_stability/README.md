# Decision Records (ApeX Stability)

This folder contains formal decision records for the ApeX stability workstream (TP/SL correctness + observability parity).

## Rules

- Any non-trivial architectural / behavioral choice that affects TP/SL correctness, reconciliation, fallback behavior, or observability must have a decision record here.
- A decision record should be created **before** (or in the same PR as) the first implementation that depends on it.
- Use the template in `docs/decisions/apex_stability/0000-template.md`.

## Proposed decisions in this folder

- **0001** TP/SL authority + state machine precedence.
- **0002** Stability SLOs + alert thresholds (measurable acceptance).
- **0003** WS-disabled degraded mode definition.
- **0004** Open orders vs TP/SL helpers (hard split).
- **0005** Reconcile triggers + anti-storm + data sources (incl. `/v3/history-orders` as supplemental verification).
- **0006** Stream health schema parity for ApeX.

