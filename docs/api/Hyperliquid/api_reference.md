# Hyperliquid API Scratchpad (Perps)

This file is a **working scratchpad** for the Hyperliquid integration. It is not meant to be perfect or complete; keep it current as the team learns specifics.

- Target: **mainnet**, **perps only**
- Integration spec: `hyperliquid-integration-spec.md`
- Decisions: create formal decision records in `docs/decisions/` for any non-trivial choices.
- Symbol display convention: `COIN-USDC` (e.g., `BTC-USDC`) while mapping to HL instruments by `coin`.

## Known endpoints / URLs (seed)

- WebSocket: `wss://api.hyperliquid.xyz/ws`

## WebSocket quick notes

### Trade prints (public)

- WS: `wss://api.hyperliquid.xyz/ws`
- Subscribe: `{"method":"subscribe","subscription":{"type":"trades","coin":"BTC"}}`

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
