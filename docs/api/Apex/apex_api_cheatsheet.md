# ApeX Omni API Cheat Sheet (REST + WebSockets)

Version: draft v1.0 for `apex-risk-trade-tool`\
Scope: REST trading endpoints (v3) + key WebSocket topics (public +
private)

## 1. Base URLs & Versions

### REST base endpoints

-   **Testnet:** `https://testnet.omni.apex.exchange/api/`
-   **Mainnet:** `https://omni.apex.exchange/api/`
-   All trading endpoints are under **`/v3/...`**.

### WebSocket endpoints

Add a `timestamp` query param with current unix ms.

**Testnet:**

-   Public:
    `wss://qa-quote.omni.apex.exchange/realtime_public?v=2&timestamp=<ts>`
-   Private:
    `wss://qa-quote.omni.apex.exchange/realtime_private?v=2&timestamp=<ts>`

**Mainnet:**

-   Public:
    `wss://quote.omni.apex.exchange/realtime_public?v=2&timestamp=<ts>`
-   Private:
    `wss://quote.omni.apex.exchange/realtime_private?v=2&timestamp=<ts>`

## 2. Authentication & Signing

### API key signature

Headers:

-   `APEX-SIGNATURE`
-   `APEX-TIMESTAMP`
-   `APEX-API-KEY`
-   `APEX-PASSPHRASE`

Signature:\
`message = timestamp + method + request_path + dataString`\
Signed with HMAC-SHA256 using base64-encoded secret.

### zkKeys signature

Used for order signing; handled by the SDK.

## 3. Symbols, Path & Parameter Conventions

-   REST uses camelCase.
-   Symbols usually `"BTC-USDT"` for REST; `"BTCUSDT"` for WS.
-   Timestamps: unix ms.

## 4. Account & Balance Endpoints

### GET `/v3/account`

Returns ethereum address, wallets, positions, contract account details.

### GET `/v3/account-balance`

Lightweight:\
- `totalEquityValue`\
- `availableBalance`\
- `initialMargin`, `maintenanceMargin`

### POST `/v3/set-initial-margin-rate`

Set custom leverage.

## 5. Order & Trading Endpoints (REST)

### POST `/v3/order` --- Create order

Required fields: - `symbol`, `side`, `type`, `size`, `price`,
`limitFee`, `expiration`, `clientOrderId`, `signature`

Optional: - `timeInForce` - `triggerPrice` - `trailingPercent` -
`reduceOnly`

Returns full order object with fields like `id`, `status`, `size`,
`price`, fill aggregates, TP/SL flags.

### POST `/v3/delete-order`

Body: - `id`: orderId

Returns: `{ "data": "<id>" }`

### POST `/v3/delete-client-order-id`

Body: - `id`: clientOrderId

#### TP/SL specifics (position protections)

- **Source of truth**: private WS `ws_zk_accounts_v3` `orders` payload; only entries with `isPositionTpsl=true` and type starting `STOP_` or `TAKE_PROFIT_` are used. REST snapshots are not used for TP/SL data.
- **Supplemental verification**: `GET /v3/history-orders` may include TP/SL-related fields for *historical* orders (e.g., after fills/triggers). Use it as a bounded, fallback corroboration/backfill signal (never a sole removal trigger), not as the primary source of active TP/SL discovery.
- **Create**: reduce-only TP = `TAKE_PROFIT_MARKET`, SL = `STOP_MARKET`; keep one active TP and one active SL per symbol.
- **Cancel**: `POST /api/v3/delete-order` (body `id`) or `POST /api/v3/delete-client-order-id` (body `id`). Apex code `20016` (“already canceled”) is treated as success.
- **Partial payloads**: merge active TP/SL entries across snapshots; canceled TP/SL entries remove only that side of the cache.
- **Backend UI flow**: `/api/positions/{position_id}/targets` accepts `take_profit`, `stop_loss`, `clear_tp`, `clear_sl`; clears cancel cached TP/SL ids from `orders_raw` and only clear locally when the exchange cancel succeeds.

### GET `/v3/open-orders`

Returns array of order objects.

Order status enums: - `PENDING`, `OPEN`, `FILLED`, `CANCELED`,
`EXPIRED`, `UNTRIGGERED`

### POST `/v3/delete-open-orders`

Cancels all or all for given symbols.

### GET `/v3/history-orders`

Order history endpoint.

- Use as **supplemental** reconciliation support when TP/SL state appears inconsistent (particularly for post-fill / post-trigger verification).
- Do not rely on this endpoint as the primary source of *active* TP/SL orders; private WS remains the source of truth for active protections.

### GET `/v3/get-worst-price`

Returns `worstPrice`, `bidOnePrice`, `askOnePrice`.

## 6. Public WebSocket Topics

### Order Book --- `orderBook{25|200}.{H|M}.{SYMBOL}`

Snapshot/delta messages with bids, asks, checksum.

### Trades --- `recentlyTrade.{H|M}.{SYMBOL}`

Trade snapshots: price, size, direction, timestamps.

### Ticker --- `instrumentInfo.{H|M}.{SYMBOL}`

Snapshot/delta with lastPrice, 24h stats, funding, oracle/index price,
open interest.

## 7. Private WebSocket --- `ws_zk_accounts_v3`

Pushes: - orders (lifecycle updates) - positions - contractWallets -
spotWallets - fills

Supports `snapshot` & `delta`.

## 8. Enums Reference

### Order Types

-   `LIMIT`, `MARKET`, `STOP_LIMIT`, `STOP_MARKET`, `TAKE_PROFIT_LIMIT`,
    `TAKE_PROFIT_MARKET`

### Status

-   `PENDING`, `OPEN`, `FILLED`, `CANCELED`, `EXPIRED`, `UNTRIGGERED`

### Cancel Reasons

-   `EXPIRED`, `USER_CANCELED`, `COULD_NOT_FILL`,
    `REDUCE_ONLY_CANCELED`, `LIQUIDATE_CANCELED`, `INTERNAL_FAILED`

### TIF

-   `GOOD_TIL_CANCEL`, `FILL_OR_KILL`, `IMMEDIATE_OR_CANCEL`,
    `POST_ONLY`

## 9. Implementation Notes

-   Wrap API in `ApexClient`.
-   Always pass `price` for MARKET orders (use `get-worst-price`).
-   Use WS (`ws_zk_accounts_v3`) for authoritative order/position
    updates.
-   Normalize symbols internally.
-   Parse numerics with `Decimal`.

*(End of Cheat Sheet v1.0)*
