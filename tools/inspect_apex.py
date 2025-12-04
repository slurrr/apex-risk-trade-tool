"""
Quick inspector for ApeX account/positions/orders using repo .env settings.

Usage:
    python tools/inspect_apex.py

It will print:
  - get_account_v3 raw payload
  - extracted positions via ExchangeGateway (normalized as the app uses)
  - open_orders_v3 raw payload

Requires env vars (loaded via backend.core.config):
  APEX_API_KEY, APEX_API_SECRET, APEX_PASSPHRASE, APEX_HTTP_ENDPOINT (optional), APEX_NETWORK, etc.
"""

import asyncio
import json
import traceback

from backend.core.config import get_settings
from backend.exchange.apex_client import ApexClient
from backend.exchange.exchange_gateway import ExchangeGateway


def dump(title: str, payload) -> None:
    print(f"\n=== {title} ===")
    try:
        print(json.dumps(payload, indent=2))
    except Exception:
        print(payload)


async def main() -> None:
    settings = get_settings()
    client = ApexClient(settings).private_client
    try:
        acct = client.get_account_v3()
        dump("get_account_v3", acct)
    except Exception:
        print("Error calling get_account_v3:")
        traceback.print_exc()

    try:
        gw = ExchangeGateway(settings, client=client)
        positions = await gw.get_open_positions(force_rest=True, publish=False)
        dump("extracted_positions", positions)
    except Exception:
        print("Error fetching positions:")
        traceback.print_exc()

    try:
        orders = client.open_orders_v3()
        dump("open_orders_v3", orders)
    except Exception:
        print("Error calling open_orders_v3:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
