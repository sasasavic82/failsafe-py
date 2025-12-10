import base64
import time
import httpx

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class AuthBase(ABC):
    @abstractmethod
    def get_headers(self) -> Dict[str, str]:
        return {}

    def get_client_kwargs(self) -> Dict[str, Any]:
        """Extra args for httpx.Client(), e.g. for mTLS certs"""
        return {}


class BearerAuth(AuthBase):
    def __init__(self, token: str):
        self.token = token

    def get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


class BasicAuth(AuthBase):
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def get_headers(self) -> Dict[str, str]:
        cred = f"{self.username}:{self.password}".encode("utf-8")
        encoded = base64.b64encode(cred).decode()
        return {"Authorization": f"Basic {encoded}"}


class OAuth2ClientCredentials(AuthBase):
    def __init__(
        self, token_url: str, client_id: str, client_secret: str, scopes: Optional[list[str]] = None
    ):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or []
        self.token = None
        self.token_expiry = 0

    def _fetch_token(self):
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.scopes:
            data["scope"] = " ".join(self.scopes)

        resp = httpx.post(self.token_url, data=data)
        resp.raise_for_status()
        d = resp.json()
        self.token = d["access_token"]
        self.token_expiry = time.time() + d.get("expires_in", 3600) - 30

    def get_headers(self) -> Dict[str, str]:
        if not self.token or time.time() >= self.token_expiry:
            self._fetch_token()
        return {"Authorization": f"Bearer {self.token}"}


class MTLSAuth(AuthBase):
    def __init__(self, cert: str, key: str):
        self.cert = cert
        self.key = key

    def get_client_kwargs(self) -> Dict[str, Any]:
        return {"cert": (self.cert, self.key)}
