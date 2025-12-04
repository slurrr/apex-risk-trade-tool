"""
Utility script to run curl-like requests with ApeX credentials from environment variables.

Usage:
    python tools/curl_runner.py "curl https://omni.apex.exchange/api/v3/account"
    python tools/curl_runner.py "curl -X POST https://omni.apex.exchange/api/v3/order -d '{\"symbol\":\"BTC-USDT\"}'"

Notes:
    - You do NOT need to paste APEX headers; the script signs with env vars:
      APEX_API_KEY, APEX_API_SECRET, APEX_PASSPHRASE
    - Optional: APEX_HTTP_ENDPOINT to override the base (e.g., testnet)
    - Supports simple GET/POST/DELETE with JSON bodies (-d / --data). For other curl flags, extend as needed.
"""

import json
import os
import shlex
import sys
import time
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

import requests
from dotenv import load_dotenv
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

from backend.core.config import get_settings
from backend.exchange.apex_client import ApexClient


def parse_curl(curl_cmd: str) -> Tuple[str, str, Dict[str, str], Optional[str]]:
    """
    Parse a curl command string into method, url, headers, and data.
    Supports:
      curl -X METHOD URL -H 'Key: Value' -d '{"a":1}'
    Defaults to GET if no -X provided.
    """
    parts = shlex.split(curl_cmd)
    if not parts or parts[0].lower() != "curl":
        raise ValueError("Command must start with curl")

    method = "GET"
    url = None
    headers: Dict[str, str] = {}
    data = None

    i = 1
    while i < len(parts):
        token = parts[i]
        if token in ("-X", "--request") and i + 1 < len(parts):
            method = parts[i + 1].upper()
            i += 2
        elif token in ("-H", "--header") and i + 1 < len(parts):
            header = parts[i + 1]
            if ":" in header:
                k, v = header.split(":", 1)
                headers[k.strip()] = v.strip()
            i += 2
        elif token in ("-d", "--data", "--data-raw") and i + 1 < len(parts):
            data = parts[i + 1]
            i += 2
        elif not url:
            url = token
            i += 1
        else:
            i += 1

    if url is None:
        raise ValueError("No URL found in curl command")

    return method, url, headers, data


def sign_apex_request(method: str, url: str, data: Dict[str, str], signer) -> Dict[str, str]:
    """
    Generate ApeX headers using the SDK signer (HttpPrivateSign.sign).
    """
    api_key = os.getenv("APEX_API_KEY")
    api_passphrase = os.getenv("APEX_PASSPHRASE")
    if not all([api_key, api_passphrase]):
        raise RuntimeError("APEX_API_KEY and APEX_PASSPHRASE must be set in env")

    parsed = urlparse(url)
    request_path = parsed.path or "/"

    timestamp = str(int(time.time() * 1000))
    signature = signer.sign(request_path, method.upper(), timestamp, data)

    return {
        "APEX-API-KEY": api_key,
        "APEX-PASSPHRASE": api_passphrase,
        "APEX-SIGNATURE": signature,
        "APEX-TIMESTAMP": timestamp,
    }


def apply_apex_auth(headers: Dict[str, str], method: str, url: str, data: Dict[str, str], signer) -> Dict[str, str]:
    """Replace Apex auth headers using computed signature."""
    out = {k: v for k, v in headers.items() if not k.upper().startswith("APEX-")}
    apex_headers = sign_apex_request(method, url, data, signer)
    out.update(apex_headers)
    return out


def maybe_override_base(url: str) -> str:
    """If APEX_HTTP_ENDPOINT is set, override base of the given URL."""
    network = (os.getenv("APEX_NETWORK") or "testnet").lower()
    base = os.getenv("APEX_HTTP_ENDPOINT")
    if not base:
        if network in {"base", "base-sepolia", "testnet-base", "testnet"}:
            base = "https://testnet.omni.apex.exchange"
        else:
            base = "https://omni.apex.exchange"
    if url.startswith("http://") or url.startswith("https://"):
        # replace scheme/host with base
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            base_parsed = urlparse(base)
            new_url = urlunparse(
                (
                    base_parsed.scheme or parsed.scheme,
                    base_parsed.netloc or parsed.netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                )
            )
            return new_url
        except Exception:
            return url
    return base.rstrip("/") + "/" + url.lstrip("/")


def replace_placeholders(text: str) -> str:
    """
    Replace {placeholder} patterns with dummy values so docs curls can be pasted directly.
    Users should still edit if they need real values.
    """
    defaults = {
        "symbol": "BTC-USDT",
        "side": "BUY",
        "type": "LIMIT",
        "size": "0.01",
        "price": "65000",
        "limitFee": "100",
        "expiration": "1767204034000",
        "timeInForce": "GOOD_TIL_CANCEL",
        "triggerPrice": "0",
        "trailingPercent": "0",
        "clientOrderId": "doc-placeholder",
    }
    out = text
    for k, v in defaults.items():
        out = out.replace(f"{{{k}}}", v)
    # remove any {signature} placeholder
    out = out.replace("{signature}", "")
    return out


def main() -> None:
    load_dotenv()
    settings = get_settings()
    sdk_client = ApexClient(settings).private_client
    if len(sys.argv) < 2:
        print("Usage: python tools/curl_runner.py \"<curl command>\"")
        sys.exit(1)
    curl_cmd = replace_placeholders(sys.argv[1])
    method, url, headers, data = parse_curl(curl_cmd)
    # strip any user-supplied apex headers from pasted curl
    headers = {k: v for k, v in headers.items() if not k.upper().startswith("APEX-")}
    url = maybe_override_base(url)
    try:
        json_data = json.loads(data) if data else None
    except Exception:
        json_data = None

    # Build data dict for signing:
    # - JSON body if provided
    # - else form-encoded body if it looks like k=v&k2=v2
    # - else query params
    sign_data: Dict[str, str] = {}
    if json_data is not None:
        sign_data = {k: str(v) for k, v in json_data.items()}
    elif data and "=" in data:
        sign_data = {k: v for k, v in parse_qsl(data)}
    else:
        parsed = urlparse(url)
        sign_data = {k: v for k, v in parse_qsl(parsed.query)}
    # Drop signature and apex headers if pasted from docs
    sign_data.pop("signature", None)
    sign_data = {k: v for k, v in sign_data.items() if not k.upper().startswith("APEX-")}

    headers = apply_apex_auth(headers, method, url, sign_data, sdk_client)
    signature_value = headers.get("APEX-SIGNATURE")

    send_kwargs = {"method": method, "url": url, "headers": headers}
    if json_data is not None:
        send_kwargs["json"] = json_data
    else:
        if signature_value:
            sign_data["signature"] = signature_value
        send_kwargs["data"] = sign_data

    resp = requests.request(**send_kwargs)
    print(f"Status: {resp.status_code}")
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text)
    else:
        print(resp.text)


if __name__ == "__main__":
    main()
