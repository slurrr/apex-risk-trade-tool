# Decision Record: Global Venue Toggle Semantics

**ID**: 0001-venue-toggle-semantics  
**Date**: 2026-02-06  
**Status**: Proposed  
**Owners**: <fill>  

## Context

The system currently runs against ApeX only. We are adding Hyperliquid (perps, mainnet) and want to toggle the active venue **in-app** (UI-driven), not per request. The backend is intended for a single operator, but multiple browser tabs may be open.

Venue switching affects:
- live WebSocket streams feeding `/ws/stream`
- cached configs, prices, orders, positions
- the `OrderManager` in-memory state and risk estimates

We must avoid “half-switched” requests placing orders on the wrong venue or mixing state.

## Decision

- The backend will maintain a single **global** `active_venue` (`apex` or `hyperliquid`) for all clients.
- The UI will provide a venue toggle and persist the selected venue in localStorage.
- The backend will expose:
  - `GET /api/venue` → `{ "active_venue": "apex" | "hyperliquid" }`
  - `POST /api/venue` with `{ "active_venue": ... }` → attempts switch and returns the active venue.
- Venue switching will be performed under a **process-wide lock** so only one switch can occur at a time.
- During a venue switch, trade/modify endpoints will return a structured “switch in progress” error (HTTP 503) rather than risk acting on a partially transitioned state.
- A switch is considered successful only after:
  - old venue streams are stopped (if running)
  - caches/state for the old venue are cleared (or clearly segregated)
  - new venue configs are loaded (or validated)
  - new venue streams are started (if enabled)
  - `OrderManager` state is refreshed from the new venue
- If any of the above fails, the backend will **rollback** to the prior active venue and return a structured error (no partial success).
- Default `active_venue` will be controlled by an env var (e.g., `ACTIVE_VENUE=apex`) but can be changed at runtime by the UI.

## Options Considered

### Option A — Per-request venue selection
- Pros: supports multi-user, no global contention.
- Cons: requires pervasive API/schema changes; higher risk of user error; larger surface area.

### Option B — Environment-only toggle (restart required)
- Pros: simplest to implement and reason about.
- Cons: does not meet requirement of “selection capability through the app UI”.

### Option C — Global backend venue toggle (chosen)
- Pros: meets UI requirement; minimal API change; easiest parity path with current architecture.
- Cons: not multi-user safe; multiple tabs share the same venue; requires careful switching lock/rollback.

## Consequences

- The app becomes “single-operator / single-venue at a time” by design.
- Documentation must explicitly warn that multiple connected UIs share a global venue.
- Implementation must add a switching lock and consistent error behavior during switch windows.
- All venue-dependent code paths must read from the venue manager (no hidden ApeX-only singletons).

## Validation Plan

- Unit test: switching lock prevents concurrent switches (second request blocks/fails deterministically).
- Unit test: if new venue config load fails, active venue remains unchanged.
- Manual:
  - open two browser tabs; switch venue in one; verify the other reflects the change after refresh.
  - attempt trade during switch; verify 503 structured response and no order placed.
- Logging: every switch emits structured logs with `from_venue`, `to_venue`, `result`, `duration_ms`.

