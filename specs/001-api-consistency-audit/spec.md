# Feature Specification: API Consistency Audit

**Feature Branch**: `001-api-consistency-audit`  
**Created**: 2025-12-02  
**Status**: Draft  
**Input**: User description: "lets create a spec to audit the codebase for api consistency. Ive uploaded apex_api_cheatsheet.md in the project root. Use this to create a constitution aligned spec for this audit that will define the scope and depth. We need to check every invocation of the api and check it to the reference document. determine whether we are using api calls appropriately i.e. REST calls where we should be using ws polling. verify assumptions like shape and parameters are all correct where they need be. we are safely invoking without leaking any private user data"

## Clarifications

### Session 2025-12-02

- Q: Should redundant Apex API calls be consolidated into the shared client or left distributed? → A: Consolidate redundant calls into `backend/exchange/apex_client.py` when behavior matches, allowing documented exceptions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Complete API inventory and mapping (Priority: P1)

An auditor catalogs every REST and WebSocket invocation in the codebase and maps each to the ApeX Omni cheat sheet to confirm path, method/topic, and environment usage.

**Why this priority**: Without a full inventory and mapping, downstream correctness and safety checks lack coverage.

**Independent Test**: Run the audit checklist on the codebase and produce a mapping table that pairs 100% of discovered calls with cheat-sheet references.

**Acceptance Scenarios**:

1. **Given** the codebase with existing API usage, **When** the auditor scans all API clients and call sites, **Then** each invocation is recorded with its endpoint/topic, expected shape, and environment.
2. **Given** the cheat sheet as reference, **When** an invocation is recorded, **Then** the mapping notes whether it matches the documented path, method/topic, and base URL version.

---

### User Story 2 - Validate transport and polling choices (Priority: P2)

An auditor verifies that latency-sensitive or streaming needs use WebSocket topics and that REST is used for transactional or idempotent operations per the cheat sheet guidance.

**Why this priority**: Ensures the system uses the correct transport, avoiding stale data or unnecessary load.

**Independent Test**: For each use case, confirm a documented rationale for REST vs WebSocket aligned to cheat-sheet recommendations.

**Acceptance Scenarios**:

1. **Given** features that need live order/position updates, **When** the auditor inspects their data sources, **Then** WebSocket topics (e.g., `ws_zk_accounts_v3`) are used instead of REST polling or a rationale for exceptions is documented.
2. **Given** transactional flows (order creation/cancel, margin changes), **When** calls are reviewed, **Then** REST endpoints under `/v3/...` are used with correct methods.

---

### User Story 3 - Verify payload correctness and data safety (Priority: P3)

An auditor checks that each call uses required fields, parameter names, symbol formats, and signatures, and that sensitive values are handled without leakage in logs or telemetry.

**Why this priority**: Prevents integration errors and protects user credentials and financial data.

**Independent Test**: Spot-check sampled calls and log outputs to ensure required fields and headers match the cheat sheet and that no secrets or PII are emitted.

**Acceptance Scenarios**:

1. **Given** REST order placement calls, **When** payloads are compared to the cheat sheet, **Then** required fields (e.g., `symbol`, `side`, `size`, `price`, `limitFee`, `expiration`, `clientOrderId`, `signature`) are present with correct casing.
2. **Given** authenticated calls, **When** headers and log statements are inspected, **Then** signatures and API keys are present only in requests and not persisted or logged in plaintext.

---

### User Story 4 - Identify redundancy and consolidation opportunities (Priority: P3)

An auditor determines whether duplicated or fragmented API calls should be consolidated into the shared Apex client wrapper (e.g., `backend/exchange/apex_client.py`) versus remaining distributed, weighing risk, maintenance, and behavioral differences.

**Why this priority**: Reduces inconsistency and drift risk while balancing effort and potential regression from refactors.

**Independent Test**: Review all discovered call sites for duplication and variance; propose a consolidation plan with benefits/risks and decide per case.

**Acceptance Scenarios**:

1. **Given** multiple call sites invoking the same endpoint/topic with similar parameters, **When** they are reviewed, **Then** duplication is identified with a recommendation to centralize or retain as-is with rationale.
2. **Given** critical flows that might be impacted by refactoring into a central client, **When** risk/benefit is evaluated, **Then** the audit documents whether to consolidate now, later, or not at all, with explicit risk notes.

---

### Edge Cases

- Dynamically constructed endpoints or topics that bypass shared clients must still be captured and validated against the cheat sheet.
- Calls using environment-dependent bases (testnet vs mainnet) must document which base is active and ensure version `/v3` is preserved.
- Retry or fallback logic must not degrade transport choice (e.g., switching to REST polling when WebSocket reconnects could suffice) without recorded justification.
- Any legacy parameter naming (snake_case) must be flagged against the camelCase REST convention in the cheat sheet.
- Cached or batched responses must still respect timestamp freshness requirements (e.g., WebSocket snapshots/deltas vs stale REST reads).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Audit MUST inventory every REST and WebSocket invocation in the codebase and map each to the ApeX Omni cheat sheet reference (path/topic, method, base URL).
- **FR-002**: Audit MUST confirm base URLs and versioning align with the cheat sheet (testnet/mainnet endpoints and `/v3` paths) for all calls.
- **FR-003**: Audit MUST verify transport choices are appropriate: WebSocket for streaming/authoritative updates (order/position/account topics), REST for transactional actions, with documented rationale for any deviations.
- **FR-004**: Audit MUST validate request payloads and response assumptions against the cheat sheet, including required fields, optional fields, enums, casing, and symbol formatting differences between REST (`BTC-USDT`) and WebSocket (`BTCUSDT`).
- **FR-005**: Audit MUST verify authentication and signing expectations: presence of required headers (`APEX-SIGNATURE`, `APEX-TIMESTAMP`, `APEX-API-KEY`, `APEX-PASSPHRASE` where applicable) and use of timestamp + method + path + body for signatures per reference.
- **FR-006**: Audit MUST confirm order workflows follow reference guidance (e.g., providing `price` even for market orders via worst-price lookup, using `limitFee`, handling order status enums and cancel reasons as documented).
- **FR-007**: Audit MUST ensure margin and balance operations use the correct endpoints (`/v3/account`, `/v3/account-balance`, `/v3/set-initial-margin-rate`) and that returned fields are not mis-assumed or repurposed.
- **FR-008**: Audit MUST assess data safety: no API keys, signatures, wallet addresses, or clientOrderIds are logged, cached, or exposed; logs redact secrets and avoid dumping full payloads unless scrubbed.
- **FR-009**: Audit MUST produce a documented list of discrepancies, gaps, or risks with recommended remediations and priorities.
- **FR-010**: Audit MUST recommend consolidating redundant Apex API call sites into `backend/exchange/apex_client.py` when behaviors are equivalent and document any exceptions with risk/benefit rationale.

### Key Entities *(include if feature involves data)*

- **API invocation**: A REST request or WebSocket subscription/message in the codebase, including path/topic, method, payload, headers, and environment base.
- **Reference contract**: The ApeX Omni API cheat sheet describing expected endpoints, topics, parameters, enums, and authentication/signing rules.
- **Sensitive data**: API keys, passphrases, signatures, wallet addresses, clientOrderIds, and any user-identifying fields that must not be logged or leaked.

### Assumptions

- The ApeX Omni cheat sheet in `apex_api_cheatsheet.md` is the authoritative reference for this audit.
- Existing code paths and feature flags are accessible for inspection across environments without needing production-only secrets.
- Log samples or tracing data can be reviewed to validate absence of sensitive value leakage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of REST and WebSocket invocations discovered are mapped to cheat-sheet references with documented status (match/deviation/rationale).
- **SC-002**: 0 unidentified or undocumented API invocations remain after the audit pass.
- **SC-003**: All transport choices for streaming data are either WebSocket-based or explicitly justified; no unjustified REST polling for live order/position updates.
- **SC-004**: No occurrences of sensitive data logged or persisted in plaintext are found in sampled logs/traces; any prior instances are documented with remediation actions.
- **SC-005**: All discrepancies in payload shape, required fields, enums, or symbol formats are cataloged with remediation recommendations and risk levels.
