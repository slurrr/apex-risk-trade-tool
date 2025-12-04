# Feature Specification: Fix TP/SL position updates

**Feature Branch**: `001-fix-tp-sl-bug`  
**Created**: 2025-12-04  
**Status**: Draft  
**Input**: User description: "we need to fix a feature. The TP/SL function"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trader reliably updates TP/SL for a position (Priority: P1)

A trader selects an open position, adjusts the take-profit and stop-loss values, and sees those protections applied exactly as entered for that position.

**Why this priority**: Reliable TP/SL updates are critical for controlling risk and locking in profit; broken behaviour can lead to unexpected losses.

**Independent Test**: With an open position, change TP and SL to new valid prices and verify that the position view reflects the new values and they remain correct after a manual refresh.

**Acceptance Scenarios**:

1. **Given** a user has an open position without TP or SL, **When** they open the TP/SL controls, enter valid TP and SL prices, and submit, **Then** the system confirms the change and the position row shows the new TP and SL values exactly as entered.
2. **Given** a user has an open position with existing TP and SL, **When** they change only one of the two fields and submit, **Then** the changed value is updated and the untouched value remains unchanged.

---

### User Story 2 - Trader intentionally clears TP and/or SL (Priority: P2)

A trader can deliberately remove one or both protective targets for a position in a way that is obvious and hard to do by accident.

**Why this priority**: Traders occasionally need to remove protections (for example to roll a strategy), but accidental removal creates unacceptable risk.

**Independent Test**: Start from a position with both TP and SL set, use the controls to clear TP, SL, and then both, and verify that the system clearly confirms each removal and never clears a target unless the user explicitly chooses to.

**Acceptance Scenarios**:

1. **Given** a position with both TP and SL set, **When** the user chooses to clear only the TP target, **Then** the positions view shows "TP: None" while the existing SL remains in place.
2. **Given** a position with TP and/or SL set, **When** the user confirms a "clear both" action, **Then** both targets are removed, the positions view shows no TP or SL values, and no further TP/SL executions occur for that position.

---

### User Story 3 - Trader trusts TP/SL display after refresh or reconnect (Priority: P3)

A trader can rely on the displayed TP/SL values even after refreshing the application or recovering from a temporary connection issue.

**Why this priority**: Stale or inconsistent TP/SL information undermines trust and may cause traders to make decisions based on incorrect protection levels.

**Independent Test**: Set TP and SL for an open position, force a refresh or simulated reconnect, and confirm that the displayed values still match the latest confirmed TP/SL levels on the account.

**Acceptance Scenarios**:

1. **Given** a position with active TP/SL protections, **When** the trader refreshes the positions view, **Then** the TP and SL values shown match the last confirmed settings and do not revert to stale data.
2. **Given** TP/SL updates and executions occur while the user is temporarily disconnected, **When** the connection is restored, **Then** the positions view reflects the true current TP and SL state (including cleared or filled protections).

---

### Edge Cases

- When a trader enters TP or SL at a price that would increase risk instead of reducing it for the position direction (for example, a stop-loss above the entry price on a long position), the system should block the change with a clear explanation and leave existing protections unchanged.
- When a trader submits a TP/SL update for a position that has just been fully closed, the system should reject the request with a clear message that the position is no longer open and no new protections are applied.
- When a trader attempts to submit multiple rapid TP/SL changes for the same position, the system should process them in order or collapse them into a single final state so that the resulting protections are predictable and clearly communicated.
- When an account data snapshot temporarily omits TP/SL orders that are still active on the exchange, the system should avoid flipping the display to "None" and instead preserve the last known good TP/SL values until it can reconcile with authoritative data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST display, for every open position, the current take-profit and stop-loss values (or an explicit indicator that none are set) in a single, easy-to-scan place.
- **FR-002**: The system MUST allow a user to submit new TP and SL values for a specific open position in a single action and apply those values only to that position.
- **FR-003**: When a user updates only one of the two values (TP or SL), the system MUST update that value and MUST NOT change or clear the other value.
- **FR-004**: The system MUST validate that TP and SL prices are consistent with the position direction (for example, long positions have a stop-loss below entry and a take-profit above entry; short positions use the inverse) and reject invalid combinations with human-readable messages.
- **FR-005**: The system MUST provide an explicit way to clear TP and SL targets, individually or together, and MUST only remove a target when the user has taken a clear "remove" action.
- **FR-006**: After a TP/SL change is accepted, subsequent views of positions and related summaries MUST show TP and SL values that are consistent with the last confirmed change, including after manual refresh or reconnect.
- **FR-007**: If the underlying exchange or downstream service rejects a TP/SL change, the system MUST surface a clear error to the user, MUST NOT leave the position in a partially updated state, and MUST keep the previous TP/SL protections active.
- **FR-008**: All TP/SL actions (set, modify, clear) MUST be logged with sufficient context (position identifier, symbol, side, old values, new values, outcome) to support later troubleshooting without exposing sensitive secrets.
- **FR-009**: The system MUST derive current TP and SL values for each open position from the authoritative account-level order and position data stream, using symbol and side to associate untriggered protective orders with their corresponding position.
- **FR-010**: For each open position, the system MUST ensure that at most one untriggered TP protection and one untriggered SL protection are active at any time; when a user requests a new TP or SL, any existing untriggered protection of the same type for that position MUST be retired or cancelled before the new protection takes effect.
- **FR-011**: The system MUST only display "None" for TP or SL when there is no active protective order of that type for the position on the account; as long as at least one valid untriggered protection of that type exists, the UI MUST show a concrete TP or SL value instead of "None".

### Key Entities *(include if feature involves data)*

- **Position**: Represents an open trade, including symbol, side, size, entry price, and pointers to the current TP and SL levels (or absence of them).
- **Protection Targets**: The pair of values (take-profit and stop-loss) attached to a position, including the most recently requested values and whether they are active or cleared.
- **TP/SL Change Request**: A single user action to set, modify, or clear TP and/or SL for one position, including requested values, validation outcome, and final applied state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In functional tests, 100% of valid TP/SL change requests result in the correct TP and SL values being displayed for the affected position within 5 seconds and remaining correct across manual refreshes.
- **SC-002**: In targeted tests where only one of TP or SL is changed, 100% of cases show the updated value while the untouched value remains identical to its previous value.
- **SC-003**: In negative tests with invalid TP/SL combinations (such as a stop-loss that would increase risk), 100% of requests are blocked with clear messages and no unintended removal or change of existing protections.
- **SC-004**: In simulated disconnect and reconnect scenarios, 100% of positions tested show TP and SL values that match the last confirmed successful change or the latest executed state on the account.
- **SC-005**: In usability sessions, at least 90% of traders can locate the TP/SL controls, update a target, and confirm the change in under 60 seconds without needing assistance.
- **SC-006**: In end-to-end tests where traders repeatedly modify TP and SL for the same position, 100% of runs end with no more than one untriggered TP and one untriggered SL protection per position on the account, and the UI matches that state.
- **SC-007**: In validation runs comparing the UI against representative account-level order snapshots, 100% of untriggered protective orders that meet the selection criteria are reflected in the TP/SL values for their associated positions, and no position with active protection is shown as "TP: None, SL: None" unless protections have truly been removed.

## Assumptions

- Each open position supports at most one active take-profit and one active stop-loss level at a time.
- TP and SL values are expressed as absolute prices in the instrument’s quote currency, not as percentages or ticks.
- Users understand the basic relationship between entry price, take-profit, and stop-loss for long and short positions; the system’s validation focuses on blocking obviously risky configurations rather than teaching trading strategies.
- Clearing TP and/or SL is considered a high-risk action, so the interface will require an explicit choice (such as a dedicated clear control or confirmation) rather than treating empty fields as an instruction to remove protections.
- The underlying exchange reliably reports the latest TP/SL state for a position so that the application can resynchronise its display after refresh or reconnect.
