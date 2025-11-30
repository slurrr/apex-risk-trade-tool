# Implementation Plan: Phase 5 - User Story 3 Monitor

**Branch**: `006-phase5-us3-monitor` | **Date**: 2025-11-30 | **Spec**: specs/006-phase5-us3-monitor/spec.md  
**Input**: Feature specification from `/specs/006-phase5-us3-monitor/spec.md`

## Summary

Deliver monitoring for open orders and positions plus cancel support using ApeX Omni SDK via FastAPI. Add API documentation (public + private endpoints and WS subscription examples) and harden symbol discovery (configs_v3) with clear troubleshooting guidance. Keep in-memory caches normalized, testnet-first, and secret-free; UI polling remains read-only except for cancel actions.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, apexomni (official SDK), httpx, pydantic, uvicorn, python-dotenv  
**Storage**: In-memory caches only (orders, positions, configs); no persistent DB  
**Testing**: pytest with existing unit/API tests under `backend/tests`  
**Target Platform**: Backend on Linux/Windows server; UI static assets served locally; ApeX testnet default; ApeX WS optional for market/portfolio streams  
**Project Type**: Web backend with minimal static UI shell  
**Performance Goals**: Sub-second API responses when ApeX responds; safe degradation with structured errors on upstream slowness  
**Constraints**: No secrets in responses/UI; block actions if configs/credentials missing; adhere to constitution risk/observability rules  
**Scale/Scope**: Single-tenant tool; modest polling load from UI; scope limited to monitor + cancel + documentation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Risk-First Architecture**: Monitor endpoints avoid side effects beyond explicit cancel; caches refreshed safely; sizing logic untouched.  
- **Minimal Surface Area**: Only `/api/orders`, `/api/positions`, `/api/orders/{id}/cancel`; no new modules beyond existing backend/UI paths.  
- **Deterministic & Testable Logic**: Normalization helpers stay pure; monitor flows covered by pytest API/unit tests.  
- **Safe Exchange Interaction**: Use official ApeX SDK; default testnet; no secrets in payloads/responses.  
- **Clarity Over Cleverness**: Straightforward routing and data shaping; avoid over-abstraction.  
- **Observability & Logging**: Structured logs for fetch/cancel counts, errors, and cache updates.  
Gate status: PASS (no constitution violations identified).

## Project Structure

### Documentation (this feature)

```text
specs/006-phase5-us3-monitor/
  plan.md          # This file
  research.md      # Phase 0 output
  data-model.md    # Phase 1 output
  quickstart.md    # Phase 1 output
  contracts/       # Phase 1 output (API contracts)
  spec.md          # Feature spec
  api-reference.md # API documentation (public/private endpoints + WS)
```

### Source Code (repository root)

```text
backend/
  api/             # FastAPI routes (trade, orders, positions)
  core/            # config and logging
  exchange/        # ApeX Omni gateway wrapper
  risk/            # risk engine logic
  trading/         # order manager and schemas
  tests/           # pytest suites for risk, gateway, API

ui/
  index.html
  js/              # preview, execute, orders, positions scripts
  css/

specs/             # feature specs and plans
.specify/          # agent/memory templates and scripts
```

**Structure Decision**: Keep existing backend + minimal UI layout; monitoring changes remain within `backend/api/routes_orders.py`, `backend/api/routes_positions.py`, `backend/trading/order_manager.py`, `backend/exchange/exchange_gateway.py`, and `ui/js/orders.js` / `ui/js/positions.js`, with documentation in `specs/006-phase5-us3-monitor/` (contracts + API reference).

## Complexity Tracking

No constitution violations identified; no additional complexity to justify.
