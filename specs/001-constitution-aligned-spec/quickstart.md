---
title: "ApeX Risk & Trade Tool - Testnet Quickstart"
---

# Manual Testnet Checklist

> Purpose: verify preview, execute, and cancel flows against ApeX testnet without risking funds.

## 1) Prepare Environment
- Copy `.env.example` to `.env` and fill **testnet** credentials only; leave production keys out of this repo.
- Ensure `APEX_NETWORK=testnet` (default) and set `APEX_ENABLE_WS=true` if you want live updates.
- Create/activate the virtual environment: `python -m venv .venv && .\\.venv\\Scripts\\activate`.
- Install deps: `.\.venv\Scripts\pip.exe install -r requirements.txt`.

## 2) Start the Backend
- Run API with hot reload: `.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000`.
- Confirm health: `curl http://localhost:8000/health` -> `{"status":"ok"}`.
- On startup the service should log that configs were cached for testnet; if not, stop and fix config before executing trades.

## 3) Open the UI Shell
- Serve `ui/` statically (e.g., `python -m http.server 8080` from `ui/`) or open `ui/index.html` directly.
- The page should point to `http://localhost:8000` by default; override `window.API_BASE` if the API runs elsewhere.

## 4) Preview a Trade
- In the form, enter a testnet symbol such as `BTC-USDT`, entry and stop prices, and risk %.
- Click **Calculate**; expect a preview block with side, size, notional, estimated_loss, and warnings.
- If you see a structured error (e.g., `validation_error`), adjust inputs until preview succeeds.

## 5) Execute a Testnet Order
- After a valid preview, click **Place Order**.
- Expect a response with `executed: true` and a non-empty `exchange_order_id`.
- If execution is blocked (e.g., configs missing or stale), resolve the issue before retrying.

## 6) Monitor and Cancel
- Scroll to **Open Orders** and **Open Positions**. Tables should populate automatically (WS) or via **Refresh**.
- Click **Cancel** on an open order; expect `canceled: true` and removal from the table after refresh/stream.
- Confirm no unintended orders remain on the testnet account.

## 7) Reset Between Sessions
- Keep `.env` local-only; never commit it. Remove any cached credentials before sharing the workspace.
- Stop the backend (`Ctrl+C`) and close the UI tab after testing.
