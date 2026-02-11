# ApeX Risk & Trade Sizing Tool

Backend + static UI for previewing, executing, and monitoring ApeX trades with risk guardrails. Defaults to **testnet** only.

## Getting Started
- Create venv: `python -m venv .venv && .\\.venv\\Scripts\\activate`.
- Install deps: `.\.venv\Scripts\pip.exe install -r requirements.txt`.
- Copy `.env.example` to `.env` and fill testnet-only credentials; do not commit secrets.
- Run API: `.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000` (health at `/health`).
- Serve UI: open `ui/index.html` directly or from `ui/` run `python -m http.server 8080`. UI points to `http://localhost:8000` unless `window.API_BASE` is set.

## Docs & Checklists
- Tasks and scope: `specs/001-constitution-aligned-spec/tasks.md`.
- Design/spec: `specs/001-constitution-aligned-spec/spec.md`, plan in `specs/001-constitution-aligned-spec/plan.md`.
- Manual testnet checklist: `specs/001-constitution-aligned-spec/quickstart.md`.

## ATR Stop-Loss Autofill
- Purpose: automatically suggests a stop price using configurable ATR timeframe, period, and multiplier whenever the trade entry price is known.
- Backend/API details live in `specs/001-atr-stop-autofill/spec.md`; implementation steps and verification flow are in `specs/001-atr-stop-autofill/quickstart.md`.
- Configure defaults via `.env`:
  - `ATR_TIMEFRAME`: candle size such as `5m`, `15m`, or `1h`.
  - `ATR_PERIOD`: number of candles included in the Wilder ATR calculation.
  - `ATR_MULTIPLIER`: factor applied to ATR when deriving the stop offset.
- ATR timeframe selector options are config-driven:
  - `ATR_SL_1`, `ATR_SL_2`, `ATR_SL_3`, `ATR_SL_4` map to the 4 UI buttons from left to right.
  - Backend exposes these via `GET /risk/atr-config`, and `/risk/atr-stop` only accepts configured options.
- Risk presets are config-driven with the same 4-button UX:
  - `RISK_PCT_1`, `RISK_PCT_2`, `RISK_PCT_3`, `RISK_PCT_4` map left-to-right under the Risk % field.
  - Default values: `1`, `3`, `6`, `9`.
  - Manual Risk % input remains fully editable.
- The selected ATR timeframe persists in localStorage and is sent as an optional `timeframe` override to `/risk/atr-stop`.
- After editing any of the above values, restart the FastAPI service (or your process manager) so the new configuration is loaded by `backend/core/config.py`.

## Hyperliquid TP/SL Behavior
- When venue is `hyperliquid`, `POST /api/trade` can submit entry + TP/SL atomically (single grouped exchange action) when `tp` and `stop_price` are provided.
- The backend uses grouped `bulk_orders` (`normalTpsl`) so TP/SL does not depend on a later `/positions/{id}/targets` call for initial protection.
- `/api/positions/{position_id}/targets` is still used for post-entry edits (change/clear TP or SL).
- Hyperliquid minimum notional guard is configurable via `HYPERLIQUID_MIN_NOTIONAL_USDC` (default: `10`).
- Hyperliquid reconcile is WS-first with low-frequency audits and signal-based checks:
  - Periodic audit: `HYPERLIQUID_RECONCILE_AUDIT_INTERVAL_SECONDS` (default `900`).
  - Stale private WS threshold: `HYPERLIQUID_RECONCILE_STALE_STREAM_SECONDS` (default `90`).
  - Submitted-order lifecycle timeout: `HYPERLIQUID_RECONCILE_ORDER_TIMEOUT_SECONDS` (default `20`).
  - Minimum gap between reconciles: `HYPERLIQUID_RECONCILE_MIN_GAP_SECONDS` (default `5`).
  - Alerting window and thresholds:
    - `HYPERLIQUID_RECONCILE_ALERT_WINDOW_SECONDS` (default `300`)
    - `HYPERLIQUID_RECONCILE_ALERT_MAX_PER_WINDOW` (default `3`)
    - `HYPERLIQUID_ORDER_TIMEOUT_ALERT_MAX_PER_WINDOW` (default `3`)
- Stream health endpoint: `GET /api/stream/health` (includes reconcile counters/reasons and WS freshness).
- Dev UI diagnostics panel:
  - Hidden by default and enabled only when `localStorage.dev_stream_health = "1"` in browser devtools.
  - Polls `/api/stream/health` every 15s and supports manual refresh.

## ApeX Stability Controls
- ApeX reconcile is reason-based (not tight-loop polling) with anti-storm min-gap:
  - `APEX_RECONCILE_AUDIT_INTERVAL_SECONDS` (default `900`)
  - `APEX_RECONCILE_STALE_STREAM_SECONDS` (default `90`)
  - `APEX_RECONCILE_MIN_GAP_SECONDS` (default `5`)
  - `APEX_RECONCILE_ALERT_WINDOW_SECONDS` (default `300`)
  - `APEX_RECONCILE_ALERT_MAX_PER_WINDOW` (default `3`)
- When `APEX_ENABLE_WS=false`, ApeX runs in degraded mode and `/ws/stream` is fed by periodic REST polling:
  - `APEX_POLL_ORDERS_INTERVAL_SECONDS` (default `5`)
  - `APEX_POLL_POSITIONS_INTERVAL_SECONDS` (default `5`)
  - `APEX_POLL_ACCOUNT_INTERVAL_SECONDS` (default `15`)
- ApeX TP/SL local hints now expire if not confirmed by authoritative stream/cache:
  - `APEX_LOCAL_HINT_TTL_SECONDS` (default `20`)
- ApeX symbol price auto-populate is WS-first and only falls back to REST when stale/missing:
  - `APEX_WS_PRICE_STALE_SECONDS` (default `30`)

## UI Whale Mock Mode
- Purpose: run the UI with big, share-safe demo balances/orders/positions for screenshots without exposing a real account.
- Config:
  - `UI_MOCK_MODE_ENABLED=true`
  - `UI_MOCK_DATA_PATH=spec/ui-whale-mock.json` (or your own JSON path)
- Venue-aware: mock payload is split by venue key (`apex`, `hyperliquid`) and follows active venue switching.
- Read-only safety: when mock mode is enabled, trading/order/position mutation endpoints are blocked (`503`) so no live orders are sent.
- Included example fixture: `spec/ui-whale-mock.json`.

## Notes
- Network is validated and defaults to testnet; unexpected networks log a warning on startup.
- UI/assets contain no secrets; keep API keys only in local `.env`.
- WebSocket stream (`/ws/stream`) powers live orders/positions; falls back to REST refresh if disconnected.
