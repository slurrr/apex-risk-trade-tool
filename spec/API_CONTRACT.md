# API Contract

## Market Data

### GET /api/market/depth-summary/{symbol}

Returns a depth-of-market liquidity summary for the symbol.

Query params:
- `tolerance_bps` (int): slippage band in bps. Allowed: `5`, `10`, `25`.
- `levels` (int): order book levels to request (clamped to 5-200).

Response:
- `symbol` (string)
- `tolerance_bps` (int)
- `levels_used` (int)
- `bid` (float, nullable)
- `ask` (float, nullable)
- `spread_bps` (float, nullable)
- `max_buy_notional` (float, nullable)
- `max_sell_notional` (float, nullable)
- `as_of` (ISO timestamp)
