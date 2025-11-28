# Repository Guidelines

## Project Structure & Module Organization
- `backend/` holds the FastAPI service. Subpackages: `api/` for route modules, `core/` for config/logging, `exchange/` for Apex Omni client helpers, `risk/` for risk engine logic, `trading/` for order mapping/management, and `tests/` for pytest suites. Entry point is `backend/main.py` (served via Uvicorn). Packages are discovered from `backend/` per `pyproject.toml`.
- `ui/` contains the static web shell (`index.html`, `css/`, `js/`) that can front the API.
- `spec/` stores design docs and contracts; keep these updated when interfaces change.
- `.env.example` shows required settings; copy to `.env` for local runs.

## Setup, Build, and Development Commands
- Create venv: `python -m venv .venv` then `.\.venv\Scripts\activate` (PowerShell) or `source .venv/bin/activate` (Unix).
- Install deps: `pip install -r requirements.txt` (uses FastAPI, httpx, apexomni, Pydantic).
- Run API locally: `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000` (hot reload for dev).
- Lint/style (if available): `python -m ruff .` or `python -m black backend` - follow these if already configured.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation; keep functions/variables `snake_case` and classes `PascalCase`.
- Prefer type hints and Pydantic models for request/response schemas; keep API contracts in `api/routes_*.py` aligned with `spec/` docs.
- Keep logging centralized via `backend/core/logging.py`; avoid ad-hoc print statements.
- Module naming: new routes in `routes_<domain>.py`, validators in `risk/validators.py`, exchange clients in `exchange/*.py`.

## Testing Guidelines
- Framework: pytest. Name files `test_*.py` and tests `test_*`.
- Run suite: `pytest backend/tests`. Add focused tests near the module under test and use fixtures for httpx/UVicorn clients when applicable.
- Aim to cover new branches/edge cases (risk checks, order mapping, API error paths) and include regression tests for any bugfix.

## Commit & Pull Request Guidelines
- Recent history uses concise, imperative subjects (`Add .editorconfig and update .gitignore`). Match that style: start with a verb, keep under ~72 chars, and scope is optional.
- Pull requests should describe the change, note breaking impacts, link related issues, and list how to run/verify (commands/tests). Include screenshots/GIFs for UI updates or API examples for new endpoints.
- Ensure `.env` is excluded from commits; use `.env.example` for new settings.

## Security & Configuration Tips
- Never commit secrets; load keys via `.env` and access through `python-dotenv` in `core/config.py` patterns.
- Validate external input at API boundaries and in `risk/validators.py`; log safely without leaking credentials or PII.
- Before deploying, pin configs in `spec/` and confirm httpx timeouts/retries in `exchange/` clients.
