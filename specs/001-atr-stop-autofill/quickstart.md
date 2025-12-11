# Quickstart: Implementing Automatic ATR-Based Stop Loss Prefill

**Feature**: Automatic ATR-Based Stop Loss Prefill  
**Spec**: specs/001-atr-stop-autofill/spec.md  
**Branch**: `001-atr-stop-autofill`

This quickstart outlines the high-level steps to implement and verify ATR-based stop loss prefilling in this repository.

---

## 1. Backend: ATR Calculation and API

1. Add ATR calculation utilities under `backend/risk/` that:
   - Accept a symbol, timeframe, and lookback period.
   - Consume OHLC candles (via existing Apex helpers in `backend/exchange/`).
   - Return an ATR value suitable for use in stop loss derivation.
2. Implement a function that derives a stop loss price from:
   - Entry price.
   - Trade side (long/short).
   - ATR value and multiplier from configuration.
3. Expose a new API route in `backend/api/` (aligned with `/risk/atr-stop` from the OpenAPI contract) that:
   - Validates the request payload (symbol, side, entry_price).
   - Loads ATR configuration (timeframe, period, multiplier) from existing config.
   - Fetches or computes the ATR value.
   - Returns the suggested stop loss price and supporting fields.

## 2. Configuration

1. Introduce or confirm environment/config entries for:
   - `ATR_TIMEFRAME` (or legacy `TIMEFRAME`): candle size (`1m`, `5m`, `15m`, `1h`, etc.).
   - `ATR_PERIOD`: number of candles considered for each ATR calculation.
   - `ATR_MULTIPLIER`: factor applied to ATR when deriving the default stop offset.
2. Wire these values through the existing configuration module in `backend/core/` so they are accessible in the risk layer and API route (already handled by `Settings.atr_*` fields).
3. After changing any ATR env var, restart the FastAPI service (or reload your process supervisor) so `backend/core/config.py` re-reads the new values.

## 3. UI Integration

1. In the UI code under `ui/js/`, hook into the existing logic that:
   - Populates the Entry field when a symbol is selected, and
   - Responds to manual Entry field edits.
2. After the Entry price is known and valid:
   - Call the ATR stop API with symbol, side, and entry price.
   - On success, update the Stop field with the suggested stop loss.
   - On failure or missing ATR data, leave the Stop field editable and show a simple indication that automatic calculation is unavailable.

## 4. Testing & Validation

1. Add unit tests (pytest) for:
   - ATR computation over sample candle sequences.
   - Stop loss calculation for both long and short trades.
2. Add API tests for:
   - Successful ATR stop calculation.
   - Validation errors for invalid input.
   - Behavior when ATR data is unavailable.
3. Manually verify in the UI that:
   - Selecting a symbol populates Entry and then Stop.
   - Editing Entry causes Stop to update.
   - Manual stop overrides are respected and not overwritten unexpectedly.

## 5. Verification Notes

Run (2025-12-11):
- Verified `uvicorn backend.main:app --reload` loads ATR config from `ATR_TIMEFRAME/ATR_PERIOD/ATR_MULTIPLIER` and `/risk/atr-stop` returns calibrated stops for BTC-USDT on testnet.
- Confirmed UI flow: select symbol → Entry auto-prefills (rounded to input step), ATR stop populates within ~1s; editing Entry re-requests ATR and updates Stop unless the user has typed their own stop.
- Simulated degraded data via bogus symbol/timeframe: `/risk/atr-stop` returns 503 with `atr_history_unavailable`, UI clears the stop field and shows “market data unavailable” message while leaving the field editable.
- Manual override test: typed custom stop, subsequent ATR calls (symbol/entry changes) left the manual stop untouched until field cleared, matching US3 behavior.
