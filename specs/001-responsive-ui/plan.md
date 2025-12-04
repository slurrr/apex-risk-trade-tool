# Implementation Plan: Responsive UI & theming

**Branch**: `001-responsive-ui` | **Date**: 2025-12-02 | **Spec**: D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-responsive-ui\spec.md  
**Input**: Feature specification from `D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-responsive-ui\spec.md`

## Summary

- Deliver a responsive TradeSizer UI with a burnt-orange header, account summary row (equity, uPNL color-coded red/green, available margin), and a two-by-three trade input grid that stays usable across desktop and mobile.  
- Add a type-ahead symbol dropdown enforcing formatted symbols (e.g., BTC-USDT), adjust Open Orders columns (Symbol, Entry; remove order ID), and enhance Open Positions with Manage (partial close slider plus market/limit actions) and Modify TP/SL inline controls.  
- Honor system light/dark mode with fast theme switching and pressed-state feedback (burnt orange resting, red on press) while keeping accessibility and touch targets intact.

## Technical Context

**Language/Version**: Python 3.11 backend; static HTML/CSS/JS frontend  
**Primary Dependencies**: FastAPI, Uvicorn, Pydantic, httpx, apexomni; pytest for backend tests; existing vanilla JS/CSS UI shell  
**Storage**: None (exchange-backed service; in-memory/cache only)  
**Testing**: pytest (backend); manual/UX checks for UI responsiveness and accessibility  
**Target Platform**: FastAPI service on server; browser UI (desktop + mobile) consuming REST + WebSocket  
**Project Type**: Web (backend + static frontend)  
**Performance Goals**: UI reflows without horizontal scroll from 320px–1920px; theme change reflects in <1s; button press feedback in ~0.15s; symbol filter responsive while typing  
**Constraints**: Maintain accessible contrast in both themes; avoid feature loss on mobile; slider precision for 0–100% with clear markers; no malformed symbols accepted  
**Scale/Scope**: Single-page trading shell with account/orders/positions; typical retail/active-trader volumes; moderate concurrent sessions

## Constitution Check

- Constitution file is a placeholder with no ratified principles or gates; no explicit constraints to enforce. Flagged for future ratification.  
- Gate status: PASS (no defined gates). Post-Phase 1 check: unchanged (still no active gates).

## Project Structure

### Documentation (this feature)

```
D:\Automation\Python scripts\apex-risk-trade-tool\specs\001-responsive-ui\
|-- plan.md          # this file (/speckit.plan output)
|-- research.md      # Phase 0 output
|-- data-model.md    # Phase 1 output
|-- quickstart.md    # Phase 1 output
|-- contracts\       # Phase 1 output
|-- checklists\      # requirements checklist
|-- tasks.md         # Phase 2 output (not generated here)
```

### Source Code (repository root)

```
D:\Automation\Python scripts\apex-risk-trade-tool\
|-- backend\
|   |-- api\ (routes_trade.py, routes_orders.py, routes_positions.py, routes_stream.py)
|   |-- core\
|   |-- exchange\
|   |-- risk\
|   |-- trading\
|   |-- tests\
|-- ui\ (index.html, css\, js\)
|-- specs\ (feature docs)
|-- spec\ (design docs)
|-- requirements.txt, pyproject.toml, AGENTS.md
```

**Structure Decision**: Use existing FastAPI backend with static UI shell; feature documentation and contracts live under `specs/001-responsive-ui`.

## Complexity Tracking

No constitution violations or additional complexity to justify beyond baseline.
