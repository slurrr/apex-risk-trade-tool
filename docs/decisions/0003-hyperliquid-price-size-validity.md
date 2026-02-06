# Decision Record: Hyperliquid Price/Size Validity Strategy

**ID**: 0003-hyperliquid-price-size-validity  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The risk engine assumes:
- prices round to a `tickSize`
- sizes round down to a `stepSize`

ApeX provides `tickSize` and `stepSize` directly. Hyperliquid may enforce different price/size validity rules (e.g., decimal limits, significant-figure constraints, instrument-specific increments).

We must ensure that:
- sizing previews match what can actually be placed
- execute requests do not fail due to avoidable “invalid price/size” rejections

## Decision

- For Hyperliquid, the gateway will provide **best-effort** `tickSize` and `stepSize` equivalents derived from HL instrument metadata for use by:
  - UI precision hints (`/api/symbols`)
  - risk engine rounding
- Additionally, Hyperliquid order placement will include a **venue-specific validity layer**:
  - validate price/size against HL rules right before submission
  - if invalid, adjust to the nearest valid value in a conservative direction:
    - size: round down to valid increment
    - price: round to nearest valid price increment that does not increase risk unexpectedly
  - return a warning in the execute response if an adjustment was made
- If HL metadata is insufficient to derive safe increments, the gateway will:
  - still validate and format on submit, and
  - return a preview warning that the venue may adjust price/size at execution time

## Options Considered

### Option A — Pretend HL has `tickSize`/`stepSize` and ignore validity beyond rounding
- Pros: simplest.
- Cons: likely order rejections; preview/execute mismatch; poor UX.

### Option B — Keep risk engine unchanged; do all validity in gateway at submit time (chosen)
- Pros: minimal churn to risk engine; correctness concentrated at venue boundary.
- Cons: previews may diverge slightly unless we also provide “equivalent” increments; requires warnings.

### Option C — Make risk engine venue-aware and encode HL rules there
- Pros: preview could perfectly match execution.
- Cons: pollutes pure risk module with venue rules; larger refactor.

## Consequences

- The gateway becomes responsible for “final-form” price/size formatting for HL.
- Execute responses may contain venue adjustment warnings; UI should display them prominently (already supports warnings).
- Tests must cover edge cases where HL rejects values unless formatted precisely.

## Validation Plan

- Unit tests for HL formatter/validator:
  - given instrument metadata, formatting produces accepted values
  - rounding direction is conservative
- Integration script:
  - attempt to place orders at boundary precision values and confirm acceptance/rejection patterns
- Manual:
  - verify preview values match execution values within expected rounding bounds; warnings appear if adjusted.

