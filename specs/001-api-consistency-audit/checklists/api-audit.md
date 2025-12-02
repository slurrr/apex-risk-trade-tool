# Checklist: API Audit Requirements Quality

**Purpose**: Unit tests for requirements quality of the API consistency audit  
**Created**: 2025-12-02  
**Audience**: Self-review (author)  
**Focus**: API correctness + security/data safety

## Requirement Completeness

- [x] CHK001 Are requirements explicit that 100% of REST and WebSocket invocations must be mapped with status in `mapping.md`? [Completeness, Spec §FR-001, Spec §SC-001]
- [x] CHK002 Are base URL and `/v3` version alignment requirements documented for all environments (testnet/mainnet) and topics? [Completeness, Spec §FR-002, Spec §Edge Cases]
- [x] CHK003 Are margin and balance endpoint requirements (`/v3/account`, `/v3/account-balance`, `/v3/set-initial-margin-rate`) fully covered? [Completeness, Spec §FR-007]
- [x] CHK004 Are redundancy/consolidation expectations captured, including how to document exceptions? [Completeness, Spec §FR-010, Clarifications 2025-12-02]

## Requirement Clarity

- [x] CHK005 Is the transport rationale requirement (REST vs WebSocket) defined with clear criteria for live vs transactional use cases? [Clarity, Spec §FR-003]
- [x] CHK006 Are required/optional payload fields and enums per endpoint/topic unambiguously specified, including casing and symbol formats? [Clarity, Spec §FR-004, Spec §Edge Cases]
- [x] CHK007 Are signing/auth header requirements (timestamp + method + path + body; header names) clearly stated without ambiguity? [Clarity, Spec §FR-005]
- [x] CHK008 Is “sensitive data” defined clearly enough to drive logging/redaction expectations (keys, passphrases, signatures, wallet addresses, clientOrderIds)? [Clarity, Spec §FR-008, Spec §Key Entities]

## Requirement Consistency

- [x] CHK009 Are symbol format rules (REST `BTC-USDT` vs WS `BTCUSDT`) applied consistently across requirements and edge cases? [Consistency, Spec §FR-004]
- [x] CHK010 Do order workflow requirements (market price via worst-price lookup, `limitFee`, status/cancel enums) align across FRs and acceptance scenarios? [Consistency, Spec §FR-006, Spec §User Story 3]

## Acceptance Criteria Quality

- [x] CHK011 Are success criteria measurable and traceable to the functional requirements (e.g., mapping coverage, unjustified polling, data leakage)? [Acceptance Criteria, Spec §SC-001–SC-005]

## Scenario Coverage

- [x] CHK012 Are streaming vs transactional scenarios covered, including rationale for transport choice per use case? [Coverage, Spec §FR-003, Spec §User Story 2]
- [x] CHK013 Are dynamically constructed endpoints/topics and UI-side calls included in the mapping scope? [Coverage, Spec §Edge Cases, Spec §User Story 1]

## Edge Case Coverage

- [x] CHK014 Are fallback/retry behaviors specified so they do not silently change transport (e.g., REST polling replacing WS) without rationale? [Edge Case, Spec §Edge Cases, Spec §FR-003]
- [x] CHK015 Are environment-dependent behaviors (testnet vs mainnet base URLs, version drift) explicitly addressed with required documentation? [Edge Case, Spec §Edge Cases, Spec §FR-002]

## Non-Functional Requirements

- [x] CHK016 Are data-safety requirements explicit on log/telemetry redaction for all sensitive identifiers and headers? [Non-Functional, Spec §FR-008]

## Dependencies & Assumptions

- [x] CHK017 Is the assumption that `apex_api_cheatsheet.md` is authoritative validated or bounded (version, updates)? [Assumption, Spec §Assumptions]

## Ambiguities & Conflicts

- [x] CHK018 Are discrepancy severity levels/categories defined to keep logging consistent across `mapping.md`, `discrepancies.md`, and summaries? [Ambiguity, Spec §FR-009, Tasks Phase 7]
