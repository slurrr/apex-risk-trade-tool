# Feature Specification: Responsive UI & theming

**Feature Branch**: `001-responsive-ui`  
**Created**: 2025-12-02  
**Status**: Draft  
**Input**: User description: "feature: ui looks and functionality updates - basics - responsive design that looks great in a web browser on pc but also looks good and is just as functional on mobile. Inherits system settings for dark/light mode. buttons are all burnt orange and turn red momentarily when pressed before"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trader sees context and enters trades fast (Priority: P1)

A trader immediately sees the branded header, account summary, and the two-by-three trade input grid to place or adjust a trade quickly.

**Why this priority**: Fast clarity and entry reduce errors and delays in volatile markets.

**Independent Test**: Load the app and complete a trade setup using the arranged inputs and filtered symbol dropdown without hunting for fields or context.

**Acceptance Scenarios**:

1. **Given** the user opens the app, **When** the header renders, **Then** it shows "TradeSizer" in a burnt-orange, assertive style and a single-row account summary with total equity, uPNL color-coded red/green, and available margin separated by subtle dividers.
2. **Given** the user fills the trade form, **When** they interact with the two-by-three grid (Symbol and Risk% on row one; Entry and Stop on row two; Take Profit and Side on row three), **Then** all fields remain visible side by side without overlap and the symbol dropdown filters in real time to formatted symbols (e.g., BTC-USDT).

---

### User Story 2 - Mobile trader completes core tasks (Priority: P2)

A mobile user can review risk and place trades on a phone-sized screen without losing functionality or needing to zoom.

**Why this priority**: Mobile parity prevents blocking users who rely on phones while away from a desktop.

**Independent Test**: Load the app at a phone-sized viewport, complete a representative workflow (e.g., review positions and submit an order) without zooming or switching to desktop.

**Acceptance Scenarios**:

1. **Given** the user opens the app on a portrait phone, **When** they navigate through primary screens, **Then** all critical controls remain visible without horizontal scrolling or clipped content.
2. **Given** the user rotates the phone between portrait and landscape, **When** the viewport changes, **Then** layouts reflow within one second and primary actions stay accessible.

---

### User Story 3 - Desktop user keeps clarity while resizing (Priority: P3)

A desktop user can resize the browser window (e.g., split-screen) and still see clear, organized content with no hidden buttons.

**Why this priority**: Many users multitask; the interface must stay usable in constrained desktop layouts.

**Independent Test**: Resize the browser between common widths (e.g., 1024px to 1440px) and confirm no overlaps, truncation, or lost actions while completing a core task.

**Acceptance Scenarios**:

1. **Given** the user resizes from full width to half-screen on a laptop, **When** key screens reload or reflow, **Then** text, inputs, and buttons remain readable and reachable without horizontal scroll.
2. **Given** tables or panels are present, **When** the viewport narrows, **Then** they stack or scroll vertically while preserving visibility of the primary action buttons.

---

### User Story 4 - Interface matches system theme with clear feedback (Priority: P4)

A user sees the UI match their device's light or dark preference and gets clear red feedback when pressing burnt-orange buttons.

**Why this priority**: Respecting system theme reduces visual fatigue; consistent button states build trust during time-sensitive actions.

**Independent Test**: Toggle the OS theme and interact with primary buttons; confirm the UI updates theme instantly and press feedback appears and clears reliably.

**Acceptance Scenarios**:

1. **Given** the device is set to dark mode, **When** the user opens the app, **Then** all screens render in dark styling without flashes of light mode.
2. **Given** the user taps a primary button, **When** the press is registered, **Then** the button turns red briefly and returns to burnt orange after release or completion.

---

### Edge Cases

- Extremely narrow screens (<320px) should still show primary actions without overlapping text; if not possible, provide a clear prompt to rotate or enlarge.
- Rapid orientation changes should not leave any panel stuck partially off-screen or duplicated.
- Switching system theme while mid-flow should not reset in-progress form inputs or selections.
- Long labels or dynamic data should wrap or truncate gracefully without pushing buttons off-screen.
- Rapid repeated taps on buttons should not leave the control stuck in the red pressed state or trigger duplicate actions.
- Symbol list fetch or formatting errors should surface a clear message and keep the form usable without accepting malformed symbols.
- Sliding to 0% or 100% in the manage window should still allow Market Close and Limit Close without ambiguity.
- Attempting a Limit Close without a limit price should block submission with a clear prompt.
- Submitting TP/SL modifications with only one field populated should still update just that field; empty fields should not clear existing targets unless explicitly requested.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The interface MUST adapt fluidly from 320px to 1920px widths with no horizontal scrolling on primary screens and without hiding critical actions.
- **FR-002**: On viewports below roughly tablet width, navigation, tables, and forms MUST reflow into touch-friendly stacking while keeping all trading and risk actions available.
- **FR-003**: All interactive controls (buttons, inputs, menus) MUST remain fully usable by touch or mouse with target areas large enough for finger use and clear focus/hover states.
- **FR-004**: Mobile experiences MUST offer the same functional capabilities and data visibility as desktop (no reduced features on smaller viewports).
- **FR-005**: The UI MUST detect the device/system light or dark preference at load and apply a matching theme consistently across all screens.
- **FR-006**: The UI MUST respond to system theme changes during a session within one second, updating visible regions without a page reload and without losing in-progress user input.
- **FR-007**: Primary buttons MUST present a burnt-orange resting state with sufficient legibility; when pressed, they MUST turn red briefly and then return to their resting state after release or action completion.
- **FR-008**: Text, icons, and key controls MUST maintain readable contrast in both themes, aligning with common accessibility thresholds for body text and controls.
- **FR-009**: Visual feedback (including pressed-state) MUST be noticeable but brief, and MUST NOT obscure button labels or suggest the control is disabled.
- **FR-010**: The top header MUST display the title "TradeSizer" in a burnt-orange, assertive style that remains legible in both light and dark modes across viewports.
- **FR-011**: An account summary row MUST present total equity, total uPNL (red when negative, green when positive), and available margin in a minimalist single row with subtle dividers between values.
- **FR-012**: Trade inputs MUST be arranged as a two-column, three-row grid (Symbol + Risk% on row one; Entry + Stop on row two; Take Profit + Side on row three) and preserve these pairings even when stacking on smaller screens.
- **FR-013**: The Symbol field MUST be a dropdown populated on load with all tradeable symbols, filter options in real time as the user types, and restrict selection to correctly formatted symbols (e.g., BTC-USDT, ETH-USDT).
- **FR-014**: The Open Orders view MUST remove the order ID column and include Symbol and Entry columns showing the selected instrument and entry price.
- **FR-015**: The Open Positions view MUST include an Actions column with a Manage button that opens an inline manage window containing a Close Position slider from 0-100% with markers at 0, 25, 50, and 100.
- **FR-016**: The manage window MUST provide Market Close and Limit Close actions that apply the slider-selected percentage; Limit Close MUST require a limit price before submission.
- **FR-017**: A TP/SL column MUST display "TP: <value or None>" and "SL: <value or None>" stacked, with a Modify button that opens an inline form containing TP and SL inputs and a single Submit action that validates and applies whichever values are provided without clearing unspecified targets.

### Key Entities *(include if feature involves data)*

- **Display Context**: Represents the current viewport range (phone, tablet, desktop) and orientation; used to determine layout patterns and component density.
- **Theme Preference**: Captures the system-provided light or dark setting and any in-session changes that trigger theme updates across the UI.
- **Interaction Control**: Buttons and primary controls with defined states (resting burnt orange, pressed red) and accessibility properties (contrast, target size).
- **Account Summary**: Aggregated account metrics (total equity, total uPNL, available margin) with contextual coloring and separators.
- **Symbol Catalog**: Collection of tradeable symbols provided at load, supporting search/filter and enforcing formatted instrument identifiers.
- **Position Management Panel**: Inline controls for closing portions of a position and modifying TP/SL targets based on user-selected percentages and inputs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In usability tests, 95% of users complete a core workflow on a phone-sized viewport without zooming or horizontal scrolling in under 3 minutes.
- **SC-002**: At least 95% of interactive elements measured on mobile-sized viewports meet or exceed a finger-friendly target size, and all remain fully functional via touch.
- **SC-003**: The interface matches the system light/dark theme on initial load and reflects theme changes within one second in 100% of tested cases without losing user input.
- **SC-004**: Primary buttons show burnt-orange resting state and clear red press feedback for 100% of tested interactions, with visible feedback appearing within 0.15 seconds and clearing after release.
- **SC-005**: Accessibility review confirms readable contrast for text and controls in both themes, with no reported blockers related to color or legibility.
- **SC-006**: On load, 100% of tested sessions display the "TradeSizer" header and account summary row with correct values and color-coding, without layout overlap.
- **SC-007**: In usability tests, 95% of participants can complete trade setup using the two-by-three input grid in under 90 seconds without misidentifying fields.
- **SC-008**: Symbol dropdown returns properly formatted results for 100% of test queries and prevents submission of malformed symbols.
- **SC-009**: Open Orders view consistently shows Symbol and Entry columns (with no order ID) across tested viewports, and Open Positions shows the TP/SL stack plus Actions column in 100% of cases.
- **SC-010**: In position management tests, users can execute Market Close or Limit Close with a selected percentage in under 30 seconds, and Limit Close attempts without a price are blocked with a clear prompt in 100% of cases; TP/SL modifications update only the fields provided.

## Assumptions

- Existing trading and risk features remain unchanged; this work focuses on layout, responsiveness, and theming.
- Users access the application via modern browsers that expose system theme preferences.
- Brand-approved burnt orange and red tones are available for use in UI styling.
- A complete, correctly formatted list of tradeable symbols is available on load.
- Account metrics (equity, uPNL, available margin) are available and refreshed frequently enough for the summary row to stay accurate.
- Position data includes current TP and SL values (or None) and supports partial close and TP/SL modify actions.
