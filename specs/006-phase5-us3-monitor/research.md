# Phase 0 Research - User Story 3 Monitor

## Monitoring transport: REST polling vs WebSocket
- **Decision**: Use REST polling with the ApeX SDK for `/api/orders` and `/api/positions`, refreshing caches on each request.
- **Rationale**: Keeps surface area minimal, avoids background WebSocket lifecycle/heartbeat handling, and aligns with existing sync model in `OrderManager`.
- **Alternatives considered**: Private WebSocket stream for push updates; deferred due to added complexity, reconnection handling, and lack of current UI need for sub-second updates.

## Cache refresh strategy
- **Decision**: Refresh orders/positions from the gateway on each monitor request and prune cache for missing IDs; reuse `refresh_state` after cancels.
- **Rationale**: Ensures responses stay aligned with exchange truth without background tasks; deterministic and testable.
- **Alternatives considered**: Background periodic refresh; adds scheduling complexity and race conditions with cancels.

## Symbol discovery reliability
- **Decision**: Use `HttpPublic.configs_v3()` (testnet endpoint) as the canonical symbol source; on empty responses, log a structured error, retry once, and surface a clear message advising to verify network ID/endpoint and trust_env/proxy settings.
- **Rationale**: configs_v3 is the documented source of symbol metadata; transient failures should not return empty data silently.
- **Alternatives considered**: Hard-coded symbol lists; rejected as brittle and non-compliant with exchange updates.

## WebSocket subscription scope
- **Decision**: Document but defer WS integration for monitoring; include examples for public market data (depth/ticker/trades) and private `ws_zk_accounts_v3` subscriptions in API docs.
- **Rationale**: Keeps implementation surface minimal while giving operators guidance to enable WS later if needed.
- **Alternatives considered**: Implement WS now; rejected due to added complexity not required for current monitoring story.

## ID normalization for cancel actions
- **Decision**: Normalize order identifiers to a single `id` field using ApeX `orderId` first, falling back to `clientOrderId` when missing.
- **Rationale**: Supports mixed server formats while keeping UI/API stable; matches existing normalization helpers.
- **Alternatives considered**: Require UI to pass raw exchange IDs; rejected to keep frontend secret-free and schema-stable.

## Error handling and observability
- **Decision**: Return structured HTTP errors for upstream failures (400/502 with message), and log monitor calls with counts and exceptions via centralized logging.
- **Rationale**: Aligns with constitution observability and clarity mandates while avoiding secret leakage.
- **Alternatives considered**: Silent fallbacks or unstructured errors; rejected for violating determinism and clarity.
