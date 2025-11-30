# Feature Specification: Phase 5 - User Story 3 Monitor

**Feature Branch**: `006-phase5-us3-monitor`  
**Created**: 2025-11-30  
**Status**: Draft  
**Input**: Extend the constitution-aligned baseline to deliver User Story 3 (monitor orders and positions) with cancel support while keeping all safety and observability rails intact.

## User Scenarios & Testing (mandatory)

### User Story 3 - Monitor orders and positions (Priority: P2)

Users can view open orders and positions and issue cancels so they can keep exposure aligned with the risk constitution.

**Why this priority**: Without live visibility and cancel control, users cannot confidently enforce risk caps or stop unsafe trades that were sent earlier.

**Independent Test**: Call `/api/orders` and `/api/positions` and confirm normalized lists match the gateway; call `/api/orders/{id}/cancel` and verify the order is removed or flagged canceled.

**Acceptance Scenarios**:

1. **Given** open positions and orders exist, **When** the UI polls `/api/positions` and `/api/orders`, **Then** it receives symbol, side, size, price/entry, PnL/status fields in a consistent schema without exposing secrets.
2. **Given** a cancel request for an open order, **When** `/api/orders/{id}/cancel` is called, **Then** the order is canceled (or a structured error is returned) and the in-memory cache reflects the current state.
3. **Given** the gateway cannot reach ApeX or configs are missing, **When** monitor endpoints are called, **Then** the API fails safely with a structured error and logs the issue without submitting orders.

### Edge Cases

- No open positions or orders (return empty lists, not errors).
- Stale or missing configs (block until refreshed; log clearly).
- Mixed ID formats from ApeX (orderId vs clientOrderId) must be normalized for the UI and cancel actions.
- Cancel attempts on already-closed orders should return a clear message without duplicate requests.
- Exchange/network errors surface as structured errors; no secrets or sensitive details in responses.

## Requirements (mandatory)

### Functional Requirements

- **FR-101**: Provide `GET /api/orders` that fetches open orders from the ApeX SDK, normalizes to a stable schema (`id`, `symbol`, `side`, `size`, `price`, `status`), refreshes the in-memory cache, and never returns secrets.
- **FR-102**: Provide `GET /api/positions` that fetches current positions, normalizes to a stable schema (`symbol`, `side`, `size`, `entry_price`, `pnl`), refreshes the in-memory cache, and never returns secrets.
- **FR-103**: Provide `POST /api/orders/{id}/cancel` that calls the ApeX cancel API, handles mixed ID formats safely, refreshes caches, and returns a structured status or error.
- **FR-104**: Monitoring endpoints must log structured events (request context, counts, errors) and align with constitution principles (risk-first, deterministic/testable logic, minimal surface area, safe exchange interaction, observability).
- **FR-105**: Default to ApeX testnet endpoints unless explicitly configured; block operations if configs are missing/stale or credentials are invalid.
- **FR-106**: UI polling for orders/positions must use these endpoints only; no secret-bearing data may reach the frontend.

### Key Entities

- **Order Summary**: Normalized order view with `id`, `symbol`, `side`, `size`, `price`, `status`.
- **Position Summary**: Normalized position view with `symbol`, `side`, `size`, `entry_price`, `pnl`.
- **Cancel Request/Response**: Input `order_id` mapped to ApeX identifier; response indicates `canceled` status and any warnings or errors.
- **Gateway State**: In-memory caches for configs, orders, positions, and risk estimates kept in sync with exchange responses.

## Success Criteria (measurable)

- **SC-101**: 100% of `/api/orders` and `/api/positions` calls return normalized data or structured errors without leaking secrets.
- **SC-102**: 100% of cancel attempts either return `canceled=true` (and remove from cache) or a structured error without duplicate requests.
- **SC-103**: Logging covers monitor calls, cancel actions, counts, and errors with constitution-aligned fields.
- **SC-104**: Monitor flows run on ApeX testnet by default and refuse to operate when configs/credentials are missing or stale.
