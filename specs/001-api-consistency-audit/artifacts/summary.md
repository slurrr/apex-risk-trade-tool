# Audit Summary

**Date**: 2025-12-02  
**Scope**: API consistency audit against `apex_api_cheatsheet.md`

## Coverage
- Mapping completed for all observed REST/WS invocations (backend only; UI has none).
- Base URLs checked: SDK uses ApeX constants; manual fallback now limited to cheat-sheet testnet/main hosts.
- Margin endpoints: `/v3/account` and `/v3/account-balance` used; `/v3/set-initial-margin-rate` documented as out of scope for now.

## Key Findings (see discrepancies.md)
- Order payload aligns to SDK signature (clientId/timeInForce); cheat sheet fields `clientOrderId`/`limitFee`/`expiration` are tracked but not sent—documented divergence.
- Order failure logging now redacts sensitive payload fields.
- WS topic mapping documented: `all_ticker_stream` ↔ `instrumentInfo`; `account_info_stream_v3` ↔ `ws_zk_accounts_v3` (confirm in runtime).
- REST price fallbacks remain using documented `get-worst-price` and `ticker_v3`; WS enabled by default mitigates staleness risk.
- `set-initial-margin-rate` left out of scope unless needed.

## Data Safety
- Order payload logging redacted; API keys/passphrases handled by SDK (headers not visible).
- Data-safety checklist updated; continue to avoid full payload dumps and secret exposure.

## Next Steps
- Validate `depth_v3` coverage vs official docs or replace with documented endpoint.
- Consider enabling WS by default for live prices to reduce REST polling staleness.
- Decide if `set-initial-margin-rate` should be added in a future iteration.
- Confirm WS topic mapping in integration logs; close remaining discrepancies accordingly.
