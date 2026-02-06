# Decision Records

This folder contains formal decision records for the multi-venue Hyperliquid integration.

## Rules

- Any non-trivial architectural / behavioral choice that affects correctness, safety, or parity must have a decision record here.
- A decision record should be created **before** (or in the same PR as) the first implementation that depends on it.
- Use the template in `docs/decisions/0000-template.md`.

## Suggested Decisions (pre-code candidates)

These can be captured before writing any code:

- **0001** Venue toggle semantics and switching safety (global backend state, locks, stream stop/start, cache reset, failure rollback).
- **0002** Symbol naming + mapping strategy (`BTC-USDT` UI format vs Hyperliquid coin/instrument identifiers).
- **0003** Price/size validity strategy for Hyperliquid (tick/step approximation vs venue-specific formatting/validation layer).
- **0004** Hyperliquid auth model (agent wallet details, signing scheme, env var layout, redaction policy, rotation plan).
- **0005** Idempotency strategy (client order ids / dedupe policy / retry semantics) and error classification.
- **0006** TP/SL model on Hyperliquid (trigger orders representation, one-TP/one-SL rule, reconciliation approach).
- **0007** Streaming strategy (WS topics, event normalization, fallback REST polling/resync, reconnect strategy).
- **0008** Auto entry prefill + ATR stop autofill parity (price source-of-truth and candle/timeframe support).
