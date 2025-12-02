from typing import Any, Optional

from backend.core.config import Settings


class ApexClient:
    """Thin wrapper around ApeX Omni SDK clients (HTTP + WebSocket)."""

    def __init__(self, settings: Settings, private_client: Optional[Any] = None, public_client: Optional[Any] = None) -> None:
        self.settings = settings
        self.private_client = private_client or self._init_private_client(settings)
        self.public_client = public_client or self._init_public_client(settings)

    def _init_private_client(self, settings: Settings) -> Any:
        from apexomni.constants import (
            APEX_OMNI_HTTP_MAIN,
            APEX_OMNI_HTTP_TEST,
            NETWORKID_MAIN,
            NETWORKID_OMNI_TEST_BNB,
            NETWORKID_OMNI_TEST_BASE,
        )
        from apexomni.http_private_sign import HttpPrivateSign

        network = getattr(settings, "apex_network", "testnet").lower()
        testnet_networks = {"base", "base-sepolia", "testnet-base", "testnet"}
        if network in {"base", "base-sepolia", "testnet-base"}:
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BASE
        elif network == "testnet":
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_TEST
            network_id = NETWORKID_OMNI_TEST_BNB
        else:
            endpoint = settings.apex_http_endpoint or APEX_OMNI_HTTP_MAIN
            network_id = NETWORKID_MAIN

        client = HttpPrivateSign(
            endpoint,
            network_id=network_id,
            zk_seeds=settings.apex_zk_seed,
            zk_l2Key=settings.apex_zk_l2key,
            api_key_credentials={
                "key": settings.apex_api_key,
                "secret": settings.apex_api_secret,
                "passphrase": settings.apex_passphrase,
            },
        )
        # Avoid inheriting system proxy settings that can block testnet calls.
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

    def _init_public_client(self, settings: Settings) -> Any:
        from apexomni.http_public import HttpPublic

        endpoint = getattr(settings, "apex_http_endpoint", None) or "https://omni.apex.exchange"
        client = HttpPublic(endpoint)
        session = client.client
        session.trust_env = False
        session.proxies = {"http": None, "https": None}
        return client

    def ws_base_endpoint(self) -> str:
        from apexomni.constants import APEX_OMNI_WS_MAIN, APEX_OMNI_WS_TEST

        network = getattr(self.settings, "apex_network", "testnet").lower()
        if network in {"base", "base-sepolia", "testnet-base", "testnet"}:
            return APEX_OMNI_WS_TEST
        return APEX_OMNI_WS_MAIN

    def create_public_ws(self) -> Any:
        from apexomni.websocket_api import WebSocket

        return WebSocket(endpoint=self.ws_base_endpoint())

    def create_private_ws(self) -> Any:
        from apexomni.websocket_api import WebSocket

        creds = {
            "key": self.settings.apex_api_key,
            "secret": self.settings.apex_api_secret,
            "passphrase": self.settings.apex_passphrase,
        }
        return WebSocket(endpoint=self.ws_base_endpoint(), api_key_credentials=creds)
