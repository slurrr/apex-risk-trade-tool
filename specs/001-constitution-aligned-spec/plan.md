# Implementation Plan: Constitution-Aligned Baseline Specification

**Branch**: `001-constitution-aligned-spec` | **Date**: 2025-11-28 | **Spec**: specs/001-constitution-aligned-spec/spec.md  
**Input**: Feature specification from `/specs/001-constitution-aligned-spec/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Deliver a risk-first MVP for ApeX Omni: compute position size from (symbol, entry, stop, risk%), enforce exchange constraints and risk caps, and optionally place orders via the official ApeX SDK. Backend is FastAPI with minimal modules (`exchange_gateway`, `risk_engine`, `order_manager`, app). UI is a single-page ticket plus positions/orders; no charts or nonessential features. Sizing is deterministic and re-run at execution; safety rails cannot be bypassed.

## Technical Context

**Language/Version**: Python ≥3.11  
**Primary Dependencies**: FastAPI, ApeX Omni Python SDK (`apexomni`), Pydantic, httpx, uvicorn, python-dotenv  
**Storage**: None (in-memory state for configs/orders/positions)  
**Testing**: pytest (unit focus on risk engine/order manager; API tests as needed)  
**Target Platform**: Backend service on server (testnet default) with static HTML/JS UI consuming REST  
**Project Type**: Web app (backend + static frontend)  
**Performance Goals**: No realtime; multi-second roundtrips acceptable; correctness and safety prioritized  
**Constraints**: No secrets in frontend; SDK-only exchange access; testnet default until explicitly switched; safety rails and risk caps mandatory; minimal UI surface  
**Scale/Scope**: Single trader/small team MVP; narrow API surface and minimal UI

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Risk-First Architecture (NON-NEGOTIABLE): sizing/safety drive scope. Status: PASS.  
- Minimal Surface Area: only constitution modules; tiny UI; no charts/indicators. Status: PASS.  
- Deterministic & Testable Logic: pure risk engine, re-run on execute, unit tests required. Status: PASS.  
- Safe Exchange Interaction: official ApeX SDK only; enforce symbol configs/leverage; idempotent IDs; secrets stay backend. Status: PASS.  
- Clarity Over Cleverness: explicit, readable flows; no over-engineering. Status: PASS.  
- Observability & Logging: structured logs for sizing, risk checks, payloads, warnings/errors. Status: PASS.  
- Security Requirements: env-based secrets, ZK/L2 treated as private keys, clock accuracy. Status: PASS.  
- Development Workflow: tests per module; reviews for risk logic/payload/config handling. Status: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-constitution-aligned-spec/
├─ plan.md              # This file (/speckit.plan command output)
├─ research.md          # Phase 0 output (/speckit.plan command)
├─ data-model.md        # Phase 1 output (/speckit.plan command)
├─ quickstart.md        # Phase 1 output (/speckit.plan command)
├─ contracts/           # Phase 1 output (/speckit.plan command)
└─ tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├─ api/                 # FastAPI routes
├─ core/                # config/logging
├─ exchange/            # ApeX SDK gateway
├─ risk/                # risk engine
├─ trading/             # order management, schemas
└─ tests/               # pytest suites

ui/
├─ index.html           # minimal ticket/positions UI
├─ css/
└─ js/

specs/001-constitution-aligned-spec/   # feature docs and contracts
```

**Structure Decision**: Web app with backend + static UI; only constitution-defined modules and minimal UI footprint.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| _None_    | —          | —                                    |

## Milestones & Phased Plan (incremental, single-developer, dependency-aware)

### Milestone 1: Project Initialization (runnable: config + env + dependencies)
- Set up `.venv`, install deps (FastAPI, uvicorn, apexomni, pydantic, python-dotenv, httpx, pytest).  
- Add `.env.example` entries for ApeX credentials, network ID, host/port, log level.  
- Initialize structured logging helper in `backend/core/logging.py` and config loader in `backend/core/config.py`.  
- Verify: `uvicorn backend.main:app --reload` serves a health stub; logging emits structured entries.

### Milestone 2: Exchange Gateway & Symbol Configs (runnable: data fetch)
- Implement `backend/exchange/exchange_gateway.py` wrapping ApeX SDK; cache `configs_v3()` at startup; expose `get_account_equity`, `get_symbol_info`, `get_open_positions`, `get_open_orders`, `place_order`, `cancel_order`, `cancel_all`.  
- Add structured error surfacing and testnet default.  
- Verify: script/endpoint to fetch configs and equity returns data (with secrets loaded from `.env`).

### Milestone 3: Risk Engine (pure, tested)
- Implement `backend/risk/risk_engine.py` as pure functions: size calculation with slippage/fee buffer, tick/step rounding, min/max size enforcement, leverage cap reduction, warnings, estimated_loss, side inference.  
- Add unit tests for long/short, below-min rejection, leverage-cap reduction, slippage effect, stop==entry rejection.  
- Verify: `pytest backend/tests` passes for risk cases.

### Milestone 4: Order Manager (orchestration + caps)
- Implement `backend/trading/order_manager.py`: fetch equity/config, invoke risk engine, enforce risk caps (per-trade, daily loss, open-risk sum), build idempotent clientOrderId, assemble order payload (limit, reduce-only, optional TP/SL), preview vs execute.  
- Maintain in-memory orders/positions updated from gateway responses.  
- Verify: unit tests/stubs confirm preview returns expected sizing; execute path respects caps and does not place when invalid.

### Milestone 5: API Layer (FastAPI surface)
- Implement routes in `backend/api/routes_trade.py` (POST `/api/trade` preview/execute, re-running sizing); `routes_orders.py` (GET `/api/orders`, POST `/api/orders/{id}/cancel`); `routes_positions.py` (GET `/api/positions`); optional `routes_config.py` (GET `/api/config`, `/api/symbols`).  
- Wire app in `backend/main.py`; add Pydantic schemas for requests/responses (no secrets).  
- Verify: fastapi test client covers trade preview/execute happy path and validation failures; endpoints return structured errors and never leak secrets.

### Milestone 6: UI Layer (minimal static)
- Build `ui/index.html` + minimal JS to call `/api/trade` (preview and execute), list `/api/orders` and `/api/positions`. Inputs: symbol, entry, stop, risk%, optional TP, optional side; buttons: Calculate, Place Order.  
- Ensure no secrets in frontend; show warnings/errors clearly.  
- Verify: manual browser test against local backend; preview and execute flows work end-to-end on testnet stub or live testnet (with env secrets).

### Milestone 7: Safety Rails & Observability Sweep
- Ensure all paths log structured entries for sizing inputs/outputs, risk checks, payloads, warnings/errors, rejected trades.  
- Confirm default to testnet unless explicitly configured; block execution if configs are missing/stale or validations fail.  
- Verify: manual testnet order succeeds; deliberate violations are rejected with clear messages.

### Milestone 8: Integration Validation
- Add integration tests (where feasible without secrets) using mocked gateway; document manual testnet checklist in `quickstart.md`.  
- Verify: `pytest` pass; checklist steps reproducible by a single developer with env secrets.
