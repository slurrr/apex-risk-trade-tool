# Data Model

## AccountSummary
- Fields: total_equity (decimal), total_upnl (decimal, signed), available_margin (decimal), as_of (datetime optional).
- Rules: uPNL sign drives red/green coloring; values must be non-negative except uPNL which may be negative; refresh should not block UI rendering.

## Symbol
- Fields: code (string, pattern `^[A-Z0-9]+-[A-Z0-9]+$`), base_asset (string optional), quote_asset (string optional), status (active/disabled optional).
- Rules: code is unique and required; only active symbols populate the dropdown list.

## TradeForm
- Fields: symbol (Symbol.code), risk_pct (decimal 0–100), entry_price (>0), stop_price (>0), take_profit (>0 optional), side (enum: long|short).
- Rules: risk_pct required; stop must be a valid protective level; take_profit optional; form layout locks pairings per row (Symbol+Risk%, Entry+Stop, Take Profit+Side).

## Order (open orders view)
- Fields: id (string), symbol (Symbol.code), side (enum), size (decimal), entry_price (decimal), status (string), created_at (datetime).
- Rules: list view shows Symbol and Entry; internal IDs may still exist but are not displayed.

## Position
- Fields: id (string), symbol (Symbol.code), side (enum), size (decimal), entry_price (decimal), take_profit (decimal or null), stop_loss (decimal or null), leverage (optional), unrealized_pnl (optional), available_to_close_pct (0–100).
- Rules: manage actions operate on this entity; tp/sl may be null; percent close cannot exceed available_to_close_pct.

## PositionCloseRequest
- Fields: position_id (string), close_percent (0–100), close_type (enum: market|limit), limit_price (decimal, required iff close_type=limit).
- Rules: close_percent may be 0 or 100; limit_price must be >0 when provided; request applies only to the specified position.

## TargetsUpdateRequest
- Fields: position_id (string), take_profit (decimal optional), stop_loss (decimal optional).
- Rules: At least one of take_profit or stop_loss must be provided; empty fields must not clear existing targets; validation prevents no-op submissions.

## DisplayContext (UI-only)
- Fields: viewport_width (int), viewport_breakpoint (phone/tablet/desktop), orientation (portrait|landscape), theme (light|dark).
- Rules: drives layout reflow and theming; does not persist server-side.
