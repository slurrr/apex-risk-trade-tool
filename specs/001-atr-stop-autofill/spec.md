# Feature Specification: Automatic ATR-Based Stop Loss Prefill

**Feature Branch**: `[001-atr-stop-autofill]`  
**Created**: 2025-12-11  
**Status**: Draft  
**Input**: User description: "New feature - I would like to implement a stop loss calculation and automatic population of the Stop field in the UI. This project currently auto populates the Entry field with the last price after fetching it based on the symbol selected in the UI Symbol dropdown menu. I would like the Stop field to automatically populate a stop loss based on whatever price is entered into the Entry field. The price in the Entry field will be used to calculate the stop loss based on ATR, for example stop_price = entry_price - atr * multiplier and atr = compute_atr(timeframe, period), where multiplier, timeframe and period are configurable and can be pulled from env vars MULTIPLIER, TIMEFRAME, PERIOD. Apex SDK shows GET /v3/klines for OHLC data and a WS subscription for candle data. I've included a reference API document scoped to this feature: klines_api.txt. We can prefetch candles with the public REST endpoint and subscribe to the WS candle stream to build a buffer that we can use to calculate ATR in near real time. The Stop field should load almost instantly with the stop_loss."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic stop loss when entry price is set (Priority: P1)

When a trader selects a symbol and has an entry price filled in (either automatically from the latest price or manually overridden), the system automatically calculates and fills a default stop loss price based on an ATR-driven risk rule, so the trader does not have to calculate it manually.

**Why this priority**: This is the primary time-saving and risk-reduction benefit; traders can consistently apply risk rules with fewer manual steps during order entry.

**Independent Test**: A tester can simulate selecting a symbol, verify the entry price appears, adjust it if needed, and confirm that a reasonable ATR-based stop loss is automatically populated without any additional user input.

**Acceptance Scenarios**:

1. **Given** a trader selects a symbol in the Symbol dropdown and the Entry field is populated with the latest price, **When** the Entry field contains a valid price and ATR data is available, **Then** the Stop field is automatically populated with a default stop loss price derived from the ATR-based rule.
2. **Given** the Stop field is auto-populated from an ATR-based rule, **When** the trader edits the Entry price before submitting the order, **Then** the Stop field is recalculated and updated to reflect the new entry price before order submission.

---

### User Story 2 - Configurable timeframe for ATR calculation (Priority: P2)

Operations staff can configure the timeframe used for ATR-based stop loss calculations in a single runtime configuration setting so that risk rules can align with different trading styles (e.g., intraday vs. swing) without code changes.

**Why this priority**: The correct timeframe is important for valid risk management, but it does not prevent basic use of the tool; most users can still benefit from automatic stops even with a default timeframe.

**Independent Test**: A tester can change the configured ATR timeframe, restart the application if required, and verify that subsequent automatic stop loss values use ATR data from the new timeframe.

**Acceptance Scenarios**:

1. **Given** a default ATR timeframe is configured in the application settings, **When** operations change this setting and the application is refreshed or restarted, **Then** all newly calculated automatic stop loss values use ATR data from the updated timeframe.
2. **Given** no explicit per-user timeframe selection is available in the UI, **When** different users enter trades after a timeframe change, **Then** all users see automatic stop loss values that consistently reflect the configured ATR timeframe.

---

### User Story 3 - Manual control and graceful degradation (Priority: P3)

When ATR data is not available or a trader prefers a custom stop loss, they can still manually enter or adjust the Stop field, with clear indication if automatic calculation was not applied.

**Why this priority**: Ensures the feature does not block trading activity and provides flexibility for advanced users.

**Independent Test**: A tester can simulate a situation where ATR data is missing or invalid and verify that the Stop field stays editable, the user is informed, and a manual stop can still be entered and used for risk checks.

**Acceptance Scenarios**:

1. **Given** ATR data for the selected symbol and configured timeframe is unavailable or incomplete, **When** a trader selects that symbol and sets an entry price, **Then** the system clearly indicates that automatic stop loss calculation is unavailable and leaves the Stop field empty but editable.
2. **Given** the Stop field is auto-populated with an ATR-based value, **When** a trader manually edits the Stop field, **Then** the system retains the trader’s manual stop loss value and uses it for any subsequent risk checks or order previews.

---

### Edge Cases

- What happens when the Entry field contains an invalid, zero, or negative price, or is cleared before submission? The system should not attempt to calculate a stop loss and should prompt the user to provide a valid entry price.
- How does the system handle situations where ATR data is delayed, partially available, or temporarily inconsistent across timeframes? The system should avoid showing misleading automatic values and should clearly indicate when a safe default cannot be provided.
- What happens if the configured ATR timeframe is missing or misconfigured in the runtime settings? The system should fall back to a safe default timeframe defined by the product owner and log the configuration issue for follow-up.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a valid entry price is present for a selected symbol and ATR data is available, the system MUST automatically calculate a default stop loss price based on a defined ATR-based risk rule and populate the Stop field without additional user input.
- **FR-002**: The system MUST recalculate and update the default automatic stop loss value whenever the Entry price is changed by the user prior to order submission.
- **FR-003**: The timeframe used for ATR-based stop loss calculations MUST be configurable through a single runtime configuration value that can be changed without modifying the application code.
- **FR-004**: When ATR data is unavailable, incomplete, or deemed unreliable for the selected symbol and configured timeframe, the system MUST refrain from populating an automatic stop loss, clearly indicate that automatic calculation is unavailable, and still allow the user to manually enter a Stop value.
- **FR-005**: The Stop field MUST remain visible and editable at all times during trade entry so that users can review, accept, or override the automatically calculated stop loss before submitting the trade.
- **FR-006**: For both long and short trades, the system MUST calculate the automatic stop loss on the appropriate side of the entry price (below entry for long positions, above entry for short positions) according to the defined ATR-based risk rule.
- **FR-007**: The stop loss value (whether automatic or manually entered) MUST be included consistently in any risk checks, previews, or summaries presented to the user before finalizing the trade.
- **FR-008**: The ATR-based risk rule MUST expose its key parameters (such as ATR lookback period and volatility multiplier) as operations-managed configuration values rather than hard-coded settings, so that risk policies can be updated without changes to application code.

### Key Entities *(include if feature involves data)*

- **Trade Input**: Represents a potential trade being entered by the user, including symbol, entry price, side (long/short), quantity, stop loss price, and any other risk-related parameters visible in the UI.
- **ATR Configuration**: Represents configuration used for ATR-based calculations, including the selected timeframe and the lookback period or other parameters defined by the risk policy, managed through runtime configuration rather than per-user settings.
- **Market Volatility Data (ATR)**: Represents historical price-derived data for each symbol and timeframe required to compute ATR-based risk metrics that inform the default stop loss price.

### Assumptions

- The ATR calculation method and specific risk rule parameters (such as ATR multiplier and ATR lookback period) are defined and owned by the risk team and surfaced through operations-managed configuration.
- Runtime configuration for the ATR timeframe follows existing project conventions for operations-managed settings (for example environment variables or configuration files that operations staff can adjust without code changes).
- Users already understand the concept of stop loss orders and how they affect trade risk; this feature does not need to educate them on basic risk management concepts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In usability tests, at least 80% of representative users can enter a trade with an appropriate stop loss in under 30 seconds using the automatic stop loss prefill, compared to their baseline manual calculation flow.
- **SC-002**: In controlled test scenarios, 100% of trades created with automatic stops have stop loss values that match the defined ATR-based risk rule within expected rounding tolerances.
- **SC-003**: After launch, the proportion of trades submitted without any stop loss configured decreases by at least 50% compared to the baseline period before this feature.
- **SC-004**: In a post-release survey or feedback review, at least 75% of active users report that automatic stop loss prefilling makes trade entry easier or reduces their need for manual calculations.
- **SC-005**: In performance tests with representative market data, at least 95% of automatic Stop field updates (after a valid Entry price is set or changed and ATR data is available) complete within 1 second, so that the stop loss appears almost instantly from the user's perspective.
