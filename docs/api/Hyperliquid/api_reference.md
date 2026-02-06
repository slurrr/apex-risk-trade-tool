# Hyperliquid API Scratchpad (Perps)

This file is a **working scratchpad** for the Hyperliquid integration. It is not meant to be perfect or complete; keep it current as the team learns specifics.

- Target: **mainnet**, **perps only**
- Integration spec: `hyperliquid-integration-spec.md`
- Decisions: create formal decision records in `docs/decisions/` for any non-trivial choices.
- Symbol display convention: `COIN-USDC` (e.g., `BTC-USDC`) while mapping to HL instruments by `coin`.

## Known endpoints / URLs (seed)

- WebSocket: `wss://api.hyperliquid.xyz/ws`
- REST info endpoint: `POST https://api.hyperliquid.xyz/info`

## REST payload notes (validated in code path)

- Symbols/constraints: `{"type":"meta"}`
  - Uses `universe[].name` (coin) and `universe[].szDecimals` for size precision.
- Mid prices: `{"type":"allMids"}`
  - Returns coin→price map; used as primary source for `/api/price/{symbol}` reference prefill.
- L2 book: `{"type":"l2Book","coin":"BTC"}`
  - Returns bid/ask ladders (`levels`) used by `/api/market/depth-summary/{symbol}`.
- Candles: `{"type":"candleSnapshot","req":{"coin":"BTC","interval":"15m","startTime":<ms>,"endTime":<ms>}}`
  - Used by `/risk/atr-stop`; currently mapped for `3m`, `15m`, `1h`, `4h` (and other common intervals).
- Account/positions: `{"type":"clearinghouseState","user":"0x..."}` (used for `/api/account/summary` and `/api/positions`).
- Open orders: `{"type":"openOrders","user":"0x..."}` (used for `/api/orders`).

## Signed exchange actions (implemented)

- Endpoint: `POST /exchange`
- Payload shape:
  - `action`: HL action object (`order`, `cancel`, ...)
  - `nonce`: ms timestamp nonce
  - `signature`: EIP-712 signature (`r`, `s`, `v`)
  - `vaultAddress`: currently `null`
- Current backend coverage:
  - place limit order (GTC)
  - cancel order by numeric order id
  - close position via reduce-only limit or IOC market-style order
  - update targets via trigger reduce-only orders (`tpsl=tp|sl`, `isMarket=true`)
  - clear TP/SL by canceling existing trigger orders by side

## WebSocket quick notes

### Trade prints (public)

- WS: `wss://api.hyperliquid.xyz/ws`
- Subscribe: `{"method":"subscribe","subscription":{"type":"trades","coin":"BTC"}}`

### Backend stream coverage (implemented)

- `allMids` subscription updates the in-memory reference-price cache used by `/api/price/{symbol}`.
- `orderUpdates` subscription is normalized into app events:
  - `orders` (open order table payload)
  - `orders_raw` (raw-ish normalized order updates for TP/SL reconciliation).
- `userEvents` subscription triggers a lightweight snapshot refresh (`orders`, `positions`, `account`) to keep UI state coherent after fills/position changes.

### TODO (fill in during Phase 0)

- User/account stream subscription(s) (auth requirements?)
- Price stream(s): mids / mark / oracle / etc.
- Orderbook stream(s) (L2 book) and snapshot behavior
- Fill/order update stream(s)
- Reconnect + resubscribe rules

## REST quick notes (TODO)

Capture the specific request/response shapes needed by this app:

- Meta / universe (symbols + constraints)
- Reference price (for `GET /api/price/{symbol}`): mid / mark / last trade (confirm best HL source)
- Candle history (supports UI timeframes `3m`, `15m`, `1h`, `4h`)
- L2 orderbook snapshot (for depth summary)
- Account summary (equity/margin/uPNL)
- Open positions
- Open orders
- Place order
- Cancel order
- Place TP/SL trigger orders and cancel them

## Authentication (Agent Wallet) — TODO

Hyperliquid supports an “API wallet / agent wallet” concept (agent private key) for signing requests.

Items to confirm and document here:
- Signing algorithm and payload format
- Nonce/time requirements
- How agent keys map to a master account / subaccount
- WS auth requirements (if any) vs REST-only auth
- Operational rotation plan (revoke/replace agent)

The final chosen approach must be captured as a decision record (see `docs/decisions/`).
