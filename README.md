# ApeX Risk & Trade Sizing Tool

Backend + static UI for previewing, executing, and monitoring ApeX trades with risk guardrails. Defaults to **testnet** only.

## Getting Started
- Create venv: `python -m venv .venv && .\\.venv\\Scripts\\activate`.
- Install deps: `.\.venv\Scripts\pip.exe install -r requirements.txt`.
- Copy `.env.example` to `.env` and fill testnet-only credentials; do not commit secrets.
- Run API: `.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000` (health at `/health`).
- Serve UI: open `ui/index.html` directly or from `ui/` run `python -m http.server 8080`. UI points to `http://localhost:8000` unless `window.API_BASE` is set.

## Docs & Checklists
- Tasks and scope: `specs/001-constitution-aligned-spec/tasks.md`.
- Design/spec: `specs/001-constitution-aligned-spec/spec.md`, plan in `specs/001-constitution-aligned-spec/plan.md`.
- Manual testnet checklist: `specs/001-constitution-aligned-spec/quickstart.md`.

## Notes
- Network is validated and defaults to testnet; unexpected networks log a warning on startup.
- UI/assets contain no secrets; keep API keys only in local `.env`.
- WebSocket stream (`/ws/stream`) powers live orders/positions; falls back to REST refresh if disconnected.
