# Research & Design Decisions: Automatic ATR-Based Stop Loss Prefill

**Feature**: specs/001-atr-stop-autofill/spec.md  
**Date**: 2025-12-11  
**Branch**: `001-atr-stop-autofill`

This document captures key technical decisions, rationale, and alternatives considered while shaping the implementation plan for ATR-based stop loss prefilling.

---

## Decision 1: Where to compute ATR and stop loss

- **Decision**: Compute ATR and the derived stop loss price in the backend risk layer, not in the UI.
- **Rationale**: Keeps risk logic centralized, testable, and reusable; avoids duplicating calculation logic in the browser; simplifies evolution of the ATR rule without requiring UI changes.
- **Alternatives considered**:
  - Compute ATR entirely in the UI using raw OHLC data from the backend.
  - Depend on a third-party ATR calculation service.

---

## Decision 2: Data source for ATR

- **Decision**: Use Apex market data (REST OHLC endpoint plus, optionally, WS candle stream) as the source for ATR calculations.
- **Rationale**: Aligns with existing Apex integration; avoids introducing a new data provider; keeps latency low by using the same venue that drives entry price population.
- **Alternatives considered**:
  - Use a generic public market data API unrelated to Apex.
  - Pre-compute ATR offline and load from a cache or database.

---

## Decision 3: Configuration of ATR parameters

- **Decision**: Make ATR timeframe, lookback period, and multiplier configurable via runtime configuration (e.g., environment variables loaded through existing config mechanisms).
- **Rationale**: Allows the risk team to adjust sensitivity and timeframe without code changes; matches the specification requirement that these parameters be configurable.
- **Alternatives considered**:
  - Hard-code ATR parameters in code.
  - Provide per-user or per-session overrides in the UI (out of scope for this feature).

---

## Decision 4: Handling missing or delayed ATR data

- **Decision**: If ATR data for the selected symbol and configured timeframe cannot be derived confidently (insufficient candles, connectivity issues, or inconsistent data), do not auto-populate a stop; instead, keep the Stop field editable and clearly indicate that automatic calculation is unavailable.
- **Rationale**: Prevents misleading risk guidance; preserves trader control; aligns with the spec’s “graceful degradation” story.
- **Alternatives considered**:
  - Fall back to a fixed-percentage stop when ATR is unavailable.
  - Reuse stale ATR values beyond a short validity window.

---

## Decision 5: Performance expectations

- **Decision**: Aim for stop loss values to appear within ~1 second of the Entry price being known, under normal market data conditions.
- **Rationale**: Matches the spec’s requirement that the Stop field load “almost instantly,” while providing a concrete latency target for design and testing.
- **Alternatives considered**:
  - No explicit latency target (harder to validate).
  - Stricter latency target (e.g., <200ms), which may not be realistic given external data dependencies.

