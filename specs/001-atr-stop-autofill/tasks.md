---
description: "Task list for Automatic ATR-Based Stop Loss Prefill"
---

# Tasks: Automatic ATR-Based Stop Loss Prefill

**Input**: Design documents from `specs/001-atr-stop-autofill/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are OPTIONAL and not explicitly requested for this feature, so this task list focuses on implementation tasks.  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- All descriptions include at least one concrete file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare configuration and documentation needed by the ATR stop-loss feature.

- [X] T001 [P] Add ATR configuration keys (TIMEFRAME, ATR_PERIOD, ATR_MULTIPLIER) to `.env.example` so they are visible to operators.
- [X] T002 [P] Add a short overview of the ATR-based stop loss feature to `README.md`, pointing to specs/001-atr-stop-autofill/spec.md and quickstart.md.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core backend infrastructure required before any user story can be completed.

**CRITICAL**: No user story work should begin until this phase is complete.

- [X] T003 Add ATR configuration settings (timeframe, period, multiplier) to `backend/core/config.py` and expose them via `get_settings()`.
- [X] T004 [P] Add an OHLC/klines fetch helper for Apex market data to `backend/exchange/apex_client.py` that returns recent candles for a symbol and timeframe.
- [X] T005 Create `backend/risk/atr.py` with a pure ATR calculation function that consumes a sequence of candles and returns an ATR value for a given symbol, timeframe, and period.
- [X] T006 Implement a helper in `backend/risk/atr.py` that combines ATR configuration and the ATR value to compute a default stop loss price for long and short trades.

**Checkpoint**: ATR configuration, market data access, and ATR computation helpers are ready for use by user-story-level endpoints and UI logic.

---

## Phase 3: User Story 1 - Automatic stop loss when entry price is set (Priority: P1)

**Goal**: When a trader selects a symbol and has an entry price filled in, the system automatically calculates and fills a default ATR-based stop loss in the Stop field, and recalculates it when the Entry price changes before submission.

**Independent Test**: With ATR data available, a tester can select a symbol, see the Entry field auto-populated (or manually set it), and observe the Stop field being populated and updated automatically based on the ATR rule, without any manual stop loss calculation.

### Implementation for User Story 1

- [X] T007 [P] [US1] Add `AtrStopRequest` and `AtrStopResponse` Pydantic models to `backend/trading/schemas.py` for requesting and returning ATR-based stop loss suggestions.
- [X] T008 [US1] Create `backend/api/routes_risk.py` with a `POST /risk/atr-stop` endpoint that validates `AtrStopRequest`, invokes the ATR stop helper in `backend/risk/atr.py`, and returns `AtrStopResponse`.
- [X] T009 [US1] Register the new risk router in `backend/main.py` using `app.include_router(...)` so the `/risk/atr-stop` endpoint is exposed to the UI.
- [X] T010 [P] [US1] Add a `TradeApp.fetchAtrStop` helper to `ui/js/app.js` that calls the `/risk/atr-stop` endpoint with `symbol`, `side`, and `entry_price` and returns the suggested stop loss.
- [X] T011 [US1] Wire automatic stop loss prefilling into symbol selection and `entry_price` changes in `ui/js/app.js` and `ui/js/preview.js` so the `stop_price` input is auto-populated when a valid entry price and ATR data are available, and is recalculated when the Entry price is modified before submission.

**Checkpoint**: User Story 1 is complete when the Stop field populates and updates automatically based on ATR whenever a valid Entry price is present and ATR data is available.

---

## Phase 4: User Story 2 - Configurable timeframe for ATR calculation (Priority: P2)

**Goal**: Operations staff can configure the timeframe used for ATR-based stop loss calculations via a single runtime configuration setting, without code changes, and all new automatic stops respect that setting.

**Independent Test**: A tester can change the ATR timeframe configuration, restart or reload the application as needed, and confirm that subsequent automatic stop loss suggestions use ATR data from the new timeframe.

### Implementation for User Story 2

- [X] T012 [US2] Ensure ATR configuration in `backend/core/config.py` reads the ATR timeframe from a single runtime setting (for example, TIMEFRAME) and passes it through to ATR helpers in `backend/risk/atr.py` instead of using any hard-coded timeframe.
- [X] T013 [US2] Document how operations can change ATR timeframe, period, and multiplier in `specs/001-atr-stop-autofill/quickstart.md` and `README.md`, including any required reload or restart steps.

**Checkpoint**: User Story 2 is complete when changing the configured ATR timeframe affects new automatic stop loss values without requiring code modifications.

---

## Phase 5: User Story 3 - Manual control and graceful degradation (Priority: P3)

**Goal**: Traders can always manually enter or adjust the Stop field, and when ATR data is unavailable or unreliable the system avoids auto-populating a stop while clearly indicating that automatic calculation is unavailable.

**Independent Test**: A tester can simulate missing ATR data or inconsistent market data and verify that the Stop field remains empty but editable with a clear message, and that any manually entered stop value is preserved and used for trade previews and execution without being overwritten by later automatic updates.

### Implementation for User Story 3

- [X] T014 [US3] Update the `/risk/atr-stop` handler in `backend/api/routes_risk.py` to distinguish between successful calculations and ATR-unavailable cases, returning an appropriate 503-style response (with error body) when a safe automatic stop cannot be computed.
- [X] T015 [US3] Update UI error handling in `ui/js/app.js` and `ui/js/preview.js` so that when ATR stop calculation fails (e.g., 503 or invalid data), the `stop_price` input remains empty and editable and a clear, non-blocking message is shown near the trade form.
- [X] T016 [US3] Add client-side logic in `ui/js/preview.js` to track manual edits to the `stop_price` input and prevent subsequent automatic ATR updates from overwriting user-provided stop loss values.

**Checkpoint**: User Story 3 is complete when traders can rely on manual stops in all degraded scenarios and are clearly informed when automatic ATR-based stops are not applied.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories and overall maintainability.

- [X] T017 [P] Add inline documentation and docstrings for ATR helpers and configuration fields in `backend/risk/atr.py` and `backend/core/config.py`.
- [X] T018 [P] Update feature documentation in `specs/001-atr-stop-autofill/spec.md` and `specs/001-atr-stop-autofill/quickstart.md` to reflect any final adjustments made during implementation.
- [X] T019 Run through the ATR stop-loss quickstart in `specs/001-atr-stop-autofill/quickstart.md` end-to-end and verify that all described steps and behaviors match the implemented system.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies – can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion – blocks all user stories because ATR configuration and helpers must exist first.
- **User Story 1 (Phase 3, P1)**: Depends on Foundational – implements core automatic stop loss behavior and should be completed first (MVP).
- **User Story 2 (Phase 4, P2)**: Depends on Foundational and User Story 1 – relies on ATR wiring but focuses on configurability.
- **User Story 3 (Phase 5, P3)**: Depends on Foundational and User Story 1 – adds graceful degradation and manual override behavior.
- **Polish (Phase 6)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2; no dependency on other user stories; defines the MVP.
- **User Story 2 (P2)**: Starts after Phase 2; logically follows US1 so that configuration applies to an already-working automatic stop feature.
- **User Story 3 (P3)**: Starts after Phase 2; ideally after US1 so degraded behavior is layered on top of the core implementation.

### Within Each User Story

- Shared helpers from Phase 2 must be available before endpoints and UI logic are added.
- For each story: configuration and backend logic should be implemented before UI wiring in `ui/js/*.js`.
- Each story should be functional and testable on its own before moving to the next priority.

### Parallel Opportunities

- Setup tasks T001 and T002 can run in parallel.
- Foundational task T004 can proceed in parallel with T003 and T005 where team capacity allows.
- In User Story 1, schema work (T007) and the front-end helper (T010) can run in parallel, while T008, T009, and T011 follow in sequence.
- Documentation and polish tasks T017 and T018 can run in parallel near the end of the implementation.

---

## Parallel Example: User Story 1

Example of safe parallelization within User Story 1:

- Backend model work:
  - Task: `T007 [US1]` in `backend/trading/schemas.py`
- Front-end helper work:
  - Task: `T010 [US1]` in `ui/js/app.js`

These can proceed in parallel, then converge on:

- API endpoint and wiring:
  - Task: `T008 [US1]` in `backend/api/routes_risk.py`
  - Task: `T009 [US1]` in `backend/main.py`
- UI integration:
  - Task: `T011 [US1]` in `ui/js/app.js` and `ui/js/preview.js`

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002).  
2. Complete Phase 2: Foundational (T003–T006).  
3. Complete Phase 3: User Story 1 (T007–T011).  
4. Stop and validate: confirm that automatic ATR-based stop loss prefilling works end-to-end for a typical trade.

### Incremental Delivery

1. Deliver MVP with Phases 1–3 (US1).  
2. Add Phase 4 (US2) to make ATR timeframe and related parameters configurable for operations.  
3. Add Phase 5 (US3) to handle degraded ATR scenarios and manual overrides gracefully.  
4. Apply Phase 6 (Polish) once core stories are stable.

### Parallel Team Strategy

With multiple developers:

- After Setup and Foundational phases, assign:
  - Developer A: Backend US1 tasks (T007–T009).
  - Developer B: Front-end US1 tasks (T010–T011).
  - Developer C: Configuration and documentation tasks for US2 (T012–T013).
  - Developer D: Degraded behavior and manual override tasks for US3 (T014–T016).

The tasks are structured so each user story remains independently implementable and testable while allowing safe parallel work.
