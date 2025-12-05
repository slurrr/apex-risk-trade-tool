---

description: "Task list for Fix TP/SL position updates feature"
---

# Tasks: Fix TP/SL position updates

**Input**: Design documents from `D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-fix-tp-sl-bug\`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: TP/SL behaviour is safety-critical; include focused backend and UI tests where noted.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- All descriptions include exact file paths

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm local environment and feature docs are ready for TP/SL work.

- [X] T001 Verify Python venv and dependencies for backend in requirements.txt using `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\pip.exe` (D:\Automation\Python scripts\apex-risk-trade-tool\requirements.txt)
- [X] T002 [P] Ensure ApeX network and WS settings are configured for testnet TP/SL testing in backend/core/config.py and .env (D:\Automation\Python scripts\apex-risk-trade-tool\backend\core\config.py)
- [X] T003 [P] Review existing TP/SL-related tests and fixtures for positions and orders in backend/tests (D:\Automation\Python scripts\apex-risk-trade-tool\backend\tests)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core backend structures that all TP/SL user stories depend on.

**CRITICAL**: No user story work should begin until this phase is complete.

- [X] T004 Add or align TP/SL-related Pydantic models (PositionResponse, TargetsUpdateRequest) with the data model in backend/trading/schemas.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\schemas.py)
- [X] T005 Wire any new TargetsUpdateRequest fields (e.g., clear_tp, clear_sl) through the positions targets endpoint in backend/api/routes_positions.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\routes_positions.py)
- [X] T006 [P] Ensure exchange gateway exposes a reliable account-level orders snapshot (including isPositionTpsl orders) for TP/SL mapping in backend/exchange/exchange_gateway.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\exchange\exchange_gateway.py)
- [X] T007 [P] Ensure OrderManager caches and exposes TP/SL mapping hooks for positions in backend/trading/order_manager.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py)
- [X] T008 Confirm Positions API response includes normalized take_profit and stop_loss fields used by the UI in backend/api/routes_positions.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\routes_positions.py)

**Checkpoint**: Backend contracts and core TP/SL plumbing are ready; user-story-specific behaviour can now be implemented.

---

## Phase 3: User Story 1 - Trader reliably updates TP/SL for a position (Priority: P1) — MVP

**Goal**: A trader can update TP and/or SL for a position and see the exact values reflected in the Positions UI and `/api/positions`, including after a manual refresh.

**Independent Test**: With an open position, change TP and SL to new valid prices using the Modify controls; verify `/api/positions` and the Positions table show the new values and they remain correct after a browser refresh.

### Tests for User Story 1

- [X] T009 [P] [US1] Add unit tests for TP/SL extraction and merge logic in OrderManager list_positions/_enrich_positions in backend/trading/order_manager.py and backend/tests (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py)
- [X] T010 [P] [US1] Add HTTP-level test for updating TP/SL via `/api/positions/{position_id}/targets` and verifying `/api/positions` in backend/tests (D:\Automation\Python scripts\apex-risk-trade-tool\backend\tests)

### Implementation for User Story 1

- [X] T011 [US1] Implement robust TP/SL map construction from account orders (isPositionTpsl, STOP_*, TAKE_PROFIT_*) in backend/exchange/exchange_gateway.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\exchange\exchange_gateway.py)
- [X] T012 [P] [US1] Ensure OrderManager merges TP/SL map into normalized positions and preserves existing hints where appropriate in backend/trading/order_manager.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py)
- [X] T013 [US1] Ensure positions listing endpoint returns positions with correct take_profit and stop_loss based on merged map in backend/api/routes_positions.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\routes_positions.py)
- [X] T014 [P] [US1] Wire existing Modify TP/SL UI controls to use the `/api/positions/{position_id}/targets` endpoint with current field names in ui/index.html and related JS (D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html)
- [X] T015 [US1] Verify Modify flow round-trip (submit, backend update_targets, refreshed positions) and align any UI display formatting (“TP: <value> / SL: <value>”) in ui/index.html and ui/js (D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html)

**Checkpoint**: User Story 1 is independently functional and testable; TP/SL updates reflect accurately in both API and UI.

---

## Phase 4: User Story 2 - Trader intentionally clears TP and/or SL (Priority: P2)

**Goal**: A trader can explicitly clear TP, SL, or both for a position in a way that is deliberate and clearly reflected in both backend state and the UI.

**Independent Test**: Starting from a position with both TP and SL set, use the UI to clear TP, clear SL, and clear both; verify `/api/positions` shows null values for cleared protections and the UI renders “TP: None” / “SL: None” accordingly.

### Tests for User Story 2

  - [X] T016 [P] [US2] Add backend tests for clear-only requests (clear_tp, clear_sl) to `/api/positions/{position_id}/targets` and resulting `/api/positions` output in backend/tests (D:\Automation\Python scripts\apex-risk-trade-tool\backend\tests)

### Implementation for User Story 2

  - [X] T017 [US2] Extend TargetsUpdateRequest validation to allow explicit clear_tp and clear_sl semantics, rejecting no-op updates in backend/trading/schemas.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\schemas.py)
  - [X] T018 [US2] Implement backend handling of clear_tp and clear_sl (cancelling existing TP/SL orders and clearing local hints/map entries) in OrderManager.modify_targets and ExchangeGateway.update_targets in backend/trading/order_manager.py and backend/exchange/exchange_gateway.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py)
  - [X] T019 [P] [US2] Update positions targets API contract usage (request/response shape) to match clear semantics while remaining backward-compatible for existing clients in backend/api/routes_positions.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\routes_positions.py)
  - [X] T020 [P] [US2] Add explicit Clear TP and Clear SL UI controls or flows wired to send clear-only requests without accidentally dropping the other target in ui/index.html and related JS (D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html)
  - [X] T021 [US2] Ensure UI labels and confirmations clearly indicate when protections are being removed and prevent accidental clears (e.g., confirmation or distinct styling) in ui/index.html (D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html)

**Checkpoint**: User Stories 1 and 2 are independently functional; traders can both modify and intentionally clear TP/SL with consistent backend and UI behaviour.

---

## Phase 5: User Story 3 - Trader trusts TP/SL display after refresh or reconnect (Priority: P3)

**Goal**: A trader can rely on TP/SL values shown in the UI after refreshes and intermittent connectivity; the display remains aligned with the latest confirmed exchange state rather than flipping to `None` during transient gaps.

**Independent Test**: Set TP/SL for a position, then simulate backend restart or WS reconnect; verify that TP/SL values in the Positions UI and `/api/positions` remain correct and do not revert to stale or `None` values unless protections are truly gone.

### Tests for User Story 3

- [X] T022 [P] [US3] Add integration-style tests or harness to simulate account stream snapshots with and without TP/SL orders and validate resulting `/api/positions` output in backend/tests (D:\Automation\Python scripts\apex-risk-trade-tool\backend\tests)

### Implementation for User Story 3

- [X] T023 [US3] Ensure account WS handler caches untriggered isPositionTpsl orders and persists a reasonable last-known state across brief gaps in backend/exchange/exchange_gateway.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\exchange\exchange_gateway.py)
- [X] T024 [P] [US3] Adjust TP/SL map merge logic so temporary empty snapshots do not clear previously known protections until an authoritative state indicates removal in backend/trading/order_manager.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py)
- [X] T025 [US3] Ensure `/api/positions` and stream payloads remain consistent (no regressions where TP/SL appears in one but not the other) in backend/api/routes_stream.py and backend/api/routes_positions.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\routes_stream.py)
- [X] T026 [P] [US3] Verify UI behaviour on refresh/reconnect (including via localhost dev setup) and adjust any client-side caching needed to avoid flickering TP/SL values in ui/index.html and ui/js (D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html)

**Checkpoint**: All three user stories function independently; TP/SL display, modify, and clear flows remain trustworthy through reconnects.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements and hardening that affect multiple TP/SL stories.

- [ ] T027 [P] Add or update inline and structured logging for TP/SL operations (set, modify, clear, stream reconciliation) in backend/exchange/exchange_gateway.py and backend/trading/order_manager.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\exchange\exchange_gateway.py)
- [ ] T028 [P] Update documentation references for TP/SL (cheatsheets, design docs) to reflect new behaviour in apex_api_cheatsheet.md and spec/ docs (D:\Automation\Python scripts\apex-risk-trade-tool\apex_api_cheatsheet.md)
- [ ] T029 Review and refactor any duplicated TP/SL mapping logic to keep a single clear code path in backend/trading/order_manager.py and backend/exchange/exchange_gateway.py (D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py)
- [ ] T030 Run full backend tests and the quickstart TP/SL checks from specs/001-fix-tp-sl-bug/quickstart.md, addressing any regressions (D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-fix-tp-sl-bug\quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **User Stories (Phases 3–5)**: All depend on Foundational completion; US1 (P1), US2 (P2), and US3 (P3) can proceed in priority order or in parallel once shared TP/SL plumbing is stable.
- **Polish (Phase 6)**: Depends on desired user stories (at least US1, preferably US1–US3) being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2; no dependency on other stories; forms the MVP.
- **User Story 2 (P2)**: Depends on US1’s modify flow and TP/SL mapping being in place; must not break US1 semantics.
- **User Story 3 (P3)**: Depends on US1/US2 so it can reason about TP/SL state under reconnect scenarios.

### Within Each User Story

- Tests (where included) should be written and run before or alongside implementation.
- Backend mapping and API behaviour should stabilize before UI wiring changes for that story.
- Story is complete when its Independent Test from spec.md passes using documented quickstart flows.

### Parallel Opportunities

- Setup tasks T002 and T003 can run in parallel with T001 once the venv exists.
- Foundational tasks T006–T008 can run in parallel after T004/T005 define the contracts.
- Within each story, tasks marked [P] (e.g., T009, T010, T012, T014, T020, T022, T024, T026, T027, T028) can be executed in parallel by different contributors, provided they do not touch the same file regions.
- User Stories 2 and 3 can begin in parallel after US1 backend behaviours are in place, as long as clear responsibilities per file are maintained.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.  
2. Complete Phase 2: Foundational.  
3. Complete Phase 3: User Story 1 (TP/SL update and display).  
4. Run quick functional checks and backend tests; ensure TP/SL updates behave correctly.  
5. Optionally deploy/demo with only US1 enabled as a minimal but reliable TP/SL fix.

### Incremental Delivery

1. After MVP, implement Phase 4 (US2 — clear TP/SL) and validate independently.  
2. Implement Phase 5 (US3 — refresh/reconnect correctness), focusing on stream behaviour and resiliency.  
3. Apply Phase 6 polish and logging, then re-run quickstart flows to ensure end-to-end stability.

### Parallel Team Strategy

With multiple contributors:

- One person focuses on backend TP/SL mapping and positions API (Phases 2–3).  
- A second focuses on UI TP/SL Modify/Clear flows (Phases 3–4).  
- A third focuses on stream resiliency and reconnect behaviour plus tests (Phase 5).  
- All can share Phase 6 polish tasks as time allows.
