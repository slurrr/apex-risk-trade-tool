---

description: "Task list for Constitution-Aligned Baseline Specification"
---

# Tasks: Constitution-Aligned Baseline Specification

**Input**: Design documents from `/specs/001-constitution-aligned-spec/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Include targeted unit tests where specified (risk engine, order manager, API). Integration/manual tests noted per story.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Create/verify project structure per plan in `backend/` and `ui/` directories
- [x] T002 Create virtual environment and install dependencies listed in `requirements.txt`
- [x] T003 Add required env keys to `.env.example` (ApeX creds, network ID, host/port, log level)
- [x] T004 [P] Add structured logging stub in `backend/core/logging.py`
- [x] T005 [P] Add config loader scaffold in `backend/core/config.py` reading `.env`

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T006 Implement logging config (structured formatter, levels) in `backend/core/logging.py`
- [ ] T007 Implement config loading for ApeX endpoints/credentials in `backend/core/config.py`
- [ ] T008 Create FastAPI app skeleton with health route in `backend/main.py`
- [ ] T009 Scaffold gateway module in `backend/exchange/exchange_gateway.py` with SDK client init placeholder
- [ ] T010 Scaffold risk engine module in `backend/risk/risk_engine.py` (pure functions placeholder)
- [ ] T011 Scaffold order manager module in `backend/trading/order_manager.py` with in-memory stores
- [ ] T012 Add base router files in `backend/api/routes_trade.py`, `backend/api/routes_orders.py`, `backend/api/routes_positions.py`

## Phase 3: User Story 1 - Preview risk-based position size (Priority: P1)

**Goal**: Provide preview sizing with safety rails and clear errors.  
**Independent Test**: POST `/api/trade` with `preview=true` returns side, size, notional, estimated_loss, warnings with constraints applied; rejects below-min-size inputs.

### Tests for User Story 1 (targeted)

- [ ] T013 [P] [US1] Add unit tests for sizing long/short, stop==entry rejection, below-min-size rejection in `backend/tests/test_risk_engine.py`

### Implementation for User Story 1

- [ ] T014 [US1] Implement pure sizing logic with slippage/fee buffer, tick/step rounding, min/max checks in `backend/risk/risk_engine.py`
- [ ] T015 [US1] Wire trade preview handler to risk engine (no execution) in `backend/api/routes_trade.py`
- [ ] T016 [US1] Add Pydantic request/response schemas for preview fields in `backend/trading/schemas.py`
- [ ] T017 [US1] Ensure preview logs structured inputs/outputs and warnings in `backend/api/routes_trade.py`
- [ ] T018 [US1] Implement frontend preview form + display (side, size, notional, estimated_loss, warnings) in `ui/js/preview.js` and `ui/index.html`

## Phase 4: User Story 2 - Execute validated order (Priority: P1)

**Goal**: Re-run sizing on execute, enforce caps, and place orders via ApeX SDK with idempotent IDs.  
**Independent Test**: POST `/api/trade` with `execute=true` returns `executed=true` and `exchange_order_id` for valid input; rejects or shrinks unsafe requests with clear errors.

### Tests for User Story 2 (targeted)

- [ ] T019 [P] [US2] Add order manager unit tests for re-run sizing, leverage-cap reduction, and risk-cap rejection in `backend/tests/test_order_manager.py`
- [ ] T020 [P] [US2] Add API tests for execute happy path and validation failures in `backend/tests/test_trade_api.py`

### Implementation for User Story 2

- [ ] T021 [US2] Implement configs cache and equity/symbol fetch in `backend/exchange/exchange_gateway.py`
- [ ] T022 [US2] Implement order payload builder with idempotent clientOrderId and SDK call in `backend/trading/order_manager.py`
- [ ] T023 [US2] Enforce per-trade, daily-loss, and open-risk caps in `backend/trading/order_manager.py`
- [ ] T024 [US2] Update trade route to support execute flow (re-run sizing, execute flag, structured errors) in `backend/api/routes_trade.py`
- [ ] T025 [US2] Add UI execute action and result handling (exchange_order_id, warnings/errors) in `ui/js/execute.js` and `ui/index.html`
- [ ] T026 [US2] Add structured logging for payloads, warnings, and rejected trades in `backend/trading/order_manager.py`

## Phase 5: User Story 3 - Monitor orders and positions (Priority: P2)

**Goal**: Provide visibility into orders and positions and allow cancel actions.  
**Independent Test**: GET `/api/orders` and `/api/positions` return current data; POST `/api/orders/{id}/cancel` removes or marks the order.

### Tests for User Story 3 (targeted)

- [ ] T027 [P] [US3] Add gateway stubs/tests for positions/orders fetch and cancel in `backend/tests/test_exchange_gateway.py`
- [ ] T028 [P] [US3] Add API tests for orders/positions retrieval and cancel in `backend/tests/test_orders_api.py`

### Implementation for User Story 3

- [ ] T029 [US3] Implement orders/positions fetch endpoints in `backend/api/routes_orders.py` and `backend/api/routes_positions.py`
- [ ] T030 [US3] Implement cancel endpoint in `backend/api/routes_orders.py`
- [ ] T031 [US3] Ensure order manager keeps in-memory orders/positions in sync with gateway responses in `backend/trading/order_manager.py`
- [ ] T032 [US3] Add UI tables for orders and positions with cancel button in `ui/js/orders.js`, `ui/js/positions.js`, and `ui/index.html`

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T033 Add quickstart manual testnet checklist documenting env, preview, execute, cancel in `specs/001-constitution-aligned-spec/quickstart.md`
- [ ] T034 Harden error handling and structured error schema across routes in `backend/api/routes_*`
- [ ] T035 Verify testnet default and block execution when configs are missing/stale in `backend/core/config.py` and `backend/exchange/exchange_gateway.py`
- [ ] T036 Add observability sweep (log fields consistency) in `backend/core/logging.py` and `backend/trading/order_manager.py`
- [ ] T037 Finalize documentation links and ensure no secrets in UI/assets in `ui/` and `README.md`

## Dependencies & Execution Order

- Story order: US1 (Preview) → US2 (Execute) → US3 (Monitor).  
- Foundational phases (1-2) must complete before any story work.  
- US1 must complete before US2; US2 before US3.

## Parallel Opportunities

- T004/T005 in parallel (logging/config scaffolds).  
- US1 tests (T013) can run parallel to schema/UI tasks (T016/T018) after risk engine stub exists.  
- US2 tests (T019/T020) can run parallel to gateway work (T021) once interfaces are defined.  
- US3 tests (T027/T028) can run parallel to UI tables (T032) after API shapes are set.

## Implementation Strategy

- MVP first: deliver US1 preview, then US2 execute, then US3 monitor.  
- Validate at each milestone with targeted tests and manual checks before proceeding.  
- Keep UI minimal and secret-free; rely on backend for all logic and validations.
