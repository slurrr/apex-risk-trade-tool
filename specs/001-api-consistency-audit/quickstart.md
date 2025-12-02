# Quickstart: API Consistency Audit

**Branch**: `001-api-consistency-audit` | **Date**: 2025-12-02

## 1) Setup

1. Create venv: `python -m venv .venv`
2. Activate: `.\.venv\Scripts\activate` (PowerShell) or `source .venv/bin/activate` (Unix)
3. Install deps: `.\.venv\Scripts\pip.exe install -r requirements.txt`
4. Open reference: `apex_api_cheatsheet.md`

## 2) Inventory API usage

- Scan for REST/WS calls: `rg "/v3/" backend` and `rg "wss://|realtime" backend`
- Catalog call sites (path/topic, method, base URL, payload fields, headers, symbol format, source file).
- Include dynamically composed URLs or topics and any UI-side fetches if present.
- To export findings quickly: `rg -n "/v3/" backend ui > specs/001-api-consistency-audit/artifacts/call-sites.txt` then append WS: `rg -n "realtime|wss://|ws_zk_accounts_v3|orderBook|instrumentInfo|recentlyTrade" backend ui >> specs/001-api-consistency-audit/artifacts/call-sites.txt`.

## 3) Validate against cheat sheet

- Confirm base URLs (testnet/mainnet) and `/v3` path usage.
- Check required fields, casing, enums, symbol formats (`BTC-USDT` REST vs `BTCUSDT` WS).
- Verify signing headers: `APEX-SIGNATURE`, `APEX-TIMESTAMP`, `APEX-API-KEY`, `APEX-PASSPHRASE`.
- Ensure market orders provide `price` via worst-price lookup and use `limitFee` where applicable.
- Validate order status/cancel enums handling.

## 4) Transport and redundancy review

- For live updates, confirm WebSocket topics (e.g., `ws_zk_accounts_v3`, orderBook, instrumentInfo) are used instead of REST polling or document rationale.
- Identify duplicated endpoint/topic usage across modules; recommend consolidation into `backend/exchange/apex_client.py` when behavior matches, noting exceptions with risk/benefit.

## 5) Data safety checks

- Search logs/telemetry for secrets or identifiers: API keys, passphrases, signatures, wallet addresses, clientOrderIds.
- Verify redaction or omission in logging/printing/caching; flag any plaintext exposure.

## 6) Deliverables

- `research.md`: decisions and rationale.
- `data-model.md`: entities and relationships for the audit.
- `contracts/overview.md`: expected audit artifacts.
- Audit report (mapping, discrepancies, consolidation recommendations) appended to spec artifacts.
