# Implementation Plan: Fix TP/SL position updates

**Branch**: `001-fix-tp-sl-bug` | **Date**: 2025-12-04 | **Spec**: D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-fix-tp-sl-bug\spec.md  
**Input**: Feature specification from `D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-fix-tp-sl-bug\spec.md`

## Summary

- Restore and harden TP/SL visibility in the Positions UI so that each open position reliably shows its current take-profit and stop-loss levels, even across refreshes and temporary disconnects.  
- Ensure the Modify TP/SL flow updates one or both targets for a position, submits appropriate isPositionTpsl orders, and cancels any older untriggered TP or SL orders of the same type so that only the latest protections remain active.

## Technical Context

**Language/Version**: Python 3.11+ backend; static HTML/CSS/JS frontend  
**Primary Dependencies**: FastAPI, Uvicorn, Pydantic, httpx, apexomni, pytest; existing vanilla JS UI shell  
**Storage**: None (ApeX exchange-backed service; in-memory caches only)  
**Testing**: pytest for backend (positions, TP/SL mapping, targets update); manual and scripted UI checks for TP/SL display and modify flows  
**Target Platform**: FastAPI service on server; browser UI (desktop + mobile) consuming REST + WebSocket (`/ws/stream`)  
**Project Type**: Web (backend API + static frontend)  
**Performance Goals**: Positions and TP/SL display converge to correct state within 5 seconds of a change or reconnect; `/api/positions` and `/api/positions/{position_id}/targets` respond under 500ms p95 under typical single-account load  
**Constraints**: Avoid breaking existing trade and position flows; do not introduce additional persistent storage; minimize extra ApeX API calls while keeping TP/SL mapping correct; keep UI semantics backward-compatible for existing buttons where possible  
**Scale/Scope**: Single-account trading tool with one open position per symbol; tens of open positions and hundreds of open orders per account; modest concurrent sessions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Current constitution file is a placeholder without concrete ratified principles or non-negotiable gates; no explicit constraints are enforced beyond general good practice.  
- Gate status (pre-Phase 0): PASS — planned changes stay within existing backend/UI structure, add tests, and avoid new services or storage.  
- Gate status (post-Phase 1, design reflected in research, data-model, and contracts): PASS — no additional complexity or cross-cutting concerns exceed the informal constitution.

## Project Structure

### Documentation (this feature)

```text
D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-fix-tp-sl-bug\
|-- plan.md          # this file (/speckit.plan output)
|-- spec.md          # feature specification (TP/SL behaviour and UI semantics)
|-- research.md      # Phase 0 output (TP/SL mapping + modify decisions)
|-- data-model.md    # Phase 1 output (entities for positions, TP/SL orders, mapping)
|-- quickstart.md    # Phase 1 output (how to run and validate TP/SL flows)
|-- contracts\       # Phase 1 output (OpenAPI contracts for positions + TP/SL)
|-- checklists\      # requirements checklist
|-- tasks.md         # Phase 2 output (not generated here)
```

### Source Code (repository root)

```text
D:\Automation\Python scripts\apex-risk-trade-tool\
|-- backend\
|   |-- api\ (routes_positions.py, routes_stream.py, routes_trade.py, routes_orders.py)
|   |-- core\
|   |-- exchange\ (exchange_gateway.py - ApeX client + TP/SL helpers)
|   |-- risk\
|   |-- trading\ (order_manager.py - positions, TP/SL merge, modify_targets)
|   |-- tests\ (HTTP and unit tests for positions, orders, and TP/SL behaviour)
|-- ui\ (index.html, css\, js\, assets\ - Positions table, TP/SL column and Modify controls)
|-- specs\ (feature docs, including 001-fix-tp-sl-bug)
|-- spec\ (baseline design docs)
|-- requirements.txt, pyproject.toml, AGENTS.md
```

**Structure Decision**: Use the existing FastAPI backend and static UI shell; this feature updates TP/SL behaviour in `backend/exchange/exchange_gateway.py`, `backend/trading/order_manager.py`, `backend/api/routes_positions.py`, `backend/api/routes_stream.py`, and the Positions/TP/SL section of the UI in `ui/index.html`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|

