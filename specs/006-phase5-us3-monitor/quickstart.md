# Quickstart - Monitor Orders & Positions (Phase 5)

## Prerequisites
- Python 3.11 and virtual env at `.venv` (run `python -m venv .venv` if missing).
- Dependencies installed: `.\.venv\Scripts\pip.exe install -r requirements.txt`.
- `.env` populated from `.env.example` (ApeX testnet creds, network, log level).

## Run the API
```powershell
.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Manual Checks
1) **Health**: `curl http://localhost:8000/health` -> `{"status":"ok"}`.  
2) **Orders**: `curl http://localhost:8000/api/orders` -> list of normalized orders (empty list if none).  
3) **Positions**: `curl http://localhost:8000/api/positions` -> list of normalized positions (empty list if none).  
4) **Cancel**: `curl -X POST http://localhost:8000/api/orders/{orderId}/cancel` -> `{"canceled":true,"order_id":"..."}` (replace `{orderId}` with an existing ID).  
5) **Logs**: watch console for structured logs showing counts/errors; no secrets should appear.

## Notes
- Service defaults to ApeX testnet; do not point to mainnet without updated env values.
- Monitor endpoints refresh configs/orders/positions on each call; failures return structured errors instead of partial data.
- UI polling should use `/api/orders` and `/api/positions`; no frontend access to secrets.
