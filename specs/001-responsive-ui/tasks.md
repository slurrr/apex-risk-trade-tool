# Tasks: Responsive UI & theming

**Input**: Design documents from `D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-responsive-ui\`
**Prerequisites**: plan.md (required), spec.md (user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec; focus on implementation and manual UX checks per quickstart.

**Organization**: Tasks grouped by user story to keep each slice independently testable.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ready environment and configuration for feature work.

- [X] T001 Install Python deps via `requirements.txt` in `D:\Automation\Python scripts\apex-risk-trade-tool\requirements.txt` using repo venv.
- [ ] T002 [P] Copy `.env.example` to `.env` and fill API credentials in `D:\Automation\Python scripts\apex-risk-trade-tool\.env`.
- [ ] T003 [P] Document/confirm `window.API_BASE` backend URL in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html` (or shared config script).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend contracts and data plumbing all stories rely on.

- [X] T004 Expand Pydantic schemas for symbols, account summary, close/targets in `D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\schemas.py`.
- [X] T005 Add ExchangeGateway helpers for symbol catalog, account summary, partial close, and TP/SL updates in `D:\Automation\Python scripts\apex-risk-trade-tool\backend\exchange\exchange_gateway.py`.
- [X] T006 Wire OrderManager methods for listing symbols, account summary, partial close, and TP/SL modify; ensure normalized fields (entry, TP/SL) in `D:\Automation\Python scripts\apex-risk-trade-tool\backend\trading\order_manager.py`.
- [X] T007 Add/adjust FastAPI routes for symbols, account summary, position close, and targets modify; keep orders/positions shapes aligned with UI needs in `D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\`.
- [X] T008 Ensure stream normalization includes new fields (symbol, entry, TP/SL) and is consistent with REST payloads in `D:\Automation\Python scripts\apex-risk-trade-tool\backend\api\routes_stream.py`.

**Checkpoint**: Backend delivers symbol list, account summary, order/position shapes, and manage/modify endpoints.

---

## Phase 3: User Story 1 - Trader sees context and enters trades fast (Priority: P1)

**Goal**: Branded header, account summary row, two-by-three trade grid with live symbol dropdown; Open Orders shows Symbol/Entry (no order ID).

**Independent Test**: Load UI, see “TradeSizer” header and account summary row; complete trade form with grid layout and filtered symbol dropdown; Open Orders shows Symbol/Entry columns without order ID.

- [X] T009 [US1] Update markup for header/title and account summary row placement in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html`.
- [X] T010 [P] [US1] Apply burnt-orange header styling, minimalist summary row dividers, and two-by-three grid layout in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css`.
- [X] T011 [P] [US1] Implement symbol dropdown with type-ahead filtering and format guard; integrate with trade form in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\js\preview.js`.
- [X] T012 [P] [US1] Fetch and render account summary (equity, uPNL color-coded, available margin) in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\js\app.js` (or new shared script) and bind to index layout.
- [X] T013 [US1] Refactor orders table markup to remove Order ID column and add Symbol/Entry headers in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html`; update population logic in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\js\orders.js`.

**Checkpoint**: US1 usable end-to-end with header, summary, grid, symbol dropdown, and updated orders view.

---

## Phase 4: User Story 2 - Mobile trader completes core tasks (Priority: P2)

**Goal**: Mobile viewport (≈320–480px) remains fully functional without horizontal scroll; paired fields stack cleanly.

**Independent Test**: On a phone-sized viewport, complete trade setup and view orders/positions with no clipped controls or horizontal scrolling.

- [ ] T014 [US2] Add responsive breakpoints to stack grid rows and ensure tables/forms reflow on ≤480px in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css`.
- [ ] T015 [P] [US2] Adjust trade form markup if needed for stacking order/pairing in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\index.html`.
- [ ] T016 [P] [US2] Increase touch target spacing and font sizing for mobile controls in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css`.

**Checkpoint**: US2 flows work on mobile without zoom or horizontal scroll.

---

## Phase 5: User Story 3 - Desktop user keeps clarity while resizing (Priority: P3)

**Goal**: Desktop split-screen (≈1024–1440px) retains readable tables and actions without overlap.

**Independent Test**: Resize desktop browser to half width; verify tables/panels reflow and primary actions remain visible.

- [ ] T017 [US3] Tune desktop breakpoints for tables/panels to wrap gracefully and keep actions visible in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css`.
- [ ] T018 [P] [US3] Adjust orders/positions rendering (column truncation or stacking cues) for mid-width layouts in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\js\orders.js` and `ui\js\positions.js`.

**Checkpoint**: US3 stays clear on resized desktop windows.

---

## Phase 6: User Story 4 - Interface matches system theme with clear feedback (Priority: P4)

**Goal**: UI respects system light/dark, uses burnt-orange resting state with red press feedback; theme switches in <1s without input loss.

**Independent Test**: Toggle OS theme; UI follows instantly. Press buttons: see red flash returning to burnt orange; text/icon contrast remains readable.

- [ ] T019 [US4] Define CSS variable palettes for light/dark, burnt-orange primary, and red press state; wire prefers-color-scheme and transitions in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css`.
- [ ] T020 [P] [US4] Add JS theme listener to apply/remove theme class and preserve form state on change in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\js\app.js`.
- [ ] T021 [P] [US4] Ensure button/interaction states use burnt-orange default and brief red pressed feedback (0.15s) in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css` and any shared JS helpers.

**Checkpoint**: US4 theme responsiveness and feedback validated.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency and validation across stories.

- [ ] T022 [P] Sweep UI for contrast/spacing regressions across breakpoints in `D:\Automation\Python scripts\apex-risk-trade-tool\ui\css\styles.css`.
- [ ] T023 [P] Smoke test endpoints and UI flows per `specs/001-responsive-ui/quickstart.md`; update notes if steps change.
- [ ] T024 Run backend lint/tests where applicable (`pytest` in `D:\Automation\Python scripts\apex-risk-trade-tool\backend\tests`) and fix any issues touched by this feature.

---

## Dependencies & Execution Order

- Phases run sequentially: Setup → Foundational → US1 → US2 → US3 → US4 → Polish.
- User stories can run in parallel after Foundational if resourcing allows, but shared files (CSS/index) favor sequential merges.
- US2–US4 build on UI patterns from US1; prefer implementing US1 first to reduce rework.

## Parallel Opportunities

- Setup tasks T002–T003 can run alongside T001.
- Foundational tasks T004–T008 can proceed in parallel where files differ (schemas vs gateway vs API vs stream), but coordinate shared model shapes.
- Within US phases, tasks marked [P] touch different files and can proceed concurrently.

## Implementation Strategy

- MVP: Complete Setup, Foundational, and US1 to deliver header + summary + grid + symbol dropdown + updated orders; validate via quickstart.
- Incremental: Add US2 (mobile), then US3 (desktop resizing), then US4 (theme/feedback); finish with Polish checks and quickstart validation.
