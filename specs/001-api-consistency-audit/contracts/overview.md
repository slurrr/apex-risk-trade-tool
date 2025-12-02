# Contracts: API Consistency Audit

**Branch**: `001-api-consistency-audit` | **Date**: 2025-12-02

This initiative introduces no new external API endpoints. Audit outputs are documentation artifacts used to validate existing ApeX Omni API usage.

## Audit Artifacts (contract for deliverables)

- **Invocation Mapping**: Table covering 100% of REST and WebSocket calls (path/topic, method, base URL, payload/headers, source file) with status (match/deviation/rationale).
- **Transport Evaluation**: For each live-data use case, recorded decision for WebSocket vs REST with justification.
- **Payload & Signing Validation**: Checklist per endpoint confirming required fields, casing, enums, symbol formats, and required headers.
- **Data Safety Log**: Findings on any logged or persisted secrets/identifiers with remediation actions.
- **Consolidation Recommendations**: List of duplicate/fragmented call sites with consolidation decision (consolidate/retain) and risk/benefit notes.
