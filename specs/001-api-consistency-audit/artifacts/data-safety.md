# Data Safety Checklist

- [ ] Are API keys, passphrases, and secrets redacted or omitted from all logs/traces? [Gap]
- [ ] Are signatures and timestamps avoided in logs except hashed/omitted? [Gap]
- [ ] Are wallet addresses and clientOrderIds excluded or masked in logs/telemetry? [Gap]
- [x] Are request/response payload dumps scrubbed of sensitive fields before logging? [Clarity] (Order payload logging now redacted in backend/exchange/exchange_gateway.py)
- [ ] Are caches or local stores free of plaintext secrets or identifiers? [Gap]
- [ ] Are WebSocket event payloads filtered before logging to avoid leaking sensitive data? [Gap]
