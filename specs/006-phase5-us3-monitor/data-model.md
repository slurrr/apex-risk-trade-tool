# Data Model - Phase 5 User Story 3 Monitor

## Entities

### OrderSummary
- **Fields**:
  - `id` (string, required): canonical order identifier (prefer ApeX `orderId`, fallback to `clientOrderId`).
  - `symbol` (string, required): market symbol (e.g., `BTC-USDT`); must exist in cached configs.
  - `side` (string, required): `BUY` or `SELL`; normalized from ApeX responses.
  - `size` (number, required): base units; non-negative.
  - `price` (number|null): limit/avg price; null when not provided by exchange.
  - `status` (string, required): exchange status/state (`NEW`, `OPEN`, `FILLED`, `CANCELED`, etc.).
- **Relationships**: Linked to `GatewayState.open_orders` cache; cancel actions operate on `OrderSummary.id`.
- **Validation Rules**: `id`, `symbol`, and `side` required; size must be > 0; status must not be empty; secrets must not appear.

### PositionSummary
- **Fields**:
  - `symbol` (string, required): market symbol; must exist in cached configs.
  - `side` (string, required): `LONG`/`SHORT` or `BUY`/`SELL` normalized.
  - `size` (number, required): position size; non-negative.
  - `entry_price` (number|null): average entry; null if unavailable.
  - `pnl` (number|null): unrealized PnL; null if unavailable.
- **Relationships**: Member of `GatewayState.positions` cache; informs open-risk estimates maintained by order manager.
- **Validation Rules**: symbol/side required; size > 0; no secrets or account identifiers.

### CancelRequest / CancelResponse
- **Fields**:
  - Request: `order_id` (string, required) supplied via path; maps to `OrderSummary.id`.
  - Response: `canceled` (bool), `order_id` (string), `raw` (object, optional for debugging), `error` (string, optional).
- **Relationships**: Mutates `GatewayState.open_orders` and `GatewayState.open_risk_estimates` after successful cancellation; triggers `refresh_state`.
- **Validation Rules**: order_id must be non-empty; response should mirror requested ID; errors must be structured and secret-free.

### GatewayState
- **Fields**:
  - `configs` (dict[symbol -> config]): loaded via ApeX public API; required before monitor calls.
  - `open_orders` (list[OrderSummary]): last fetched open orders; refreshed on monitor or cancel.
  - `positions` (list[PositionSummary]): last fetched positions; refreshed on monitor or cancel.
  - `open_risk_estimates` (dict[order_id -> float]): estimated potential loss for open orders.
  - `daily_realized_loss` (float): carried from execution flows; referenced for caps.
- **Relationships**: Owned by `OrderManager`; read by API routes; updated via gateway helpers.
- **Validation Rules**: configs must exist before monitor responses; caches pruned when exchange omits an order; no sensitive credentials stored.
