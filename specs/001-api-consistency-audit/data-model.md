# Data Model: API Consistency Audit

**Branch**: `001-api-consistency-audit` | **Date**: 2025-12-02

## Entities

### API Invocation
- **Attributes**: path or topic, HTTP method or WS topic, base URL (testnet/mainnet), transport (REST/WS), payload fields, headers, symbol format, source file/location, feature purpose.
- **Relationships**: Maps to a Reference Contract entry; may link to a Consolidation Decision and to Discrepancies.

### Reference Contract
- **Attributes**: source document (`apex_api_cheatsheet.md`), version, endpoint/topic definitions, required/optional fields, enums, signing rules.
- **Relationships**: Serves as canonical target for all API Invocation mappings.

### Sensitive Data
- **Attributes**: data type (API key, passphrase, signature, wallet address, clientOrderId), presence in code/logs, handling expectation (redacted/avoided), evidence location.
- **Relationships**: Associated with API Invocations and Discrepancies when leakage risk is detected.

### Consolidation Decision
- **Attributes**: endpoint/topic identifier, duplication count, centralization recommendation (consolidate/retain), rationale, risk/benefit notes, owner/action.
- **Relationships**: Aggregates multiple API Invocations for the same contract; links to Discrepancies if divergence exists.

### Discrepancy
- **Attributes**: category (transport, payload shape, signing/auth, data safety, redundancy), severity, remediation recommendation, status.
- **Relationships**: Attached to API Invocations (and optionally Consolidation Decisions) that diverge from the Reference Contract.

## State/Status Notes
- Discrepancies progress from `found` → `reviewed` → `remediated` → `verified`.
- Consolidation Decisions progress from `identified` → `recommended` → `accepted/rejected` → `implemented` (if applicable).
