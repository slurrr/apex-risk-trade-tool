# Research: API Consistency Audit

**Branch**: `001-api-consistency-audit` | **Date**: 2025-12-02

## Findings

### Decision: Coverage-first audit approach
- **Rationale**: Full inventory and mapping is prerequisite for validating correctness, transport choices, and safety.
- **Alternatives considered**: Sample-based review (rejected: risk of missed violations); endpoint-only catalog without payload/header review (rejected: would miss shape/signing errors).

### Decision: Apply transport policy (WS for streaming, REST for transactions)
- **Rationale**: Cheat sheet designates WebSocket topics (e.g., `ws_zk_accounts_v3`, `orderBook`, `instrumentInfo`) as authoritative for live updates; REST `/v3` is transactional.
- **Alternatives considered**: Allow REST polling for live data (rejected: staleness and load); treat transport as optional (rejected: increases divergence risk).

### Decision: Validate payloads and signing against cheat sheet
- **Rationale**: Required fields, casing, symbol formats, and headers (`APEX-SIGNATURE`, `APEX-TIMESTAMP`, `APEX-API-KEY`, `APEX-PASSPHRASE`) are critical to correctness and safety.
- **Alternatives considered**: Header-only check (rejected: payload/enums could still drift); payload-only check (rejected: signing/auth leaks could persist).

### Decision: Consolidate redundant calls into `backend/exchange/apex_client.py` when behavior matches, allow documented exceptions
- **Rationale**: Reduces drift and duplicate logic while avoiding risky refactors where behaviors diverge; aligns with User Story 4 and FR-010.
- **Alternatives considered**: Mandate full consolidation (rejected: higher regression risk); leave all calls distributed (rejected: increases inconsistency risk).

### Decision: Enforce data safety review for secrets and identifiers
- **Rationale**: API keys, passphrases, signatures, wallet addresses, and clientOrderIds must not be logged or persisted; aligns with SC-004 and FR-008.
- **Alternatives considered**: Trust existing logging defaults (rejected: insufficient assurance); redact only keys (rejected: other identifiers still sensitive).
