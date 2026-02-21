# Decision Records (Order Classification)

This folder contains decision records for the cross-venue order classification refactor (canonical order + shared intent classifier).

## Rules

- Any non-trivial change to canonical order fields, classifier precedence, hint TTLs, or unknown handling must be documented as a decision record here.
- Use the template in `docs/decisions/order_classification/0000-template.md`.

## Proposed decisions

- **0000** Template
- **0001** Canonical internal order schema (`CanonicalOrder`)
- **0002** Intent classifier precedence + hints + unknown policy
- **0003** Publication rules (orders_raw authoritative; discretionary-only open orders)
- **0004** Migration plan and feature flags
- **0005** Hyperliquid endpoint precedence for intent (frontendOpenOrders + orderStatus enrichment)
- **0006** Snapshot-authoritative state + WS-accelerated updates (authority flip)
