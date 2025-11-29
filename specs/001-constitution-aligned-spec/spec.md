# Feature Specification: Constitution-Aligned Baseline Specification

**Feature Branch**: `001-constitution-aligned-spec`  
**Created**: 2025-11-28  
**Status**: Draft  
**Input**: User description: "I want the baseline specification to strictly follow the Constitution for the ApeX Risk & Trade Sizing Tool (MVP) and the design doc MVP_without_TV_Design_Doc.txt. These are the functional, non-functional, architectural, and API requirements the spec must fully capture."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preview risk-based position size (Priority: P1)

Users enter symbol, entry, stop, and risk% to calculate a compliant position size before sending any order.

**Why this priority**: Provides the core value of the tool—risk-first sizing with safety rails—without placing orders.

**Independent Test**: Call `/api/trade` with `preview=true` and verify returned side, size, notional, estimated_loss, and warnings match expected outputs for provided inputs.

**Acceptance Scenarios**:

1. **Given** valid symbol config, account equity, and inputs, **When** a preview request is submitted, **Then** the response returns side, size, notional, estimated_loss, and any warnings with all exchange constraints applied.
2. **Given** inputs that would compute size below `minOrderSize`, **When** preview is requested, **Then** the trade is rejected with a clear error explaining the minimum size breach.

---

### User Story 2 - Execute validated order (Priority: P1)

Users place an order only after the system re-validates sizing and safety rails at execution time.

**Why this priority**: Ensures live orders honor up-to-date equity, symbol constraints, and risk caps, preventing unsafe trades.

**Independent Test**: Call `/api/trade` with `execute=true` on valid inputs and confirm an exchange order ID is returned; repeat with violating inputs and confirm the order is blocked with a clear error.

**Acceptance Scenarios**:

1. **Given** a valid preview result, **When** execute is requested with unchanged inputs, **Then** the backend recomputes sizing, enforces caps, and returns `executed=true` plus the exchange order ID.
2. **Given** inputs that breach leverage or max size, **When** execute is requested, **Then** the system reduces size (if permitted) with warnings or rejects the order if still unsafe, and no order is placed.

---

### User Story 3 - Monitor orders and positions (Priority: P2)

Users view current orders and positions to decide whether to place, adjust, or cancel trades.

**Why this priority**: Visibility is required to keep risk exposure aligned with the constitution and decide on new orders.

**Independent Test**: Call `/api/orders` and `/api/positions` and confirm data matches the gateway’s state; issue a cancel via `/api/orders/{id}/cancel` and verify the order is removed.

**Acceptance Scenarios**:

1. **Given** open positions and orders exist, **When** the UI polls `/api/positions` and `/api/orders`, **Then** it receives current symbols, sizes, sides, and statuses without exposing secrets.
2. **Given** a cancel request for an open order, **When** `/api/orders/{id}/cancel` is called, **Then** the order is canceled (or a structured error is returned) and no unintended orders remain.

### Edge Cases

- Stop equals entry (must reject with clear message).
- Computed size below `minOrderSize` (reject).
- Computed size above leverage-cap or `maxOrderSize` (shrink with warning; reject if still unsafe).
- Slow or failing ApeX API responses (surface structured errors; no duplicate submissions).
- Missing or stale symbol config (fail safely until refreshed).
- Testnet/mainnet selection (default testnet; no secrets leaked to UI).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate position size using `size = (equity * (risk_pct/100)) / abs(entry - stop)` and infer side (BUY/SELL) from entry vs stop, applying slippage and fee buffers consistently.
- **FR-002**: System MUST enforce symbol constraints (tickSize, stepSize, minOrderSize, maxOrderSize) and leverage caps; if computed size is below minimum, reject; if above caps, reduce size and return warnings or reject if still unsafe.
- **FR-003**: System MUST return preview outputs: side, size, notional, estimated_loss, and warnings without placing any order when `preview=true`.
- **FR-004**: System MUST re-run the entire sizing calculation and all validations at execution time to avoid stale data and place an order only on `execute=true`, using idempotent client order IDs and structured errors on failure. Execute responses MUST include preview fields plus `executed` and `exchange_order_id` (or a clear error with no order placed).
- **FR-005**: System MUST support limit orders, reduce-only close orders, optional take-profit price, and optional stop-loss price within the same trade request, honoring safety rails before sending.
- **FR-006**: System MUST expose endpoints: GET `/api/config`, GET `/api/positions`, GET `/api/orders`, POST `/api/trade` (preview or execute), POST `/api/orders/{id}/cancel`, GET `/api/symbols` (optional), and optional `/api/ws`, with responses that never include secrets.
- **FR-007**: System MUST track open orders and positions in memory for quick responses and keep them aligned with exchange state; cancellation must remove or mark orders accordingly.
- **FR-008**: System MUST log structured entries for sizing inputs/outputs, risk checks, payloads sent to exchange, warnings, errors, and rejected trades.
- **FR-009**: System MUST default to ApeX testnet until explicitly configured otherwise and must never send orders if validation or risk caps fail.
- **FR-010**: System MUST ensure UI can compute, preview, and place trades end-to-end via REST while remaining secret-free.

### Key Entities *(include if feature involves data)*

- **Trade Request**: Inputs for sizing and orders (symbol, entry_price, stop_price, risk_pct, side optional, tp optional, preview/execute flags).
- **Position Sizing Result**: Derived side, size, notional, estimated_loss, warnings, and any rejection reason.
- **Symbol Config**: Exchange constraints per symbol (tickSize, stepSize, minOrderSize, maxOrderSize, maxLeverage).
- **Order Payload**: Validated request ready for exchange submission, including idempotent clientOrderId, requested order type (limit, reduce-only), and optional TP/SL.
- **Risk Caps State**: Per-trade cap, daily loss cap, and total open-risk sum used to block unsafe orders.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of preview requests return side, size, notional, estimated_loss, and warnings with constitution-aligned validation (no missing fields).
- **SC-002**: 100% of execution attempts re-run sizing and either place an order with an exchange order ID or return a clear structured error without placing any order.
- **SC-003**: Risk cap violations (per-trade, daily loss, open-risk sum) are blocked in 100% of applicable requests with explicit messages.
- **SC-004**: Risk engine unit tests cover long/short, below-min-size rejection, leverage-capped sizing, and slippage/fee adjustments with all tests passing.
- **SC-005**: UI users can complete a preview and an executed testnet trade in under 3 minutes end-to-end without exposure to secrets.
