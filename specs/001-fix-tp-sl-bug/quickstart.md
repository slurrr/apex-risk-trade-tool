# Quickstart: Fix TP/SL position updates

## Prerequisites
- Python 3.11+  
- Virtual env created at `.venv` with dependencies: `.\.venv\Scripts\pip.exe install -r requirements.txt`  
- Environment: copy `.env.example` to `.env` and configure ApeX credentials and network.

## Run backend (FastAPI)
```powershell
.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000
```
- Health: `http://localhost:8000/health`
- Key endpoints for this feature:
  - `GET /api/positions` (returns positions with effective TP/SL)
  - `POST /api/positions/{position_id}/targets` (modify or clear TP/SL)
  - WebSocket: `ws://localhost:8000/ws/stream` (orders, positions, and TP/SL updates)

## Run UI
Serve `ui/` statically (any local server). Example:
```powershell
cd ui
python -m http.server 3000
```
Open `http://localhost:3000` and ensure it points to the backend base URL (configure in UI settings if applicable).

## Functional checks for TP/SL
- With an open position that has no TP/SL, use the Modify control in the Positions table to set both TP and SL; verify the row shows the exact values entered and remains correct after a manual refresh.  
- Modify only TP (or only SL) for a position that already has both set; confirm the changed target updates while the untouched one stays the same in both the UI and `/api/positions`.  
- Use the UI to clear TP, clear SL, and then clear both; confirm the corresponding values become `None` in `/api/positions` and render as “TP: None” / “SL: None” in the UI.  
- Trigger a reconnect or restart the backend while TP/SL protections are active; after the UI resumes streaming, verify that the TP/SL values still reflect the latest confirmed state rather than reverting to `None`.  
- Inspect WebSocket snapshots in `sessions\YYYY\MM\DD\ws_orders_*.json` to confirm that untriggered isPositionTpsl orders are present when TP/SL is shown and absent when protections are cleared.

## Testing
- Backend: `.\.venv\Scripts\pytest.exe backend/tests` (focus on tests covering TP/SL mapping, `/api/positions`, and targets update behaviour).  
- UI: manual checks of TP/SL display and Modify interactions on both desktop and mobile viewports, including refresh and brief disconnect scenarios.

