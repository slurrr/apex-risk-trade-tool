# Quickstart: Responsive UI & theming

## Prerequisites
- Python 3.11+  
- Virtual env created at `.venv` with dependencies: `.\.venv\Scripts\pip.exe install -r requirements.txt`
- Environment: copy `.env.example` to `.env` and fill API keys.

## Run backend (FastAPI)
```powershell
.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000
```
- Health: `http://localhost:8000/health`
- Key endpoints for this feature:
  - `GET /api/account/summary`
  - `GET /api/symbols`
  - `POST /api/trade` (preview/execute)
  - `GET /api/orders`, `POST /api/orders/{order_id}/cancel`
  - `GET /api/positions`, `POST /api/positions/{position_id}/close`, `POST /api/positions/{position_id}/targets`
  - WebSocket: `ws://localhost:8000/ws/stream` (orders, positions)

## Run UI
Serve `ui/` statically (any local server). Example:
```powershell
cd ui
python -m http.server 3000
```
Open `http://localhost:3000` and ensure it points to the backend base URL (configure in UI settings if applicable).

## Functional checks
- Verify header shows “TradeSizer” in burnt orange with account summary row (equity, uPNL color-coded, available margin).  
- Trade form uses a two-by-three grid (Symbol+Risk%, Entry+Stop, Take Profit+Side); symbol dropdown filters and enforces format (e.g., BTC-USDT).  
- Open Orders table shows Symbol and Entry columns (order ID hidden).  
- Open Positions table shows TP/SL stack, Actions column with Manage (slider 0/25/50/100, Market/Limit close) and Modify (TP/SL inputs, single submit).  
- Theme follows system light/dark; pressed state flashes red briefly from burnt orange.

## Testing
- Backend: `.\.venv\Scripts\pytest.exe backend/tests`
- UI: manual responsive checks (320px–1920px), theme switch latency (<1s), button feedback (~0.15s), symbol filter responsiveness.
