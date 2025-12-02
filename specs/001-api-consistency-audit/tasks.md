# Tasks: API Consistency Audit

**Input**: Design documents from `/specs/001-api-consistency-audit/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are optional and not requested; focus on audit deliverables and validation artifacts.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare audit workspace and references

- [X] T001 Create audit artifact directory structure at `specs/001-api-consistency-audit/artifacts/` (mapping, discrepancies, safety).
- [X] T002 Copy reference `apex_api_cheatsheet.md` into `specs/001-api-consistency-audit/artifacts/reference/` for offline comparison.
- [X] T003 [P] Record tooling commands (rg, grep, search patterns) in `specs/001-api-consistency-audit/quickstart.md` if additional commands are needed for this audit.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Baseline inventory and templates that all stories rely on

- [X] T004 Generate initial API call site listing with `rg`/static scan and save to `specs/001-api-consistency-audit/artifacts/call-sites.txt`.
- [X] T005 Create mapping template table in `specs/001-api-consistency-audit/artifacts/mapping.md` (columns: source file/line, endpoint/topic, method, base URL, payload fields, headers, symbol format, status, notes).
- [X] T006 [P] Create discrepancy log skeleton in `specs/001-api-consistency-audit/artifacts/discrepancies.md` (categories: transport, payload, signing/auth, data safety, redundancy; severity; remediation).
- [X] T007 [P] Create data-safety checklist in `specs/001-api-consistency-audit/artifacts/data-safety.md` (items: logging redaction, caching, traces, clientOrderIds, keys, passphrases, signatures).

**Checkpoint**: Inventory scaffold ready; user stories can run in parallel.

---

## Phase 3: User Story 1 - Complete API inventory and mapping (Priority: P1)

**Goal**: Catalog 100% of REST/WS invocations and map to cheat sheet

**Independent Test**: `mapping.md` covers every call site with match/deviation status and reference alignment.

### Implementation for User Story 1

- [X] T008 [US1] Populate `mapping.md` with all REST endpoints (`/v3/...`) discovered in backend code.
- [X] T009 [P] [US1] Populate `mapping.md` with all WebSocket topics (`realtime_public`, `realtime_private`, `orderBook`, `instrumentInfo`, `recentlyTrade`, `ws_zk_accounts_v3`) from backend code.
- [X] T010 [P] [US1] Include any UI-side API calls (if present) in `mapping.md` with paths/topics and payload assumptions.
- [X] T011 [US1] Mark each row in `mapping.md` with status (match/deviation/rationale) against `apex_api_cheatsheet.md`.
- [X] T026 [US1] Validate base URLs (testnet/mainnet) and `/v3` path usage for all REST/WS calls; record per-row status in `specs/001-api-consistency-audit/artifacts/mapping.md`.
- [X] T027 [P] [US1] Log any environment or version mismatches in `specs/001-api-consistency-audit/artifacts/discrepancies.md` with notes on transport/payload impact.

**Checkpoint**: Mapping complete with 100% coverage and status labels.

---

## Phase 4: User Story 2 - Validate transport and polling choices (Priority: P2)

**Goal**: Ensure correct REST vs WebSocket usage per cheat sheet guidance

**Independent Test**: Each live-data use case documents transport choice and rationale; unjustified REST polling is flagged.

### Implementation for User Story 2

- [X] T012 [US2] Review `mapping.md` rows for live/streaming needs and annotate transport choice (REST vs WS) rationale.
- [X] T013 [P] [US2] Add transport findings to `discrepancies.md` for any unjustified REST polling or missing WebSocket subscriptions.
- [X] T014 [US2] Document approved exceptions (if any) in `mapping.md` with concise rationale.

**Checkpoint**: Transport choices validated or flagged with rationale.

---

## Phase 5: User Story 3 - Verify payload correctness and data safety (Priority: P3)

**Goal**: Validate payload fields, signing headers, symbol formats, and secret handling

**Independent Test**: Payloads match cheat sheet; no plaintext secrets/identifiers in logs or traces.

### Implementation for User Story 3

- [X] T015 [US3] Compare REST payloads to cheat sheet requirements and record deviations in `discrepancies.md` (required fields, casing, enums, symbol formats).
- [X] T016 [P] [US3] Verify signing/auth headers per cheat sheet and note gaps in `discrepancies.md` (APEX-SIGNATURE, APEX-TIMESTAMP, APEX-API-KEY, APEX-PASSPHRASE).
- [X] T017 [P] [US3] Run log/telemetry scan for sensitive data leakage and document results in `data-safety.md` and `discrepancies.md` if issues found.
- [X] T018 [US3] Confirm market order pricing (`price` via worst-price) and `limitFee` usage align with guidance; log findings in `discrepancies.md`.
- [X] T028 [US3] Audit `/v3/account` and `/v3/account-balance` usage for field assumptions and alignment with the cheat sheet; document in `mapping.md` and `discrepancies.md`.
- [X] T029 [P] [US3] Audit `/v3/set-initial-margin-rate` usage (inputs/validation) and record findings in `discrepancies.md`.

**Checkpoint**: Payload, signing, and data safety validated with documented issues.

---

## Phase 6: User Story 4 - Identify redundancy and consolidation opportunities (Priority: P3)

**Goal**: Identify duplicated calls and recommend consolidation into shared Apex client where behaviors match

**Independent Test**: Consolidation recommendations exist for every duplicated endpoint/topic with risk/benefit rationale.

### Implementation for User Story 4

- [X] T019 [US4] Cross-reference `mapping.md` for duplicated endpoints/topics and list candidates in `discrepancies.md` under redundancy category.
- [X] T020 [P] [US4] For each candidate, draft consolidation recommendation into `backend/exchange/apex_client.py` (or document retention) with rationale in `discrepancies.md`.
- [X] T021 [US4] Summarize consolidation plan and exceptions in `mapping.md` and link to `discrepancies.md` entries.

**Checkpoint**: Redundancy assessment complete with consolidation recommendations.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Finalize audit outputs and cross-story consistency

- [X] T022 [P] Normalize terminology and severity labels across `mapping.md`, `discrepancies.md`, and `data-safety.md`.
- [X] T023 Ensure all success criteria in spec are addressed and note completion status in `plan.md`.
- [X] T024 [P] Prepare final audit summary in `specs/001-api-consistency-audit/artifacts/summary.md` referencing mapping and discrepancies.
- [X] T025 Validate quickstart steps against actual commands used; update `quickstart.md` if needed.

---

## Phase 8: Remediation & Implementation Fixes

**Purpose**: Resolve audit findings and align implementation with cheat sheet/SDK

- [X] T030 Update order payload construction in `backend/exchange/exchange_gateway.py` to align with SDK signature (clientId/timeInForce) while tracking cheat-sheet fields; ensure signing covers full payload.
- [X] T031 [P] Redact or remove sensitive order payload logging on failures in `backend/exchange/exchange_gateway.py` (e.g., create_order_v3 exceptions).
- [X] T032 [P] Validate WS topic mappings vs cheat sheet (`instrumentInfo`, `orderBook`, `recentlyTrade`, `ws_zk_accounts_v3`) and document or adjust SDK subscriptions in `backend/exchange/exchange_gateway.py`.
- [X] T033 [P] Decide on QA host fallback for `/api/v3/ticker` in `backend/exchange/exchange_gateway.py`; align to cheat-sheet bases or gate by environment and document rationale in `artifacts/discrepancies.md`.
- [X] T034 [P] Decide on `/v3/set-initial-margin-rate` usage; either implement via `backend/exchange/exchange_gateway.py` or document as out of scope in `artifacts/mapping.md` and `discrepancies.md`.
- [X] T035 [P] Confirm signing headers attached by SDK; capture assurance in `artifacts/discrepancies.md` and `data-safety.md` (APEX-SIGNATURE, APEX-TIMESTAMP, APEX-API-KEY, APEX-PASSPHRASE).
- [X] T036 Consolidate ApeX REST/WS handling into `backend/exchange/apex_client.py`, refactor `exchange_gateway` to consume it, and document any intentional deviations in `artifacts/discrepancies.md`.
- [X] T037 Update `artifacts/mapping.md`, `artifacts/discrepancies.md`, `artifacts/data-safety.md`, and `artifacts/summary.md` to reflect remediations and close items.
- [X] T038 Walk `checklists/api-audit.md` and mark completed items reflecting remediations; keep evidence references.

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): No dependencies.
- Foundational (Phase 2): Depends on Setup; blocks all user stories.
- User Stories (Phases 3-6): Depend on Foundational; then run in priority order (US1 → US2 → US3/US4 in parallel if desired).
- Polish (Phase 7): Depends on completion of targeted user stories.

### User Story Dependencies

- US1 (P1): Baseline; no upstream story dependency.
- US2 (P2): Depends on US1 mapping to assess transport.
- US3 (P3): Depends on US1 mapping for payload/linkage.
- US4 (P3): Depends on US1 mapping; can run alongside US2/US3 after mapping ready.

### Parallel Opportunities

- Setup tasks T003 can run parallel to T001/T002.
- Foundational tasks T006 and T007 can run parallel to T004/T005.
- Within US1: T009 and T010 can run in parallel after T008.
- US2, US3, and US4 can proceed in parallel once mapping (US1) is complete.
- Data safety scan (T017) can run parallel to payload/signing checks (T015/T016).

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1 mapping.
4. Stop and validate coverage before proceeding.

### Incremental Delivery

1. Finish Setup + Foundational → mapping ready.
2. Add US2 (transport) → validate.
3. Add US3 (payload/signing/safety) → validate.
4. Add US4 (redundancy/consolidation) → validate.
5. Polish outputs and finalize summary.
