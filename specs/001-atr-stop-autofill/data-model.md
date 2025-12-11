# Data Model: Automatic ATR-Based Stop Loss Prefill

**Feature**: specs/001-atr-stop-autofill/spec.md  
**Branch**: `001-atr-stop-autofill`

This document describes the main conceptual entities, attributes, and relationships relevant to ATR-based stop loss prefilling. It is technology-agnostic and aligns with the feature specification.

---

## Entity: TradeInput

Represents a potential trade being entered through the UI.

- **symbol**: Identifier for the instrument being traded (e.g., `BTCUSDC`).
- **side**: Direction of the trade (`long` / `short`).
- **entry_price**: Price at which the trader intends to enter (auto-populated from latest price or manually edited).
- **quantity**: Size of the position.
- **stop_loss_price**: Proposed stop loss price (automatic ATR-based value or manual override).
- **timestamp**: Time when the trade input was last updated (optional for auditing/testing).

Relationships:

- Uses `ATRConfiguration` to determine how stop loss should be derived.
- May reference `ATRMeasurement` snapshots to justify the automatic stop value.

---

## Entity: ATRConfiguration

Represents configuration for ATR-based risk rules.

- **timeframe**: Chosen candle interval for ATR computation (e.g., `1m`, `5m`, `15m`), managed via runtime configuration.
- **lookback_period**: Number of candles used to compute ATR (e.g., 14).
- **multiplier**: Factor applied to ATR to derive the distance between entry and stop (e.g., 1.5x ATR).
- **symbol_filters** (optional): Rules indicating which symbols are eligible for ATR-based stops if needed later.

Relationships:

- Applied to `MarketCandle` histories to compute `ATRMeasurement`.
- Determines where the automatic stop is placed relative to `TradeInput.entry_price`.

---

## Entity: MarketCandle

Represents a single OHLCV candle used for ATR computation.

- **symbol**: Instrument identifier.
- **timeframe**: Candle interval (must match `ATRConfiguration.timeframe` for this feature).
- **open**, **high**, **low**, **close**: Candle prices.
- **volume** (optional): Traded volume for the interval.
- **start_time**: Start timestamp of the candle.

Relationships:

- A sequence of `MarketCandle` records feeds into the ATR calculation.

---

## Entity: ATRMeasurement

Represents an ATR value calculated for a symbol over a particular timeframe and period.

- **symbol**: Instrument identifier.
- **timeframe**: Candle interval used.
- **period**: Lookback period in candles (should align with `ATRConfiguration.lookback_period`).
- **value**: Calculated ATR numeric value.
- **as_of**: Timestamp indicating when this ATR value was computed or last refreshed.

Relationships:

- Combined with `TradeInput.entry_price` and `ATRConfiguration.multiplier` to derive `CalculatedStopLoss`.

---

## Entity: CalculatedStopLoss

Represents the automatic stop loss suggestion derived from ATR.

- **symbol**: Instrument identifier.
- **side**: `long` / `short` (determines whether stop is below or above entry).
- **entry_price**: Entry price used for calculation.
- **atr_value**: ATR value used for this calculation.
- **multiplier**: ATR multiplier used.
- **stop_loss_price**: Resulting automatic stop price.
- **source**: Indicator of data source and rule version (e.g., `atr_v1`).
- **generated_at**: Timestamp for the calculation.

Relationships:

- Returned to the UI as part of a preview/validation response for the trade.

