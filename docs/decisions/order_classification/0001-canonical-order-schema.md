# Decision Record: Canonical Internal Order Schema

**ID**: 0001-canonical-order-schema  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

Order payloads differ between venues and are sometimes transiently inconsistent (notably for helper legs). The app needs one internal order shape that can drive:
- Open Orders UI
- cancel behavior
- TP/SL representation on positions
- reconciliation and diagnostics

## Decision

Adopt a single canonical internal order schema (`CanonicalOrder`) as described in `order-classification-refactor-spec.md` §5.1, with fields sufficient to:
- represent both discretionary and helper orders
- preserve raw evidence without leaking secrets
- support stable classification

Adapters must map raw WS/REST order rows into this schema.

## Options Considered

### Option A — Keep venue-native dicts and patch per venue
- Pros: minimal refactor.
- Cons: brittle; repeats logic; classification drift; hard to add venues.

### Option B — Canonical schema + shared classifier (chosen)
- Pros: consistent; testable; isolates venue quirks; easier multi-venue support.
- Cons: initial refactor cost; schema governance needed.

## Consequences

- Requires explicit mapping tables and tests per venue.
- Enables “unknown” intent handling to prevent UI pollution.

## Validation Plan

- Unit tests for adapter mapping (raw → canonical).
- Replay captured WS sequences to ensure stable canonicalization.

