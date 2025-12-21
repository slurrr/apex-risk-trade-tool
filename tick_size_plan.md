# Plan

  Allow entry/stop/TP fields to accept valid prices for all symbols (including low-priced alts like 1000PEPE-USDT at 0.00409) without HTML
  “Please enter a valid value” errors, while still respecting per-symbol tick sizes on the backend and avoiding cases where entry and stop
  collapse to the same rounded price.

## What’s happening today

- UI constraints
  - ui/index.html:40+ sets:
    - entry_price, stop_price, tp as type="number" step="0.0001".
  - Browsers enforce that value must be a multiple of step (relative to min/default), otherwise they show “Please enter a valid value” and block form submit.

  - 0.00409 is not a multiple of 0.0001 (it has 5 decimals), so the browser rejects it before the request ever hits the API.
  - ui/js/app.js has snapToInputStep(value, input) which:
    - Reads the step attribute, snaps values (like prefilled prices) to a multiple of step, and formats them to that many decimals.
    - So the current 4-decimal step is baked into both validation and auto-fill rounding.
- Backend constraints
  - backend/trading/schemas.py:TradeRequest just enforces numeric > 0; no decimal limit.
  - backend/risk/risk_engine.py:
    - Pulls per-symbol tickSize and stepSize from symbol_config.
    - _round_price(value, tick) rounds entry/stop to the symbol’s tick.
    - If entry_price_rounded == stop_price_rounded, it raises PositionSizingError("Stop price equals entry price.").
  - backend/exchange/exchange_gateway.py:
    - Loads exchange configs with per-symbol tickSize, stepSize, etc.
  - backend/trading/order_manager.py:list_symbols:
    - Exposes /api/symbols as SymbolResponse with code/base_asset/quote_asset/status only — no tick/step metadata reaches the UI.

  Conclusion on “same decimals for all symbols”

- The exchange constraints are per-symbol (tickSize/stepSize differ), so the true set of acceptable prices is symbol-dependent.
- However, the backend already tolerates arbitrary decimals and then rounds to per-symbol tickSize.
- The “Please enter a valid value” issue is purely a frontend HTML step constraint, not a backend one.
- So:
  - We can safely let the UI accept a uniform maximum precision (e.g., 6–8 decimals or effectively unlimited) and let the backend enforce        symbol-specific tick sizes.
  - We don’t have to enforce per-symbol precision on the UI just to keep the exchange happy.

## Requirements

- Allow values like 0.00409 for 1000PEPE-USDT without HTML validation errors.
- Avoid regressions for symbols that currently work (e.g., BTC-USDT, DOGE-USDT).
- Keep backend tickSize/stepSize enforcement as the source of truth.
- Minimize user confusion when rounding causes stop_price to equal entry_price.
- Prefer a solution that doesn’t require hand-curating symbol metadata in the UI.

## Scope

- In
  - Frontend entry/stop/tp input behavior and HTML attributes.
  - How the UI chooses/uses step and formats prefilled prices.
  - (Optionally) enriching /api/symbols with tick/precision metadata.
- Out
  - Changing the core risk engine sizing math.
  - Changing actual exchange tickSize/stepSize configs.
  - Non-price-related validations (risk %, size caps, etc.).

## Files and entry points

- ui/index.html – current input[type=number] for entry_price, stop_price, tp.
- ui/js/app.js – snapToInputStep, prefillEntryPrice, loadSymbols, state.symbols.
- ui/js/preview.js & ui/js/execute.js – how entry/stop/TP values are read and sent.
- backend/trading/schemas.py – TradeRequest & AtrStopRequest.
- backend/risk/risk_engine.py –_round_price, calculate_position_size, tick handling.
- backend/exchange/exchange_gateway.py – where tickSize and stepSize are loaded.
- backend/trading/order_manager.py – list_symbols shaping the /api/symbols payload.

## Data model / API changes (optional)

- Extend /api/symbols to carry precision metadata:
  - Either raw: tick_size, step_size.
  - Or derived: price_decimals, size_decimals.
- This would let the UI:
  - Set step and formatting based on the selected symbol.
  - Potentially show better error messages when a price is off-tick.

## Action items

  1. Confirm exchange precision boundaries
      - Inspect a sample of symbol configs from ApeX (via load_configs) to determine:
          - Minimum tickSize across markets.
          - Typical decimal ranges (e.g., 2, 4, 5, 6+ decimals).
      - Decide a safe “max decimals” we want the UI to support (e.g., 6 or 8) that covers all current and likely future markets.
  2. Decide UI precision strategy

     Option 1 – Global max precision (simpler, likely enough)
      - Set all price-related inputs (entry_price, stop_price, tp) to one of:
          - step="0.00000001" (or similar small power of 10 that covers all ticks), or
          - step="any" to fully disable browser step validation.
      - Let the backend continue to round to symbol tickSize as it does today.
      - Pros:
          - Minimal change.
          - 0.00409 and any other reasonable price will be accepted.
          - No need for the UI to know per-symbol precision.
      - Cons:
          - The arrows will move in extremely small increments (if using a tiny numeric step).
          - The user can still type values that are off-tick; the backend will silently round (as today).

     Option 2 – Per-symbol step from configs (more precise, more moving parts)
      - Extend SymbolResponse and OrderManager.list_symbols to include e.g.:
          - tick_size, step_size, maybe price_decimals derived from tickSize.
      - When the user picks a symbol in the UI:
          - Find the corresponding symbol config in state.symbols.
          - Dynamically set entry_price.step, stop_price.step, and tp.step to the symbol’s tick_size.
          - Optionally override step for particularly ill-behaved markets (e.g., set a smaller step but still snap to tick on submit).
      - Update snapToInputStep to:
          - Use the per-symbol step as before for prefilled prices.
          - Preserve a reasonable number of decimals in the displayed value (toFixed(price_decimals)).
      - Pros:
          - UI input matches the exact exchange tick for each symbol.
          - Users get consistent behavior between UI increments and actual order increments.
      - Cons:
          - Requires changes to backend schemas, routes, and UI.
          - Slightly more complex testing surface.

     Option 3 – Hybrid
      - Near term: adopt Option 1 (high global precision or step="any") to eliminate the “valid value” errors and support assets like
        1000PEPE immediately.
      - Later: implement Option 2 to align UI steps with per-symbol ticks for a more polished experience.
  3. Handle the “stop equals entry after rounding” case more clearly
      - Keep backend logic that raises PositionSizingError("Stop price equals entry price.").
      - Ensure the UI surfaces that error message clearly to the user (it looks like it already bubbles detail from ErrorResponse — verify
        the message text is visible).
      - Optionally add a small client-side check:
          - Once we know the symbol’s tick (if Option 2 is adopted), warn when abs(entry - stop) < tick and suggest a wider stop.
  4. Update UI behavior around auto-fill and formatting
      - Ensure prefillEntryPrice(sym.code) uses snapToInputStep such that:
          - For a global small step, it doesn’t introduce weird formatting (e.g., avoid scientific notation).
          - For per-symbol step, it formats to the correct number of decimals.
      - Double-check that ATR stop auto-fill in ui/js/preview.js behaves sensibly with updated precision:
          - It reads numeric values with parseFloat; this is already tolerant of extra decimals.
  5. Testing and validation plan
      - Backend tests
          - Extend backend/tests/test_risk_engine.py to include:
              - A symbol with a very small tick size where entry and stop differ by one or two ticks; ensure they don’t collapse.
              - A case where they do collapse and the error "Stop price equals entry price." is raised.
      - UI manual test matrix
          - For a high-priced symbol (e.g. BTC-USDT):
              - Enter entry and stop with both coarse and fine decimals; confirm the form submits and backend rounds sensibly.
          - For a mid-priced symbol (e.g. DOGE-USDT):
              - Use typical tick decimals; verify no HTML “valid value” errors.
          - For a low-priced symbol (e.g. 1000PEPE-USDT at ~0.00409):
              - Type 0.00409 for entry and a slightly lower stop; ensure:
                  - Browser accepts the input.
                  - Backend does not reject due to rounding unless they’re truly too close.
                  - If rejected, the UI shows the “Stop price equals entry price” message, not a generic “valid value” error.
          - If per-symbol steps are implemented:
              - Verify that the step attributes change when symbol changes and that increments from the arrows match expected ticks.
  6. Risk and UX considerations
      - Using a very small global step:
          - Might surprise users with many trailing zeros; mitigate by formatting display to a reasonable number of decimals when rendering  
            results.
      - Using step="any":
          - Removes browser-level step validation entirely; makes the UI more flexible but relies entirely on backend + custom JS for
            validation.
      - Per-symbol step:
          - Requires the symbols endpoint to be stable and always populated; handle fallback gracefully (e.g., if symbol metadata is missing,
            fall back to the global max precision step).
