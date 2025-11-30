# ApeX Omni API Reference (Testnet-first)

This feature uses the official ApeX Omni Python SDK (`apexomni`). Endpoints are grouped by public (no auth) and private (signed). All examples assume testnet defaults (`APEX_OMNI_HTTP_TEST`, `NETWORKID_OMNI_TEST_BNB` or `NETWORKID_OMNI_TEST_BASE`).

## Public Endpoints (HttpPublic)

### Get Symbol Configs (canonical symbols)
- **Method**: `configs_v3()`
- **Purpose**: Returns tradable instruments and specs (tickSize, stepSize, minOrderSize, maxOrderSize, maxLeverage, status).
- **Notes**: If the response is empty, verify network ID, endpoint, and proxy settings (`trust_env=False`, no proxies). Cache results on startup and refresh on demand.
- **Example (Python)**:
```python
from apexomni.http_public import HttpPublic
from apexomni.constants import APEX_OMNI_HTTP_TEST

public = HttpPublic(APEX_OMNI_HTTP_TEST)
public.client.trust_env = False
public.client.proxies = {"http": None, "https": None}
configs = public.configs_v3()
symbols = [s["symbol"] for s in configs["result"]["symbols"]]
```

### Market Data
- **Order Book**: `depth_v3(symbol, limit=25)` → levels and best bid/ask.
- **Recent Trades**: `trades_v3(symbol, limit=50)` → tape of latest trades.
- **Klines**: `klines_v3(symbol, interval, limit, start, end)` → historical candles.
- **Ticker**: Depending on SDK version, `tickers_v3()` or equivalent to fetch L1 stats.

## Private Endpoints (HttpPrivateSign)

Initialize:
```python
from apexomni.http_private_v3 import HttpPrivateSign
from apexomni.constants import APEX_OMNI_HTTP_TEST, NETWORKID_OMNI_TEST_BNB

client = HttpPrivateSign(
    APEX_OMNI_HTTP_TEST,
    network_id=NETWORKID_OMNI_TEST_BNB,
    zk_seeds="your_seed",
    zk_l2Key="your_l2Key",
    api_key_credentials={"key": API_KEY, "secret": API_SECRET, "passphrase": PASSPHRASE},
)
client.client.trust_env = False
client.client.proxies = {"http": None, "https": None}
```

### Account
- **Get Account**: `get_account_v3()` → equity, balances, positions.
- **Balance-only**: SDK may expose `account_balance_v3()` depending on version.

### Orders
- **Create Order**: `create_order_v3(symbol, side, type, size, price, clientOrderId=..., **flags)`
  - Market orders still require a price (worst-case bound); use top-of-book ± slippage.
  - Stop/TP fields: `isOpenTpslOrder=True`, `isSetOpenSl=True` with `slPrice`/`slTriggerPrice`, `isSetOpenTp=True` with `tpPrice`.
- **Open Orders**: `open_orders_v3(symbol=None)` → list current open orders.
- **Cancel by ID**: `delete_order_v3(orderId=...)`.
- **Cancel by clientOrderId**: `delete_order_by_client_order_id_v3(clientOrderId=...)` (if available).
- **Cancel All (symbol)**: `delete_open_orders_v3(symbol="BTC-USDT")`.
- **Order History**: SDK exposes history endpoints (e.g., `history_orders_v3`); use for fills and audits.

### Positions & Fills
- **Positions**: via `get_account_v3()` positions list.
- **Fills**: `fills_v3(symbol=None, limit=50, ...)` for recent executions.

## WebSocket Subscriptions

### Private WS (portfolio/orders)
- **Endpoint**: `APEX_OMNI_WS_TEST` (or mainnet).
- **Channel**: `ws_zk_accounts_v3` delivers order/position/balance deltas.
- **Usage**:
```python
from apexomni.websocket import WebSocket
from apexomni.constants import APEX_OMNI_WS_TEST

ws = WebSocket(APEX_OMNI_WS_TEST, api_key_credentials={"key": API_KEY, "secret": API_SECRET, "passphrase": PASSPHRASE}, zk_seeds="your_seed", zk_l2Key="your_l2Key")

def handle(msg):
    print("update", msg)

ws.account_info_stream_v3(handle)  # subscribes to ws_zk_accounts_v3
ws.run_forever()  # ensure ping/pong or heartbeat per SDK docs
```
- **Notes**: Subscribe before placing orders to catch state transitions; implement reconnect + resubscribe on drop.

### Public WS (market data)
- **Depth**: `depth_stream(callback, 'BTCUSDT', 25)` → order book updates.
- **Ticker**: `ticker_stream(callback, 'BTCUSDT')` → best bid/ask, last.
- **Trades**: `trade_stream(callback, 'BTCUSDT')` → live trades.
- **Klines**: `kline_stream(callback, 'BTCUSDT', '1m')` → streaming candles.

## Symbol Retrieval Troubleshooting
- Ensure you are using the correct network ID for testnet (`NETWORKID_OMNI_TEST_BNB` or `NETWORKID_OMNI_TEST_BASE`) and endpoint (`APEX_OMNI_HTTP_TEST`).
- Disable proxy inheritance: `client.client.trust_env = False` and clear proxies for both public and private clients.
- On empty `configs_v3()`:
  1) Log the response and status code; retry once with a fresh client.
  2) Confirm env vars for endpoint/network are set and not pointing to mainnet inadvertently.
  3) If still empty, surface a structured error to the API consumer and avoid proceeding without configs.

## Minimal Flows (Monitoring)
- **List Orders**: call `open_orders_v3()` → normalize to `id/symbol/side/size/price/status` → return to UI.
- **List Positions**: use `get_account_v3()` → normalize to `symbol/side/size/entry_price/pnl`.
- **Cancel**: call `delete_order_v3(orderId=...)`; if order IDs vary, also support `delete_order_by_client_order_id_v3`.
