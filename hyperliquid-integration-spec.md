# Hyperliquid Integration Spec (Multi-Venue: ApeX ↔ Hyperliquid)

**Repo**: `apex-risk-trade-tool`  
**Date**: 2026-02-06  
**Status**: Draft for planning / team alignment (no implementation in this doc)  

## 1) Summary

This project is a FastAPI backend + static UI that previews, executes, and monitors perp trades with risk guardrails. Today it supports **ApeX Omni only** via `backend/exchange/exchange_gateway.py`.

Goal: add **Hyperliquid (perps, mainnet)** with **feature parity** to the existing tool while enabling a **single global venue toggle** (ApeX ↔ Hyperliquid) controlled from the UI (not per-request).

This spec is phased to support a collaborative build, keeping the system stable and testable at each milestone.

## 1.1 Documentation & Decision Records (Process Requirement)

This repo uses a `docs/` structure for living API notes and formal implementation decisions:

- `docs/api/`: API scratchpads + copied reference materials by venue/provider.
  - Hyperliquid scratchpad: `docs/api/Hyperliquid/api_reference.md` (working notes; update freely).
- `docs/decisions/`: **formal decision records** (required for this implementation).
- `docs/reference/`: stable references not tied to a single decision.

**Policy**: Any non-trivial architectural / behavioral choice that affects correctness, safety, or parity MUST be written as a decision record in `docs/decisions/` before (or alongside) the first PR that implements it. PRs that introduce such behavior without a decision record are considered incomplete for this transition.

## 2) Scope

### In Scope
- **Venue toggle in-app** (global backend state), persisted in the UI and reflected by the backend.
- Hyperliquid perps support with parity across:
  - Preview/execute trade (`/api/trade`)
  - Monitor positions/orders (`/api/positions`, `/api/orders`)
  - Entry price autofill helper (`/api/price/{symbol}`) used by the UI to prefill entry
  - Cancel order (`/api/orders/{id}/cancel`)
  - Close position (`/api/positions/{position_id}/close`)
  - Update TP/SL targets (`/api/positions/{position_id}/targets`)
  - ATR stop-loss autofill (`/risk/atr-stop`)
  - Depth/liquidity summary (`/api/market/depth-summary/{symbol}`)
  - WebSocket streaming to UI (`/ws/stream`) with equivalent event types
- Hyperliquid auth via **API wallet / agent wallet** (see §7).

### Out of Scope (for this effort)
- Hyperliquid **spot**
- Per-request venue selection (e.g., `?venue=` on endpoints)
- Multi-user backend concurrency isolation (we explicitly accept “global venue” as a single-operator mode)
- Portfolio/risk across venues simultaneously (only one venue active at a time)

## 3) Current Architecture (Baseline)

### Backend modules (today)
- `backend/main.py`: builds `ExchangeGateway(settings)` and `OrderManager(gateway, ...)`, wires routes.
- `backend/exchange/exchange_gateway.py`: ApeX-specific gateway; also acts as event bus for `/ws/stream`.
- `backend/trading/order_manager.py`: venue-agnostic-ish business logic but currently assumes gateway semantics (and TP/SL behavior is ApeX-shaped).
- `backend/risk/risk_engine.py`: pure, venue-agnostic sizing logic using `tickSize`, `stepSize`, min/max sizes, max leverage.
- `backend/api/routes_risk.py`: **currently Apex-coupled** because it calls `gateway.apex_client.fetch_klines(...)` directly for ATR candles.
- UI: static `ui/` consuming REST and `/ws/stream`.

### WebSocket event shapes (today)
`/ws/stream` forwards gateway events of types:
- `orders` (normalized open orders for UI table)
- `orders_raw` (raw account orders snapshot; used to reconcile TP/SL state)
- `positions` (normalized; positions table with TP/SL enrichment)
- `account` (equity/margin/uPNL header)

Hyperliquid integration must produce compatible event types so the UI doesn’t need a full rewrite.

## 4) Design Goals & Principles

- **Safety first**: never place orders if validation/risk checks fail.
- **Parity**: Hyperliquid should match the feature suite (trade, monitor, TP/SL, ATR, depth, streaming).
- **Isolation by boundary**: venue-specific code lives behind a gateway interface; shared logic stays shared.
- **Deterministic/testable**: keep risk calculations pure; mock external calls in tests; provide replayable fixtures.
- **No secrets in UI**: agent keys/private keys remain backend-only; logs redact sensitive identifiers.
- **Operator clarity**: UI clearly indicates which venue is active and blocks actions during venue switches.

## 5) Proposed Target Architecture (Multi-Venue)

### 5.1 Gateway Interface (Venue Boundary)

Introduce a venue-agnostic interface (conceptual) that both venues implement. The active implementation is selected by a “venue manager”.

**Minimum method surface** (aligned to current call sites):
- `load_configs()` / `ensure_configs_loaded()`
- `list_symbols()` and `get_symbol_info(symbol)`
- `get_account_equity()` and `get_account_summary()`
- `get_mark_price(symbol)` and `get_symbol_last_price(symbol)`
- `get_depth_snapshot(symbol, levels)`
- `fetch_klines(symbol, timeframe, limit)` (for ATR)
- `get_open_positions(force_rest?, publish?)`
- `get_open_orders(force_rest?, publish?)`
- `place_order(payload)` (limit + market support as required)
- `cancel_order(order_id, client_id?)`
- `cancel_all(symbol?)`
- `place_close_order(symbol, side, size, close_type, limit_price?)`
- `update_targets(symbol, side, size, take_profit?, stop_loss?, cancel_existing?, cancel_tp?, cancel_sl?)`
- Streaming / event bus:
  - `start_streams()`, `stop_streams()`, `attach_loop(loop)`
  - `register_subscriber()` / `unregister_subscriber()`
  - publish events in the same shape (`orders`, `orders_raw`, `positions`, `account`)

### 5.2 Venue Manager (Global Active Venue)

Backend holds a single global state:
- `active_venue = "apex" | "hyperliquid"`
- Two gateway instances, one per venue, each configured via settings.
- When switching venues:
  - stop streams for old venue
  - clear caches (orders/positions/prices/configs) for old venue
  - set `active_venue`
  - load configs for new venue
  - start streams for new venue
  - refresh `OrderManager` state

### 5.3 API / UI Integration for Venue Toggle

Add endpoints:
- `GET /api/venue` → `{ "active_venue": "apex" | "hyperliquid" }`
- `POST /api/venue` with `{ "active_venue": ... }` → switches and returns new state

UI:
- Add a “Venue” selector (ApeX / Hyperliquid) in header.
- Persist last selection in localStorage.
- On change:
  - call `POST /api/venue`
  - clear symbol cache; re-fetch `/api/symbols`
  - reconnect `/ws/stream`
  - refresh orders/positions/account summary

## 6) Parity Feature Requirements (Hyperliquid)

This section defines “full feature suite parity” as it applies to Hyperliquid.

### 6.1 Symbols & Constraints (for sizing + UI precision)

Hyperliquid must supply an equivalent “symbol config” model with:
- `tickSize` (or an equivalent derived increment / formatting rule)
- `stepSize` (minimum order size increment)
- `minOrderSize`, `maxOrderSize` (if enforceable; otherwise conservative defaults)
- `maxLeverage`
- Status/enabled flag

Notes:
- Risk sizing depends on rounding entry/stop to tick and size down to step.
- If Hyperliquid uses different validity rules (e.g., sig-fig constraints), the gateway must **convert** those into conservative `tickSize`/`stepSize` equivalents and/or apply a venue-specific “format/round validity” layer when building payloads.

### 6.2 Market Data

Hyperliquid gateway must provide:
- Latest price / mark price for a symbol (for PnL enrichment + UI convenience).
- L2 orderbook snapshot (for depth-summary).
- Candle history for requested timeframes (for ATR-stop).

Entry price autofill requirement:
- UI uses `GET /api/price/{symbol}` to prefill the Entry field when a symbol is selected.
- Hyperliquid must implement an equivalent “best available price” source that is stable and fast enough for interactive use (see decision record `docs/decisions/0008-auto-entry-and-atr-autofill.md`).

Timeframes required by UI:
- `3m`, `15m`, `1h`, `4h`

### 6.3 Account Summary

Expose the same header fields as today:
- `total_equity`
- `available_margin`
- `total_upnl`

Hyperliquid gateway should compute these from available account endpoints; if a field is not directly available, derive conservatively and document the derivation.

### 6.4 Orders & Positions

Must support:
- Fetch open positions and normalize to:
  - `id`, `symbol`, `side`, `size`, `entry_price`, `pnl`, `take_profit?`, `stop_loss?`
- Fetch open orders and normalize to:
  - `id`, `client_id?`, `symbol`, `side`, `size`, `entry_price`, `status`, `reduce_only?`

### 6.5 Trade Execution & Close Position

Trade execution must support:
- Limit entries (current app places LIMIT by default)
- Optional TP/SL at entry (today ApeX supports “open TP/SL” fields; Hyperliquid may require multiple orders)
- Idempotency: protect against duplicate placement on double-clicks

Close position must support:
- Reduce-only **market** and **limit** close
- Partial close by percent (the API already supports `close_percent`)

### 6.6 TP/SL Targets (Modify Targets)

The existing UI behavior expects:
- Set TP and/or SL for an open position
- Clear TP and/or SL
- The positions table shows TP/SL values even if they are represented as separate trigger orders

Hyperliquid implementation requirement:
- Represent TP/SL as one “active TP” and one “active SL” per symbol/position.
- Maintain an internal map similar to current `_tpsl_targets_by_symbol` so UI reads remain stable even if exchange APIs lag.
- Provide a reconciliation path (via WS events and/or periodic REST snapshot) to keep local TP/SL state correct.

### 6.7 WebSocket Streaming

Streaming parity must deliver the same event types to `/ws/stream`:
- Orders updates (create/cancel/fill)
- Positions updates
- Account/equity updates (or periodic refresh)
- Optional raw order snapshots used for TP/SL reconciliation

Minimum acceptable behavior:
- UI tables update “live enough” for a single operator.
- If WS disconnects, REST refresh still works and resync endpoints remain accurate.

## 7) Authentication & Key Management (Hyperliquid)

User guidance: Hyperliquid provides an “API wallet / agent wallet” concept that yields a private key used for API signing.

### Requirements
- Support agent wallet authentication **without exposing secrets** to UI.
- Store secrets in `.env` (and `.env.example` as placeholders), loaded via `backend/core/config.py`.
- Ensure logs are redacted (never log raw private keys; mask request signatures; mask client ids if needed).

### Open Decisions (must be settled early in Phase 0/1)
Because this repo is planning-only right now, we explicitly track these as decisions to confirm against official Hyperliquid docs:
- What exact signing scheme is required for agent wallet requests?
- Are there separate credentials for WS user streams vs REST trading?
- Are there nonce/time requirements that must be synchronized?

**Decision outcome target**:
- Standardize on a single primary auth mechanism for v1 (agent wallet).
- Document fallback/rotation strategy (key rotation, revoke agent, etc.).

### Decision Records Required (Auth / Keys)

At minimum, capture these as decision records before implementing Hyperliquid private endpoints:
- **HL-Auth-01**: Agent wallet signing scheme and key storage pattern in `.env` (what keys, which format, how loaded, what’s redacted).
- **HL-Auth-02**: WS auth requirements (if any) and session lifecycle.
- **HL-Auth-03**: Operational key rotation / revoke plan and “safe failure” behaviors.

## 8) API Contract Changes

### 8.1 New endpoints
- `GET /api/venue`
- `POST /api/venue`

### 8.2 Existing endpoints (unchanged behavior, but venue-dependent)
- `GET /api/symbols`
- `GET /api/account/summary`
- `GET /api/price/{symbol}`
- `POST /api/trade`
- `GET /api/orders`
- `POST /api/orders/{id}/cancel`
- `GET /api/positions`
- `POST /api/positions/{position_id}/close`
- `POST /api/positions/{position_id}/targets`
- `POST /risk/atr-stop`
- `GET /api/market/depth-summary/{symbol}`
- `GET /ws/stream`

### 8.3 Venue switching semantics
On `POST /api/venue`, backend should:
- return success only after:
  - new venue configs are loaded (or a clear error is returned)
  - streams are started if enabled
- return a structured error if switch fails, and keep the previous venue active.

## 9) Phased Execution Plan (Collaborative Build)

This mirrors the phased execution sequence previously agreed, but written as PR-sized deliverables with acceptance checks.

### Phase 0 — Discovery & Contracts (1–3 days)
**Objective**: remove unknowns before code changes.

Deliverables:
- Expand the Hyperliquid scratchpad `docs/api/Hyperliquid/api_reference.md` covering:
  - endpoints needed for meta/symbols, candles, depth, equity, positions, open orders, place/cancel, triggers, WS topics
  - auth/signing specifics for agent wallet
  - precision rules (price/size validity)
  - price source decision support (mid/mark/last/best-bid-ask) for `/api/price/{symbol}` and UI autofill
- Agreement on:
  - symbol naming format in UI (keep `BASE-QUOTE` like `BTC-USDC` vs HL “coin” like `BTC`)
  - mapping strategy between UI symbols and HL instrument identifiers
- Create required decision records in `docs/decisions/` for Phase 1+ changes (see “Phase Gates” below).

Acceptance:
- Team can answer: “How do we sign and submit an order on HL mainnet?” and “How do we fetch candles for ATR timeframes?”

### Phase Gates (Decision Records)

To keep collaboration clean, each phase has a “decision gate”:
- Phase 1 gate: venue toggle semantics + switching safety.
- Phase 2 gate: symbol naming + precision/rounding/validity strategy.
- Phase 3 gate: order placement/cancel idempotency strategy.
- Phase 4 gate: TP/SL representation + reconciliation strategy.
- Phase 5 gate: WS topic coverage + fallback behaviors.

### Phase 1 — Multi-Venue Skeleton + Toggle (ApeX remains default)
**Objective**: introduce venue switching without impacting current ApeX functionality.

Deliverables:
- Venue manager concept + API endpoints `GET/POST /api/venue`
- UI toggle + persistence + reconnect behavior
- No Hyperliquid trading yet (stub only is acceptable), but switching must not break ApeX.

Acceptance:
- Switching venue updates UI state and backend state deterministically.
- ApeX behavior unchanged when venue is ApeX.

### Phase 2 — Hyperliquid Public Data (Symbols, Prices, Depth, Candles → ATR works)
**Objective**: make the UI functional for symbol selection and risk helpers on HL.

Deliverables:
- HL symbol catalog with constraints mapped into app’s schema
- HL best-available price source for `/api/price/{symbol}` so the UI can prefill entry on symbol selection
- HL price + depth snapshot wiring so `depth-summary` works
- HL candles wiring so `/risk/atr-stop` works on HL
- Refactor `/risk/atr-stop` to call a venue-agnostic candle fetch method (remove Apex-coupling)

Acceptance:
- With venue=Hyperliquid, UI can:
  - load symbols
  - show depth summary
  - compute ATR stop for supported timeframes

### Phase 3 — Hyperliquid Private Data + Core Trading (Account, Orders, Positions, Place/Cancel, Close)
**Objective**: place and manage discretionary orders and closes on HL.

Deliverables:
- HL account summary implementation (equity/margin/uPNL)
- HL open orders + open positions endpoints
- Place order (limit) and cancel order
- Reduce-only close position (market + limit)
- Idempotency strategy (client ids / dedupe)

Acceptance:
- With venue=Hyperliquid:
  - preview sizing works with HL constraints
  - execute places a limit order
  - orders/positions endpoints reflect reality
  - cancel works
  - close works

### Phase 4 — Hyperliquid TP/SL Targets + Reconciliation
**Objective**: implement “Modify Targets” parity and keep UI stable.

Deliverables:
- Implement TP trigger and SL trigger behavior per HL’s supported order types
- Clear TP and/or SL behavior
- Reconciliation path:
  - via WS events + periodic snapshots OR
  - via REST snapshots only (acceptable if WS user stream is not ready yet)
- Ensure positions table shows TP/SL consistently and promptly after updates.

Acceptance:
- Set TP/SL reflects in UI within a bounded time window (e.g., <2s WS / <10s REST).
- Clearing targets updates UI and does not cancel the wrong side.

### Phase 5 — Hyperliquid Streaming Parity (`/ws/stream`)
**Objective**: make the app “live” on HL like it is on ApeX.

Deliverables:
- HL WS client(s) with reconnect
- Publish events to the existing `/ws/stream` fanout
- Ensure events drive:
  - account header refresh
  - orders/positions live updates
  - TP/SL reconciliation events if applicable

Acceptance:
- UI updates live without polling in normal operation.
- If WS fails, REST refresh still yields correct state.

## 10) Testing Strategy

### Unit tests
- Gateway method-level tests using fake clients (pattern exists in `backend/tests/test_exchange_gateway.py`).
- Risk engine tests remain unchanged; add cases relevant to HL rounding/constraints once mapped.

### Integration scripts (encouraged)
Provide simple scripts (in `tools/`) for developers/operators to validate:
- HL meta/symbol catalog mapping output
- HL candle fetch vs expected timeframe behavior
- HL account snapshot fetch
- HL order placement + cancel + trigger orders

These scripts should:
- load `.env`
- print redacted outputs
- avoid writing secrets to disk

### Manual checklist (operator)
- Switch venue to HL; verify symbols load
- Compute ATR stop; verify stop populates plausibly
- Preview and execute small-size order; verify order appears
- Cancel order; verify it disappears
- Open a position; set TP/SL; verify targets show in UI
- Close position partially; verify size decreases
- Verify WS updates when enabled

## 11) Observability & Safety

Logging:
- Use structured logging via `backend/core/logging.py`.
- Add an `active_venue` field to all relevant logs for debugging.
- Redact sensitive payload fields consistently.

Safety controls:
- Maintain existing risk caps (`PER_TRADE_RISK_CAP_PCT`, `DAILY_LOSS_CAP_PCT`, `OPEN_RISK_CAP_PCT`).
- Ensure venue switch blocks trade endpoints during transition (brief lock) to prevent “half switched” requests.

## 12) Configuration Changes

Add to `.env.example` (names TBD during Phase 0 discovery; do not leak secrets):
- Hyperliquid base URL (mainnet)
- Hyperliquid agent wallet private key (or path/secret reference)
- Optional: WS enable flag per venue

Also add a default active venue setting:
- `ACTIVE_VENUE=apex` (default)

## 13) Open Questions / Risks

1) **Auth/signing correctness**: agent wallet signing must be confirmed from official docs and tested against mainnet.
2) **Precision/validity rules**: HL price/size constraints differ from “tick/step”; mapping must be correct or orders will be rejected.
3) **TP/SL semantics**: HL trigger orders may not map 1:1 to ApeX “position TP/SL”; careful reconciliation is required to avoid canceling wrong orders.
4) **Global venue toggle**: acceptable for a single operator; if multiple UIs connect simultaneously, they will share a venue (documented limitation).
5) **WS parity**: user-specific WS streams may require separate auth/session; fallback REST reconciliation must exist.

## 14) Decision Record Format (Required)

Decision records live in `docs/decisions/` and should be lightweight but explicit.

- Filename: `docs/decisions/NNNN-short-slug.md` (e.g., `0003-hl-symbol-mapping.md`)
- Required sections:
  - **Context**
  - **Decision**
  - **Options Considered**
  - **Consequences**
  - **Validation Plan** (how we’ll know it works / what to test)

---

## Appendix A — Implementation Mapping Checklist (Call-Site Driven)

These are the known Apex-coupled/venue-touched areas to address during implementation:
- `backend/api/routes_risk.py` uses `gateway.apex_client.fetch_klines` directly → must become venue-agnostic candle fetch.
- `backend/exchange/exchange_gateway.py` is ApeX-specific but currently also owns:
  - event bus
  - caches
  - order payload builder
  - TP/SL cancel/update behaviors
  Multi-venue requires splitting “generic gateway contract” from “ApeX implementation”.
