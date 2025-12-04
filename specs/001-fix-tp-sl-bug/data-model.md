# Data Model: Fix TP/SL position updates

## Position
- Fields: id (string), symbol (string, formatted like `BTC-USDT`), side (enum: BUY/SELL), size (decimal), entry_price (decimal), take_profit (decimal or null), stop_loss (decimal or null), pnl (decimal optional).
- Rules: At most one open Position per symbol; size must be >0 for positions to be visible; take_profit and stop_loss represent the effective current protections after merging exchange state and local hints.

## TpslOrder (account stream representation)
- Fields: symbol (string), side (enum: BUY/SELL), type (string, values including `TAKE_PROFIT_MARKET`, `STOP_MARKET`), size (decimal), trigger_price (decimal), price (decimal optional), is_position_tpsl (boolean), reduce_only (boolean), status (string, e.g., `UNTRIGGERED`, `CANCELED`, `TRIGGERED`), client_id (string optional), order_id (string or numeric optional).
- Rules: Only untriggered orders where `is_position_tpsl` is true and type starts with `TAKE_PROFIT_` or `STOP_` participate in the TP/SL mapping; triggered or canceled orders must be ignored for current protections.

## TpslMap (symbol → protection targets)
- Fields: symbol (string) → { take_profit (decimal optional), stop_loss (decimal optional), source (string enum: `stream`, `rest`, `local_hint`) }.
- Rules: Each symbol has at most one take_profit and one stop_loss value; when multiple untriggered orders of the same type exist for a symbol, the most recent is chosen; map is recomputed from the account stream and merged with any temporary local hints until exchange state confirms updates.

## TargetsUpdateRequest
- Fields: position_id (string – path parameter), take_profit (decimal optional), stop_loss (decimal optional), clear_tp (boolean optional), clear_sl (boolean optional).
- Rules: At least one of `take_profit`, `stop_loss`, `clear_tp`, or `clear_sl` must be provided; omitted numeric fields leave existing targets unchanged; `clear_tp=true` removes any active TP for the position regardless of numeric values; `clear_sl=true` removes any active SL; validation must reject no-op requests where nothing would change.

## PositionsResponseRow (UI-facing projection)
- Fields: id (string), symbol (string), side (string), size (decimal), entry_price (decimal), take_profit (decimal or null), stop_loss (decimal or null).
- Rules: `take_profit` and `stop_loss` must never show `None` when the TpslMap holds a valid target for that symbol; when no active protection exists of a given type, the field is null and the UI renders “TP: None” or “SL: None” accordingly.

