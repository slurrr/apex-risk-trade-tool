# Implementation Plan: Automatic ATR-Based Stop Loss Prefill

**Branch**: `[001-atr-stop-autofill]` | **Date**: 2025-12-11 | **Spec**: specs/001-atr-stop-autofill/spec.md  
**Input**: Feature specification from `specs/001-atr-stop-autofill/spec.md`

**Note**: This plan follows the `.specify/templates/commands/plan.md` workflow for this repo.

## Summary

The feature adds an automatic, ATR-based stop loss prefill for trades entered through the UI.  
When a symbol is selected and an entry price is present (either auto-populated from the latest price or manually edited), the backend will compute a default stop loss using a configurable ATR-based risk rule and return it so the UI can populate the Stop field almost instantly.  
ATR configuration (timeframe, lookback period, multiplier) is managed via runtime configuration so risk policies can be adjusted without code changes, and users can always override or supply a manual stop loss when automatic calculation is unavailable or not desired.

## Technical Context

**Language/Version**: Python 3.11 (per repo toolchain)  
**Primary Dependencies**: FastAPI, Pydantic, httpx, apexomni (Apex Omni SDK), python-dotenv  
**Storage**: No dedicated database changes for this feature; uses existing in-memory request/response processing and external market data only.  
**Testing**: pytest (unit tests for ATR calculation and API contract, optional integration tests for end-to-end UI + API flow).  
**Target Platform**: Backend on Linux/Windows server (FastAPI via Uvicorn), browser-based UI.  
**Project Type**: Web application with `backend/` FastAPI service and static `ui/` front-end.  
**Performance Goals**: Stop loss prefill visible to users within ~1 second of a valid Entry price being known, assuming timely ATR data availability.  
**Constraints**: Must not introduce blocking calls that materially slow existing quote/entry flows; ATR computation should be efficient over a bounded, configurable lookback window; handle intermittent market data latency gracefully.  
**Scale/Scope**: Single-user desktop usage up to active intraday trading; feature scope limited to computing and surfacing a per-trade default stop loss (no portfolio-wide analytics).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution file `.specify/memory/constitution.md` currently contains placeholder sections and does not define concrete, project-specific principles. For this feature, we align with the repository AGENTS guidelines instead:

- Prefer clear separation between UI concerns (`ui/`) and business logic in the backend (`backend/risk`, `backend/trading`).
- Use configuration-driven behavior for risk parameters (timeframe, period, multiplier) rather than hard-coding values.
- Provide testable units for ATR calculation and stop loss derivation.

**Gate Evaluation (Pre-Design)**:

- No conflicting technology or structural choices detected for this feature.  
- Plan keeps ATR/risk logic in backend code rather than embedding it directly in the UI.  
- Testing strategy includes unit tests for core logic.

**Result**: Gate PASSED; no complexity tracking entries required at this stage.

## Project Structure

### Documentation (this feature)

```text
specs/001-atr-stop-autofill/
├── spec.md          # Feature specification
├── plan.md          # This file (/speckit.plan command analogue)
├── research.md      # Phase 0 output (design decisions & rationale)
├── data-model.md    # Phase 1 output (entities & relationships)
├── quickstart.md    # Phase 1 output (how to implement & verify)
├── contracts/       # Phase 1 output (API contracts for ATR stop)
└── checklists/      # Requirements/checklist files (already present)
```

### Source Code (repository root)

```text
backend/
├── main.py              # FastAPI entrypoint
├── api/                 # Route modules (order entry, risk, etc.)
├── core/                # Config/logging, including env var loading
├── exchange/            # Apex Omni client helpers for market data
├── risk/                # Risk engine logic (good place for ATR calc)
└── trading/             # Order mapping/management

ui/
├── index.html           # Web shell
├── css/                 # Styles
└── js/                  # Front-end behavior (forms, field updates)
```

**Structure Decision**: Implement ATR and stop loss calculations in the backend `risk/` layer (possibly with helpers in `exchange/` for data access) and expose them via existing or new API routes in `backend/api/`. The UI will consume these APIs and update the Stop field accordingly; no new top-level packages are required.

## Complexity Tracking

No constitution violations identified; complexity tracking table not required for this feature.

