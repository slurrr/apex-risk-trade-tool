# Architecture Notes

- `ExchangeGateway` now prefers live data from ApeX Omni WebSocket feeds. When `APEX_ENABLE_WS=true`, it starts public ticker (`instrumentInfo.all`) and private account stream (`ws_zk_accounts_v3`) to keep prices, orders, positions, and account equity caches hot. REST remains as a fallback when caches are empty or after reconnects.
- FastAPI exposes `/ws/stream` that fan-outs gateway events (orders, positions, ticker/account) to UI clients. Updates are queued and delivered via an asyncio event bus.
- The UI pages (`ui/js/orders.js`, `ui/js/positions.js`) subscribe to `/ws/stream`; tables update automatically on pushes and fall back to manual refresh if the socket drops.
- Startup: gateway attaches the running loop during FastAPI startup; streams start only when `APEX_ENABLE_WS=true`. Credentials and network selection still come from existing ApeX env vars.
- Reconnects: the underlying `apexomni` websocket manager auto-reconnects on errors; caches persist in-memory. REST calls can repopulate caches if a gap is detected or if WebSockets are disabled.
